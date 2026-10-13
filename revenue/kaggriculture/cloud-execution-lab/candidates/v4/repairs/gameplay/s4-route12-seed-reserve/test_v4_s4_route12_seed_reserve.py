# SPDX-License-Identifier: Apache-2.0
"""Focused source-only checks for V4 route-12 JIT seed reserve."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import r04_s4_route12_seed_reserve as lane  # noqa: E402


def _pass_action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def _tapes():
    tapes = [[_pass_action() for _ in range(719)] for _ in range(13)]
    tape = tapes[12]
    tape[213] = {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
    tape[257] = {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
    tape[261] = {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
    tape[262] = {
        "farmer": ["PLANT", "WHEAT"],
        "hands": [["PLANT", "WHEAT"], ["PLANT", "WHEAT"]],
        "market": [],
    }
    return tapes


def _observation(step, *, money=100, wheat_seeds=0, fert=0, wool=0,
                 shops=("YARN_STORE", "YARN_STORE")):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    shed = {item: 0 for item in (
        "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
        "EGG", "MILK", "WOOL", "FERTILIZER", "GOOSE", "COW", "SHEEP")}
    shed["FERTILIZER"] = fert
    shed["WOOL"] = wool
    return {
        "step": step,
        "player": 0,
        "town": {"unlocked_shops": list(shops)},
        "farms": [{"money": money, "tiles": tiles, "farmer": [4, 4],
                    "hands": [], "unlocked_quadrants": ["NW"], "hires_today": 0}],
        "private": {
            "seeds": {"WHEAT": wheat_seeds, "CARROT": 0, "TOMATO": 0,
                      "STRAWBERRY": 0, "MELON": 0},
            "shed": shed,
            "inventories": [{}],
        },
        "market": {
            "inventory": {item: 10000 for item in (
                "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
                "EGG", "MILK", "WOOL", "FERTILIZER")},
            "prices": {item: 100 for item in (
                "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
                "EGG", "MILK", "WOOL", "FERTILIZER")},
        },
    }


class Route12SeedReserve(unittest.TestCase):
    def setUp(self):
        self.original_policy = r04._POLICY
        self.tapes = _tapes()

    def tearDown(self):
        r04._POLICY = self.original_policy

    def _arm_policy(self, step, plan=12):
        r04._POLICY = SimpleNamespace(
            players={0: SimpleNamespace(last_step=step, plan=plan)},
            tapes=self.tapes,
        )

    def test_disabled_is_exact_parent(self):
        self._arm_policy(212)
        obs = _observation(212, money=0, fert=3)
        parent = {"farmer": ["PASS"], "hands": [],
                  "market": [["SELL", "FERTILIZER", 3]]}
        self.assertIs(lane.apply_route12_seed_reserve(obs, parent), parent)

    def test_step212_first_fertilizer_sale_funds_one_seed(self):
        self._arm_policy(212)
        obs = _observation(212, money=0, fert=3)
        parent = {"farmer": ["PASS"], "hands": [],
                  "market": [["SELL", "FERTILIZER", 3]]}
        before = copy.deepcopy(parent)
        out = lane.apply_route12_seed_reserve(obs, parent, enabled=True)
        self.assertIsNot(out, parent)
        self.assertEqual(parent, before)
        self.assertEqual(out["market"],
                         [["SELL", "FERTILIZER", 3], ["BUY_SEED", "WHEAT", 1]])

    def test_step256_buys_exact_raw_window_demand(self):
        self._arm_policy(256)
        obs = _observation(256, money=50)
        parent = {"farmer": ["PASS"], "hands": [], "market": []}
        out = lane.apply_route12_seed_reserve(obs, parent, enabled=True)
        self.assertEqual(out["market"], [["BUY_SEED", "WHEAT", 5]])

    def test_route_plan_and_policy_step_must_agree(self):
        parent = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = _observation(256, money=100, shops=("PET_CAFE", "YARN_STORE"))
        self._arm_policy(256)
        self.assertIs(lane.apply_route12_seed_reserve(obs, parent, enabled=True), parent)
        obs = _observation(256, money=100)
        self._arm_policy(256, plan=0)
        self.assertIs(lane.apply_route12_seed_reserve(obs, parent, enabled=True), parent)
        self._arm_policy(255)
        self.assertIs(lane.apply_route12_seed_reserve(obs, parent, enabled=True), parent)

    def test_tape_drift_fails_closed(self):
        self._arm_policy(256)
        self.tapes[12][262]["hands"].pop()
        obs = _observation(256, money=100)
        parent = {"farmer": ["PASS"], "hands": [], "market": []}
        self.assertIs(lane.apply_route12_seed_reserve(obs, parent, enabled=True), parent)

    def test_future_authored_wheat_refill_owns_window(self):
        self._arm_policy(256)
        self.tapes[12][261]["market"] = [["BUY_SEED", "WHEAT", 1]]
        obs = _observation(256, money=100)
        parent = {"farmer": ["PASS"], "hands": [], "market": []}
        self.assertIs(lane.apply_route12_seed_reserve(obs, parent, enabled=True), parent)

    def test_nonzero_seed_stock_fails_closed(self):
        self._arm_policy(256)
        obs = _observation(256, money=100, wheat_seeds=1)
        parent = {"farmer": ["PASS"], "hands": [], "market": []}
        self.assertIs(lane.apply_route12_seed_reserve(obs, parent, enabled=True), parent)

    def test_market_cap_duplicate_and_cash_spend_fail_closed(self):
        self._arm_policy(256)
        obs = _observation(256, money=100)
        capped = {"farmer": ["PASS"], "hands": [],
                  "market": [["SELL", "WOOL", 1] for _ in range(10)]}
        self.assertIs(lane.apply_route12_seed_reserve(obs, capped, enabled=True), capped)

        duplicate = {"farmer": ["PASS"], "hands": [],
                     "market": [["BUY_SEED", "WHEAT", 1]]}
        self.assertIs(lane.apply_route12_seed_reserve(obs, duplicate, enabled=True), duplicate)

        spend = {"farmer": ["PASS"], "hands": [],
                 "market": [["BUY_PRODUCT", "WHEAT", 1]]}
        self.assertIs(lane.apply_route12_seed_reserve(obs, spend, enabled=True), spend)

    def test_step212_requires_real_fertilizer_stock_and_row_zero_funding(self):
        self._arm_policy(212)
        no_stock_obs = _observation(212, money=0, fert=0)
        parent = {"farmer": ["PASS"], "hands": [],
                  "market": [["SELL", "FERTILIZER", 3]]}
        self.assertIs(lane.apply_route12_seed_reserve(no_stock_obs, parent, enabled=True), parent)

        obs = _observation(212, money=0, fert=3, wool=1)
        late_fert = {"farmer": ["PASS"], "hands": [],
                     "market": [["SELL", "WOOL", 1], ["SELL", "FERTILIZER", 3]]}
        self.assertIs(lane.apply_route12_seed_reserve(obs, late_fert, enabled=True), late_fert)

    def test_shed_touching_unit_action_fails_closed(self):
        self._arm_policy(256)
        obs = _observation(256, money=100)
        parent = {"farmer": ["DROP"], "hands": [], "market": []}
        self.assertIs(lane.apply_route12_seed_reserve(obs, parent, enabled=True), parent)

    def test_custom_market_and_bool_poison_fail_closed(self):
        self._arm_policy(212)
        obs = _observation(212, money=0, fert=3)
        parent = {"farmer": ["PASS"], "hands": [],
                  "market": [["SELL", "FERTILIZER", 3]]}
        self.assertIs(
            lane.apply_route12_seed_reserve(
                obs, parent, configuration={"marketParams": {}}, enabled=True),
            parent,
        )
        obs["private"]["shed"]["FERTILIZER"] = True
        self.assertIs(lane.apply_route12_seed_reserve(obs, parent, enabled=True), parent)


if __name__ == "__main__":
    unittest.main()
