# SPDX-License-Identifier: Apache-2.0
"""Candidate-bound exact-slot and retry contracts for P02."""
from copy import deepcopy
import unittest

from land_unlock_runtime_strict import LandUnlockOverlay
from test_land_unlock_runtime import Analyzer, Cert, agent, obs, row


class StrictOverlayTests(unittest.TestCase):
    def test_confirmed_advance_never_suppresses_a_different_slot(self):
        route = [row() for _ in range(110)]
        route[100] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(
            analyzer=Analyzer([Cert(100, 99)]), mechanics=object(), decision_steps=())
        subject = agent(route)
        overlay.apply(subject, obs(99), {}, row())
        overlay.apply(subject, obs(100, unlocked=2), {}, row([["BUY_LAND"]]))
        moved = row([["SELL", "WHEAT", 1], ["BUY_LAND"]])
        result, report = overlay.apply(subject, obs(100, unlocked=2), {}, moved)
        self.assertEqual(report["reason"], "same_step_action_changed")
        self.assertEqual(result, moved)
        self.assertIsNone(overlay.pending)

    def test_suppression_requires_the_certified_slot_on_first_original_call(self):
        route = [row() for _ in range(110)]
        route[100] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(
            analyzer=Analyzer([Cert(100, 99)]), mechanics=object(), decision_steps=())
        subject = agent(route)
        overlay.apply(subject, obs(99), {}, row())
        moved = row([["SELL", "WHEAT", 1], ["BUY_LAND"]])
        result, report = overlay.apply(subject, obs(100, unlocked=2), {}, moved)
        self.assertEqual(report["reason"], "suppression_declined")
        self.assertEqual(report["decline_reason"], "slot_mismatch")
        self.assertEqual(result, moved)
        self.assertIsNone(overlay.pending)

    def test_initial_deferral_rolls_back_when_selected_slot_moved(self):
        route = [row() for _ in range(110)]
        route[95] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(
            analyzer=Analyzer([Cert(95, 99)]), mechanics=object(), decision_steps=())
        moved = row([["SELL", "WHEAT", 1], ["BUY_LAND"]])
        result, report = overlay.apply(agent(route), obs(95), {}, moved)
        self.assertEqual(report["reason"], "deferral_declined")
        self.assertEqual(report["decline_reason"], "slot_mismatch")
        self.assertEqual(result, moved)
        self.assertIsNone(overlay.pending)

    def test_same_step_deferral_replay_with_slot_drift_is_declined(self):
        route = [row() for _ in range(110)]
        route[95] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(
            analyzer=Analyzer([Cert(95, 99)]), mechanics=object(), decision_steps=())
        subject = agent(route)
        original = row([["BUY_LAND"]])
        first, first_report = overlay.apply(subject, obs(95), {}, original)
        self.assertEqual(first_report["reason"], "original_deferred")
        self.assertEqual(first["market"], [[]])
        moved = row([["SELL", "WHEAT", 1], ["BUY_LAND"]])
        result, report = overlay.apply(subject, obs(95), {}, moved)
        self.assertEqual(report["reason"], "deferral_declined")
        self.assertEqual(report["decline_reason"], "slot_mismatch")
        self.assertEqual(report["slots"], [1])
        self.assertEqual(report["expected_slot"], 0)
        self.assertEqual(result, moved)
        self.assertIsNone(overlay.pending)

    def test_same_step_suppression_retry_is_byte_equivalent(self):
        route = [row() for _ in range(110)]
        route[100] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(
            analyzer=Analyzer([Cert(100, 99)]), mechanics=object(), decision_steps=())
        subject = agent(route)
        overlay.apply(subject, obs(99), {}, row())
        original = row([["BUY_LAND"]])
        first, first_report = overlay.apply(subject, obs(100, unlocked=2), {}, original)
        second, second_report = overlay.apply(subject, obs(100, unlocked=2), {}, original)
        self.assertEqual(first, second)
        self.assertEqual(first_report, second_report)
        self.assertEqual(first["market"], [[]])

    def test_same_step_changed_input_fails_closed_and_clears_pending(self):
        route = [row() for _ in range(110)]
        route[100] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(
            analyzer=Analyzer([Cert(100, 99)]), mechanics=object(), decision_steps=())
        subject = agent(route)
        overlay.apply(subject, obs(99), {}, row())
        changed = row([["SELL", "WHEAT", 1]])
        result, report = overlay.apply(subject, obs(99), {}, changed)
        self.assertEqual(report["reason"], "same_step_action_changed")
        self.assertEqual(result, changed)
        self.assertIsNone(overlay.pending)


if __name__ == "__main__":
    unittest.main()
