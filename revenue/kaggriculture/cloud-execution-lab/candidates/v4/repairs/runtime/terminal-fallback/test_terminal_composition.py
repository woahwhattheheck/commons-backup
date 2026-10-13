# SPDX-License-Identifier: Apache-2.0
"""Four-arm terminal recovery through exact main.agent and real deadline timers.

The producer is deliberately a test double. The entrypoint, signal/worker timer,
liquidation routine, and settlement interpreter are exact production/engine bytes.
This is component composition, not a complete V4 package or a playing-strength test.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import types
import unittest
from unittest.mock import patch

import test_terminal_fallback as slots
from repair_terminal_fallback import git_blob, repair

HERE = Path(__file__).resolve().parent
MAIN_PIN = "4a8cf7bcda1f0fea231a144692cb84a779a9e73e"
DONOR_PIN = "3cbbef93fbb84e6f08aac2713a02dab1dd3a685d"
ARGS = None
ROWS = []


def load_source(name, source, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


class TerminalComposition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        slots.ARGS = types.SimpleNamespace(lab_root=ARGS.lab_root, engine_root=None)
        slots.TerminalFallbackTests.setUpClass()
        cls.fixture = slots.TerminalFallbackTests()
        cls.original_main = ARGS.main_source.read_bytes()
        if git_blob(cls.original_main) != MAIN_PIN:
            raise ValueError("current main.py source drift")
        donor_path = HERE / "legacy/terminal_deadline_patch.py"
        donor_bytes = donor_path.read_bytes()
        if git_blob(donor_bytes) != DONOR_PIN:
            raise ValueError("legacy terminal-precedence donor drift")
        cls.donor = load_source("recovered_precedence", donor_bytes, donor_path)
        cls.fixed_main = cls.donor.patch_main(cls.original_main.decode()).encode()
        cls.main_sources = {False: cls.original_main, True: cls.fixed_main}
        cls.deadlines = {False: cls.fixture.before, True: cls.fixture.after}

    def run_arm(self, *, precedence, raw_slots, seat, worker, step=718,
                crowded=False, stage="finalization", foreign=False, completed=False):
        shed = (self.fixture.crowded_shed() if crowded else
                {"WHEAT": 5, "MILK": 3})
        state, env = self.fixture.fixture(shed, seat=seat,
            inventories=[{}] if crowded else [{"CARROT": 4}])
        obs = state[seat].observation
        obs.update(step=step, day=step // 24, hour=step % 24)
        before = copy.deepcopy(obs)
        deadline = self.deadlines[raw_slots]
        module = load_source("composition_main", self.main_sources[precedence], ARGS.main_source)
        selected = {"farmer": ["PASS"], "hands": [],
                    "market": [["BUY_SEED", "MELON", 1]]}
        sentinel = deadline.DeadlineExceeded("foreign owner")
        calls = []
        instance = types.SimpleNamespace(
            features=types.SimpleNamespace(budget_seconds=.06, reserve_seconds=.005,
                                           consumer="frozen"),
            selected=None, post=None, ready=True, diagnostics={})

        def act(observation, configuration, *, entry_started):
            calls.append("act")
            if stage == "finalization":
                instance.selected = copy.deepcopy(selected)
                instance.diagnostics = {"status": "completed"}
                calls.append("selected_published")
            if foreign:
                raise sentinel
            if completed:
                return copy.deepcopy(selected)
            while True:
                pass

        instance.act = act
        module._INSTANCE = instance
        shim = types.ModuleType("titan_runtime")
        shim.deadline = deadline

        def invoke():
            trace_before = sys.gettrace()
            context_before = deadline._ACTIVE_TIMER.get()
            try:
                if foreign:
                    with self.assertRaises(deadline.DeadlineExceeded) as caught:
                        module.agent(obs, env.configuration)
                    self.assertIs(caught.exception, sentinel)
                    self.assertIs(module._INSTANCE, instance)
                    self.assertTrue(instance.ready)
                    self.assertNotEqual(instance.diagnostics.get("status"), "deadline_fallback")
                    return None
                result = module.agent(obs, env.configuration)
                if completed:
                    self.assertEqual(result, selected)
                    self.assertIs(module._INSTANCE, instance)
                    self.assertTrue(instance.ready)
                else:
                    self.assertEqual(instance.diagnostics["status"], "deadline_fallback")
                    self.assertEqual(instance.diagnostics["fallback_stage"],
                        "entrypoint_finalization" if stage == "finalization" else "entrypoint_runtime")
                    self.assertIs(instance.diagnostics["entrypoint_guard"], True)
                    self.assertIsNone(module._INSTANCE)
                    self.assertFalse(instance.ready)
                return result
            finally:
                self.assertIs(sys.gettrace(), trace_before)
                self.assertIs(deadline._ACTIVE_TIMER.get(), context_before)

        handler_before = signal.getsignal(signal.SIGALRM)
        with patch.dict(sys.modules, {"titan_runtime": shim}):
            if worker:
                # Real worker trace timer must not touch process-global signals.
                with patch.object(signal, "signal", side_effect=AssertionError("worker signal write")), \
                     patch.object(signal, "setitimer", side_effect=AssertionError("worker timer write")):
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        action = executor.submit(invoke).result(timeout=5)
            else:
                action = invoke()
        self.assertIs(signal.getsignal(signal.SIGALRM), handler_before)
        self.assertEqual(obs, before)
        self.assertEqual(calls.count("act"), 1)
        if stage == "finalization":
            self.assertEqual(calls, ["act", "selected_published"])
        if foreign:
            return None
        expected = (selected if completed or (stage == "finalization" and not (precedence and step == 718))
                    else (deadline.terminal_liquidation_fallback(obs, env.configuration)
                          if step == 718 else deadline.legal_pass(obs)))
        self.assertEqual(action, expected)
        row = dict(precedence=precedence, raw_slots=raw_slots, seat=seat,
                   worker=worker, step=step, crowded=crowded, stage=stage,
                   completed=completed, action=action)
        if step == 718:
            state[seat].action = action
            self.fixture.engine.interpreter(state, env)
            self.assertEqual([s.status for s in state], ["DONE", "DONE"])
            row["terminal_cash"] = state[seat].reward
        ROWS.append(row)
        return row

    def test_four_arm_actual_finalization_timer_and_engine(self):
        for seat in (0, 1):
            for worker in (False, True):
                for crowded in (False, True):
                    result = {}
                    for precedence in (False, True):
                        for raw_slots in (False, True):
                            with self.subTest(seat=seat, worker=worker, crowded=crowded,
                                              precedence=precedence, raw_slots=raw_slots):
                                result[precedence, raw_slots] = self.run_arm(
                                    precedence=precedence, raw_slots=raw_slots, seat=seat,
                                    worker=worker, crowded=crowded)
                    self.assertEqual(result[False, False]["action"], result[False, True]["action"])
                    self.assertGreater(result[True, True]["terminal_cash"], result[False, False]["terminal_cash"])
                    if crowded:
                        self.assertGreater(result[True, True]["terminal_cash"], result[True, False]["terminal_cash"])
                    else:
                        self.assertEqual(result[True, True]["action"], result[True, False]["action"])

    def test_nonterminal_selection_preserved_in_all_arms(self):
        for seat in (0, 1):
            for worker in (False, True):
                for precedence in (False, True):
                    for raw_slots in (False, True):
                        self.run_arm(precedence=precedence, raw_slots=raw_slots,
                                     seat=seat, worker=worker, step=717)

    def test_preselection_timer_keeps_visible_fallback(self):
        for seat in (0, 1):
            for worker in (False, True):
                for step in (717, 718):
                    self.run_arm(precedence=True, raw_slots=True, seat=seat,
                                 worker=worker, step=step, stage="production")

    def test_foreign_sentinel_keeps_identity_and_no_false_cleanup(self):
        for seat in (0, 1):
            for worker in (False, True):
                for precedence in (False, True):
                    self.run_arm(precedence=precedence, raw_slots=True,
                                 seat=seat, worker=worker, foreign=True)

    def test_completed_calls_are_unchanged_in_all_arms(self):
        for seat in (0, 1):
            for worker in (False, True):
                for precedence in (False, True):
                    for raw_slots in (False, True):
                        self.run_arm(precedence=precedence, raw_slots=raw_slots,
                                     seat=seat, worker=worker, completed=True)

    def test_exact_source_and_donor_pins(self):
        self.assertEqual(git_blob(self.original_main), MAIN_PIN)
        self.assertEqual(git_blob(self.fixture.original), slots.EXPECTED_SOURCE)
        self.assertEqual(git_blob(repair(self.fixture.original)), slots.EXPECTED_POSTIMAGE)
        with self.assertRaises(self.donor.CandidateError):
            self.donor.patch_main(self.fixed_main.decode())


def main():
    global ARGS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab-root", required=True, type=Path)
    parser.add_argument("--main-source", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    ARGS = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(TerminalComposition))
    receipt = {"schema": "titan-v4-terminal-composition/v1",
               "main_source_blob": MAIN_PIN, "donor_blob": DONOR_PIN,
               "main_postimage_blob": git_blob(TerminalComposition.fixed_main)
                    if hasattr(TerminalComposition, "fixed_main") else None,
               "deadline_source_blob": slots.EXPECTED_SOURCE,
               "deadline_postimage_blob": slots.EXPECTED_POSTIMAGE,
               "engine_blob": slots.ENGINE_PIN, "python": sys.version.split()[0],
               "optimized": not __debug__, "tests_run": result.testsRun,
               "success": result.wasSuccessful(), "failures": len(result.failures),
               "errors": len(result.errors), "cases": ROWS,
               "boundary": "exact main.agent + real main/worker timer + real engine; producer double; not full current V4"}
    ARGS.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
