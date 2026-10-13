# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[4]
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

_spec = importlib.util.spec_from_file_location(
    "v4_row_shed_sell_order_prefix", HERE / "row_shed_sell_order.py"
)
row_shed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(row_shed)


def action(rows):
    return {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(rows)}


class RowShedMarketPrefixTests(unittest.TestCase):
    def test_inert_suffix_sell_cannot_enter_executable_prefix(self):
        weights = {"A": 1, "B": 2, "C": 100}

        def quote(item, level, _params):
            return 1000 - weights[item] * (level - 10000)

        raw = action([
            ["SELL", "A", 1],
            ["SELL", "B", 1],
            ["SELL", "C", 1],
            ["HIRE"],
        ])
        obs = {"market": {"inventory": {"A": 10000, "B": 10000, "C": 10000}}}
        transform = row_shed.RowShedSellOrder(quote)
        got = transform.transform(
            obs,
            {"maxMarketOrdersPerTurn": 2},
            raw,
            post_unit_shed={"A": 1, "B": 1, "C": 1},
        )

        # C has by far the largest score, but row 2 is engine-inert at cap=2.
        # It must neither enter the executable prefix nor move within the suffix.
        self.assertEqual(got["market"], [
            ["SELL", "B", 1],
            ["SELL", "A", 1],
            ["SELL", "C", 1],
            ["HIRE"],
        ])
        self.assertEqual(transform.diagnostics["market_prefix_limit"], 2)
        self.assertEqual(transform.diagnostics["leading_sell_count"], 2)
        self.assertEqual(
            [row["original_index"] for row in transform.diagnostics["scores"]],
            [0, 1],
        )

    def test_truthy_malformed_inert_suffix_cannot_veto_prefix_reorder(self):
        weights = {"A": 1, "B": 100}

        def quote(item, level, _params):
            return 1000 - weights[item] * (level - 10000)

        poison = {"engine": "never parses row 2"}
        raw = action([
            ["SELL", "A", 1],
            ["SELL", "B", 1],
            poison,
            ["HIRE"],
        ])
        transform = row_shed.RowShedSellOrder(quote)
        got = transform.transform(
            {"market": {"inventory": {"A": 10000, "B": 10000}}},
            {"maxMarketOrdersPerTurn": 2},
            raw,
            post_unit_shed={"A": 1, "B": 1},
        )

        self.assertEqual(got["market"], [
            ["SELL", "B", 1],
            ["SELL", "A", 1],
            poison,
            ["HIRE"],
        ])
        self.assertEqual(got["market"][2:], raw["market"][2:])
        self.assertEqual(transform.diagnostics["status"], "applied")
        self.assertEqual(transform.diagnostics["leading_sell_count"], 2)

    def test_truthy_malformed_row_inside_prefix_fails_closed(self):
        raw = action([
            ["SELL", "A", 1],
            {"poison": 1},
            ["SELL", "B", 1],
        ])
        fallback = action([["HIRE"]])
        transform = row_shed.RowShedSellOrder(lambda *_: 10)
        got = transform.transform(
            {"market": {"inventory": {"A": 10000, "B": 10000}}},
            {"maxMarketOrdersPerTurn": 2},
            raw,
            post_unit_shed={"A": 1, "B": 1},
            fallback_action=fallback,
        )

        self.assertEqual(got, fallback)
        self.assertEqual(transform.diagnostics["status"], "fallback")
        self.assertIn("executable market row", transform.diagnostics["reason"])

    def test_missing_public_inventory_fails_closed_instead_of_fabricating_i0(self):
        weights = {"A": 1, "B": 100}

        def quote(item, level, _params):
            return 1000 - weights[item] * (level - 10000)

        raw = action([["SELL", "A", 1], ["SELL", "B", 1]])
        transform = row_shed.RowShedSellOrder(quote)
        got = transform.transform(
            {"market": {"inventory": {"A": 10000}}},
            {"maxMarketOrdersPerTurn": 2},
            raw,
            post_unit_shed={"A": 1, "B": 1},
        )
        self.assertEqual(got, raw)
        self.assertEqual(transform.diagnostics["status"], "fallback")
        self.assertIn("market inventory is incomplete", transform.diagnostics["reason"])

        control = row_shed.RowShedSellOrder(quote)
        complete = control.transform(
            {"market": {"inventory": {"A": 10000, "B": 10000}}},
            {"maxMarketOrdersPerTurn": 2},
            raw,
            post_unit_shed={"A": 1, "B": 1},
        )
        self.assertEqual(complete["market"], [["SELL", "B", 1], ["SELL", "A", 1]])
        self.assertEqual(control.diagnostics["status"], "applied")

    def test_zero_quantity_sell_is_engine_dead_ordering_barrier(self):
        def quote(item, level, _params):
            # B would outrank A if the dead row were incorrectly included and
            # crossed. The official interpreter rejects SELL quantity zero.
            return 1000 - ({"A": 1, "B": 100}[item] * (level - 10000))

        raw = action([
            ["SELL", "A", 0],
            ["SELL", "B", 1],
            ["HIRE"],
        ])
        obs = {"market": {"inventory": {"A": 10000, "B": 10000}}}
        transform = row_shed.RowShedSellOrder(quote)
        got = transform.transform(
            obs,
            {"maxMarketOrdersPerTurn": 2},
            raw,
            post_unit_shed={"A": 1, "B": 1},
        )

        self.assertEqual(got, raw)
        self.assertEqual(transform.diagnostics["market_prefix_limit"], 2)
        self.assertEqual(transform.diagnostics["leading_sell_count"], 0)
        self.assertEqual(transform.diagnostics["status"], "identity")
        self.assertEqual(transform.diagnostics["scores"], [])

    def test_negative_quantity_sell_after_live_rows_is_hard_barrier(self):
        weights = {"A": 1, "B": 100}

        def quote(item, level, _params):
            return 1000 - weights[item] * (level - 10000)

        raw = action([
            ["SELL", "A", 1],
            ["SELL", "B", 1],
            ["SELL", "C", -1],
            ["HIRE"],
        ])
        transform = row_shed.RowShedSellOrder(quote)
        got = transform.transform(
            {"market": {"inventory": {"A": 10000, "B": 10000}}},
            {"maxMarketOrdersPerTurn": 3},
            raw,
            post_unit_shed={"A": 1, "B": 1},
        )

        self.assertEqual(got["market"], [
            ["SELL", "B", 1],
            ["SELL", "A", 1],
            ["SELL", "C", -1],
            ["HIRE"],
        ])
        self.assertEqual(transform.diagnostics["leading_sell_count"], 2)
        self.assertEqual(transform.diagnostics["status"], "applied")

    def test_negative_quantity_sell_at_front_is_identity_barrier(self):
        raw = action([
            ["SELL", "A", -1],
            ["SELL", "B", 1],
        ])
        transform = row_shed.RowShedSellOrder(lambda *_: 10)
        got = transform.transform(
            {"market": {"inventory": {"A": 10000, "B": 10000}}},
            {"maxMarketOrdersPerTurn": 2},
            raw,
            post_unit_shed={"A": 1, "B": 1},
        )

        self.assertEqual(got, raw)
        self.assertEqual(transform.diagnostics["leading_sell_count"], 0)
        self.assertEqual(transform.diagnostics["status"], "identity")
        self.assertEqual(transform.diagnostics["scores"], [])

    def test_zero_and_negative_caps_follow_engine_minimum_one(self):
        raw = action([["SELL", "A", 1], ["SELL", "B", 1]])
        obs = {"market": {"inventory": {"A": 10000, "B": 10000}}}
        for cap in (0, -7):
            with self.subTest(cap=cap):
                transform = row_shed.RowShedSellOrder(lambda *_: 10)
                got = transform.transform(
                    obs,
                    {"maxMarketOrdersPerTurn": cap},
                    raw,
                    post_unit_shed={"A": 1, "B": 1},
                )
                self.assertEqual(got, raw)
                self.assertEqual(transform.diagnostics["market_prefix_limit"], 1)
                self.assertEqual(transform.diagnostics["leading_sell_count"], 1)
                self.assertEqual(transform.diagnostics["status"], "identity")

    def test_market_cap_type_poison_fails_closed_to_explicit_fallback(self):
        raw = action([["SELL", "A", 1], ["SELL", "B", 1]])
        fallback = action([["HIRE"]])
        obs = {"market": {"inventory": {"A": 10000, "B": 10000}}}
        for bad in (True, 2.0, "2"):
            with self.subTest(bad=bad):
                transform = row_shed.RowShedSellOrder(lambda *_: 10)
                got = transform.transform(
                    obs,
                    {"maxMarketOrdersPerTurn": bad},
                    raw,
                    post_unit_shed={"A": 1, "B": 1},
                    fallback_action=fallback,
                )
                self.assertEqual(got, fallback)
                self.assertEqual(transform.diagnostics["status"], "fallback")
                self.assertIn("plain int", transform.diagnostics["reason"])


if __name__ == "__main__":
    unittest.main()
