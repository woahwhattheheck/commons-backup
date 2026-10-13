# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import unittest

from fert_floor_current import (
    FertFloorArbitrageCurrentABI,
    ITEM,
    MAX_BUY_PRICE,
    FERT_PRICE2_PREBUY_INVENTORY,
    FERT_PRICE1_PREBUY_INVENTORY,
)


def obs(*, price=2, inventory=10489, money=20, fert=0, shed=0, covered=-1, step=240):
    tile = {
        "kind": "PLANT",
        "crop": "MELON",
        "fertilized_until_day": covered,
        "dead": False,
    }
    tiles = [[None for _ in range(4)] for _ in range(4)]
    tiles[1][1] = tile
    return {
        "player": 0,
        "step": step,
        "farms": [
            {"farmer": [1, 1], "hands": [[2, 2]], "tiles": tiles, "money": money},
            {"farmer": [0, 0], "hands": [], "tiles": [[None]], "money": 0},
        ],
        "private": {
            "inventories": [{ITEM: fert}, {}],
            "shed": {ITEM: shed},
        },
        "market": {
            "inventory": {ITEM: inventory},
            "prices": {ITEM: price},
        },
    }


def action(*, farmer=None, hand=None, market=None):
    return {
        "farmer": ["PASS"] if farmer is None else farmer,
        "hands": [["PASS"] if hand is None else hand],
        "market": [] if market is None else market,
    }


