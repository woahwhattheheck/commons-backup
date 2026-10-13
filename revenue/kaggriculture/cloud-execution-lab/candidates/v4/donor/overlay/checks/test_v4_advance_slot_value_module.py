# SPDX-License-Identifier: Apache-2.0
"""Focused checks for the matching-module ADVANCE_SLOT_VALUE seam."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_advance_slot_value as lane  # noqa: E402

PRODUCTS = (
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
)


class View:
    def __init__(self, prices):
        self.prices = dict(prices)


class State:
    def __init__(self):
        self.advanced_sales = {}
        self.sale_due_step = None


class AdvanceSlotValueModuleTests(unittest.TestCase):
    def test_disabled_is_exact_mutation_noop(self):
        action = {"market": [[] for _ in range(9)]}
        before = copy.deepcopy(action)
        state = State()
        used = lane.apply_advance_slot_value(
            action, View({"WOOL": 200}), state,
            {"WOOL": 1}, {"WOOL": 1}, set(), PRODUCTS, 10, 2,
            enabled=False,
        )
        self.assertIs(used, False)
        self.assertEqual(action, before)
        self.assertEqual(state.advanced_sales, {})
        self.assertIsNone(state.sale_due_step)

    def test_single_slot_prefers_higher_public_value(self):
        action = {"market": [[] for _ in range(9)]}
        state = State()
        used = lane.apply_advance_slot_value(
            action, View({"CARROT": 2, "WOOL": 200}), state,
            {"CARROT": 10, "WOOL": 1},
            {"CARROT": 10, "WOOL": 1}, set(), PRODUCTS, 10, 2,
            enabled=True,
        )
        self.assertIs(used, True)
        self.assertEqual(action["market"][-1], ["SELL", "WOOL", 1])
        self.assertEqual(state.advanced_sales, {"WOOL": 1})
        self.assertEqual(state.sale_due_step, 2)

    def test_equal_value_preserves_product_order(self):
        action = {"market": [[] for _ in range(9)]}
        state = State()
        lane.apply_advance_slot_value(
            action, View({"CARROT": 20, "WOOL": 200}), state,
            {"CARROT": 10, "WOOL": 1},
            {"CARROT": 10, "WOOL": 1}, set(), PRODUCTS, 10, 2,
            enabled=True,
        )
        self.assertEqual(action["market"][-1], ["SELL", "CARROT", 10])
        self.assertEqual(state.advanced_sales, {"CARROT": 10})

    def test_existing_sell_remains_ineligible(self):
        action = {"market": [[] for _ in range(8)] + [["SELL", "WOOL", 1]]}
        state = State()
        lane.apply_advance_slot_value(
            action, View({"CARROT": 3, "WOOL": 200}), state,
            {"CARROT": 1, "WOOL": 5},
            {"CARROT": 1, "WOOL": 5}, {"WOOL"}, PRODUCTS, 10, 2,
            enabled=True,
        )
        self.assertEqual(action["market"][-1], ["SELL", "CARROT", 1])
        self.assertEqual(state.advanced_sales, {"CARROT": 1})


if __name__ == "__main__":
    unittest.main()
