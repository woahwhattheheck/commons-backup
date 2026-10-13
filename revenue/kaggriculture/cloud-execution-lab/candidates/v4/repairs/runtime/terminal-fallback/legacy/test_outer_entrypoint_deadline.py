#!/usr/bin/env python3
"""Whole-entrypoint deadline contracts for the SOL-TERMINUS candidate.

The parent packet proves the fallback helper directly. These tests force the
real ``main.agent`` context-manager exit to raise after ``instance.act`` has
published a completed selection, which is the predecessor-discriminating outer
finalization window under review.
"""
from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest

CONTROL = Path(os.environ["TITAN_TERMINUS_CONTROL"]).resolve()
CANDIDATE = Path(os.environ["TITAN_TERMINUS_CANDIDATE"]).resolve()

RAW_SELECTED = {
    "farmer": ["EAST"],
    "hands": [["PASS"]],
    "market": [["BUY_SEED", "MELON", 1]],
}
VISIBLE_LIQUIDATION = {
    "farmer": ["DROP"],
    "hands": [["PASS"]],
    "market": [["SELL", "WHEAT", 4]],
}
LEGAL_PASS = {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ForcedDeadline(Exception):
    """Synthetic deadline type with identity-sensitive owned sentinels."""


class PublishedInstance:
    def __init__(self, trace: list[str]):
        self.trace = trace
        self.features = types.SimpleNamespace(
            budget_seconds=1.0,
            reserve_seconds=0.0,
            consumer="sol-bulwark",
        )
        self.ready = True
        self.selected = {"stale": True}
        self.diagnostics: dict[str, object] = {}

    def act(self, _observation, _configuration, *, entry_started):
        self.trace.append("act:entered")
        self.selected = copy.deepcopy(RAW_SELECTED)
        self.diagnostics = {
            "status": "completed",
            "producer_receipt": "published-before-outer-expiry",
            "entry_started_seen": entry_started,
        }
        self.trace.append("act:published")
        return copy.deepcopy(self.selected)


class OuterEntrypointDeadlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.control = _load("_bulwark_control_main", CONTROL / "main.py")
        cls.candidate = _load("_bulwark_candidate_main", CANDIDATE / "main.py")

    def _exercise(self, module, step: int, *, foreign: bool = False):
        trace: list[str] = []
        timer_state: dict[str, object] = {}

        def terminal_liquidation(observation, configuration):
            trace.append(f"fallback:terminal:{observation['step']}")
            self.assertEqual(configuration["episodeSteps"], 720)
            return copy.deepcopy(VISIBLE_LIQUIDATION)

        def legal_pass(observation):
            trace.append(f"fallback:legal:{observation['step']}")
            return copy.deepcopy(LEGAL_PASS)

        class ExitDeadlineTimer:
            def __init__(self, seconds: float):
                self.seconds = seconds
                self.expired = ForcedDeadline("owned outer deadline")
                timer_state["timer"] = self
                timer_state["owned"] = self.expired

            def __enter__(self):
                trace.append("timer:enter")
                return self

            def __exit__(self, kind, _error, _traceback):
                trace.append(f"timer:exit:{'none' if kind is None else kind.__name__}")
                raised = (
                    ForcedDeadline("foreign deadline") if foreign else self.expired
                )
                timer_state["raised"] = raised
                raise raised

        deadline = types.SimpleNamespace(
            DeadlineExceeded=ForcedDeadline,
            _DeadlineTimer=ExitDeadlineTimer,
            terminal_liquidation_fallback=terminal_liquidation,
            legal_pass=legal_pass,
        )
        runtime = types.ModuleType("titan_runtime")
        runtime.deadline = deadline

        instance = PublishedInstance(trace)
        module._INSTANCE = instance
        previous_runtime = sys.modules.get("titan_runtime")
        sys.modules["titan_runtime"] = runtime
        result = None
        error = None
        try:
            try:
                result = module.agent(
                    {"step": step},
                    {"episodeSteps": 720, "turnsPerDay": 24},
                )
            except ForcedDeadline as caught:
                error = caught
            retained_instance = module._INSTANCE
        finally:
            module._INSTANCE = None
            if previous_runtime is None:
                sys.modules.pop("titan_runtime", None)
            else:
                sys.modules["titan_runtime"] = previous_runtime
        return types.SimpleNamespace(
            result=result,
            error=error,
            instance=instance,
            retained_instance=retained_instance,
            trace=trace,
            timer=timer_state,
        )

    def _assert_owned_cleanup(self, run) -> None:
        self.assertIsNone(run.error)
        self.assertIsNone(run.retained_instance)
        self.assertFalse(run.instance.ready)
        self.assertEqual(run.instance.diagnostics["status"], "deadline_fallback")
        self.assertEqual(
            run.instance.diagnostics["fallback_stage"], "entrypoint_finalization"
        )
        self.assertIs(run.instance.diagnostics["entrypoint_guard"], True)
        self.assertEqual(
            run.instance.diagnostics["producer_receipt"],
            "published-before-outer-expiry",
        )
        self.assertIs(run.timer["raised"], run.timer["owned"])
        self.assertGreater(run.timer["timer"].seconds, 0.0)

    def test_step_718_real_agent_path_discriminates_predecessor(self) -> None:
        control = self._exercise(self.control, 718)
        candidate = self._exercise(self.candidate, 718)

        self.assertEqual(control.result, RAW_SELECTED)
        self.assertEqual(candidate.result, VISIBLE_LIQUIDATION)
        self.assertNotEqual(candidate.result, RAW_SELECTED)
        self._assert_owned_cleanup(control)
        self._assert_owned_cleanup(candidate)

        self.assertEqual(
            control.trace,
            [
                "fallback:terminal:718",
                "timer:enter",
                "act:entered",
                "act:published",
                "timer:exit:none",
            ],
        )
        self.assertEqual(
            candidate.trace,
            control.trace + ["fallback:terminal:718"],
        )

    def test_step_717_real_agent_path_preserves_selected_fallback(self) -> None:
        control = self._exercise(self.control, 717)
        candidate = self._exercise(self.candidate, 717)

        self.assertEqual(control.result, RAW_SELECTED)
        self.assertEqual(candidate.result, RAW_SELECTED)
        self._assert_owned_cleanup(control)
        self._assert_owned_cleanup(candidate)
        expected_trace = [
            "fallback:legal:717",
            "timer:enter",
            "act:entered",
            "act:published",
            "timer:exit:none",
        ]
        self.assertEqual(control.trace, expected_trace)
        self.assertEqual(candidate.trace, expected_trace)

    def test_foreign_deadline_propagates_without_false_cleanup(self) -> None:
        for label, module in (("control", self.control), ("candidate", self.candidate)):
            with self.subTest(label=label):
                run = self._exercise(module, 718, foreign=True)
                self.assertIs(run.error, run.timer["raised"])
                self.assertIsNot(run.error, run.timer["owned"])
                self.assertIs(run.retained_instance, run.instance)
                self.assertTrue(run.instance.ready)
                self.assertEqual(run.instance.selected, RAW_SELECTED)
                self.assertEqual(run.instance.diagnostics["status"], "completed")
                self.assertNotIn("entrypoint_guard", run.instance.diagnostics)
                self.assertNotIn("fallback_stage", run.instance.diagnostics)


if __name__ == "__main__":
    unittest.main(verbosity=2)
