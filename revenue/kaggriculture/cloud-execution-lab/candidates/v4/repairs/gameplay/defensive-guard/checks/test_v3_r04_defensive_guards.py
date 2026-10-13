# SPDX-License-Identifier: Apache-2.0
"""Defensive last-mile guards in the V3 router: PLANT overdemand cap and
numeric-arg sanitization.

The engine's atomic PLANT rule drops ALL of a turn's PLANT requests for a crop
to PASS when the total exceeds seeds held. The engine's PICKUP/PLACE paths call
bare int(action[2]), so a malformed qty raises ValueError and kills the whole
interpreter step for both players. Both guards are identity when nothing needs
fixing; both are fail-closed on malformed input.

    python -m unittest -v checks/test_v3_r04_defensive_guards.py

Standard library only.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402


def obs_with_seeds(seeds):
    return {"private": {"seeds": dict(seeds)}, "step": 100, "player": 0}


class PlantOverdemandGuard(unittest.TestCase):
    def test_overdemand_trims_excess_keeps_priority(self):
        # 3 PLANT WHEAT requests, 2 seeds -> exactly 2 PLANTs, 1 PASS.
        obs = obs_with_seeds({"WHEAT": 2})
        action = {"farmer": ["PLANT", "WHEAT"],
                  "hands": [["PLANT", "WHEAT"], ["PLANT", "WHEAT"], ["PASS"]],
                  "market": []}
        out = r04._guard_plant_overdemand(obs, action)
        self.assertIsNot(out, action)
        plants = [c for c in [out["farmer"]] + out["hands"]
                  if isinstance(c, list) and len(c) >= 2 and c[0] == "PLANT"]
        self.assertEqual(len(plants), 2)
        # Priority: farmer + first hand kept, second hand trimmed to PASS.
        self.assertEqual(out["farmer"], ["PLANT", "WHEAT"])
        self.assertEqual(out["hands"][0], ["PLANT", "WHEAT"])
        self.assertEqual(out["hands"][1], ["PASS"])
        self.assertEqual(out["hands"][2], ["PASS"])
        # Untouched commands keep their identity.
        self.assertIs(out["hands"][0], action["hands"][0])

    def test_no_overdemand_returns_identity(self):
        obs = obs_with_seeds({"WHEAT": 5})
        action = {"farmer": ["PLANT", "WHEAT"],
                  "hands": [["PLANT", "WHEAT"]], "market": []}
        self.assertIs(r04._guard_plant_overdemand(obs, action), action)

    def test_exact_demand_not_trimmed(self):
        obs = obs_with_seeds({"WHEAT": 2})
        action = {"farmer": ["PLANT", "WHEAT"],
                  "hands": [["PLANT", "WHEAT"]], "market": []}
        self.assertIs(r04._guard_plant_overdemand(obs, action), action)

    def test_per_crop_independent(self):
        # WHEAT overdemanded, CARROT fine -> only WHEAT trimmed.
        obs = obs_with_seeds({"WHEAT": 1, "CARROT": 3})
        action = {"farmer": ["PLANT", "WHEAT"],
                  "hands": [["PLANT", "WHEAT"], ["PLANT", "CARROT"]],
                  "market": []}
        out = r04._guard_plant_overdemand(obs, action)
        self.assertEqual(out["farmer"], ["PLANT", "WHEAT"])
        self.assertEqual(out["hands"][0], ["PASS"])
        self.assertEqual(out["hands"][1], ["PLANT", "CARROT"])

    def test_zero_seeds_trims_all(self):
        obs = obs_with_seeds({"WHEAT": 0})
        action = {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
        out = r04._guard_plant_overdemand(obs, action)
        self.assertEqual(out["farmer"], ["PASS"])

    def test_farmer_overdemand_trims_farmer_last(self):
        # Farmer is highest priority: excess is trimmed from hands first.
        obs = obs_with_seeds({"WHEAT": 1})
        action = {"farmer": ["PLANT", "WHEAT"],
                  "hands": [["PLANT", "WHEAT"], ["PLANT", "WHEAT"]],
                  "market": []}
        out = r04._guard_plant_overdemand(obs, action)
        self.assertEqual(out["farmer"], ["PLANT", "WHEAT"])
        self.assertEqual(out["hands"][0], ["PASS"])
        self.assertEqual(out["hands"][1], ["PASS"])

    def test_fail_closed_on_malformed(self):
        action = {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
        self.assertIs(r04._guard_plant_overdemand(None, action), action)
        self.assertIs(r04._guard_plant_overdemand({}, action), action)
        self.assertIs(r04._guard_plant_overdemand({"private": None}, action), action)
        # {"private": {}} means legitimately zero seeds (engine would block too),
        # so trimming there is correct, not a fail-closed case.

    def test_engine_never_sees_overdemand_after_guard(self):
        # Simulate the engine's atomic rule: post-guard demand <= seeds.
        obs = obs_with_seeds({"WHEAT": 2, "CARROT": 1})
        action = {"farmer": ["PLANT", "WHEAT"],
                  "hands": [["PLANT", "WHEAT"], ["PLANT", "WHEAT"],
                            ["PLANT", "CARROT"], ["PLANT", "CARROT"]],
                  "market": []}
        out = r04._guard_plant_overdemand(obs, action)
        demand = {}
        for c in [out["farmer"]] + out["hands"]:
            if isinstance(c, list) and len(c) >= 2 and c[0] == "PLANT":
                demand[c[1]] = demand.get(c[1], 0) + 1
        for crop, n in demand.items():
            self.assertLessEqual(n, obs["private"]["seeds"].get(crop, 0))


class NumericArgSanitizer(unittest.TestCase):
    def test_string_qty_dropped_to_pass(self):
        # The engine's bare int("abc") would raise and kill the whole step.
        action = {"farmer": ["PICKUP", "WHEAT", "abc"],
                  "hands": [["PLACE", "WOOL", "xyz"]], "market": []}
        out = r04._sanitize_numeric_args(action)
        self.assertIsNot(out, action)
        self.assertEqual(out["farmer"], ["PASS"])
        self.assertEqual(out["hands"], [["PASS"]])

    def test_coercible_qty_normalized(self):
        action = {"farmer": ["PICKUP", "WHEAT", "5"],
                  "hands": [["PLACE", "WOOL", 3.0]], "market": []}
        out = r04._sanitize_numeric_args(action)
        self.assertEqual(out["farmer"], ["PICKUP", "WHEAT", 5])
        self.assertEqual(out["hands"], [["PLACE", "WOOL", 3]])

    def test_clean_int_qty_returns_identity(self):
        action = {"farmer": ["PICKUP", "WHEAT", 5],
                  "hands": [["PLACE", "WOOL", 3], ["PASS"]], "market": []}
        self.assertIs(r04._sanitize_numeric_args(action), action)

    def test_none_qty_dropped(self):
        action = {"farmer": ["PICKUP", "WHEAT", None], "hands": [], "market": []}
        out = r04._sanitize_numeric_args(action)
        self.assertEqual(out["farmer"], ["PASS"])

    def test_nan_qty_dropped(self):
        action = {"farmer": ["PICKUP", "WHEAT", float("nan")],
                  "hands": [], "market": []}
        out = r04._sanitize_numeric_args(action)
        self.assertEqual(out["farmer"], ["PASS"])

    def test_non_qty_commands_untouched(self):
        action = {"farmer": ["PLANT", "WHEAT"],
                  "hands": [["WATER"], ["MOVE", "NORTH"]], "market": []}
        self.assertIs(r04._sanitize_numeric_args(action), action)

    def test_missing_qty_defaults_safe(self):
        # len < 3 -> engine defaults to 1; sanitizer leaves it alone.
        action = {"farmer": ["PICKUP", "WHEAT"], "hands": [], "market": []}
        self.assertIs(r04._sanitize_numeric_args(action), action)

    def test_inf_unit_qty_dropped(self):
        # int(inf) raises OverflowError (not ValueError) -- the crash vector.
        action = {"farmer": ["PICKUP", "WHEAT", float("inf")],
                  "hands": [["PLACE", "WOOL", float("-inf")]], "market": []}
        out = r04._sanitize_numeric_args(action)
        self.assertEqual(out["farmer"], ["PASS"])
        self.assertEqual(out["hands"], [["PASS"]])

    def test_inf_market_qty_becomes_noop_row(self):
        # _parse_order doesn't catch OverflowError: replace with ["PASS"] so
        # max_orders slot positions are preserved exactly.
        action = {"farmer": ["PASS"], "hands": [],
                  "market": [["SELL", "WHEAT", float("inf")],
                             ["SELL", "MILK", 10]]}
        out = r04._sanitize_numeric_args(action)
        self.assertIsNot(out, action)
        self.assertEqual(out["market"][0], ["PASS"])
        self.assertEqual(out["market"][1], ["SELL", "MILK", 10])
        self.assertEqual(len(out["market"]), 2)

    def test_abc_market_qty_left_for_engine(self):
        # ValueError IS caught by _parse_order; engine rejects safely.
        action = {"farmer": ["PASS"], "hands": [],
                  "market": [["SELL", "WHEAT", "abc"]]}
        self.assertIs(r04._sanitize_numeric_args(action), action)

    def test_clean_market_rows_untouched(self):
        action = {"farmer": ["PASS"], "hands": [],
                  "market": [["SELL", "WHEAT", 10], ["HIRE"]]}
        self.assertIs(r04._sanitize_numeric_args(action), action)

    def test_coercible_market_qty_normalized(self):
        action = {"farmer": ["PASS"], "hands": [],
                  "market": [["BUY_PRODUCT", "WHEAT", "5"]]}
        out = r04._sanitize_numeric_args(action)
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 5]])

    def test_fail_closed(self):
        self.assertIs(r04._sanitize_numeric_args(None), None)
        self.assertIs(r04._sanitize_numeric_args("nope"), "nope")
        action = {"farmer": ["PICKUP", "WHEAT", "abc"]}
        # hands not a list -> only farmer fixed, no crash
        out = r04._sanitize_numeric_args(action)
        self.assertEqual(out["farmer"], ["PASS"])


class TestEodAutodropGuard(unittest.TestCase):
    def _obs(self, step=23, shed=None, invs=None, prices=None):
        tiles = [[None] * 10 for _ in range(10)]
        return {
            "step": step, "player": 0,
            "farms": [{"farmer": [4, 4], "hands": [], "tiles": tiles,
                       "money": 5000}],
            "private": {"shed": shed or {},
                        "inventories": invs if invs is not None else [{}],
                        "seeds": {}},
            "market": {"prices": prices or {"WHEAT": 10, "WOOL": 50}},
        }

    def test_no_overflow_identity(self):
        obs = self._obs(shed={"WHEAT": 60}, invs=[{"WOOL": 30}])
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        self.assertIs(r04._guard_eod_autodrop(obs, action), action)

    def test_overflow_sells_cheapest_from_shed(self):
        # SELL takes from the shed (engine _commit_unit): 60 + 50 - 100 = 10
        # excess -> sell 10 WHEAT (cheapest shed good); the EOD drop then
        # refills the shed with carried WOOL instead of destroying it.
        obs = self._obs(shed={"WHEAT": 60}, invs=[{"WOOL": 50}])
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        out = r04._guard_eod_autodrop(obs, action)
        self.assertIsNot(out, action)
        self.assertEqual(out["market"], [["SELL", "WHEAT", 10]])

    def test_scheduled_sells_free_room(self):
        # Flush already sells 30 from the shed: 60-30+50 = 80 <= 100.
        obs = self._obs(shed={"WHEAT": 60}, invs=[{"WOOL": 50}])
        action = {"farmer": ["PASS"], "hands": [],
                  "market": [["SELL", "WHEAT", 30]]}
        self.assertIs(r04._guard_eod_autodrop(obs, action), action)

    def test_scheduled_buys_consume_room(self):
        # 90 + 5 + 10 (buy) = 105 -> sell 5 cheapest (WHEAT).
        obs = self._obs(shed={"WHEAT": 90}, invs=[{"MILK": 5}])
        action = {"farmer": ["PASS"], "hands": [],
                  "market": [["BUY_PRODUCT", "WHEAT", 10]]}
        out = r04._guard_eod_autodrop(obs, action)
        self.assertEqual(out["market"][0], ["SELL", "WHEAT", 5])

    def test_merge_with_existing_sell_row(self):
        # Existing SELL WHEAT 20 + need 10 more -> bumped to 30, one row.
        # excess = 100 + 30 - 20 - 100 = 10.
        obs = self._obs(shed={"WHEAT": 100}, invs=[{"WOOL": 30}])
        action = {"farmer": ["PASS"], "hands": [],
                  "market": [["SELL", "WHEAT", 20]]}
        out = r04._guard_eod_autodrop(obs, action)
        self.assertEqual(out["market"], [["SELL", "WHEAT", 30]])

    def test_rescue_rows_prepended(self):
        obs = self._obs(shed={"WHEAT": 60, "WOOL": 0}, invs=[{"MILK": 50}],
                        prices={"WHEAT": 10, "WOOL": 50, "MILK": 40})
        action = {"farmer": ["PASS"], "hands": [],
                  "market": [["SELL", "MILK", 5]]}
        out = r04._guard_eod_autodrop(obs, action)
        # excess = 60+50-5-100 = 5 -> cheapest shed good is WHEAT; new row first.
        self.assertEqual(out["market"][0], ["SELL", "WHEAT", 5])
        self.assertEqual(out["market"][1], ["SELL", "MILK", 5])

    def test_not_last_step_untouched(self):
        obs = self._obs(step=22, shed={"WHEAT": 60}, invs=[{"WOOL": 50}])
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        self.assertIs(r04._guard_eod_autodrop(obs, action), action)

    def test_unpriced_shed_goods_skipped(self):
        # SHEEP (animal, no price) can't be SELL-rescued -> identity.
        obs = self._obs(shed={"SHEEP": 95}, invs=[{"WOOL": 10}],
                        prices={"WOOL": 50})
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        self.assertIs(r04._guard_eod_autodrop(obs, action), action)

    def test_fail_closed(self):
        self.assertIs(r04._guard_eod_autodrop({}, None), None)
        self.assertIs(r04._guard_eod_autodrop(None, "x"), "x")


if __name__ == "__main__":
    unittest.main()
