# SPDX-License-Identifier: Apache-2.0
"""Current-helper oracle for the operating-stock executable-prefix repair.

This is intentionally source-pinned.  It proves that current production helper bytes
observe engine-dead market suffix rows today, then proves the prefix guard makes those
rows observationally irrelevant while preserving them exactly in the returned action.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import unittest

import operating_stock_prefix as prefix_guard

EXPECTED_OPERATING_STOCK = "781aa90da0d85d0ba23c665e29d6087d182c085e"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def load_current_helper():
    root = Path(__file__).resolve().parents[5]
    source = root / "operating_stock.py"
    data = source.read_bytes()
    actual = git_blob(data)
    if actual != EXPECTED_OPERATING_STOCK:
        raise RuntimeError(f"OPERATING_STOCK_SOURCE_MISMATCH expected={EXPECTED_OPERATING_STOCK} got={actual}")
    spec = importlib.util.spec_from_file_location("_opstock_current_prefix_oracle", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load current operating_stock.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Mechanics:
    ANIMALS = {}
    CROPS = {
        "BERRY": {
            "ongoing": True,
            "first_yield_day": 2,
            "interval": 1,
            "max_yield": 6,
            "seed": 1,
        }
    }
    PRODUCTS = {"FERTILIZER", "BERRY"}
    LAND_PRICES = []

    @staticmethod
    def market_price(item, _inventory, _params):
        return 1 if item == "FERTILIZER" else 100

    @staticmethod
    def _hire_cost(_hires, _mult):
        return 1

    @staticmethod
    def _spawn_hand(_farm, _board):
        return [4, 4]

    @staticmethod
    def _default_spawn(_board):
        return [4, 4]


def blank_action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def fixture():
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[4][4] = {
        "kind": "PLANT",
        "crop": "BERRY",
        "planted_day": 1,
        "yield_units": 0,
        "fertilized_until_day": -1,
        "max_lifespan_step": -1,
        "watered_today": False,
        "consecutive_unwatered": 0,
    }
    post_farm = {
        "farmer": [4, 4],
        "hands": [],
        "tiles": tiles,
        "money": 100,
        "hires_today": 0,
        "unlocked_quadrants": ["NW"],
    }
    post_private = {"shed": {"FERTILIZER": 2}, "inventories": [{}]}
    observation = {
        "step": 24,
        "market": {"inventory": {"FERTILIZER": 10, "BERRY": 10}, "params": {}},
    }
    configuration = {"maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}
    route = [blank_action() for _ in range(72)]
    route[25]["farmer"] = ["PICKUP", "FERTILIZER", 1]
    route[26]["farmer"] = ["FERTILIZE"]
    route[48]["farmer"] = ["WATER"]
    selected = blank_action()
    selected["market"] = [["SELL", "FERTILIZER", 2]] + [[] for _ in range(9)]
    return observation, configuration, selected, post_farm, post_private, route


class CurrentDelegatePrefixOracle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = load_current_helper()
        cls.mechanics = Mechanics()

    def run_bare(self, selected, route):
        obs, cfg, _base, farm, private, _route = fixture()
        return self.helper.protect_operating_stock(
            self.mechanics, obs, cfg, selected, farm, private, route, ())

    def run_guarded(self, selected, route):
        obs, cfg, _base, farm, private, _route = fixture()
        return prefix_guard.protect_operating_stock_prefix(
            self.helper.protect_operating_stock,
            self.mechanics, obs, cfg, selected, farm, private, route, ())

    def test_clean_executable_prefix_is_admitted(self):
        _obs, _cfg, selected, _farm, _private, route = fixture()
        out, report = self.run_bare(selected, route)
        self.assertTrue(report["changed"], report)
        self.assertEqual(report["reason"], "reserve_reachable_fertilizer")
        self.assertEqual(out["market"][0], ["SELL", "FERTILIZER", 1])

    def test_dead_tail_hire_is_a_real_predecessor_counterexample(self):
        _obs, _cfg, selected, _farm, _private, route = fixture()
        tailed = deepcopy(selected)
        tailed["market"].append(["HIRE"])
        out, report = self.run_bare(tailed, route)
        self.assertIs(out, tailed)
        self.assertEqual(report["reason"], "current_hiring_boundary")

        fixed, fixed_report = self.run_guarded(tailed, route)
        self.assertTrue(fixed_report["changed"], fixed_report)
        self.assertEqual(fixed["market"][:10], self.run_bare(selected, route)[0]["market"][:10])
        self.assertEqual(fixed["market"][10:], [["HIRE"]])

    def test_dead_tail_buy_is_a_real_predecessor_counterexample(self):
        _obs, _cfg, selected, _farm, _private, route = fixture()
        tailed = deepcopy(selected)
        tailed["market"].append(["BUY_PRODUCT", "FERTILIZER", 99])
        _out, report = self.run_bare(tailed, route)
        self.assertFalse(report["changed"], report)
        self.assertEqual(report["reason"], "retained_stock_conflicts_with_arrival_room")

        fixed, fixed_report = self.run_guarded(tailed, route)
        self.assertTrue(fixed_report["changed"], fixed_report)
        self.assertEqual(fixed["market"][:10], self.run_bare(selected, route)[0]["market"][:10])
        self.assertEqual(fixed["market"][10:], [["BUY_PRODUCT", "FERTILIZER", 99]])

    def test_dead_tail_sell_is_not_rewritten_by_guard(self):
        _obs, _cfg, selected, _farm, _private, route = fixture()
        tail = ["SELL", "FERTILIZER", 99]
        tailed = deepcopy(selected)
        tailed["market"].append(deepcopy(tail))
        bare, bare_report = self.run_bare(tailed, route)
        self.assertTrue(bare_report["changed"], bare_report)
        self.assertNotEqual(bare["market"][10], tail)

        fixed, fixed_report = self.run_guarded(tailed, route)
        self.assertTrue(fixed_report["changed"], fixed_report)
        self.assertEqual(fixed["market"][10], tail)
        self.assertEqual(fixed["market"][:10], self.run_bare(selected, route)[0]["market"][:10])

    def test_future_dead_tail_hire_no_longer_truncates_scan(self):
        _obs, _cfg, selected, _farm, _private, route = fixture()
        tailed_route = deepcopy(route)
        tailed_route[25]["market"] = [[] for _ in range(10)] + [["HIRE"]]
        bare, bare_report = self.run_bare(selected, tailed_route)
        self.assertFalse(bare_report["changed"], bare_report)
        self.assertNotEqual(bare_report["reason"], "reserve_reachable_fertilizer")

        fixed, fixed_report = self.run_guarded(selected, tailed_route)
        self.assertTrue(fixed_report["changed"], fixed_report)
        self.assertEqual(fixed["market"][:10], self.run_bare(selected, route)[0]["market"][:10])
        self.assertEqual(tailed_route[25]["market"][10:], [["HIRE"]])


if __name__ == "__main__":
    unittest.main()
