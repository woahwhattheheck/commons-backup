# SPDX-License-Identifier: Apache-2.0
"""Focused V4 checks for repaired D4 STRAWBERRY timing."""
from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_d4_strawberry_timing as d4  # noqa: E402
import r04_full_router as r04  # noqa: E402
from titan_runtime import Features  # noqa: E402

CONFIG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}


class View:
    def __init__(self, stock=12, price=200):
        self.shed = {item: 0 for item in r04.PRODUCTS}
        self.shed["STRAWBERRY"] = stock
        self.prices = {item: 1 for item in r04.PRODUCTS}
        self.prices["STRAWBERRY"] = price
        self.positions = []
        self.inventories = []

    def inventory(self, actor):
        return {}

    def beside_shed(self, position):
        return False


def action(market=None):
    return {"farmer": ["PASS"], "hands": [], "market": list(market or [])}


def tape_with(step, qty=1000, pickup_step=None):
    tape = [{"farmer": ["PASS"], "hands": [], "market": []}
            for _ in range(r04.LAST_STEP + 1)]
    tape[step]["market"] = [["SELL", "STRAWBERRY", qty]]
    if pickup_step is not None:
        tape[pickup_step]["farmer"] = ["PICKUP", "STRAWBERRY", 1]
    return tape


def state(debts=None):
    return SimpleNamespace(queues={}, sale_window_debts={} if debts is None else debts)


