# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 ``r04_advance_slot_value``.

Run in a materialised candidate package:

    python -B -m unittest -v checks/test_v4_advance_slot_value.py
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
from titan_runtime import Features  # noqa: E402


class View:
    def __init__(self, shed, prices):
        self.shed = dict(shed)
        self.prices = dict(prices)
        self.positions = []
        self.inventories = []


def action(rows=9):
    return {"farmer": ["PASS"], "hands": [], "market": [[] for _ in range(rows)]}


def tape(*orders):
    return [
        {"farmer": ["PASS"], "hands": [], "market": []},
        {"farmer": ["PASS"], "hands": [], "market": []},
        {"farmer": ["PASS"], "hands": [], "market": [list(order) for order in orders]},
    ]


def run(enabled, *, rows=9, shed=None, prices=None, orders=()):
    r04.ADVANCE_SLOT_VALUE = bool(enabled)
    parent = action(rows)
    state = r04.DayState()
    view = View(shed or {}, prices or {})
    r04.advance_sales(parent, view, state, tape(*orders), 1)
    return parent, state


class AdvanceSlotValueTests(unittest.TestCase):
    def tearDown(self):
        r04.ADVANCE_SLOT_VALUE = False

    def test_key_ships_off_and_features_accept_it(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_advance_slot_value"], False)
        features = Features(**data)
        self.assertIs(features.r04_advance_slot_value, False)
        self.assertIs(r04.ADVANCE_SLOT_VALUE, False)

    def test_disabled_preserves_native_fixed_product_order(self):
        parent, state = run(
            False,
            shed={"CARROT": 10, "WOOL": 1},
            prices={"CARROT": 2, "WOOL": 200},
            orders=(("SELL", "CARROT", 10), ("SELL", "WOOL", 1)),
        )
        self.assertEqual(parent["market"][-1], ["SELL", "CARROT", 10])
        self.assertEqual(state.advanced_sales, {"CARROT": 10})
        self.assertEqual(state.sale_due_step, 2)

    def test_enabled_spends_single_free_slot_on_higher_public_value(self):
        parent, state = run(
            True,
            shed={"CARROT": 10, "WOOL": 1},
            prices={"CARROT": 2, "WOOL": 200},
            orders=(("SELL", "CARROT", 10), ("SELL", "WOOL", 1)),
        )
        self.assertEqual(parent["market"][-1], ["SELL", "WOOL", 1])
        self.assertEqual(state.advanced_sales, {"WOOL": 1})
        self.assertEqual(state.sale_due_step, 2)

    def test_equal_value_preserves_native_product_order(self):
        parent, state = run(
            True,
            shed={"CARROT": 10, "WOOL": 1},
            prices={"CARROT": 20, "WOOL": 200},
            orders=(("SELL", "CARROT", 10), ("SELL", "WOOL", 1)),
        )
        self.assertEqual(parent["market"][-1], ["SELL", "CARROT", 10])
        self.assertEqual(state.advanced_sales, {"CARROT": 10})

    def test_two_free_slots_choose_top_two_but_emit_in_native_product_order(self):
        base = action(8)
        before = copy.deepcopy(base["market"])
        r04.ADVANCE_SLOT_VALUE = True
        state = r04.DayState()
        view = View(
            {"CARROT": 10, "MILK": 2, "WOOL": 1},
            {"CARROT": 2, "MILK": 60, "WOOL": 200},
        )
        planned = tape(("SELL", "CARROT", 10), ("SELL", "MILK", 2), ("SELL", "WOOL", 1))
        r04.advance_sales(base, view, state, planned, 1)
        self.assertEqual(base["market"][:8], before)
        self.assertEqual(base["market"][8:], [["SELL", "MILK", 2], ["SELL", "WOOL", 1]])
        self.assertEqual(state.advanced_sales, {"MILK": 2, "WOOL": 1})

    def test_existing_same_item_sell_remains_ineligible(self):
        r04.ADVANCE_SLOT_VALUE = True
        parent = action(8)
        parent["market"].append(["SELL", "WOOL", 1])
        state = r04.DayState()
        view = View({"CARROT": 1, "WOOL": 5}, {"CARROT": 3, "WOOL": 200})
        r04.advance_sales(parent, view, state,
                          tape(("SELL", "CARROT", 1), ("SELL", "WOOL", 5)), 1)
        self.assertEqual(parent["market"][-1], ["SELL", "CARROT", 1])
        self.assertEqual(state.advanced_sales, {"CARROT": 1})

    def test_install_setter_controls_flag(self):
        r04.install(advance_slot_value=True)
        self.assertIs(r04.ADVANCE_SLOT_VALUE, True)
        r04.install(advance_slot_value=False)
        self.assertIs(r04.ADVANCE_SLOT_VALUE, False)


if __name__ == "__main__":
    unittest.main()
