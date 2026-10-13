# SPDX-License-Identifier: Apache-2.0
"""F2 future-cash proof needs the whole actionable day, not a tape prefix.

These isolate the cash-coverage proof with a router-shaped fixture. They do not
claim to run the official interpreter or establish F2 economic performance.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_feed_prebuy as lane


def _pass_action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def _router(step=39, length=719):
    state = SimpleNamespace(last_step=step, plan=0, queues={},
                            v217_used=0, v217_task=None)
    tape = [_pass_action() for _ in range(length)]
    return SimpleNamespace(
        LAST_STEP=718, MAX_ORDERS=10, SHED_CAPACITY=100,
        _POLICY=SimpleNamespace(players={0: state}, tapes=[tape]))


def _observation(step=39):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[4][6] = {"animal": "GOOSE", "fed_today": False,
                   "consecutive_unfed": 1}
    return {
        "step": step, "player": 0,
        "farms": [{"money": 5000.0, "farmer": [4, 4], "hands": [],
                   "tiles": tiles}],
        "private": {"shed": {"WHEAT": 0}, "inventories": [{}]},
        "market": {"prices": {"WHEAT": 30, "EGG": 100},
                   "inventory": {"WHEAT": 10000}},
    }


CONFIG = {"episodeSteps": 720, "boardSize": 10, "turnsPerDay": 24,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
          "marketParams": {}}


class FeedPrebuyDayCoverageTests(unittest.TestCase):
    def setUp(self):
        self.report = dict(lane.REPORT)

    def tearDown(self):
        lane.REPORT.clear()
        lane.REPORT.update(self.report)

    def test_each_day_requires_every_remaining_actionable_row(self):
        for day in range(30):
            step = 24 * day + 15
            stop = min((day + 1) * 24, 719)
            for length in (step + 1, step + 2, stop - 1):
                with self.subTest(day=day, length=length):
                    router = _router(step, length)
                    self.assertFalse(lane._remaining_day_cash_spend_free(
                        _observation(step), router))

    def test_exact_day_coverage_is_sufficient_without_next_day(self):
        for day in range(30):
            step = 24 * day + 15
            stop = min((day + 1) * 24, 719)
            with self.subTest(day=day):
                self.assertTrue(lane._remaining_day_cash_spend_free(
                    _observation(step), _router(step, stop)))

    def test_final_partial_day_requires_718_but_not_719(self):
        obs = _observation(711)
        self.assertFalse(lane._remaining_day_cash_spend_free(obs, _router(711, 718)))
        self.assertTrue(lane._remaining_day_cash_spend_free(obs, _router(711, 719)))

    def test_final_actionable_purchase_is_still_included(self):
        for step, final in ((39, 47), (711, 718)):
            with self.subTest(step=step):
                router = _router(step)
                router._POLICY.tapes[0][final]["market"] = [["BUY_LAND"]]
                self.assertFalse(lane._remaining_day_cash_spend_free(
                    _observation(step), router))

    def test_next_day_purchase_is_not_in_the_proof_window(self):
        router = _router()
        router._POLICY.tapes[0][48]["market"] = [["BUY_LAND"]]
        self.assertTrue(lane._remaining_day_cash_spend_free(_observation(), router))

    def test_negative_hour15_steps_do_not_index_the_tape_tail(self):
        for step in (-9, -33, -705):
            with self.subTest(step=step):
                self.assertFalse(lane._remaining_day_cash_spend_free(
                    _observation(step), _router(step)))

    def test_out_of_episode_and_noninteger_steps_fail_closed(self):
        for step in (719, 735, 10**1000 + 15, True, 39.0, "39", None):
            with self.subTest(step_type=type(step).__name__):
                self.assertFalse(lane._remaining_day_cash_spend_free(
                    _observation(step), _router(step)))

    def test_unproven_router_horizon_cannot_shorten_the_day(self):
        for last_step in (40, 47, True, 718.0, "718", None):
            with self.subTest(last_step=last_step):
                router = _router()
                router.LAST_STEP = last_step
                self.assertFalse(lane._remaining_day_cash_spend_free(
                    _observation(), router))

    def test_executable_prefix_and_sell_semantics_are_preserved(self):
        router = _router()
        router._POLICY.tapes[0][47]["market"] = (
            [["SELL", "CARROT", 1] for _ in range(10)] + [["BUY_LAND"]])
        self.assertTrue(lane._remaining_day_cash_spend_free(_observation(), router))
        router._POLICY.tapes[0][47]["market"][9] = ["BUY_LAND"]
        self.assertFalse(lane._remaining_day_cash_spend_free(_observation(), router))

    def test_incomplete_day_declines_before_counterfactual_planner(self):
        obs, action, router = _observation(), _pass_action(), _router(length=41)
        before = copy.deepcopy((obs, action, vars(router._POLICY)))
        with patch.object(lane, "_next_v217_task") as planner:
            self.assertIsNone(lane._purchase_quantity(obs, action, CONFIG, router))
            planner.assert_not_called()
        self.assertEqual((obs, action, vars(router._POLICY)), before)

    def test_enabled_incomplete_day_returns_exact_parent(self):
        obs, action, router = _observation(), _pass_action(), _router(length=47)
        with patch.dict(sys.modules, {"r04_full_router": router}), \
                patch.object(lane, "_next_v217_task") as planner:
            self.assertIs(lane.apply_feed_prebuy(obs, action, CONFIG, True), action)
            planner.assert_not_called()

    def test_disabled_path_remains_exact_identity(self):
        action = _pass_action()
        with patch.object(lane, "_purchase_quantity") as quantity:
            self.assertIs(lane.apply_feed_prebuy(None, action, None, False), action)
            quantity.assert_not_called()

    def test_full_coverage_still_reaches_existing_purchase_decision(self):
        obs, action, router = _observation(), _pass_action(), _router(length=48)
        before = copy.deepcopy((obs, action))
        def task(observation, parent, quantity, module):
            return {"target": [6, 4]} if quantity == 2 else None
        with patch.object(lane, "_next_v217_task", side_effect=task) as planner:
            self.assertEqual(lane._purchase_quantity(obs, action, CONFIG, router), 2)
            self.assertEqual(planner.call_count, 3)
        self.assertEqual((obs, action), before)


if __name__ == "__main__":
    unittest.main()