class D4V4Tests(unittest.TestCase):
    def setUp(self):
        self.old_horizon = r04.SALE_HORIZON
        self.old_flush = r04.EVENING_FLUSH
        self.old_min_price = getattr(r04, "D4_STRAWBERRY_MIN_PRICE", 180)
        r04.SALE_HORIZON = 8
        r04.EVENING_FLUSH = True
        for key in d4.REPORT:
            d4.REPORT[key] = 0 if key in ("engaged", "units_advanced") else None

    def tearDown(self):
        r04.SALE_HORIZON = self.old_horizon
        r04.EVENING_FLUSH = self.old_flush
        if hasattr(r04, "D4_STRAWBERRY_TIMING"):
            r04.D4_STRAWBERRY_TIMING = False
        if hasattr(r04, "D4_STRAWBERRY_MIN_PRICE"):
            r04.D4_STRAWBERRY_MIN_PRICE = self.old_min_price

    def test_key_ships_off_and_install_round_trips(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_d4_strawberry_timing"], False)
        self.assertEqual(data["r04_d4_strawberry_min_price"], 180)
        features = Features(**data)
        self.assertIs(features.r04_d4_strawberry_timing, False)
        self.assertEqual(features.r04_d4_strawberry_min_price, 180)
        r04.install(d4_strawberry_timing=True, d4_strawberry_min_price=211)
        self.assertIs(r04.D4_STRAWBERRY_TIMING, True)
        self.assertEqual(r04.D4_STRAWBERRY_MIN_PRICE, 211)
        r04.install(d4_strawberry_timing=False)
        self.assertIs(r04.D4_STRAWBERRY_TIMING, False)

    def test_install_rejects_type_poisoned_or_too_low_threshold(self):
        for bad in (True, 1, 1.0, "180"):
            with self.subTest(value=bad):
                before = r04.D4_STRAWBERRY_MIN_PRICE
                with self.assertRaises(ValueError):
                    r04.install(d4_strawberry_min_price=bad)
                self.assertEqual(r04.D4_STRAWBERRY_MIN_PRICE, before)

    def test_d4_is_composed_after_h4_before_row_order_and_evening_flush(self):
        source = inspect.getsource(r04._v3_stack)
        d4_index = source.index("r04_d4_strawberry_timing.apply_d4")
        self.assertLess(source.index("if STRAWBERRY_TOPUP"), d4_index)
        self.assertLess(d4_index, source.index("if ROW_ORDER"))
        self.assertLess(d4_index, source.index("if EVENING_FLUSH"))
        self.assertIn("min_price=D4_STRAWBERRY_MIN_PRICE", source)

    def test_disabled_apply_returns_exact_parent_object(self):
        parent = action()
        self.assertIs(d4.apply_d4({}, parent, enabled=False), parent)

    def test_nonstandard_configuration_and_bad_player_fail_closed(self):
        parent = action()
        obs = {"step": 369, "player": 0}
        self.assertTrue(d4._standard_configuration(dict(CONFIG)))
        self.assertTrue(d4._standard_configuration(SimpleNamespace(**CONFIG)))
        bad = dict(CONFIG)
        bad["maxMarketOrdersPerTurn"] = 9
        self.assertFalse(d4._standard_configuration(bad))
        self.assertFalse(d4._standard_configuration(None))
        self.assertIs(d4.apply_d4(obs, parent, bad, enabled=True), parent)
        self.assertIs(d4.apply_d4({"step": 369, "player": True}, parent,
                                  dict(CONFIG), enabled=True), parent)
        self.assertIs(d4.apply_d4({"step": 369, "player": 2}, parent,
                                  dict(CONFIG), enabled=True), parent)

    def test_malformed_current_action_is_exact_parent(self):
        parent = {"farmer": {}, "hands": [], "market": []}
        out, added, reservations = d4.advance_midgame_strawberry(
            r04, parent, View(), state(), tape_with(380), 369, min_price=180)
        self.assertIs(out, parent)
        self.assertEqual((0, ()), (added, reservations))

    def test_malformed_future_work_is_exact_parent(self):
        parent = action()
        future = tape_with(380)
        future[378]["hands"] = 7
        memory = state()
        out, added, reservations = d4.advance_midgame_strawberry(
            r04, parent, View(), memory, future, 369, min_price=180)
        self.assertIs(out, parent)
        self.assertEqual((0, ()), (added, reservations))
        self.assertEqual({}, memory.sale_window_debts)

    def test_missing_debt_state_is_exact_parent(self):
        parent = action()
        memory = SimpleNamespace(queues={})
        out, added, reservations = d4.advance_midgame_strawberry(
            r04, parent, View(), memory, tape_with(380), 369, min_price=180)
        self.assertIs(out, parent)
        self.assertEqual((0, ()), (added, reservations))
        self.assertFalse(hasattr(memory, "sale_window_debts"))

    def test_pre_flush_authored_sale_is_advanced_and_reserved(self):
        original = action()
        st = state()
        out, added, reservations = d4.advance_midgame_strawberry(
            r04, original, View(stock=12, price=200), st, tape_with(380), 369,
            min_price=180)
        self.assertIsNot(out, original)
        self.assertEqual(12, added)
        self.assertEqual(((380, 12),), reservations)
        self.assertEqual([["SELL", "STRAWBERRY", 12]], out["market"])
        self.assertEqual({380: {"STRAWBERRY": 12}}, st.sale_window_debts)
        self.assertEqual([], original["market"])

    def test_incumbent_flush_owns_later_h22_sale(self):
        original = action()
        st = state()
        out, added, reservations = d4.advance_midgame_strawberry(
            r04, original, View(), st, tape_with(382), 373, min_price=180)
        self.assertIs(out, original)
        self.assertEqual((0, ()), (added, reservations))
        self.assertEqual({}, st.sale_window_debts)

    def test_current_strawberry_trade_is_h4_owned(self):
        original = action([["SELL", "STRAWBERRY", 2]])
        st = state()
        out, added, _ = d4.advance_midgame_strawberry(
            r04, original, View(), st, tape_with(380), 369, min_price=180)
        self.assertIs(out, original)
        self.assertEqual(0, added)

    def test_future_pickup_blocks_the_advance(self):
        original = action()
        st = state()
        out, added, _ = d4.advance_midgame_strawberry(
            r04, original, View(), st, tape_with(380, pickup_step=379), 369,
            min_price=180)
        self.assertIs(out, original)
        self.assertEqual(0, added)

    def test_existing_e184_debt_is_subtracted_exactly(self):
        original = action()
        st = state({380: {"STRAWBERRY": 8}})
        out, added, reservations = d4.advance_midgame_strawberry(
            r04, original, View(stock=5), st, tape_with(380, qty=10), 369,
            min_price=180)
        self.assertEqual(2, added)
        self.assertEqual(((380, 2),), reservations)
        self.assertEqual(10, st.sale_window_debts[380]["STRAWBERRY"])
        self.assertEqual([["SELL", "STRAWBERRY", 2]], out["market"])

    def test_full_inherited_debt_map_is_fail_closed(self):
        malformed = (
            {True: {"STRAWBERRY": 1}},
            {"380": {"STRAWBERRY": 1}},
            {720: {"STRAWBERRY": 1}},
            {380: []},
            {380: {"STRAWBERRY": True}},
            {380: {"STRAWBERRY": 1.0}},
            {380: {"STRAWBERRY": "1"}},
            {380: {"STRAWBERRY": -1}},
            {380: {"NOT_A_PRODUCT": 1}},
        )
        for debts in malformed:
            with self.subTest(debts=debts):
                original = action()
                st = state(debts)
                out, added, reservations = d4.advance_midgame_strawberry(
                    r04, original, View(stock=5), st, tape_with(380, qty=10), 369,
                    min_price=180)
                self.assertIs(out, original)
                self.assertEqual((0, ()), (added, reservations))
                self.assertIs(st.sale_window_debts, debts)

    def test_price_order_cap_and_day_guards_are_identity(self):
        cases = [
            (View(price=179), action(), 369),
            (View(), action([["SELL", "WHEAT", 1] for _ in range(r04.MAX_ORDERS)]), 369),
            (View(), action(), 287),
            (View(), action(), 456),
        ]
        for view, original, step in cases:
            with self.subTest(step=step, market=len(original["market"])):
                st = state()
                due = min(max(step + 11, 0), r04.LAST_STEP)
                out, added, _ = d4.advance_midgame_strawberry(
                    r04, original, view, st, tape_with(due), step, min_price=180)
                self.assertIs(out, original)
                self.assertEqual(0, added)


if __name__ == "__main__":
    unittest.main()
