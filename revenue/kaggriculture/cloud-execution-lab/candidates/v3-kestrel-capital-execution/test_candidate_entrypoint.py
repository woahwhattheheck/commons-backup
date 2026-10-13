# SPDX-License-Identifier: Apache-2.0
"""Real exported-entrypoint contracts for the KESTREL containment carrier."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
ENTRYPOINT = HERE / "candidate_main.py"


def _load_entrypoint_without_candidate_path():
    """Load as an evaluator would, without relying on candidate-dir sys.path."""
    name = "_kestrel_exported_entrypoint_contract"
    for module_name in (
        name,
        "_kestrel_canonical_main",
        "_kestrel_candidate_runtime",
    ):
        sys.modules.pop(module_name, None)

    original_path = list(sys.path)
    here = HERE.resolve()
    sys.path[:] = [
        value for value in sys.path
        if Path(value or ".").resolve() != here
    ]
    absent_before_load = all(
        Path(value or ".").resolve() != here for value in sys.path
    )
    try:
        spec = importlib.util.spec_from_file_location(name, ENTRYPOINT)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {ENTRYPOINT}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        added_during_load = any(
            Path(value or ".").resolve() == here for value in sys.path
        )
    finally:
        sys.path[:] = original_path
    return module, absent_before_load, added_during_load


class _Features:
    def __init__(self, *, budget=0.20, reserve=0.01):
        self.budget_seconds = budget
        self.reserve_seconds = reserve
        self.consumer = "frozen"


class _QuickInstance:
    def __init__(self, action):
        self.features = _Features()
        self.action = deepcopy(action)
        self.selected = None
        self.ready = True
        self.post = None
        self.diagnostics = {}
        self.calls = 0

    def act(self, _observation, _configuration=None, *, entry_started=None):
        self.calls += 1
        self.selected = deepcopy(self.action)
        return deepcopy(self.action)


class _LateInstance(_QuickInstance):
    def __init__(self, action, *, publish_selected=True):
        super().__init__(action)
        self.features = _Features(budget=0.04, reserve=0.015)
        self.publish_selected = publish_selected
        self.diagnostics = {"status": "completed"}

    def act(self, _observation, _configuration=None, *, entry_started=None):
        self.calls += 1
        self.selected = deepcopy(self.action) if self.publish_selected else None
        end = time.perf_counter() + 0.08
        while time.perf_counter() < end:
            pass
        return deepcopy(self.action)


class KestrelExportedEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry, cls.absent_before_load, cls.added_during_load = (
            _load_entrypoint_without_candidate_path()
        )
        import titan_runtime

        cls.titan_runtime = titan_runtime
        cls.candidate_base = cls.entry._CANDIDATE_RUNTIME.KestrelTitanAgent
        cls.predecessor_base = cls.candidate_base.__mro__[1]
        cls.feature_data = json.loads((LAB / "TITAN-CONFIG.json").read_text())

    def setUp(self):
        self.entry._CANONICAL._INSTANCE = None
        self.observation = {
            "step": 100,
            "player": 0,
            "farms": [{"hands": [[4, 4]]}, {"hands": []}],
            "private": {},
        }
        self.configuration = {"episodeSteps": 720}
        self.selected = {
            "farmer": ["PASS"],
            "hands": [["PASS"]],
            "market": [["SELL", "CARROT", 1]],
        }

    def tearDown(self):
        self.entry._CANONICAL._INSTANCE = None
        self.assertIs(self.titan_runtime.TitanAgent, self.predecessor_base)

    def test_evaluator_shape_loads_without_candidate_sys_path(self):
        self.assertTrue(self.absent_before_load)
        self.assertTrue(self.added_during_load)
        self.assertIs(self.entry.agent, self.entry._CANONICAL.agent)
        self.assertIs(
            self.entry.agent.__globals__,
            self.entry._CANONICAL.__dict__,
        )
        self.assertIs(
            self.entry._CANONICAL._new_instance,
            self.entry._new_instance,
        )

    def test_real_factory_builds_exact_final_pressure_kestrel_mro(self):
        instance = self.entry._new_instance(LAB, dict(self.feature_data))
        mro = type(instance).__mro__
        self.assertEqual(type(instance).__name__, "FinalPressureAgent")
        self.assertIs(mro[1], self.candidate_base)
        self.assertIs(mro[2], self.predecessor_base)
        self.assertIs(self.titan_runtime.TitanAgent, self.predecessor_base)

    def test_factory_restores_canonical_base_after_construction_error(self):
        error = RuntimeError("synthetic construction failure")
        with patch.object(
            self.entry,
            "_CANONICAL_NEW_INSTANCE",
            side_effect=error,
        ):
            with self.assertRaises(RuntimeError) as caught:
                self.entry._new_instance(LAB, dict(self.feature_data))
        self.assertIs(caught.exception, error)
        self.assertIs(self.titan_runtime.TitanAgent, self.predecessor_base)

    def test_final_pressure_runs_after_kestrel_exactly_once(self):
        calls = []

        def kestrel_early(instance, _obs, _cfg, selected):
            calls.append("kestrel")
            result = deepcopy(selected)
            result["trace"] = result.get("trace", []) + ["kestrel"]
            return result

        def base_pressure(instance, _obs, _cfg, selected):
            calls.append("pressure")
            result = deepcopy(selected)
            result["trace"] = result.get("trace", []) + ["pressure"]
            return result

        with patch.object(
            self.candidate_base,
            "_early_capital_selected",
            new=kestrel_early,
        ), patch.object(
            self.predecessor_base,
            "_market_pressure_selected",
            new=base_pressure,
        ):
            instance = self.entry._new_instance(LAB, dict(self.feature_data))
            selected = {"trace": []}
            self.assertIs(
                instance._market_pressure_selected({}, {}, selected),
                selected,
            )
            self.assertEqual(calls, [])

            instance.diagnostics = {"status": "completed"}
            result = instance._early_capital_selected({}, {}, selected)
            self.assertEqual(result["trace"], ["kestrel", "pressure"])
            self.assertEqual(calls, ["kestrel", "pressure"])
            self.assertFalse(instance._final_pressure_boundary)

            self.assertIs(
                instance._market_pressure_selected({}, {}, selected),
                selected,
            )
            self.assertEqual(calls, ["kestrel", "pressure"])

    def test_normal_call_uses_canonical_agent_and_retains_instance(self):
        fake = _QuickInstance(self.selected)
        self.entry._CANONICAL._INSTANCE = fake
        output = self.entry.agent(self.observation, self.configuration)
        self.assertEqual(output, self.selected)
        self.assertEqual(fake.calls, 1)
        self.assertIs(self.entry._CANONICAL._INSTANCE, fake)
        self.assertTrue(fake.ready)
        self.assertNotIn("entrypoint_guard", fake.diagnostics)

    def test_outer_deadline_returns_selected_and_destroys_partial_instance(self):
        fake = _LateInstance(self.selected)
        self.entry._CANONICAL._INSTANCE = fake
        started = time.perf_counter()
        output = self.entry.agent(self.observation, self.configuration)
        elapsed = time.perf_counter() - started

        self.assertEqual(output, self.selected)
        self.assertLess(elapsed, 0.5)
        self.assertEqual(fake.calls, 1)
        self.assertFalse(fake.ready)
        self.assertIsNone(self.entry._CANONICAL._INSTANCE)
        self.assertEqual(fake.diagnostics["status"], "deadline_fallback")
        self.assertEqual(
            fake.diagnostics["fallback_stage"],
            "entrypoint_finalization",
        )
        self.assertTrue(fake.diagnostics["entrypoint_guard"])
        self.assertIsNone(self.titan_runtime.deadline._ACTIVE_TIMER.get())

    def test_outer_deadline_clears_stale_selected_before_runtime(self):
        stale = deepcopy(self.selected)
        stale["market"] = [["SELL", "MILK", 99]]
        fake = _LateInstance(self.selected, publish_selected=False)
        fake.selected = stale
        self.entry._CANONICAL._INSTANCE = fake

        output = self.entry.agent(self.observation, self.configuration)
        self.assertEqual(
            output,
            {"farmer": ["PASS"], "hands": [["PASS"]], "market": []},
        )
        self.assertNotEqual(output, stale)
        self.assertIsNone(self.entry._CANONICAL._INSTANCE)
        self.assertFalse(fake.ready)


if __name__ == "__main__":
    unittest.main(verbosity=2)
