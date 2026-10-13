# SPDX-License-Identifier: Apache-2.0
"""Focused tests for R04-EXPANDTAX."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import expandtax
from expandtax import TrailingBooks, filter_market_orders, next_unlock_price, should_expand


def _obs(day=10, quadrants=("NW",), *, step=None):
    obs = {
        "day": day,
        "farm": {"unlocked_quadrants": list(quadrants), "money": 5000},
    }
    if step is not None:
        obs["step"] = step
    return obs


def _cfg(on=True, **overrides):
    cfg = {
        "r04_expandtax": on,
        "turnsPerDay": 24,
        "episodeSteps": 720,
        "maxMarketOrdersPerTurn": 10,
    }
    cfg.update(overrides)
    return cfg


def _books(rev, act):
    b = TrailingBooks()
    b.note_day(3000.0, 20, 100)
    action_delta = int(round((rev * 20) / max(act, 1e-9))) if act else 0
    b.note_day(3000.0 + rev * 20, 20, 100 + action_delta)
    return b


class TestShouldExpand(unittest.TestCase):
    def test_blocks_when_books_zero(self):
        self.assertFalse(should_expand(1000, 0.0, 5.0, 20))

    def test_allows_when_tax_cleared(self):
        self.assertTrue(should_expand(1000, 50.0, 5.0, 20))

    def test_blocks_high_price_short_horizon(self):
        self.assertFalse(should_expand(4000, 50.0, 5.0, 2))

    def test_type_poison_and_nonfinite_fail_closed(self):
        bad = (None, "1", True, [], {}, float("nan"), float("inf"))
        for value in bad:
            with self.subTest(value=value):
                self.assertFalse(should_expand(value, 5.0, 1.0, 5))
                self.assertFalse(should_expand(1000, value, 1.0, 5))
                self.assertFalse(should_expand(1000, 5.0, value, 5))
                self.assertFalse(should_expand(1000, 5.0, 1.0, value))

    def test_negative_action_value_cannot_invert_tax(self):
        self.assertFalse(should_expand(1000, 0.05, -100.0, 20))


class TestFilter(unittest.TestCase):
    def test_off_and_absent_are_exact_identity(self):
        action = {"market": [["BUY_LAND"], ["SELL", "CARROT", 3], ["BUY_LAND"]]}
        self.assertIs(filter_market_orders(action, _obs(), _cfg(False), None), action)
        self.assertIs(filter_market_orders(action, _obs(), {}, None), action)

    def test_truthy_nonbool_flag_is_off(self):
        action = {"market": [["BUY_LAND"]]}
        for poison in (1, "true", [True], {"enabled": True}):
            with self.subTest(poison=poison):
                self.assertIs(filter_market_orders(action, _obs(), _cfg(poison), None), action)

    def test_no_executable_buy_land_is_identity(self):
        action = {"market": [["SELL", "CARROT", 3]]}
        self.assertIs(filter_market_orders(action, _obs(), _cfg(), _books(50, 5)), action)

    def test_reject_removes_executable_land_only(self):
        action = {"market": [["BUY_LAND"], ["SELL", "CARROT", 3]]}
        out = filter_market_orders(action, _obs(day=28), _cfg(), _books(1.0, 5))
        self.assertEqual(out["market"], [["SELL", "CARROT", 3]])

    def test_allow_single_land_preserves_identity(self):
        action = {"market": [["BUY_LAND"]]}
        out = filter_market_orders(action, _obs(day=5), _cfg(), _books(60, 5))
        self.assertIs(out, action)

    def test_multi_buy_admits_only_first_precommit_price(self):
        action = {"market": [
            ["BUY_LAND"], ["SELL", "CARROT", 3], ["BUY_LAND"], ["HIRE"], ["BUY_LAND"]
        ]}
        out = filter_market_orders(action, _obs(day=5), _cfg(), _books(60, 5))
        self.assertEqual(out["market"], [
            ["BUY_LAND"], ["SELL", "CARROT", 3], ["HIRE"]
        ])
        self.assertEqual(action["market"][0], ["BUY_LAND"])
        self.assertEqual(len(action["market"]), 5)

    def test_second_price_is_used_when_ne_already_unlocked(self):
        action = {"market": [["BUY_LAND"]]}
        out = filter_market_orders(
            action, _obs(day=10, quadrants=("NW", "NE")), _cfg(), _books(3.0, 1.0)
        )
        self.assertEqual(out["market"], [])

    def test_inert_suffix_is_byte_preserved_and_cannot_engage_gate(self):
        action = {"market": [
            ["SELL", "CARROT", 3],
            ["BUY_LAND"],
            ["BUY_LAND", "TAIL"],
        ]}
        out = filter_market_orders(
            action, _obs(day=28), _cfg(maxMarketOrdersPerTurn=1), _books(0.1, 5)
        )
        self.assertIs(out, action)
        self.assertEqual(out["market"][1:], [["BUY_LAND"], ["BUY_LAND", "TAIL"]])

    def test_reject_prefix_preserves_raw_suffix(self):
        tail = [["BUY_LAND"], {"opaque": 1}, ["SELL", "CARROT", 99]]
        action = {"market": [["BUY_LAND"], ["HIRE"]] + tail}
        out = filter_market_orders(
            action, _obs(day=28), _cfg(maxMarketOrdersPerTurn=2), _books(0.1, 5)
        )
        self.assertEqual(out["market"], [["HIRE"]] + tail)
        self.assertIs(out["market"][-2], tail[-2])

    def test_minimum_one_market_cap(self):
        action = {"market": [["BUY_LAND"], ["BUY_LAND"]]}
        out0 = filter_market_orders(
            action, _obs(day=28), _cfg(maxMarketOrdersPerTurn=0), _books(0.1, 5)
        )
        outneg = filter_market_orders(
            action, _obs(day=28), _cfg(maxMarketOrdersPerTurn=-7), _books(0.1, 5)
        )
        self.assertEqual(out0["market"], [["BUY_LAND"]])
        self.assertEqual(outneg["market"], [["BUY_LAND"]])

    def test_cap_type_poison_returns_identity(self):
        action = {"market": [["BUY_LAND"], ["SELL", "CARROT", 3]]}
        for poison in (True, 2.0, "2", None, []):
            with self.subTest(poison=poison):
                cfg = _cfg(maxMarketOrdersPerTurn=poison)
                self.assertIs(filter_market_orders(action, _obs(), cfg, _books(60, 5)), action)

    def test_malformed_observation_never_mints_positive_verdict(self):
        action = {"market": [["BUY_LAND"], ["SELL", "CARROT", 3]]}
        bad_obs = (
            {},
            {"farm": {}},
            {"farm": {"unlocked_quadrants": ["NE"]}, "day": 5},
            {"farm": {"unlocked_quadrants": ["NW", "SW"]}, "day": 5},
            {"farm": {"unlocked_quadrants": ["NW"]}, "day": "5"},
            {"farm": {"unlocked_quadrants": ["NW"]}, "day": 5, "step": 24},
        )
        for obs in bad_obs:
            with self.subTest(obs=obs):
                out = filter_market_orders(action, obs, _cfg(), _books(60, 5))
                self.assertEqual(out["market"], [["SELL", "CARROT", 3]])

    def test_missing_or_foreign_books_blocks_land(self):
        action = {"market": [["BUY_LAND"], ["HIRE"]]}
        for books in (None, object(), {"rev": 999}):
            with self.subTest(books=books):
                out = filter_market_orders(action, _obs(), _cfg(), books)
                self.assertEqual(out["market"], [["HIRE"]])

    def test_all_unlocked_strips_executable_noop_land(self):
        action = {"market": [["SELL", "CARROT", 3], ["BUY_LAND"], ["HIRE"]]}
        out = filter_market_orders(
            action, _obs(quadrants=("NW", "NE", "SW", "SE")), _cfg(), _books(60, 5)
        )
        self.assertEqual(out["market"], [["SELL", "CARROT", 3], ["HIRE"]])

    def test_non_dict_action_and_non_list_market_are_identity(self):
        self.assertIsNone(filter_market_orders(None, _obs(), _cfg(), None))
        action = {"market": "BUY_LAND"}
        self.assertIs(filter_market_orders(action, _obs(), _cfg(), _books(60, 5)), action)


class TestUnlockPrice(unittest.TestCase):
    def test_prices_follow_canonical_prefix(self):
        self.assertEqual(next_unlock_price(_obs(quadrants=("NW",))), 1000)
        self.assertEqual(next_unlock_price(_obs(quadrants=("NW", "NE"))), 2000)
        self.assertEqual(next_unlock_price(_obs(quadrants=("NW", "NE", "SW"))), 4000)
        self.assertIsNone(next_unlock_price(_obs(quadrants=("NW", "NE", "SW", "SE"))))

    def test_malformed_quadrant_state_raises(self):
        for obs in ({}, {"farm": {}}, _obs(quadrants=("NE",)),
                    _obs(quadrants=("NW", "SW")), _obs(quadrants=("NW", "NE", "SE"))):
            with self.subTest(obs=obs):
                with self.assertRaises(ValueError):
                    next_unlock_price(obs)


class TestTrailingBooks(unittest.TestCase):
    def test_empty_and_single_day_are_zero(self):
        b = TrailingBooks()
        self.assertEqual(b.rev_per_tile_day, 0.0)
        self.assertEqual(b.dollars_per_action, 0.0)
        b.note_day(3000.0, 20, 100)
        self.assertEqual(b.rev_per_tile_day, 0.0)

    def test_delta_math(self):
        b = TrailingBooks()
        b.note_day(3000.0, 20, 100)
        b.note_day(4000.0, 20, 200)
        self.assertAlmostEqual(b.rev_per_tile_day, 50.0)
        self.assertAlmostEqual(b.dollars_per_action, 10.0)

    def test_note_type_poison_rejected(self):
        cases = [
            ("3000", 20, 100),
            (float("nan"), 20, 100),
            (3000, True, 100),
            (3000, 20.0, 100),
            (3000, 20, "100"),
            (3000, 20, True),
        ]
        for args in cases:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    TrailingBooks().note_day(*args)

    def test_action_total_must_be_monotone(self):
        b = TrailingBooks()
        b.note_day(3000, 20, 100)
        with self.assertRaises(ValueError):
            b.note_day(3100, 20, 99)

    def test_window_bounded(self):
        b = TrailingBooks()
        for i in range(10):
            b.note_day(3000 + i * 100, 20, 100 + i)
        self.assertLessEqual(len(b._days), TrailingBooks.WINDOW + 1)


if __name__ == "__main__":
    unittest.main()