class FertFloorCurrentTests(unittest.TestCase):
    def test_price_two_source_boundary_adds_one_buy(self):
        selected = action()
        out, report = FertFloorArbitrageCurrentABI(apply=False).transform(obs(), selected)
        self.assertEqual(out["market"], [["BUY_PRODUCT", ITEM, 1]])
        self.assertTrue(report["buy_added"])
        self.assertEqual(report["source_postbuy_price"], 2)
        self.assertEqual(selected["market"], [])

    def test_true_floor_price_one_adds_one_buy(self):
        selected = action()
        out, report = FertFloorArbitrageCurrentABI(apply=False).transform(
            obs(price=1, inventory=FERT_PRICE1_PREBUY_INVENTORY, money=1), selected
        )
        self.assertEqual(out["market"], [["BUY_PRODUCT", ITEM, 1]])
        self.assertEqual(report["source_postbuy_price"], 1)

    def test_price_two_one_inventory_too_early_is_rejected(self):
        selected = action()
        out, report = FertFloorArbitrageCurrentABI(apply=False).transform(
            obs(price=2, inventory=FERT_PRICE2_PREBUY_INVENTORY - 1), selected
        )
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "fertilizer_postbuy_quote_above_ceiling")

    def test_public_price_drift_from_authenticated_inventory_rejected(self):
        selected = action()
        out, report = FertFloorArbitrageCurrentABI(apply=False).transform(
            obs(price=1, inventory=FERT_PRICE2_PREBUY_INVENTORY), selected
        )
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "fertilizer_market_authority_drift")

    def test_price_three_never_buys(self):
        selected = action()
        out, report = FertFloorArbitrageCurrentABI(apply=False).transform(
            obs(price=3, inventory=FERT_PRICE2_PREBUY_INVENTORY), selected
        )
        self.assertIs(out, selected)
        self.assertFalse(report["changed"])

    def test_apply_only_literal_pass_and_never_also_buys_owned_fert(self):
        selected = action()
        out, report = FertFloorArbitrageCurrentABI().transform(obs(fert=1), selected)
        self.assertEqual(out["farmer"], ["FERTILIZE"])
        self.assertEqual(out["market"], [])
        self.assertEqual(report["fertilize_actor_indices"], (0,))
        self.assertFalse(report["buy_added"])

    def test_non_pass_is_never_overwritten(self):
        selected = action(farmer=["WATER"])
        out, report = FertFloorArbitrageCurrentABI(buy=False).transform(obs(fert=1), selected)
        self.assertIs(out, selected)
        self.assertFalse(report["changed"])

    def test_already_covered_plant_is_not_fertilized_or_bought(self):
        selected = action()
        day = 240 // 24
        out, report = FertFloorArbitrageCurrentABI().transform(
            obs(fert=1, covered=day + 2), selected
        )
        self.assertIs(out, selected)
        self.assertFalse(report["changed"])

    def test_existing_owned_fertilizer_suppresses_buy(self):
        for kwargs in ({"fert": 1}, {"shed": 1}):
            with self.subTest(**kwargs):
                selected = action()
                out, report = FertFloorArbitrageCurrentABI(apply=False).transform(
                    obs(**kwargs), selected
                )
                self.assertIs(out, selected)
                self.assertEqual(report["reason"], "owned_fertilizer_already_present")

    def test_parent_fertilizer_market_intent_suppresses_buy(self):
        for row in (["BUY_PRODUCT", ITEM, 1], ["SELL", ITEM, 1]):
            with self.subTest(row=row):
                selected = action(market=[row])
                out, report = FertFloorArbitrageCurrentABI(apply=False).transform(
                    obs(), selected
                )
                self.assertIs(out, selected)
                self.assertEqual(report["reason"], "parent_fertilizer_market_intent")

    def test_full_market_suppresses_buy(self):
        selected = action(market=[["SELL", "CARROT", 1] for _ in range(10)])
        out, report = FertFloorArbitrageCurrentABI(apply=False).transform(obs(), selected)
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "market_capacity_full")

    def test_cash_is_bound_to_authenticated_postbuy_quote(self):
        selected = action()
        out, report = FertFloorArbitrageCurrentABI(apply=False).transform(
            obs(money=1, price=2, inventory=FERT_PRICE2_PREBUY_INVENTORY), selected
        )
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "insufficient_cash_for_source_quote")
        out, report = FertFloorArbitrageCurrentABI(apply=False).transform(
            obs(money=1, price=1, inventory=FERT_PRICE1_PREBUY_INVENTORY), selected
        )
        self.assertEqual(out["market"], [["BUY_PRODUCT", ITEM, 1]])

    def test_no_live_crop_suppresses_buy(self):
        observation = obs()
        observation["farms"][0]["tiles"][1][1] = None
        selected = action()
        out, report = FertFloorArbitrageCurrentABI(apply=False).transform(
            observation, selected
        )
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "no_live_fertilizer_opportunity")

    def test_worker_cardinality_drift_fails_closed(self):
        observation = obs()
        observation["private"]["inventories"] = [{}]
        selected = action()
        out, report = FertFloorArbitrageCurrentABI().transform(observation, selected)
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "malformed_farm_state")

    def test_malformed_inventory_quantity_fails_closed(self):
        observation = obs()
        observation["private"]["inventories"][0][ITEM] = True
        selected = action()
        out, report = FertFloorArbitrageCurrentABI().transform(observation, selected)
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "malformed_fertilizer_inventory")

    def test_malformed_market_inventory_fails_closed(self):
        observation = obs()
        observation["market"]["inventory"][ITEM] = True
        selected = action()
        out, report = FertFloorArbitrageCurrentABI().transform(observation, selected)
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "malformed_fertilizer_market_inventory")

    def test_huge_numbers_do_not_overflow_or_gain_authority(self):
        selected = action()
        out, report = FertFloorArbitrageCurrentABI(apply=False).transform(
            obs(price=10**1000, money=10**1000), selected
        )
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "fertilizer_market_authority_drift")

    def test_inputs_are_immutable(self):
        observation = obs()
        selected = action()
        before_obs = deepcopy(observation)
        before_selected = deepcopy(selected)
        FertFloorArbitrageCurrentABI().transform(observation, selected)
        self.assertEqual(observation, before_obs)
        self.assertEqual(selected, before_selected)

    def test_flags_are_exact_bool(self):
        for kwargs in ({"buy": 1}, {"apply": "yes"}):
            with self.subTest(**kwargs):
                with self.assertRaises(TypeError):
                    FertFloorArbitrageCurrentABI(**kwargs)

    def test_configuration_drift_fails_closed(self):
        selected = action()
        for cfg in (
            {"maxMarketOrdersPerTurn": 11},
            {"marketParams": {"FERTILIZER": {"base": 50}}},
        ):
            with self.subTest(cfg=cfg):
                out, report = FertFloorArbitrageCurrentABI().transform(obs(), selected, cfg)
                self.assertIs(out, selected)
                self.assertEqual(report["reason"], "malformed_envelope")

    def test_price_ceiling_and_inventory_boundaries_are_pinned(self):
        self.assertEqual(MAX_BUY_PRICE, 2)
        self.assertEqual(FERT_PRICE2_PREBUY_INVENTORY, 10489)
        self.assertEqual(FERT_PRICE1_PREBUY_INVENTORY, 10494)


if __name__ == "__main__":
    unittest.main(verbosity=2)
