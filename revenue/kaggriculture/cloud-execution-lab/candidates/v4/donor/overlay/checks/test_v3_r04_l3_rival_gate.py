# SPDX-License-Identifier: Apache-2.0
"""Fail-closed contracts for the public-opening L3 rival gate.

A complete, contiguous, strictly typed public opening may certify OFF_TAPE. Anything
ambiguous preserves incumbent E184 (equivalent to treating the rival as on-tape).
Standard library only. Fixtures model Kaggle's recursive Struct(dict) transport.
"""
from __future__ import annotations

import copy
import unittest
from pathlib import Path
import sys

V3_ROOT = Path(__file__).resolve().parents[2]
OVERLAY = V3_ROOT / "overlay"
if str(OVERLAY) not in sys.path:
    sys.path.insert(0, str(OVERLAY))

import r04_full_router as r04  # noqa: E402
import r04_no_late_sale_advance as nla  # noqa: E402


class Struct(dict):
    """Minimal stdlib facsimile of kaggle_environments.utils.Struct."""

    __getattr__ = dict.__getitem__


def structify(value):
    if isinstance(value, dict):
        return Struct({key: structify(item) for key, item in value.items()})
    if isinstance(value, list):
        return [structify(item) for item in value]
    return value


def observation(step, ours=(4, 4), theirs=(4, 4), player=0):
    farm = {"tiles": [], "farmer": list(ours), "hands": []}
    rival = copy.deepcopy(farm)
    rival["farmer"] = list(theirs)
    farms = [farm, rival] if player == 0 else [rival, farm]
    return structify({"step": step, "player": player, "farms": farms})


def play_complete(match_steps, player=0):
    """Feed the exact 0..143 opening and return the frozen decision at step 143."""
    result = True
    for step in range(0, 144):
        same = step == 0 or step in match_steps
        result = r04.rival_on_tape(
            observation(step, theirs=(4, 4) if same else (9, 9), player=player), step
        )
    return result


class RivalGate(unittest.TestCase):
    def setUp(self):
        r04._reset_rival_tape()

    def test_complete_on_tape_opening_is_on_tape(self):
        self.assertTrue(play_complete(set(range(1, 144))))
        self.assertEqual(r04._RIVAL_TAPE["seen"], r04.RIVAL_GATE_REQUIRED_SEEN)

    def test_complete_off_tape_opening_is_off_tape(self):
        matches = {step for step in range(1, 144) if step % 3 == 0}
        self.assertFalse(play_complete(matches))
        self.assertFalse(r04._RIVAL_TAPE["decision"])

    def test_complete_window_threshold_edge_only(self):
        self.assertTrue(play_complete(set(range(1, 116))))  # 115/143 >= .8
        r04._reset_rival_tape()
        self.assertFalse(play_complete(set(range(1, 115))))  # 114/143 < .8

    def test_partial_divergent_evidence_cannot_certify_off_tape(self):
        self.assertTrue(r04.rival_on_tape(observation(0), 0))
        for step in range(1, 101):
            self.assertTrue(r04.rival_on_tape(observation(step, theirs=(9, 9)), step))
        self.assertIsNone(r04._RIVAL_TAPE["decision"])
        self.assertTrue(r04.rival_on_tape(observation(650, theirs=(9, 9)), 650))

    def test_single_divergent_sample_cannot_certify_off_tape(self):
        self.assertTrue(r04.rival_on_tape(observation(1, theirs=(9, 9)), 1))
        self.assertEqual(r04._RIVAL_TAPE["seen"], 1)
        self.assertIsNone(r04._RIVAL_TAPE["decision"])

    def test_malformed_coordinate_invalidates_opening_fail_closed(self):
        r04.rival_on_tape(observation(0), 0)
        result = True
        for step in range(1, 144):
            obs = observation(step, theirs=(9, 9))
            if step == 50:
                obs["farms"][1]["farmer"] = [True, 9]
            result = r04.rival_on_tape(obs, step)
        self.assertTrue(result)
        self.assertFalse(r04._RIVAL_TAPE["valid"])
        self.assertIsNone(r04._RIVAL_TAPE["decision"])

    def test_player_type_poison_fails_closed(self):
        for poisoned in (True, 0.0, "0", None):
            with self.subTest(player=poisoned):
                r04._reset_rival_tape()
                obs = observation(1)
                obs["player"] = poisoned
                self.assertTrue(r04.rival_on_tape(obs, 1))
                self.assertFalse(r04._RIVAL_TAPE["valid"])

    def test_coordinate_type_poison_fails_closed(self):
        for poisoned in (True, 4.0, "4", None):
            with self.subTest(coordinate=poisoned):
                r04._reset_rival_tape()
                obs = observation(1)
                obs["farms"][1]["farmer"] = [poisoned, 4]
                self.assertTrue(r04.rival_on_tape(obs, 1))
                self.assertFalse(r04._RIVAL_TAPE["valid"])

    def test_wrong_farm_cardinality_fails_closed(self):
        obs = observation(1)
        obs["farms"] = obs["farms"][:1]
        self.assertTrue(r04.rival_on_tape(obs, 1))
        self.assertFalse(r04._RIVAL_TAPE["valid"])

    def test_gap_invalidates_opening(self):
        self.assertTrue(r04.rival_on_tape(observation(0), 0))
        self.assertTrue(r04.rival_on_tape(observation(1, theirs=(9, 9)), 1))
        self.assertTrue(r04.rival_on_tape(observation(3, theirs=(9, 9)), 3))
        for step in range(4, 144):
            result = r04.rival_on_tape(observation(step, theirs=(9, 9)), step)
        self.assertTrue(result)
        self.assertIsNone(r04._RIVAL_TAPE["decision"])

    def test_rewind_to_new_game_rebuilds_evidence(self):
        for step in range(0, 20):
            r04.rival_on_tape(observation(step), step)
        matches = {step for step in range(1, 144) if step % 3 == 0}
        self.assertFalse(play_complete(matches))

    def test_complete_decision_is_frozen_after_opening(self):
        matches = {step for step in range(1, 144) if step % 3 == 0}
        self.assertFalse(play_complete(matches))
        self.assertFalse(r04.rival_on_tape(observation(650), 650))

    def test_seat_one_reads_the_other_farm(self):
        self.assertTrue(play_complete(set(range(1, 144)), player=1))


