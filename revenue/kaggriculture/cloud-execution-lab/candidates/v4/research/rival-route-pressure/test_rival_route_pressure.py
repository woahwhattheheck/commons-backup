from __future__ import annotations

from copy import deepcopy
import unittest

import rival_route_pressure as R


def action(*market):
    return {"farmer": ["PASS"], "hands": [], "market": list(market)}


def route(rows, length=12):
    result = [action() for _ in range(length)]
    for step, act in rows.items():
        result[step] = act
    return result


def observation(*, player=0, rival_tiles=None, shops=None, private=None):
    rival_tiles = rival_tiles if rival_tiles is not None else [[None]]
    own = {"tiles": [[None]], "money": 3000}
    rival = {"tiles": rival_tiles, "money": 3000}
    farms = [own, rival] if player == 0 else [rival, own]
    return {
        "player": player,
        "farms": farms,
        "private": private if private is not None else {"shed": {"WOOL": 999}},
        "town": {"unlocked_shops": list(shops or [])},
        "market": {"inventory": {}, "prices": {}},
    }


CFG = {
    "maxMarketOrdersPerTurn": 2,
    "townShopSellInterval": 4,
    "townCenterSellInterval": 24,
}


class RivalRoutePressureTests(unittest.TestCase):
    def test_route_signature_uses_only_executable_prefix(self):
        r = route({
            1: action(["SELL", "MILK", 3], ["HIRE"], ["SELL", "WOOL", 99]),
            2: action(["SELL", "WOOL", 4]),
        })
        self.assertEqual(R.route_sell_signature(r, 1, 2, max_orders=2), {"MILK": 3, "WOOL": 4})

    def test_branch_delta_is_target_minus_incumbent(self):
        a = route({1: action(["SELL", "WOOL", 3])})
        b = route({1: action(["SELL", "WOOL", 7], ["SELL", "MILK", 2])})
        self.assertEqual(R.branch_sell_delta(a, b, 1, 1, max_orders=2), {"MILK": 2, "WOOL": 4})

    def test_route_inputs_are_not_mutated(self):
        a = route({1: action(["SELL", "WOOL", 3])})
        b = route({1: action(["SELL", "WOOL", 7])})
        before = deepcopy((a, b))
        R.branch_sell_delta(a, b, 0, 4)
        self.assertEqual((a, b), before)

    def test_visible_rival_signal_maps_crop_animal_and_fertilizer_flag(self):
        tiles = [[
            {"kind": "PLANT", "crop": "CARROT", "yield_units": 4},
            {"kind": "PASTURE", "animal": "SHEEP", "yield_units": 3, "fertilizer_available": True},
            {"kind": "COOP", "animal": "GOOSE", "yield_units": 1},
        ]]
        got = R.visible_rival_signal(observation(rival_tiles=tiles))
        self.assertEqual(got["standing_yield"], {"CARROT": 4, "EGG": 1, "WOOL": 3})
        self.assertEqual(got["productive_sources"], {"CARROT": 1, "EGG": 1, "WOOL": 1})
        self.assertEqual(got["collectable_fertilizer_tiles"], 1)

    def test_private_rival_or_own_inventory_is_not_an_input(self):
        tiles = [[{"kind": "PASTURE", "animal": "COW", "yield_units": 2}]]
        a = observation(rival_tiles=tiles, private={"shed": {"MILK": 0}})
        b = observation(rival_tiles=tiles, private={"shed": {"MILK": 999999}})
        self.assertEqual(R.visible_rival_signal(a), R.visible_rival_signal(b))

    def test_known_town_absorption_counts_current_shops_only(self):
        obs = observation(shops=["YARN_STORE", "BAKERY"])
        # steps 0,4,8 -> YARN_STORE pulls 2 WOOL each = 6, plus town center at 0.
        self.assertEqual(R.known_town_absorption("WOOL", 0, 8, obs, CFG), 7)
        # BAKERY pulls 1 EGG on 0,4,8 and town center pulls 1 at step0.
        self.assertEqual(R.known_town_absorption("EGG", 0, 8, obs, CFG), 4)
        # FERTILIZER is absent from town center and all shops.
        self.assertEqual(R.known_town_absorption("FERTILIZER", 0, 24, obs, CFG), 0)

    def test_duplicate_shop_instances_count_independently(self):
        obs = observation(shops=["YARN_STORE", "YARN_STORE"])
        self.assertEqual(R.known_town_absorption("WOOL", 4, 4, obs, CFG), 4)

    def test_unknown_future_shop_is_not_inferred(self):
        obs = observation(shops=[])
        self.assertEqual(R.known_town_absorption("WOOL", 0, 71, obs, CFG), 3)  # center at 0,24,48

    def test_pressure_report_rival_signal_can_exacerbate_incremental_route_load(self):
        routes = {
            "MAIN": route({0: action(["SELL", "WOOL", 1])}),
            "YARN": route({0: action(["SELL", "WOOL", 5])}),
        }
        obs = observation(
            rival_tiles=[[{"kind": "PASTURE", "animal": "SHEEP", "yield_units": 3}]],
            shops=[],
        )
        report = R.route_pressure_report(routes, "MAIN", "YARN", obs, CFG, start=0, horizon=1)
        row = report["incremental_sell_rows"][0]
        # Incremental own=4, rival visible=3, center drain=1 => public pressure=6.
        self.assertEqual(row["public_pressure_units"], 6)
        self.assertTrue(row["rival_exacerbated"])
        self.assertTrue(report["has_public_pressure_witness"])
        self.assertFalse(report["decision_authority"])

    def test_current_shop_demand_can_absorb_pressure(self):
        routes = {
            "A": route({4: action()}),
            "B": route({4: action(["SELL", "WOOL", 2])}),
        }
        obs = observation(
            rival_tiles=[[{"kind": "PASTURE", "animal": "SHEEP", "yield_units": 1}]],
            shops=["YARN_STORE", "YARN_STORE"],
        )
        report = R.route_pressure_report(routes, "A", "B", obs, CFG, start=4, horizon=1)
        row = report["incremental_sell_rows"][0]
        self.assertEqual(row["known_current_shop_absorption"], 4)
        self.assertEqual(row["public_pressure_units"], 0)
        self.assertFalse(report["has_public_pressure_witness"])

    def test_target_with_only_reduced_sales_has_no_pressure_row(self):
        routes = {
            "A": route({0: action(["SELL", "MILK", 5])}),
            "B": route({0: action(["SELL", "MILK", 2])}),
        }
        report = R.route_pressure_report(routes, "A", "B", observation(), CFG, start=0, horizon=1)
        self.assertEqual(report["incremental_sell_rows"], [])
        self.assertFalse(report["has_public_pressure_witness"])

    def test_catalog_covers_every_incumbent_for_each_target(self):
        routes = {"MAIN": route({}), "YARN": route({}), "MILK": route({})}
        decisions = [(2, "shop_YARN_STORE", 1, "YARN"), (5, "inv_MILK", 7, "MILK")]
        rows = R.branch_catalog(routes, decisions, horizon=2, max_orders=2)
        self.assertEqual(len(rows), 4)  # two non-target incumbents per decision
        self.assertEqual({row["target"] for row in rows}, {"YARN", "MILK"})

    def test_malformed_visible_yield_fails_closed(self):
        obs = observation(rival_tiles=[[{"kind": "PLANT", "crop": "CARROT", "yield_units": -1}]])
        with self.assertRaises(R.UnsupportedEvidence):
            R.visible_rival_signal(obs)

    def test_unknown_unlocked_shop_fails_closed(self):
        with self.assertRaises(R.UnsupportedEvidence):
            R.known_town_absorption("MILK", 0, 1, observation(shops=["FUTURE_UNKNOWN"]), CFG)

    def test_minimum_one_market_limit_matches_engine(self):
        routes = {
            "A": route({0: action()}),
            "B": route({0: action(["SELL", "WOOL", 3], ["SELL", "MILK", 99])}),
        }
        for raw in (0, -1, -99):
            with self.subTest(maxMarketOrdersPerTurn=raw):
                cfg = dict(CFG, maxMarketOrdersPerTurn=raw)
                report = R.route_pressure_report(
                    routes, "A", "B", observation(), cfg, start=0, horizon=1)
                self.assertEqual(report["max_market_orders_per_turn"], 1)
                self.assertEqual(report["sell_delta"], {"WOOL": 3})
                self.assertNotIn("MILK", report["sell_delta"])

    def test_non_int_market_limit_fails_closed(self):
        routes = {"A": route({}), "B": route({})}
        for raw in (True, 1.0, "1", None):
            with self.subTest(maxMarketOrdersPerTurn=raw):
                cfg = dict(CFG, maxMarketOrdersPerTurn=raw)
                with self.assertRaises(R.UnsupportedEvidence):
                    R.route_pressure_report(
                        routes, "A", "B", observation(), cfg, start=0, horizon=1)


if __name__ == "__main__":
    unittest.main()
