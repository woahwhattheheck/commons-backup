# SPDX-License-Identifier: Apache-2.0
"""Expanded current-ABI regression contract for V3.1 row-shed semantics."""
from __future__ import annotations

import copy
import importlib.util
import math
from pathlib import Path
import random
import sys
import unittest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[4]
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

import mechanics

_spec = importlib.util.spec_from_file_location(
    "v4_row_shed_sell_order", HERE / "row_shed_sell_order.py"
)
row_shed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(row_shed)

OBS = {"market": {"inventory": {"WOOL": 10000, "MILK": 10000, "EGG": 10000}}}
PRODUCTS = tuple(mechanics.MARKET_PARAMS)
LEGACY_PARAMS = {
    "WHEAT": (25, 400, "sqrt", 0.80, "log", 0.20),
    "CARROT": (35, 450, "hinge", 1.00, "sqrt", 0.70),
    "TOMATO": (60, 200, "hinge", 0.40, "sqrt", 0.60),
    "STRAWBERRY": (120, 100, "sqrt", 0.70, "linear", 1.60),
    "MELON": (250, 300, "log", 0.20, "sq", 3.60),
    "EGG": (50, 332, "hinge", 0.40, "log", 0.20),
    "MILK": (160, 122, "sqrt", 0.60, "linear", 1.60),
    "WOOL": (200, 105, "log", 0.20, "sq", 3.20),
    "FERTILIZER": (100, 200, "linear", 0.40, "linear", 0.40),
}


def action(rows):
    return {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(rows)}


def _legacy_shape(name, x, span):
    x = max(0.0, x)
    if name == "linear":
        return x
    if name == "sq":
        return x * x
    if name == "sqrt":
        return x ** 0.5
    if name == "log":
        return math.log(1.0 + x)
    if name == "hinge":
        u = x / span
        return u + 8.0 * max(0.0, u - 1.0) ** 2
    return x


def _legacy_price(item, inventory):
    base, span, below_func, below_target, above_func, above_target = LEGACY_PARAMS[item]
    if inventory < 10000:
        amp = below_target * base / _legacy_shape(below_func, span, span)
        price = base + amp * _legacy_shape(below_func, 10000 - inventory, span)
    else:
        amp = above_target * base / _legacy_shape(above_func, span, span)
        price = base - amp * _legacy_shape(above_func, inventory - 10000, span)
    return max(1, int(round(price)))


def _legacy_reference(market, inventory, shed=None):
    """Literal small reference for the reviewed 7cbe552 order_sells body."""
    lead = 0
    while lead < len(market) and market[lead] and market[lead][0] == "SELL":
        lead += 1
    if lead < 2:
        return market
    if shed is not None:
        block = market[:lead]
        if any(len(row) < 3 or type(row[2]) is not int or row[2] < 0 for row in block):
            return market
        if not isinstance(shed, dict) or any(
            type(shed.get(row[1])) is not int or shed[row[1]] < 0 for row in block
        ):
            shed = None

    def drop(row):
        item = row[1]
        if item not in LEGACY_PARAMS or len(row) < 3:
            return 0
        level = int(inventory.get(item, 10000))
        quantity = max(0, int(row[2]))
        if shed is not None:
            quantity = min(quantity, max(0, shed[item]))
        return (_legacy_price(item, level) - _legacy_price(item, level + quantity)) * quantity

    return sorted(market[:lead], key=drop, reverse=True) + market[lead:]


