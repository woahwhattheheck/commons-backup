# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

LAB = Path(__file__).resolve().parent
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

import build_integrated
import main as titan_main
import titan_runtime


class _FakeFeatures:
    def __init__(self, **values):
        self.consumer = values.get("consumer", "frozen")
        self.terminal_route = values.get("terminal_route", False)
        self.fourth_quadrant = values.get("fourth_quadrant", False)
        self.overflow_safe_drop = values.get("overflow_safe_drop", False)
        self.budget_seconds = values.get("budget_seconds", 1.0)


class _FakeTitanAgent:
    def __init__(self, *args, **kwargs):
        self.diagnostics = {"status": "completed"}
        self.consumer = object()
        self.history = None
        self.spatial = None
        self.selected = None

    def _initialize(self):
        return None

    def act(self, observation, configuration=None, *, entry_started=None):
        return {"farmer": ["PASS"], "hands": [], "market": []}

    def _early_capital_selected(self, obs, cfg, selected):
        return deepcopy(selected)

    def _market_pressure_selected(self, obs, cfg, selected):
        return selected

    def _feed_stock_selected(self, obs, cfg, selected):
        return selected


class OverflowSafeDropRuntimeTest(unittest.TestCase):
    def _new(self, feature, load):
        with (mock.patch.object(titan_runtime, "TitanAgent", _FakeTitanAgent),
              mock.patch.object(titan_runtime, "Features", _FakeFeatures),
              mock.patch.object(titan_runtime, "load", load)):
            return titan_main._new_instance(
                LAB,
                {
                    "consumer": "frozen",
                    "terminal_route": False,
                    "fourth_quadrant": False,
                    "overflow_safe_drop": feature,
                },
            )

    @staticmethod
    def _selected():
        return {
            "farmer": ["DROP"],
            "hands": [],
            "market": [["SELL", "CARROT", 5]],
        }

    @staticmethod
    def _observation(step=100):
        return {
            "player": 0,
            "step": step,
            "farms": [
                {"farmer": [4, 4], "hands": []},
                {"farmer": [0, 0], "hands": []},
            ],
            "private": {
                "inventories": [{"CARROT": 10}],
                "shed": {"CARROT": 95},
            },
        }

    @staticmethod
    def _configuration():
        return {
            "boardSize": 10,
            "shedCapacity": 100,
            "maxMarketOrdersPerTurn": 10,
            "episodeSteps": 720,
        }

    def test_feature_is_strict_default_off_bool(self):
        self.assertFalse(titan_runtime.Features().overflow_safe_drop)
        self.assertTrue(titan_runtime.Features(overflow_safe_drop=True).overflow_safe_drop)
        for poison in (0, 1, "true", None):
            with self.subTest(poison=poison):
                with self.assertRaises(TypeError):
                    titan_runtime.Features(overflow_safe_drop=poison)
        config = json.loads((LAB / "TITAN-CONFIG.json").read_text())
        self.assertIs(config["overflow_safe_drop"], False)

    def test_release_maps_exact_canonical_helper_and_runtime_test(self):
        mapping = build_integrated.source_files()
        self.assertEqual(
            mapping["overflow_safe_drop.py"],
            "candidates/v5/research/overflow-safe-drop/overflow_safe_drop.py",
        )
        self.assertEqual(
            mapping["checks/test_overflow_safe_drop_runtime.py"],
            "test_overflow_safe_drop_runtime.py",
        )

    def test_false_feature_does_not_load_helper_and_preserves_action(self):
        calls = []

        def forbidden_load(name, path, *, cache=False):
            calls.append((name, str(path), cache))
            raise AssertionError("default-OFF overflow helper must not load")

        instance = self._new(False, forbidden_load)
        selected = self._selected()
        returned = instance._early_capital_selected(
            self._observation(), self._configuration(), selected
        )
        self.assertEqual(returned, selected)
        self.assertEqual(calls, [])
        self.assertEqual(instance._finalizer_checkpoint["stage"], "market_pressure")
        self.assertNotIn("overflow_safe_drop", instance.diagnostics)

    def test_true_feature_loads_canonical_helper_and_rewrites_natural_drop(self):
        original_load = titan_runtime.load
        loaded = []

        def traced_load(name, path, *, cache=False):
            loaded.append((name, Path(path), cache))
            return original_load(name, path, cache=cache)

        instance = self._new(True, traced_load)
        returned = instance._early_capital_selected(
            self._observation(), self._configuration(), self._selected()
        )
        self.assertEqual(returned["farmer"], ["PLACE", "CARROT", 5])
        self.assertEqual(returned["market"], [["SELL", "CARROT", 5]])
        self.assertTrue(instance.diagnostics["overflow_safe_drop"]["changed"])
        self.assertEqual(
            instance.diagnostics["overflow_safe_drop"]["preserved_in_pocket_lower_bound"],
            5,
        )
        self.assertEqual(instance._finalizer_checkpoint["stage"], "overflow_safe_drop")
        self.assertEqual(instance._finalizer_checkpoint["action"], returned)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0][0], "_titan_overflow_safe_drop")
        self.assertTrue(
            str(loaded[0][1]).endswith(
                "candidates/v5/research/overflow-safe-drop/overflow_safe_drop.py"
            )
        )

    def test_terminal_step_suppresses_helper_call_and_checkpoint(self):
        class Helper:
            calls = 0

            @staticmethod
            def transform(selected, observation, configuration):
                Helper.calls += 1
                changed = deepcopy(selected)
                changed["farmer"] = ["PLACE", "CARROT", 5]
                return changed, {"changed": True}

        def fake_load(name, path, *, cache=False):
            self.assertEqual(name, "_titan_overflow_safe_drop")
            return Helper

        instance = self._new(True, fake_load)
        selected = self._selected()
        returned = instance._early_capital_selected(
            self._observation(step=718), self._configuration(), selected
        )
        self.assertEqual(returned, selected)
        self.assertEqual(Helper.calls, 0)
        self.assertEqual(instance._finalizer_checkpoint["stage"], "market_pressure")
        self.assertNotIn("overflow_safe_drop", instance.diagnostics)

    def test_incomplete_path_suppresses_optional_helper(self):
        class Helper:
            calls = 0

            @staticmethod
            def transform(selected, observation, configuration):
                Helper.calls += 1
                return selected, {"changed": False}

        instance = self._new(True, lambda *args, **kwargs: Helper)
        instance.diagnostics["status"] = "deadline_fallback"
        selected = self._selected()
        returned = instance._early_capital_selected(
            self._observation(), self._configuration(), selected
        )
        self.assertEqual(returned, selected)
        self.assertEqual(Helper.calls, 0)
        self.assertEqual(instance._finalizer_checkpoint["stage"], "early_capital")
        self.assertNotIn("overflow_safe_drop", instance.diagnostics)


if __name__ == "__main__":
    unittest.main()
