# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import unittest

from demand_aware_reinvestment import (
    ProductionCandidate,
    choose_reinvestment,
    evaluate_candidate,
    forecast_marginal_receipts,
    public_rival_standing_units,
)


class Mechanics:
    PRODUCTS = ["WHEAT", "CARROT", "EGG", "FERTILIZER"]
    ANIMALS = {"GOOSE": {"product": "EGG"}}
    SHOPS = {"PET_CAFE": ["CARROT"], "BAKERY": ["EGG", "WHEAT"]}
    TOWN_CENTER_PRODUCTS = ["WHEAT", "CARROT", "EGG"]
    PRICE_FLOOR = 1

    @staticmethod
    def market_price(item, inventory, params=None):
        base = {"WHEAT": 50, "CARROT": 100, "EGG": 80, "FERTILIZER": 60}[item]
        slope = {"WHEAT": 1, "CARROT": 5, "EGG": 2, "FERTILIZER": 1}[item]
        return max(1, base - slope * max(0, int(inventory)))


def observation(*, inventory=0, shops=None, rival_tiles=None):
    tiles = [[None for _ in range(2)] for _ in range(2)]
    if rival_tiles:
        for x, y, tile in rival_tiles:
            tiles[y][x] = deepcopy(tile)
    ours = [[None for _ in range(2)] for _ in range(2)]
    return {
        "step": 1,
        "player": 0,
        "farms": [{"tiles": ours}, {"tiles": tiles}],
        "market": {"inventory": {p: inventory for p in Mechanics.PRODUCTS}, "params": None},
        "town": {"unlocked_shops": list(shops or [])},
    }


CFG = {"episodeSteps": 20, "townShopSellInterval": 4, "townCenterSellInterval": 24}


