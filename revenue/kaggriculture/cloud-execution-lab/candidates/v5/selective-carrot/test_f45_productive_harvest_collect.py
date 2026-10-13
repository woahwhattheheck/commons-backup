# SPDX-License-Identifier: Apache-2.0
"""Hostile unit and injector cases for Wave-4 F45."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = Path(__file__).resolve().parents[3]
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import mechanics
from build_f45_productive_harvest_collect import GUARD, RUNTIME, inject, patch_runtime
from f45_productive_harvest_collect import protect_productive_units

CFG = {
    "episodeSteps": 720,
    "boardSize": 2,
    "turnsPerDay": 24,
    "shedCapacity": 100,
}


def _action(farmer, hands=None, market=None):
    return {
        "farmer": copy.deepcopy(farmer),
        "hands": copy.deepcopy(hands or []),
        "market": copy.deepcopy(market or []),
    }


def _obs(tile0, tile1=None, *, step=700):
    farm = {
        "farmer": [0, 0],
        "hands": [[1, 0]],
        "tiles": [[copy.deepcopy(tile0), copy.deepcopy(tile1)], [None, None]],
    }
    return {
        "step": step,
        "player": 0,
        "farms": [farm, {"tiles": [[None, None], [None, None]]}],
        "private": {"inventories": [{}, {}], "shed": {}, "seeds": {}},
    }


def _plant(units=2):
    return {"kind": "PLANT", "crop": "WHEAT", "planted_day": 0, "yield_units": units}


def _animal(*, fertilizer=True):
    return {
        "kind": "PASTURE",
        "animal": "COW",
        "fertilizer_available": fertilizer,
        "yield_units": 0,
        "fed_today": True,
        "cared_today": True,
    }


class ProductiveProtectionCases(unittest.TestCase):
    def test_restores_replay_proven_harvest_over_pass(self):
        selected = _action(["HARVEST"], [["PASS"]], [["SELL", "WHEAT", 1]])
        returned = _action(["PASS"], [["PASS"]], [["SELL", "WHEAT", 1]])
        out, report = protect_productive_units(mechanics, _obs(_plant(2)), CFG, selected, returned)
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(out["market"], returned["market"])
        self.assertTrue(report["changed"])
        self.assertEqual(report["commodity_gain"], 2)
        self.assertEqual(report["restored_slots"][0]["slot"], 0)

    def test_restores_collect_fertilizer_over_movement(self):
        selected = _action(["PASS"], [["COLLECT_FERTILIZER"]])
        returned = _action(["PASS"], [["WEST"]])
        out, report = protect_productive_units(
            mechanics, _obs(None, _animal()), CFG, selected, returned)
        self.assertEqual(out["hands"][0], ["COLLECT_FERTILIZER"])
        self.assertEqual(report["commodity_gain"], 1)

    def test_never_steals_drop_surface_from_f44(self):
        selected = _action(["HARVEST"], [["PASS"]])
        returned = _action(["DROP"], [["PASS"]])
        out, report = protect_productive_units(mechanics, _obs(_plant(3)), CFG, selected, returned)
        self.assertEqual(out, returned)
        self.assertFalse(report["changed"])

    def test_never_changes_market_or_pickup_place_surface(self):
        selected = _action(["HARVEST"], [["PASS"]], [["SELL", "WOOL", 3]])
        for replacement in (["PICKUP", "WHEAT", 1], ["PLACE", "COW"]):
            returned = _action(replacement, [["PASS"]], [["SELL", "WOOL", 3]])
            out, report = protect_productive_units(
                mechanics, _obs(_plant(3)), CFG, selected, returned)
            self.assertEqual(out, returned)
            self.assertFalse(report["changed"])
            self.assertEqual(out["market"], [["SELL", "WOOL", 3]])

    def test_zero_yield_and_empty_fertilizer_fail_replay_proof(self):
        cases = [
            (_obs(_plant(0)), _action(["HARVEST"], [["PASS"]]),
             _action(["PASS"], [["PASS"]])),
            (_obs(None, _animal(fertilizer=False)),
             _action(["PASS"], [["COLLECT_FERTILIZER"]]),
             _action(["PASS"], [["NORTH"]])),
        ]
        for observation, selected, returned in cases:
            with self.subTest(selected=selected):
                out, report = protect_productive_units(
                    mechanics, observation, CFG, selected, returned)
                self.assertEqual(out, returned)
                self.assertFalse(report["changed"])

    def test_terminal_horizon_is_hard_gate(self):
        selected = _action(["HARVEST"], [["PASS"]])
        returned = _action(["PASS"], [["PASS"]])
        out, report = protect_productive_units(
            mechanics, _obs(_plant(2), step=100), CFG, selected, returned)
        self.assertEqual(out, returned)
        self.assertEqual(report["reason"], "outside_terminal_horizon")

    def test_duplicate_same_tile_work_only_restores_real_increment(self):
        observation = _obs(_plant(2), step=700)
        observation["farms"][0]["hands"][0] = [0, 0]
        selected = _action(["HARVEST"], [["HARVEST"]])
        returned = _action(["PASS"], [["PASS"]])
        out, report = protect_productive_units(mechanics, observation, CFG, selected, returned)
        self.assertTrue(report["changed"])
        self.assertEqual(len(report["restored_slots"]), 1)
        self.assertEqual(report["commodity_gain"], 2)
        self.assertIn(["HARVEST"], (out["farmer"], out["hands"][0]))

    def test_inputs_are_immutable(self):
        observation = _obs(_plant(2))
        selected = _action(["HARVEST"], [["PASS"]])
        returned = _action(["PASS"], [["PASS"]])
        before = copy.deepcopy((observation, selected, returned))
        protect_productive_units(mechanics, observation, CFG, selected, returned)
        self.assertEqual((observation, selected, returned), before)

    def test_malformed_shapes_fail_closed(self):
        selected = _action(["HARVEST"], [["PASS"]])
        returned = _action(["PASS"], [["PASS"]])
        malformed = _obs(_plant(2))
        malformed["private"] = None
        out, report = protect_productive_units(mechanics, malformed, CFG, selected, returned)
        self.assertEqual(out, returned)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "baseline_replay_failed")


class InjectorCases(unittest.TestCase):
    @staticmethod
    def runtime_fixture():
        return b"""class Features:\n    overflow_safe_drop: bool = False\n\n    def __post_init__(self):\n        bool_fields = (*bool_fields, 'exec_pace', 'overflow_safe_drop')\n\nclass TitanAgent:\n    def _finish_production(self, obs, returned, cfg=None):\n        pass\n        return returned\n\n    def _seed_selected(self, obs, cfg, selected):\n        return selected\n"""

    def test_inject_adds_only_runtime_and_helper(self):
        base = {RUNTIME: self.runtime_fixture(), "keep.txt": b"same"}
        source = b"# guard\r\n"
        files = inject(base, source)
        self.assertEqual(base["keep.txt"], files["keep.txt"])
        self.assertEqual(files[GUARD], b"# guard\n")
        self.assertIn(b"productive_terminal_guard: bool = True", files[RUNTIME])
        self.assertIn(b"_productive_terminal_guard_selected", files[RUNTIME])
        self.assertIn(b"returned = self._productive_terminal_guard_selected", files[RUNTIME])
        self.assertNotIn(GUARD, base)
        self.assertNotEqual(files[RUNTIME], base[RUNTIME])

    def test_patch_fails_closed_on_anchor_drift(self):
        fixture = self.runtime_fixture()
        anchors = [
            b"overflow_safe_drop: bool = False",
            b"bool_fields = (*bool_fields, 'exec_pace', 'overflow_safe_drop')",
            b"def _finish_production(self, obs, returned, cfg=None):",
            b"return returned\n\n    def _seed_selected",
        ]
        for anchor in anchors:
            with self.subTest(anchor=anchor):
                drifted = fixture.replace(anchor, b"DRIFT", 1)
                with self.assertRaises(ValueError):
                    patch_runtime(drifted)

    def test_inject_rejects_existing_helper_and_missing_runtime(self):
        with self.assertRaises(ValueError):
            inject({GUARD: b"old"}, b"new")
        with self.assertRaises(ValueError):
            inject({RUNTIME: self.runtime_fixture(), GUARD: b"old"}, b"new")


if __name__ == "__main__":
    unittest.main()
