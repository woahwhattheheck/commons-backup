# SPDX-License-Identifier: Apache-2.0
"""Focused fail-closed regressions for V4 M1 money and public-seat shape."""
from __future__ import annotations

import math
import unittest

import r04_m1_wheat_trade as m1


CONFIG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}


def _eligible_prefix(*, player=0, seats=2):
    farm = {"money": 5000.0, "farmer": [4, 4], "hands": []}
    return {
        "step": 101,
        "player": player,
        "market": {"inventory": {"WHEAT": 98}, "prices": {"WHEAT": 20}},
        "private": {"shed": {}},
        "farms": [dict(farm) for _ in range(seats)],
    }, {"farmer": ["PASS"], "hands": [], "market": []}


class M1MoneyOverflowTests(unittest.TestCase):
    def test_huge_json_integer_is_not_valid_money_and_does_not_raise(self):
        huge = 10 ** 1000
        with self.assertRaises(OverflowError):
            math.isfinite(huge)
        self.assertIs(m1._plain_nonnegative_money(huge), False)

    def test_finite_nonnegative_money_still_accepts_normal_engine_values(self):
        for value in (0, 1, 1000, 1000.0, 1234.5):
            with self.subTest(value=value):
                self.assertIs(m1._plain_nonnegative_money(value), True)

    def test_bool_negative_nan_and_inf_are_rejected(self):
        for value in (True, False, -1, -0.5, float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                self.assertIs(m1._plain_nonnegative_money(value), False)

    def test_three_seat_snapshot_fails_before_scarcity_state_mutation(self):
        observation, parent = _eligible_prefix(player=0, seats=3)
        original = m1._observe_scarcity
        try:
            def forbidden(*args, **kwargs):
                raise AssertionError("malformed public seat vector reached scarcity state")
            m1._observe_scarcity = forbidden
            out = m1.apply_m1_wheat_trade(
                observation, parent, (), configuration=CONFIG, enabled=True)
        finally:
            m1._observe_scarcity = original
        self.assertIs(out, parent)

    def test_third_seat_player_fails_before_scarcity_state_mutation(self):
        observation, parent = _eligible_prefix(player=2, seats=3)
        original = m1._observe_scarcity
        try:
            def forbidden(*args, **kwargs):
                raise AssertionError("third-seat player reached scarcity state")
            m1._observe_scarcity = forbidden
            out = m1.apply_m1_wheat_trade(
                observation, parent, (), configuration=CONFIG, enabled=True)
        finally:
            m1._observe_scarcity = original
        self.assertIs(out, parent)


if __name__ == "__main__":
    unittest.main()