class DemandAwareReinvestmentContracts(unittest.TestCase):
    def test_high_current_quote_collapses_under_own_expansion(self):
        obs = observation(inventory=0)
        static_quote_value = Mechanics.market_price("CARROT", 0) * 10
        self.assertGreater(static_quote_value, 300)
        candidate = ProductionCandidate(
            "expand-carrot", "CARROT", ((4, 10),), {"seed_service_travel": 800},
            rival_supply_units=0,
        )
        report = evaluate_candidate(Mechanics, obs, CFG, candidate)
        self.assertEqual(report["reason"], "nonpositive_marginal_value")
        self.assertLess(report["marginal_receipts"], static_quote_value)
        self.assertLessEqual(report["net_marginal_value"], 0)

    def test_repeated_known_demand_restores_marginal_value_between_sales(self):
        obs = observation(inventory=8, shops=["PET_CAFE", "PET_CAFE"])
        with_demand = forecast_marginal_receipts(
            Mechanics, obs, CFG, "CARROT", ((4, 2), (8, 2)), rival_supply_units=0)
        no_demand = forecast_marginal_receipts(
            Mechanics, observation(inventory=8), CFG, "CARROT", ((4, 2), (8, 2)),
            rival_supply_units=0)
        self.assertGreater(with_demand["known_town_absorption_units"], 0)
        self.assertGreater(with_demand["marginal_receipts"], no_demand["marginal_receipts"])
        cost = (with_demand["marginal_receipts"] + no_demand["marginal_receipts"]) / 2
        candidate = ProductionCandidate(
            "repeat-carrot", "CARROT", ((4, 2), (8, 2)), {"all_incremental": cost},
            rival_supply_units=0,
        )
        self.assertTrue(evaluate_candidate(Mechanics, obs, CFG, candidate)["admissible"])

    def test_visible_crop_and_animal_yield_are_public_supply(self):
        obs = observation(rival_tiles=[
            (0, 0, {"kind": "PLANT", "crop": "CARROT", "yield_units": 3}),
            (1, 0, {"kind": "COOP", "animal": "GOOSE", "yield_units": 2}),
        ])
        self.assertEqual(public_rival_standing_units(Mechanics, obs, "CARROT"), 3)
        self.assertEqual(public_rival_standing_units(Mechanics, obs, "EGG"), 2)
        stressed = forecast_marginal_receipts(Mechanics, obs, CFG, "CARROT", ((4, 2),))
        clean = forecast_marginal_receipts(
            Mechanics, observation(), CFG, "CARROT", ((4, 2),), rival_supply_units=0)
        self.assertLess(stressed["marginal_receipts"], clean["marginal_receipts"])
        self.assertEqual(stressed["rival_supply_source"], "public_standing_yield")

    def test_existing_seller_forecast_can_replace_local_public_fallback(self):
        obs = observation(rival_tiles=[
            (0, 0, {"kind": "PLANT", "crop": "CARROT", "yield_units": 3}),
        ])
        local = forecast_marginal_receipts(Mechanics, obs, CFG, "CARROT", ((4, 2),))
        seller = forecast_marginal_receipts(
            Mechanics, obs, CFG, "CARROT", ((4, 2),), rival_supply_units=7)
        self.assertEqual(seller["rival_supply_units"], 7)
        self.assertEqual(seller["rival_supply_source"], "caller_supplied_public_seller_forecast")
        self.assertLess(seller["marginal_receipts"], local["marginal_receipts"])

    def test_late_investment_cannot_claim_terminal_payback(self):
        report = evaluate_candidate(
            Mechanics, observation(), CFG,
            ProductionCandidate("late", "CARROT", ((19, 2),), {"seed": 1}, ready_step=19),
        )
        self.assertFalse(report["executable"])
        self.assertEqual(report["reason"], "output_beyond_terminal_horizon")
        self.assertIsNone(report["payback_step"])

    def test_unfunded_candidate_is_rejected_before_forecast(self):
        report = evaluate_candidate(
            Mechanics, observation(), CFG,
            ProductionCandidate("unfunded", "CARROT", ((4, 1),), {"seed": 20}, funded=False),
        )
        self.assertEqual(report["reason"], "funded_payback_rejected")
        self.assertFalse(report["executable"])

    def test_inherited_highest_value_is_explicit_noop(self):
        obs = observation(inventory=5)
        candidates = [
            ProductionCandidate("inherited", "CARROT", ((4, 2),), {"all": 10}, rival_supply_units=0),
            ProductionCandidate("worse", "CARROT", ((4, 4),), {"all": 300}, rival_supply_units=0),
        ]
        choice = choose_reinvestment(Mechanics, obs, CFG, candidates, inherited_key="inherited")
        self.assertFalse(choice["changed"])
        self.assertEqual(choice["chosen"], "inherited")
        self.assertEqual(choice["reason"], "inherited_mix_has_highest_executable_marginal_value")

    def test_strictly_better_funded_candidate_can_win(self):
        obs = observation(inventory=5, shops=["PET_CAFE"])
        candidates = [
            ProductionCandidate("inherited", "CARROT", ((4, 1),), {"all": 60}, rival_supply_units=0),
            ProductionCandidate("candidate", "CARROT", ((4, 1), (8, 1)), {"all": 70}, rival_supply_units=0),
        ]
        choice = choose_reinvestment(Mechanics, obs, CFG, candidates, inherited_key="inherited")
        self.assertTrue(choice["changed"])
        self.assertEqual(choice["chosen"], "candidate")
        self.assertEqual(choice["reason"], "strictly_higher_executable_marginal_value")

    def test_same_step_output_rows_do_not_double_count_payback(self):
        obs = observation(inventory=0)
        report = evaluate_candidate(
            Mechanics, obs, CFG,
            ProductionCandidate("split", "CARROT", ((4, 1), (4, 1)), {"all": 150},
                                rival_supply_units=0),
        )
        self.assertEqual(report["marginal_receipts"], 195)
        self.assertEqual(report["payback_step"], 4)

    def test_same_step_sale_precedes_town_absorption(self):
        obs = observation(inventory=10, shops=["PET_CAFE"])
        report = forecast_marginal_receipts(
            Mechanics, obs, CFG, "CARROT", ((4, 1),), rival_supply_units=0)
        row = next(r for r in report["inventory_trace"] if r["step"] == 4)
        expected_price = Mechanics.market_price("CARROT", row["inventory_before_market"])
        self.assertEqual(row["candidate_receipts"], expected_price)
        self.assertEqual(row["known_town_absorption"], 2)


if __name__ == "__main__":
    unittest.main()
