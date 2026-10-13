# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))


def _load_candidate():
    path = HERE / "candidate.py"
    spec = importlib.util.spec_from_file_location("_sol_fuse_candidate_under_test", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


candidate = _load_candidate()
from titan_runtime import TitanAgent


def action(market):
    return {"farmer": ["PASS"], "hands": [], "market": deepcopy(market)}


def observation(money=176):
    return {"step": 96, "player": 0,
            "farms": [{"money": money, "hires_today": 0,
                       "unlocked_quadrants": ["NW", "NE"]}, {}]}


class FakeInstance:
    def __init__(self, status="completed"):
        self.diagnostics = {"status": status}
        self._final_pressure_boundary = False


class CandidateCompositionTests(unittest.TestCase):
    def setUp(self):
        self.original_early = TitanAgent._early_capital_selected
        self.original_pressure = TitanAgent._market_pressure_selected
        self.before = action([["SELL", "CARROT", 10], ["SELL", "MILK", 10],
                              ["BUY_LAND"]])
        self.after = action([["SELL", "MILK", 10], ["SELL", "CARROT", 10],
                             ["BUY_LAND"]])

    def tearDown(self):
        TitanAgent._early_capital_selected = self.original_early
        TitanAgent._market_pressure_selected = self.original_pressure
        candidate._LAST_REPORT = None

    def install(self, *, status="completed", pressure=None):
        before = deepcopy(self.before)
        after = deepcopy(self.after if pressure is None else pressure)
        calls = []

        def early(instance, obs, cfg, selected):
            calls.append(("early", instance._final_pressure_boundary))
            return deepcopy(before)

        def final_pressure(instance, obs, cfg, selected):
            calls.append(("pressure", instance._final_pressure_boundary))
            self.assertEqual(selected, before)
            return deepcopy(after)

        TitanAgent._early_capital_selected = early
        TitanAgent._market_pressure_selected = final_pressure
        instance = candidate._install(FakeInstance(status=status))
        return instance, calls

    def test_source_receipt_is_exact_current(self):
        receipt = candidate.source_receipt()
        self.assertTrue(receipt["valid"])
        self.assertEqual(receipt["base_commit"], candidate.BASE_COMMIT)
        self.assertEqual(set(receipt["files"]), set(candidate.EXPECTED_BLOBS))

    def test_installed_stage_runs_early_then_pressure_then_reverts(self):
        instance, calls = self.install()
        returned = instance._early_capital_selected(
            observation(), {"maxMarketOrdersPerTurn": 10}, action([]))
        self.assertEqual(returned, self.before)
        self.assertEqual(calls, [("early", False), ("pressure", True)])
        self.assertFalse(instance._final_pressure_boundary)
        report = instance.diagnostics["pressure_capital_solvency"]
        self.assertFalse(report["accepted"])
        self.assertEqual(candidate.last_report(), report)

    def test_independently_funded_stage_keeps_pressure(self):
        instance, calls = self.install()
        returned = instance._early_capital_selected(
            observation(2000), {"maxMarketOrdersPerTurn": 10}, action([]))
        self.assertEqual(returned, self.after)
        self.assertEqual(calls, [("early", False), ("pressure", True)])
        self.assertTrue(instance.diagnostics["pressure_capital_solvency"]["accepted"])

    def test_noncompleted_action_never_starts_final_pressure(self):
        instance, calls = self.install(status="deadline_fallback")
        returned = instance._early_capital_selected(
            observation(), {"maxMarketOrdersPerTurn": 10}, action([]))
        self.assertEqual(returned, self.before)
        self.assertEqual(calls, [("early", False)])
        self.assertEqual(candidate.last_report()["reason"], "noncompleted_action")

    def test_guard_error_restores_prepressure_action(self):
        original = candidate._GUARD.preserve_acquisition_solvency
        try:
            candidate._GUARD.preserve_acquisition_solvency = (
                lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
            instance, calls = self.install()
            returned = instance._early_capital_selected(
                observation(), {"maxMarketOrdersPerTurn": 10}, action([]))
        finally:
            candidate._GUARD.preserve_acquisition_solvency = original
        self.assertEqual(returned, self.before)
        self.assertEqual(calls, [("early", False), ("pressure", True)])
        report = instance.diagnostics["pressure_capital_solvency"]
        self.assertEqual(report["reason"], "guard_error")
        self.assertIn("RuntimeError", report["error"])

    def test_install_is_idempotent(self):
        instance, calls = self.install()
        first = instance._early_capital_selected
        candidate._install(instance)
        self.assertIs(instance._early_capital_selected, first)
        returned = first(observation(), {"maxMarketOrdersPerTurn": 10}, action([]))
        self.assertEqual(returned, self.before)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
