# SPDX-License-Identifier: Apache-2.0
"""S1 must prove the entire remaining day before spending parent cash.

These are isolated helper checks, not generated-package or economic gates.
They use the real S1 helper with a deterministic parent/action fixture.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import r04_s1_fert_sweep as lane  # noqa: E402

CONFIG = {
    "episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
    "shedCapacity": 100, "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1,
}


def action():
    return {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}


def tape(length=720):
    return [action() for _ in range(length)]


def observation(day=4, player=0):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    for x, y in ((4, 3), (3, 4), (4, 2)):
        tiles[y][x] = {"animal": "GOOSE", "kind": "COOP", "fertilizer_available": True}
    farm = {"tiles": tiles, "farmer": [4, 4], "hands": [[4, 4]],
            "hires_today": 2, "money": 5000.0}
    return {"step": day * 24 + 14, "player": player,
            "farms": [copy.deepcopy(farm), copy.deepcopy(farm)],
            "private": {"inventories": [{}, {}], "shed": {}},
            "market": {"prices": {"FERTILIZER": 100}}}


class S1DayCoverageTest(unittest.TestCase):
    def setUp(self):
        lane._STATE.clear()
        for key in lane.REPORT:
            lane.REPORT[key] = 0

    def test_all_admission_hours_reject_every_incomplete_current_day_suffix(self):
        authored = tape()
        for day in range(4, 24):
            for hour in range(14, 23):
                step = day * 24 + hour
                end = (day + 1) * 24
                for length in range(step + 1, end):
                    with self.subTest(day=day, hour=hour, length=length):
                        incomplete = authored[:length]
                        self.assertIsNone(lane._rest_of_day(incomplete, step))
                        self.assertTrue(lane._future_conflict(incomplete, step))
                        self.assertTrue(lane._future_wheat_topup_risk(incomplete, step, {}))

    def test_missing_suffix_cannot_hire_or_mutate_either_players_parent(self):
        for player in (0, 1):
            for day in range(4, 24):
                obs = observation(day, player)
                end = (day + 1) * 24
                for length in (obs["step"] + 1, end - 1):
                    with self.subTest(player=player, day=day, length=length):
                        parent = action()
                        before = copy.deepcopy((obs, parent))
                        state = lane._Day(day)
                        result = lane._consider_hire(obs, parent, state, tape(length), CONFIG)
                        self.assertIs(result, parent)
                        self.assertIsNone(state.pending)
                        self.assertFalse(state.tried)
                        self.assertEqual((obs, parent), before)

    def test_exact_day_end_is_sufficient_without_whole_episode_tape(self):
        for player in (0, 1):
            for day in (4, 12, 23):
                with self.subTest(player=player, day=day):
                    obs = observation(day, player)
                    authored = tape((day + 1) * 24)
                    self.assertLess(len(authored), 720)
                    self.assertEqual(len(lane._rest_of_day(authored, obs["step"])), 9)
                    parent = action()
                    result = lane._consider_hire(obs, parent, lane._Day(day), authored, CONFIG)
                    self.assertEqual(result["market"], [["HIRE"]])
                    self.assertEqual(parent["market"], [])

    def test_last_current_day_market_obligation_is_not_clipped(self):
        obs = observation()
        for order in (["HIRE"], ["BUY_PRODUCT", "WHEAT", 1],
                      ["BUY_SEED", "WHEAT", 1], ["BUY_LAND", "NE"]):
            with self.subTest(order=order):
                authored = tape(120)
                authored[119]["market"] = [order]
                parent = action()
                self.assertIs(lane._consider_hire(obs, parent, lane._Day(4), authored, CONFIG), parent)

    def test_last_current_day_farmer_and_hand_wheat_pickups_are_owned(self):
        obs = observation()
        for actor in ("farmer", "hand"):
            with self.subTest(actor=actor):
                authored = tape(120)
                if actor == "farmer":
                    authored[119]["farmer"] = ["PICKUP", "WHEAT", 1]
                else:
                    authored[119]["hands"][0] = ["PICKUP", "WHEAT", 1]
                parent = action()
                self.assertIs(lane._consider_hire(obs, parent, lane._Day(4), authored, CONFIG), parent)

    def test_next_day_cash_and_pickups_do_not_overguard_current_day(self):
        obs = observation()
        authored = tape(121)
        authored[120] = {"market": [["HIRE"], ["BUY_PRODUCT", "WHEAT", 1]],
                         "farmer": ["PICKUP", "WHEAT", 1],
                         "hands": [["PICKUP", "WHEAT", 1]]}
        self.assertFalse(lane._future_conflict(authored, obs["step"]))
        self.assertFalse(lane._future_wheat_topup_risk(authored, obs["step"], obs["farms"][0]))
        result = lane._consider_hire(obs, action(), lane._Day(4), authored, CONFIG)
        self.assertEqual(result["market"], [["HIRE"]])

    def test_bad_tape_or_clock_fails_closed_without_slice_errors(self):
        authored = tape(120)
        for step in (None, True, False, 110.0, "110", -1, 120, 10 ** 1000):
            with self.subTest(step=step):
                self.assertIsNone(lane._rest_of_day(authored, step))
                self.assertTrue(lane._future_conflict(authored, step))
                self.assertTrue(lane._future_wheat_topup_risk(authored, step, {}))
        for invalid in (None, {}, tuple(authored), "tape", []):
            with self.subTest(tape_type=type(invalid).__name__):
                self.assertIsNone(lane._rest_of_day(invalid, 110))

    def test_wrapper_with_incomplete_tape_calls_parent_once_and_preserves_identity(self):
        for player in (0, 1):
            with self.subTest(player=player):
                obs = observation(player=player)
                sentinel = action()
                calls = []
                def parent(o, configuration=None):
                    calls.append(o)
                    return sentinel
                wrapped = lane.wrap(parent, lambda o: tape(o["step"] + 1))
                self.assertIs(wrapped(obs, CONFIG), sentinel)
                self.assertEqual(len(calls), 1)
                self.assertIs(calls[0], obs)
                self.assertIsNone(lane._STATE[player].pending)

    def test_complete_day_evidence_can_recover_on_next_callback(self):
        for player in (0, 1):
            with self.subTest(player=player):
                lane._STATE.clear()
                obs = observation(player=player)
                start = obs["step"]
                authored = tape(120)
                sentinel = action()
                calls = []
                def parent(o, configuration=None):
                    calls.append(o["step"])
                    return sentinel
                wrapped = lane.wrap(parent, lambda o: authored[:start + 1]
                                    if o["step"] == start else authored)
                self.assertIs(wrapped(obs, CONFIG), sentinel)
                state = lane._STATE[player]
                self.assertFalse(state.tried)
                self.assertIsNone(state.pending)
                next_obs = copy.deepcopy(obs)
                next_obs["step"] += 1
                result = wrapped(next_obs, CONFIG)
                self.assertEqual(result["market"], [["HIRE"]])
                self.assertIs(lane._STATE[player], state)
                self.assertTrue(state.tried)
                self.assertEqual(state.pending, len(obs["farms"][player]["hands"]))
                self.assertEqual(calls, [start, start + 1])
                self.assertEqual(sentinel["market"], [])

    def test_missing_tape_does_not_interrupt_owned_middle_hand(self):
        for player in (0, 1):
            with self.subTest(player=player):
                lane._STATE.clear()
                obs = observation(player=player)
                obs["farms"][player]["hands"] = [[4, 4], [4, 3], [3, 4]]
                obs["private"]["inventories"] = [{}, {"WHEAT": 1}, {}, {"FERTILIZER": 2}]
                state = lane._STATE[player] = lane._Day(4)
                state.index, state.tried, state.last_step = 1, True, obs["step"] - 1
                sentinel = {"farmer": ["PASS"], "hands": [["EAST"], ["SOUTH"]], "market": []}
                before = copy.deepcopy((obs, sentinel))
                seen = []
                def parent(o, configuration=None):
                    seen.append(o)
                    return sentinel
                count = lane.REPORT["collections"]
                result = lane.wrap(parent, lambda o: tape(o["step"] + 1))(obs, CONFIG)
                self.assertEqual(len(seen), 1)
                self.assertEqual(seen[0]["farms"][player]["hands"], [[4, 4], [3, 4]])
                self.assertEqual(seen[0]["private"]["inventories"], [{}, {"WHEAT": 1}, {"FERTILIZER": 2}])
                self.assertEqual(result["hands"], [["EAST"], ["COLLECT_FERTILIZER"], ["SOUTH"]])
                self.assertEqual(result["market"], [])
                self.assertEqual(lane.REPORT["collections"], count + 1)
                self.assertEqual(state.index, 1)
                self.assertEqual((obs, sentinel), before)

    def test_failed_hire_does_not_retry_when_tape_coverage_changes(self):
        for player in (0, 1):
            with self.subTest(player=player):
                lane._STATE.clear()
                obs = observation(player=player)
                start = obs["step"]
                sentinel = action()
                calls = []
                def parent(o, configuration=None):
                    calls.append(o["step"])
                    return sentinel
                wrapped = lane.wrap(parent, lambda o: tape(o["step"] + 1)
                                    if o["step"] == start + 1 else tape(120))
                failures = lane.REPORT["hire_failures"]
                self.assertEqual(wrapped(obs, CONFIG)["market"], [["HIRE"]])
                state = lane._STATE[player]
                self.assertEqual(state.pending, 1)
                for offset in (1, 2):
                    followup = copy.deepcopy(obs)  # Same hand count: the HIRE failed.
                    followup["step"] += offset
                    self.assertIs(wrapped(followup, CONFIG), sentinel)
                    self.assertTrue(state.tried)
                    self.assertIsNone(state.pending)
                    self.assertIsNone(state.index)
                self.assertEqual(lane.REPORT["hire_failures"], failures + 1)
                self.assertEqual(calls, [start, start + 1, start + 2])

    def test_all_calendar_boundaries_preserve_complete_day_slices(self):
        authored = tape(721)
        cases = 0
        for day in range(30):
            end = (day + 1) * 24
            for hour in range(24):
                step = day * 24 + hour
                for length in (step, step + 1, end - 1, end, end + 1):
                    with self.subTest(day=day, hour=hour, length=length):
                        remaining = lane._rest_of_day(authored[:length], step)
                        if length < end:
                            self.assertIsNone(remaining)
                        else:
                            self.assertEqual(remaining, authored[step + 1:end])
                        cases += 1
        self.assertEqual(cases, 3600)


if __name__ == "__main__":
    unittest.main()
