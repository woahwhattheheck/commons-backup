# SPDX-License-Identifier: Apache-2.0
"""Predecessor killers for terminal observation identity coercion."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
MODULE = HERE / "reference" / "titan-current" / "terminal.py"
SPEC = importlib.util.spec_from_file_location("_terminal_identity_under_test", MODULE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load terminal.py")
terminal = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = terminal
SPEC.loader.exec_module(terminal)

PARENT = {"farmer": ["PASS"], "hands": [], "market": []}


class TerminalObservationIdentityTests(unittest.TestCase):
    def assert_invalid_identity(self, observation):
        with self.assertRaises(ValueError):
            terminal.overlay(observation, PARENT, {"turnsPerDay": "invalid-after-identity"})

        planner = terminal.Planner()
        planner.queues = [[['EAST']], [['WEST']]]
        planner.last_step = 717
        planner.player = 1
        before = ([list(map(list, row)) for row in planner.queues],
                  planner.last_step, planner.player)
        with self.assertRaises(ValueError):
            planner.act(observation, PARENT, {"turnsPerDay": "invalid-after-identity"})
        after = ([list(map(list, row)) for row in planner.queues],
                 planner.last_step, planner.player)
        self.assertEqual(after, before, "invalid identity mutated planner state")

    def test_player_is_exact_int_zero_or_one(self):
        for bad in (True, False, 0.0, 1.0, "0", "1", -1, 2, None, [], {}):
            with self.subTest(player=bad):
                self.assert_invalid_identity({"player": bad, "step": 0})
        self.assert_invalid_identity({"step": 0})

    def test_step_is_nonnegative_exact_int(self):
        for bad in (True, False, 0.0, 1.0, "0", "718", -1, None, [], {}):
            with self.subTest(step=bad):
                self.assert_invalid_identity({"player": 0, "step": bad})
        self.assert_invalid_identity({"player": 0})

    def test_both_fields_validate_before_config_and_window_routing(self):
        # Old overlay returned early for step=0 before reading player, while old
        # Planner coerced both values and could clear queues/update last_step.
        for observation in (
            {"player": True, "step": 0},
            {"player": 0, "step": False},
            {"player": "0", "step": "0"},
        ):
            with self.subTest(observation=observation):
                self.assert_invalid_identity(observation)

    def test_exact_valid_identity_preserves_existing_outside_window_semantics(self):
        for player in (0, 1):
            observation = {"player": player, "step": 0}
            self.assertIs(terminal.overlay(observation, PARENT), PARENT)
            planner = terminal.Planner()
            planner.queues = [[['EAST']]]
            planner.last_step = 99
            planner.player = 1 - player
            self.assertIs(planner.act(observation, PARENT), PARENT)
            self.assertIsNone(planner.queues)
            self.assertEqual(planner.last_step, 0)
            # Existing early-return behavior did not update planner.player.
            self.assertEqual(planner.player, 1 - player)


if __name__ == "__main__":
    unittest.main()