class RowShedSellOrderTests(unittest.TestCase):
    def test_official_price_shape_uses_fillable_units(self):
        raw = action([["SELL", "WOOL", 1000], ["SELL", "MILK", 6], ["HIRE"]])
        got = row_shed.RowShedSellOrder().transform(
            OBS, {}, raw, post_unit_shed={"WOOL": 1, "MILK": 6}
        )
        self.assertEqual(
            got["market"],
            [["SELL", "MILK", 6], ["SELL", "WOOL", 1000], ["HIRE"]],
        )

    def test_raw_slots_falsey_barrier_and_tail_are_preserved(self):
        raw = action([["SELL", "WOOL", 1000], [], ["SELL", "MILK", 6], ["HIRE"]])
        got = row_shed.RowShedSellOrder().transform(
            OBS, {}, raw, post_unit_shed={"WOOL": 1}
        )
        self.assertEqual(got, raw)

    def test_reorder_never_changes_rows_or_input(self):
        rows = [
            ["SELL", "WOOL", 1000],
            ["SELL", "MILK", 6],
            ["SELL", "EGG", 3],
            ["HIRE"],
        ]
        raw = action(rows)
        snapshot = copy.deepcopy(raw)
        got = row_shed.RowShedSellOrder().transform(
            OBS, {}, raw, post_unit_shed={"WOOL": 0, "MILK": 6, "EGG": 3}
        )
        self.assertEqual(sorted(map(tuple, got["market"][:3])), sorted(map(tuple, rows[:3])))
        self.assertEqual(got["market"][3:], rows[3:])
        self.assertEqual(raw, snapshot)

    def test_incomplete_projection_fails_closed(self):
        raw = action([["SELL", "WOOL", 1000], ["SELL", "MILK", 6], ["HIRE"]])
        got = row_shed.RowShedSellOrder().transform(
            OBS, {}, raw, post_unit_shed={"MILK": 6}
        )
        self.assertEqual(got, raw)

    def test_projection_poison_fails_closed(self):
        raw = action([["SELL", "WOOL", 1000], ["SELL", "MILK", 6], ["HIRE"]])
        for bad in (True, 1.0, "1", -1):
            with self.subTest(bad=bad):
                got = row_shed.RowShedSellOrder().transform(
                    OBS, {}, raw, post_unit_shed={"WOOL": bad, "MILK": 6}
                )
                self.assertEqual(got, raw)

    def test_quantity_poison_fails_closed(self):
        for bad in (True, 6.0, "6", -1):
            with self.subTest(bad=bad):
                raw = action([["SELL", "WOOL", bad], ["SELL", "MILK", 6], ["HIRE"]])
                got = row_shed.RowShedSellOrder().transform(
                    OBS, {}, raw, post_unit_shed={"WOOL": 1, "MILK": 6}
                )
                self.assertEqual(got, raw)

    def test_truthy_malformed_row_anywhere_fails_closed(self):
        raw = action([["SELL", "WOOL", 1000], ["SELL", "MILK", 6], 1])
        got = row_shed.RowShedSellOrder().transform(
            OBS, {}, raw, post_unit_shed={"WOOL": 1, "MILK": 6}
        )
        self.assertEqual(got, raw)

    def test_equal_scores_are_stable(self):
        raw = action([["SELL", "WOOL", 2], ["SELL", "MILK", 3], ["HIRE"]])
        got = row_shed.RowShedSellOrder(lambda *_: 10).transform(
            OBS, {}, raw, post_unit_shed={"WOOL": 2, "MILK": 3}
        )
        self.assertEqual(got, raw)

    def test_malformed_envelope_returns_explicit_fallback(self):
        selected = action([["SELL", "WOOL", 1000], ["SELL", "MILK", 6]])
        fallback = action([["HIRE"]])
        got = row_shed.RowShedSellOrder().transform(
            OBS,
            "bad",
            selected,
            post_unit_shed={"WOOL": 1, "MILK": 6},
            fallback_action=fallback,
        )
        self.assertEqual(got, fallback)

    def test_missing_projection_is_parent_identity(self):
        raw = action([["SELL", "WOOL", 1000], ["SELL", "MILK", 6]])
        got = row_shed.RowShedSellOrder().transform(OBS, {}, raw)
        self.assertEqual(got, raw)

    def test_complete_default_domain_matches_literal_v31_donor(self):
        rng = random.Random(20260911)
        for case in range(800):
            count = rng.randint(0, 5)
            block = []
            shed = {}
            inventory = {}
            for _ in range(count):
                item = rng.choice(PRODUCTS)
                # Zero-unit SELL is engine-dead in V4 and intentionally outside
                # this historical parity domain; its barrier contract is tested
                # separately in test_row_shed_market_prefix.py.
                quantity = rng.randint(1, 1200)
                block.append(["SELL", item, quantity])
                shed[item] = rng.randint(0, 25)
                inventory[item] = rng.randint(9500, 10600)
            tail = rng.choice(
                ([], [["HIRE"]], [[], ["SELL", "WOOL", 3]], [["BUY_SEED", "WHEAT", 1]])
            )
            rows = block + copy.deepcopy(tail)
            raw = action(rows)
            observation = {"market": {"inventory": copy.deepcopy(inventory)}}
            got = row_shed.RowShedSellOrder().transform(
                observation, {}, raw, post_unit_shed=copy.deepcopy(shed)
            )
            expected = _legacy_reference(
                copy.deepcopy(rows), copy.deepcopy(inventory), copy.deepcopy(shed)
            )
            with self.subTest(case=case):
                self.assertEqual(got["market"], expected)

    def test_incomplete_projection_divergence_from_v31_is_intentional(self):
        rows = [["SELL", "MILK", 6], ["SELL", "WOOL", 1000], ["HIRE"]]
        raw = action(rows)
        current = row_shed.RowShedSellOrder().transform(
            OBS, {}, raw, post_unit_shed={"MILK": 6}
        )
        legacy = _legacy_reference(
            copy.deepcopy(rows), OBS["market"]["inventory"], {"MILK": 6}
        )
        self.assertEqual(current, raw)
        self.assertNotEqual(legacy, rows)

    def test_bad_inventory_and_price_fail_closed(self):
        raw = action([["SELL", "WOOL", 1000], ["SELL", "MILK", 6]])
        for bad in (True, 1.0, "10000", -1):
            with self.subTest(inventory=bad):
                observation = {"market": {"inventory": {"WOOL": bad, "MILK": 10000}}}
                got = row_shed.RowShedSellOrder().transform(
                    observation, {}, raw, post_unit_shed={"WOOL": 1, "MILK": 6}
                )
                self.assertEqual(got, raw)

        def boom(*_args):
            raise ValueError("boom")

        got = row_shed.RowShedSellOrder(boom).transform(
            OBS, {}, raw, post_unit_shed={"WOOL": 1, "MILK": 6}
        )
        self.assertEqual(got, raw)

    def test_current_abi_passes_market_params_to_quote(self):
        raw = action([["SELL", "WOOL", 2], ["SELL", "MILK", 3]])
        params = {"marker": "current-v4"}
        seen = []

        def quote(_item, level, received):
            seen.append(received)
            return 100 - level % 2

        observation = {
            "market": {
                "inventory": {"WOOL": 10000, "MILK": 10000},
                "params": params,
            }
        }
        row_shed.RowShedSellOrder(quote).transform(
            observation, {}, raw, post_unit_shed={"WOOL": 2, "MILK": 3}
        )
        self.assertTrue(seen)
        self.assertTrue(all(received is params for received in seen))


if __name__ == "__main__":
    unittest.main()
