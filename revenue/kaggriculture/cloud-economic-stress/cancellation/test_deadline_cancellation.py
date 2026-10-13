# SPDX-License-Identifier: Apache-2.0
"""Source-bound cancellation regressions; no engine, seed, or full-game runs.

Run from any directory with an explicit --adapter to check another source file.
The default tests the adjacent repository deadline_adapter.py. The three existing guard tests are
AST-selected unchanged from the exact upstream test_runner.py (runner.py itself
is not needed). Production cases execute the retained real _commit method with
an injected chooser; these are boundary tests, not full PlanOverlay executions.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import platform
import signal
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
D = None
MEASUREMENTS = []


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CommitExcerpt = load_module("commit_excerpt", HERE / "source/plan_overlay_commit_excerpt.py").CommitExcerpt
SELECTED = {"farmer": ["WEST"], "hands": [["CARE"]], "market": [["SELL", "MILK", 12]]}
TRANSFORMED = {"farmer": ["WEST"], "hands": [["CARE"]], "market": [["SELL", "MILK", 6]]}
OBS = {"player": 0, "step": 100, "day": 4, "hour": 4,
       "farms": [{"farmer": [0, 0], "hands": [[1, 1]]}]}


class Production(CommitExcerpt):
    """Use the real _commit body; no claim to execute the full producer."""
    def __init__(self, risk=lambda: 3):
        self.calls = 0
        self.errands = {}
        self.one_way = True
        self.risk = risk
        self.chooser = SimpleNamespace(at_risk=lambda *_args: self.risk())

    def act(self, observation):
        self.calls += 1
        self._commit({"errand_id": "test-errand"},
                     {"at": [1, 2], "product": "EGG", "units": 4},
                     observation, 0, observation["step"], observation["player"])
        return copy.deepcopy(SELECTED)


class Integrated:
    def __init__(self, production=None, transform=None):
        self.production = production if production is not None else Production()
        self.transform_calls = 0
        self.diagnostics = {"test_harness": True}
        self.transform_body = transform

    def transform(self, obs, cfg, selected, **kwargs):
        self.transform_calls += 1
        if self.transform_body is not None:
            return self.transform_body(obs, cfg, selected, **kwargs)
        return copy.deepcopy(TRANSFORMED)


def alarm_now():
    D._alarm(None, None)


@unittest.skipUnless(hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer"),
                     "Requires Linux/Unix main-thread SIGALRM")
class CancellationTests(unittest.TestCase):
    def setUp(self):
        self.previous_handler = signal.getsignal(signal.SIGALRM)
        self.previous_timer = signal.getitimer(signal.ITIMER_REAL)
        if self.previous_timer[0] != 0:
            self.skipTest("Run in a fresh subprocess; do not replace an active caller timer")

    def tearDown(self):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.previous_handler)

    def make_guard(self, integrated, **kwargs):
        return D.DeadlineFallbackAgent(integrated, budget_seconds=.5,
                                       reserve_seconds=.002, **kwargs)

    def assert_clean(self):
        self.assertEqual(signal.getsignal(signal.SIGALRM), self.previous_handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_cancellation_crosses_actual_commit_exception_handler(self):
        integrated = Integrated(Production(alarm_now))
        guard = self.make_guard(integrated)
        action = guard(OBS, {})
        self.assertEqual(action, D.legal_pass(OBS))
        self.assertEqual(guard.diagnostics["status"], "deadline_fallback")
        self.assertEqual(guard.diagnostics["fallback_stage"], "production")
        self.assertEqual(integrated.production.calls, 1)
        self.assertEqual(integrated.transform_calls, 0)
        self.assertEqual(integrated.production.errands, {})
        self.assert_clean()

    def test_real_sigalrm_crosses_actual_commit_handler(self):
        def slow_risk():
            time.sleep(.08)
            return 3
        def slow_transform(*_args, **_kwargs):
            time.sleep(.04)
            return copy.deepcopy(TRANSFORMED)
        integrated = Integrated(Production(slow_risk), slow_transform)
        guard = D.DeadlineFallbackAgent(integrated, budget_seconds=.03, reserve_seconds=.002)
        started = time.perf_counter()
        action = guard(OBS, {})
        elapsed = time.perf_counter() - started
        MEASUREMENTS.append({"case": "real_sigalrm_in_actual_commit", "budget_s": .03,
            "reserve_s": .002, "elapsed_s": elapsed,
            "status": guard.diagnostics["status"], "action": action,
            "production_calls": integrated.production.calls,
            "transform_calls": integrated.transform_calls})
        # No fragile wall-time assertion: the output and skipped transform prove
        # delivery of this signal; elapsed is retained as a measurement only.
        self.assertEqual(action, D.legal_pass(OBS))
        self.assertEqual(guard.diagnostics["status"], "deadline_fallback")
        self.assertEqual(integrated.transform_calls, 0)
        self.assertEqual(integrated.production.calls, 1)
        self.assert_clean()

    def test_transform_exception_handler_cannot_swallow_cancellation(self):
        def body(*_args, **_kwargs):
            try:
                alarm_now()
            except Exception:
                return copy.deepcopy(TRANSFORMED)
        integrated = Integrated(transform=body)
        guard = self.make_guard(integrated)
        self.assertEqual(guard(OBS, {}), SELECTED)
        self.assertEqual(guard.diagnostics["fallback_stage"], "transform")
        self.assertEqual((integrated.production.calls, integrated.transform_calls), (1, 1))
        self.assert_clean()

    def test_before_transform_exception_handler_cannot_swallow_cancellation(self):
        swallowed = []
        def callback(*_args):
            try:
                alarm_now()
            except Exception:
                swallowed.append(True)
        integrated = Integrated()
        guard = self.make_guard(integrated, before_transform=callback)
        self.assertEqual(guard(OBS, {}), SELECTED)
        self.assertEqual(swallowed, [])
        self.assertEqual(integrated.transform_calls, 0)
        self.assertEqual(integrated.production.calls, 1)
        self.assert_clean()

    def test_normal_production_and_transform_remain_unchanged(self):
        obs = copy.deepcopy(OBS)
        integrated = Integrated()
        guard = self.make_guard(integrated)
        self.assertEqual(guard(obs, {}), TRANSFORMED)
        self.assertEqual(obs, OBS)
        self.assertEqual(guard.diagnostics["status"], "completed")
        self.assertEqual(integrated.production.errands["test-errand"]["units_incremental"], 3)
        self.assertEqual((integrated.production.calls, integrated.transform_calls), (1, 1))
        self.assert_clean()

    def test_ordinary_at_risk_error_remains_recoverable(self):
        def ordinary_error():
            raise ValueError("existing recoverable metadata failure")
        integrated = Integrated(Production(ordinary_error))
        guard = self.make_guard(integrated)
        self.assertEqual(guard(OBS, {}), TRANSFORMED)
        self.assertEqual(integrated.production.errands["test-errand"]["units_incremental"], 0)
        self.assertEqual(guard.diagnostics["status"], "completed")
        self.assertEqual((integrated.production.calls, integrated.transform_calls), (1, 1))
        self.assert_clean()

    def test_ordinary_transform_failure_propagates_without_retry(self):
        error = RuntimeError("original transform failure")
        def broken(*_args, **_kwargs):
            raise error
        integrated = Integrated(transform=broken)
        with self.assertRaises(RuntimeError) as got:
            self.make_guard(integrated)(OBS, {})
        self.assertIs(got.exception, error)
        self.assertEqual((integrated.production.calls, integrated.transform_calls), (1, 1))
        self.assert_clean()

    def test_ordinary_production_typeerror_propagates_without_retry(self):
        error = TypeError("original producer failure")
        class Broken:
            calls = 0
            def act(self, _obs):
                self.calls += 1
                raise error
        integrated = Integrated(Broken())
        with self.assertRaises(TypeError) as got:
            self.make_guard(integrated)(OBS, {})
        self.assertIs(got.exception, error)
        self.assertEqual((integrated.production.calls, integrated.transform_calls), (1, 0))
        self.assert_clean()

    def test_keyboard_interrupt_is_not_a_deadline(self):
        error = KeyboardInterrupt("test interruption")
        def interrupted(*_args, **_kwargs):
            raise error
        integrated = Integrated(transform=interrupted)
        with self.assertRaises(KeyboardInterrupt) as got:
            self.make_guard(integrated)(OBS, {})
        self.assertIs(got.exception, error)
        self.assert_clean()

    def test_system_exit_is_not_a_deadline(self):
        error = SystemExit(7)
        def exiting(*_args, **_kwargs):
            raise error
        integrated = Integrated(transform=exiting)
        with self.assertRaises(SystemExit) as got:
            self.make_guard(integrated)(OBS, {})
        self.assertIs(got.exception, error)
        self.assert_clean()

    def test_selected_fallback_keeps_copy_before_callback_mutation(self):
        def callback(_obs, _cfg, selected):
            selected["market"][0][2] = 999
            alarm_now()
        integrated = Integrated()
        guard = self.make_guard(integrated, before_transform=callback)
        self.assertEqual(guard(OBS, {}), SELECTED)
        self.assertEqual(integrated.transform_calls, 0)
        self.assertEqual(integrated.production.calls, 1)
        self.assert_clean()

    def test_next_invocation_after_cancellation_is_not_a_retry(self):
        production = Production(alarm_now)
        integrated = Integrated(production)
        guard = self.make_guard(integrated)
        first = guard(OBS, {})
        production.risk = lambda: 2
        second = guard(OBS, {})
        self.assertEqual(first, D.legal_pass(OBS))
        self.assertEqual(second, TRANSFORMED)
        self.assertEqual((production.calls, integrated.transform_calls), (2, 1))
        self.assertEqual(guard.diagnostics["status"], "completed")
        self.assert_clean()

    def test_terminal_cancellation_keeps_existing_liquidation_fallback_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                farm = {"tiles": [[None] * 10 for _ in range(10)],
                        "farmer": [4, 4], "hands": [[0, 0]]}
                obs = {"player": seat, "step": 718, "day": 29, "hour": 22,
                       "farms": [copy.deepcopy(farm), copy.deepcopy(farm)],
                       "private": {"shed": {"MILK": 90, "WOOL": 5},
                                   "inventories": [{"MILK": 10}, {"WOOL": 9}]}}
                integrated = Integrated(Production(alarm_now))
                guard = self.make_guard(integrated)
                self.assertEqual(guard(obs, {}), {"farmer": ["DROP"], "hands": [["PASS"]],
                    "market": [["SELL", "MILK", 95], ["SELL", "WOOL", 5]]})
                self.assertEqual((integrated.production.calls, integrated.transform_calls), (1, 0))
                self.assertEqual(guard.diagnostics["fallback_stage"], "production")
                self.assert_clean()

    def test_timeout_type_bypasses_only_ordinary_exception_handling(self):
        self.assertTrue(issubclass(D.DeadlineExceeded, BaseException))
        self.assertFalse(issubclass(D.DeadlineExceeded, Exception))
        with self.assertRaises(D.DeadlineExceeded):
            alarm_now()

    def test_existing_custom_signal_handler_is_restored(self):
        def prior_handler(*_args):
            raise AssertionError("prior handler must not execute in this test")
        signal.signal(signal.SIGALRM, prior_handler)
        integrated = Integrated(Production(alarm_now))
        guard = self.make_guard(integrated)
        guard(OBS, {})
        self.assertIs(signal.getsignal(signal.SIGALRM), prior_handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))


def upstream_guard_suite():
    """Run only the three unchanged adapter methods, not the unrelated runner."""
    text = (HERE.parent / "test_runner.py").read_text()
    root = ast.parse(text)
    cls = next(node for node in root.body if isinstance(node, ast.ClassDef))
    names = {"test_transform_timeout_returns_exact_selected_action",
             "test_production_timeout_returns_legal_pass_for_all_workers",
             "test_terminal_fallback_places_visible_cargo_then_sells_post_unit_shed"}
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(cls.body) == 3
    namespace = {"unittest": unittest, "copy": copy, "time": time, "D": D,
                 "__name__": "unchanged_upstream_guard_tests"}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), "upstream/test_runner.py", "exec"), namespace)
    return unittest.defaultTestLoader.loadTestsFromTestCase(namespace["RunnerTests"])


def main():
    global D
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, default=HERE.parent / "deadline_adapter.py")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.adapter.is_file():
        parser.error(f"Adapter not found: {args.adapter}")
    D = load_module("deadline_under_test", args.adapter)
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(CancellationTests),
                               upstream_guard_suite()])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"adapter": str(args.adapter.resolve()),
              "adapter_sha256": hashlib.sha256(args.adapter.read_bytes()).hexdigest(),
              "python": platform.python_version(), "platform": platform.platform(),
              "tests_run": result.testsRun,
              "new_regression_methods": 15, "unchanged_upstream_guard_methods": 3,
              "failures": [{"test": t.id(), "traceback": tb} for t, tb in result.failures],
              "errors": [{"test": t.id(), "traceback": tb} for t, tb in result.errors],
              "skipped": [{"test": t.id(), "reason": why} for t, why in result.skipped],
              "measurements": MEASUREMENTS,
              "scope": "Synthetic boundary tests plus unchanged actual _commit excerpt; no full games"}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
