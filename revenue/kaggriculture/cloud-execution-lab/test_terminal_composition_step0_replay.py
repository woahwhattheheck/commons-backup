# SPDX-License-Identifier: MIT
"""Replay/reset contract for the canonical terminal-composition entrypoint."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
TARGET = HERE / "reference" / "titan-current" / "terminal_composition.py"
MODULE_NAME = "_test_terminal_composition_step0_replay"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, TARGET)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"unable to load {TARGET}")
terminal_composition = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = terminal_composition
SPEC.loader.exec_module(terminal_composition)


class _StubTerminalSell:
    def __init__(self, token="stub"):
        self.token = token
        self.calls = []

    def act(self, observation, configuration=None):
        self.calls.append((dict(observation), dict(configuration or {})))
        return {"token": self.token, "calls": len(self.calls)}


class _FailingTerminalSell(_StubTerminalSell):
    def act(self, observation, configuration=None):
        self.calls.append((dict(observation), dict(configuration or {})))
        raise RuntimeError("injected reset failure")


class TerminalCompositionReplayTests(unittest.TestCase):
    def setUp(self):
        terminal_composition._INSTANCE = None
        terminal_composition._LAST_STEP = None

    def tearDown(self):
        terminal_composition._INSTANCE = None
        terminal_composition._LAST_STEP = None

    def test_equal_step_reuses_instance_and_strict_rewind_rebuilds(self):
        created = []

        def make_stub():
            stub = _StubTerminalSell(f"terminal-{len(created)}")
            created.append(stub)
            return stub

        with patch.object(terminal_composition, "TerminalSell", side_effect=make_stub) as factory:
            first = terminal_composition.agent({"step": 0}, {})
            replay = terminal_composition.agent({"step": 0}, {})
            forward = terminal_composition.agent({"step": 4}, {})
            same = terminal_composition.agent({"step": 4}, {})
            rewind = terminal_composition.agent({"step": 3}, {})

        self.assertEqual(factory.call_count, 2)
        self.assertEqual(
            [first["token"], replay["token"], forward["token"], same["token"]],
            ["terminal-0"] * 4,
        )
        self.assertEqual(rewind["token"], "terminal-1")
        self.assertEqual([len(instance.calls) for instance in created], [4, 1])
        self.assertEqual(terminal_composition._LAST_STEP, 3)

    def test_public_step_is_exact_before_wrapper_state_changes(self):
        old = _StubTerminalSell("old")
        terminal_composition._INSTANCE = old
        terminal_composition._LAST_STEP = 5

        rejected = [
            {},
            {"step": None},
            {"step": True},
            {"step": "4"},
            {"step": 4.0},
            {"step": -1},
        ]
        with patch.object(terminal_composition, "TerminalSell") as factory:
            for observation in rejected:
                with self.subTest(observation=observation):
                    with self.assertRaises((TypeError, ValueError)):
                        terminal_composition.agent(observation, {})
                    self.assertIs(terminal_composition._INSTANCE, old)
                    self.assertEqual(terminal_composition._LAST_STEP, 5)
                    self.assertEqual(old.calls, [])
                    factory.assert_not_called()

        self.assertEqual(
            terminal_composition.agent({"step": 5}, {}),
            {"token": "old", "calls": 1},
        )
        self.assertIs(terminal_composition._INSTANCE, old)
        self.assertEqual(terminal_composition._LAST_STEP, 5)

    def test_failed_cold_start_publishes_nothing_and_retry_builds_fresh(self):
        failed = _FailingTerminalSell("failed-cold-start")
        retry = _StubTerminalSell("retry-cold-start")
        created = []

        def make_cold_start():
            instance = failed if not created else retry
            created.append(instance)
            return instance

        with patch.object(terminal_composition, "TerminalSell", side_effect=make_cold_start) as factory:
            with self.assertRaisesRegex(RuntimeError, "injected reset failure"):
                terminal_composition.agent({"step": 0}, {})
            self.assertIsNone(terminal_composition._INSTANCE)
            self.assertIsNone(terminal_composition._LAST_STEP)

            recovered = terminal_composition.agent({"step": 0}, {})

        self.assertEqual(factory.call_count, 2)
        self.assertIs(terminal_composition._INSTANCE, retry)
        self.assertEqual(terminal_composition._LAST_STEP, 0)
        self.assertEqual(recovered["token"], "retry-cold-start")
        self.assertEqual(len(failed.calls), 1)
        self.assertEqual(len(retry.calls), 1)

    def test_failed_rewind_keeps_committed_instance_and_retry_rebuilds_again(self):
        old = _StubTerminalSell("old")
        failed = _FailingTerminalSell("failed-reset")
        retry = _StubTerminalSell("retry-reset")
        terminal_composition._INSTANCE = old
        terminal_composition._LAST_STEP = 5
        created = []

        def make_reset():
            instance = failed if not created else retry
            created.append(instance)
            return instance

        with patch.object(terminal_composition, "TerminalSell", side_effect=make_reset) as factory:
            with self.assertRaisesRegex(RuntimeError, "injected reset failure"):
                terminal_composition.agent({"step": 0}, {})
            self.assertIs(terminal_composition._INSTANCE, old)
            self.assertEqual(terminal_composition._LAST_STEP, 5)

            recovered = terminal_composition.agent({"step": 0}, {})

        self.assertEqual(factory.call_count, 2)
        self.assertIs(terminal_composition._INSTANCE, retry)
        self.assertEqual(terminal_composition._LAST_STEP, 0)
        self.assertEqual(recovered["token"], "retry-reset")
        self.assertEqual(len(failed.calls), 1)
        self.assertEqual(len(retry.calls), 1)


if __name__ == "__main__":
    unittest.main()