class CallSite(unittest.TestCase):
    """L3 may suppress E184 only after a complete OFF_TAPE public opening."""

    def setUp(self):
        self.calls = []
        self.parent_action = {"farmer": ["PASS"], "hands": [], "market": []}
        self.saved = (
            r04.reserve_sales,
            r04._SALE_PARENT,
            r04._POLICY,
            r04.NO_LATE_SALE_ADVANCE,
            r04.FarmView,
        )
        r04.reserve_sales = lambda *args: self.calls.append(args[-1])
        r04._SALE_PARENT = lambda obs, cfg=None: self.parent_action
        state0 = type("State", (), {"plan": 0})()
        state1 = type("State", (), {"plan": 0})()
        r04._POLICY = type(
            "Policy", (), {"players": {0: state0, 1: state1}, "tapes": {0: []}}
        )()
        r04.NO_LATE_SALE_ADVANCE = True
        r04.FarmView = lambda obs: None
        r04._reset_rival_tape()

    def tearDown(self):
        (
            r04.reserve_sales,
            r04._SALE_PARENT,
            r04._POLICY,
            r04.NO_LATE_SALE_ADVANCE,
            r04.FarmView,
        ) = self.saved
        r04._reset_rival_tape()
        nla.reset()

    def run_game(self, match_steps):
        play_complete(match_steps)
        r04.agent(observation(650), None)

    def test_complete_on_tape_rival_keeps_reservation(self):
        self.run_game(set(range(1, 144)))
        self.assertEqual(self.calls, [650])

    def test_complete_off_tape_rival_gets_l3(self):
        matches = {step for step in range(1, 144) if step % 3 == 0}
        self.run_game(matches)
        self.assertEqual(self.calls, [])

    def test_incomplete_opening_keeps_incumbent_reservation(self):
        for step in range(0, 20):
            r04.rival_on_tape(observation(step, theirs=(9, 9)), step)
        r04.agent(observation(650, theirs=(9, 9)), None)
        self.assertEqual(self.calls, [650])

    def test_malformed_step_or_player_returns_exact_parent_action(self):
        for key, value in (("step", "650"), ("step", True), ("player", "0"), ("player", False)):
            with self.subTest(key=key, value=value):
                self.calls.clear()
                obs = observation(650)
                obs[key] = value
                result = r04.agent(obs, None)
                self.assertIs(result, self.parent_action)
                self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
