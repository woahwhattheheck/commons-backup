# SPDX-License-Identifier: Apache-2.0
"""Standalone M1 repair composition checks; no materializer/runtime required.

Run from donor/overlay with unittest discovery restricted to test_v4_m1_day*.
These are component checks, not a hosted match or economic promotion gate.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / "r04_m1_wheat_trade.py").is_file() and str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import r04_m1_wheat_trade as m1

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10}


def action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def tape(step=101, due=104, end=119):
    result = [action() for _ in range(end + 1)]
    result[due]["farmer"] = ["PICKUP", "WHEAT", 3]
    return result


def observation(step=101, *, player=0, inventory=98, money=5000.0):
    farm = {"farmer": [4, 4], "hands": [], "money": money}
    return {"step": step, "player": player,
            "farms": [copy.deepcopy(farm), copy.deepcopy(farm)],
            "private": {"shed": {}},
            "market": {"prices": {"WHEAT": 20},
                       "inventory": {"WHEAT": inventory}}}


def certificate(route, step=101):
    return m1._future_literal_pickup(route, step, [[4, 4]], [["PASS"]], 10)


class M1DayIntegration(unittest.TestCase):
    def setUp(self):
        m1.reset_for_tests()

    def tearDown(self):
        m1.reset_for_tests()

    def prime(self, *, player=0, parent=None):
        m1.apply_m1_wheat_trade(
            observation(100, player=player, inventory=100),
            action() if parent is None else parent, tape(),
            configuration=CONFIG, enabled=True)

    def run_lane(self, obs=None, parent=None, route=None):
        return m1.apply_m1_wheat_trade(
            observation() if obs is None else obs,
            action() if parent is None else parent,
            tape() if route is None else route,
            configuration=CONFIG, enabled=True)

    def test_every_observed_truncation_fails_closed(self):
        for day in (1, 4, 12, 28):
            end = day * 24 + 23
            route = [action() for _ in range(end + 1)]
            for hour in (0, 5, 16, 19, 20, 21):
                step = day * 24 + hour
                for delta in range(2, 7):
                    due = step + delta
                    if due >= end:
                        continue
                    route[due]["farmer"] = ["PICKUP", "WHEAT", 3]
                    for missing_from in range(due + 1, end + 1):
                        with self.subTest(step=step, due=due, eof=missing_from-1):
                            self.assertEqual(certificate(route[:missing_from], step), (None, 0))
                    self.assertEqual(certificate(route, step), (due, 3))
                    self.assertEqual(certificate(tuple(route), step), (due, 3))
                    route[due]["farmer"] = ["PASS"]

    def test_each_later_same_day_cash_owner_vetoes_in_raw_prefix_only(self):
        for due in range(105, 120):
            for op in ("HIRE", "BUY_LAND", "BUY_PRODUCT", "BUY_ANIMAL", "BUY_SEED"):
                for raw_index in (0, 9, 10):
                    route = tape()
                    route[due]["market"] = [[] for _ in range(raw_index)] + [[op]]
                    expected = (104, 3) if raw_index == 10 else (None, 0)
                    with self.subTest(step=due, op=op, raw_index=raw_index):
                        self.assertEqual(certificate(route), expected)

    def test_next_day_cash_owner_is_not_current_day_evidence(self):
        route = tape(end=120)
        route[120]["market"] = [["HIRE"]]
        self.assertEqual(certificate(route), (104, 3))

    def test_public_entrypoint_buys_for_both_seats_without_mutating_parent(self):
        for player in (0, 1):
            m1.reset_for_tests()
            self.prime(player=player)
            parent = action()
            before = copy.deepcopy(parent)
            out = self.run_lane(observation(player=player), parent)
            self.assertIsNot(out, parent)
            self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 3]])
            self.assertEqual(parent, before)
            self.assertEqual(m1.REPORT["buy_units"], 3)

    def test_public_entrypoint_truncation_never_spends_or_books_a_buy(self):
        for end in range(104, 119):
            m1.reset_for_tests()
            self.prime()
            parent = action()
            out = self.run_lane(parent=parent, route=tape(end=end))
            with self.subTest(eof=end):
                self.assertIs(out, parent)
                self.assertEqual(m1.REPORT["buy_units"], 0)
                self.assertEqual(m1._STATE[0]["bought_today"], 0)

    def test_money_guard_composes_with_positive_complete_day_path(self):
        for money in (10 ** 1000, float("nan"), float("inf"), True, -1):
            m1.reset_for_tests()
            self.prime()
            parent = action()
            out = self.run_lane(observation(money=money), parent)
            self.assertIs(out, parent)
            self.assertEqual(m1.REPORT["buy_orders"], 0)

    def test_exact_cash_reserve_boundary_is_preserved(self):
        for money, buys in ((1134.99, False), (1135.0, True)):
            m1.reset_for_tests()
            self.prime()
            parent = action()
            out = self.run_lane(observation(money=money), parent)
            self.assertEqual(out is not parent, buys)

    def test_disabled_path_does_not_touch_inputs_or_state(self):
        class Poison:
            def __getattribute__(self, name):
                raise AssertionError("disabled path inspected an input")
        parent = object()
        before = dict(m1.REPORT)
        out = m1.apply_m1_wheat_trade(Poison(), parent, Poison(),
                                     configuration=Poison(), enabled=False)
        self.assertIs(out, parent)
        self.assertEqual(m1.REPORT, before)
        self.assertEqual(m1._STATE, {})

    def test_self_induced_scarcity_suppression_is_preserved(self):
        parent_buy = action()
        parent_buy["market"] = [["BUY_PRODUCT", "WHEAT", 1]]
        self.prime(parent=parent_buy)
        parent = action()
        self.assertIs(self.run_lane(parent=parent), parent)
        out = self.run_lane(observation(102, inventory=96), action())
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 3]])

    def test_future_inflow_and_unreachable_pickup_remain_vetoed(self):
        for op in ("DROP", "PLACE"):
            route = tape()
            route[102]["farmer"] = [op]
            self.assertEqual(certificate(route), (None, 0))
        self.assertEqual(m1._future_literal_pickup(
            tape(), 101, [[0, 0]], [["PASS"]], 10), (None, 0))

    def test_hour_23_and_one_step_pickups_remain_vetoed(self):
        self.assertEqual(certificate(tape(due=119), 117), (None, 0))
        self.assertEqual(certificate(tape(due=102)), (None, 0))

    def test_raw_prefix_shape_is_checked_but_dead_suffix_is_ignored(self):
        for raw_index in (9, 10):
            route = tape()
            route[110]["market"] = [[] for _ in range(raw_index)] + [object()]
            expected = (None, 0) if raw_index == 9 else (104, 3)
            self.assertEqual(certificate(route), expected)


if __name__ == "__main__":
    unittest.main()
