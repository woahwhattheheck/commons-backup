#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import compose_current_native as base
import compose_current_native_strict as strict
import test_compose_current_native as base_tests


HERE = Path(__file__).resolve().parent
V4 = HERE.parents[1]
LAB = V4.parent.parent


def function_from(source: str, name: str, namespace=None):
    start, end = base._span(source, name)
    ns = {} if namespace is None else dict(namespace)
    exec(compile(source[start:end], f"<{name}>", "exec"), ns)
    return ns[name]


def quantities(orders):
    result = {}
    for order in orders:
        if order and len(order) > 2 and order[0] == "SELL":
            result[order[1]] = result.get(order[1], 0) + max(0, int(order[2]))
    return result


class StrictListOnlyPrefixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_frozen = (LAB / "frozen_selected.py").read_text()
        cls.base_frozen = base._rewrite_frozen(cls.raw_frozen)
        cls.strict_frozen = strict._harden_frozen(cls.base_frozen, base)
        base_tests.CurrentPrefixCompositionTests.setUpClass()
        cls.loom_scheduler_b = base_tests.CurrentPrefixCompositionTests.loom_scheduler_b
        cls.loom_frozen_b = base_tests.CurrentPrefixCompositionTests.loom_frozen_b
        cls.h3_frozen_b = base_tests.CurrentPrefixCompositionTests.h3_frozen_b

    def test_materializer_cannot_turn_tuple_market_into_executable_rows(self):
        old_fn = function_from(self.base_frozen, "materialize_sales")
        new_fn = function_from(self.strict_frozen, "materialize_sales")
        malformed = (["SELL", "MILK", 4],)
        args = (malformed, {"MILK": 3}, {"MILK": 3}, {"MILK"}, 1)
        self.assertEqual(old_fn(*args), [["SELL", "MILK", 3]])
        self.assertEqual(new_fn(*args), [])

    def test_sale_quantities_treats_non_list_market_as_engine_empty(self):
        old_fn = function_from(self.base_frozen, "sale_quantities")
        new_fn = function_from(self.strict_frozen, "sale_quantities")
        malformed = (["SELL", "MILK", 4],)
        self.assertEqual(old_fn(malformed), {"MILK": 4})
        self.assertEqual(new_fn(malformed), {})

    def test_market_prefix_state_does_not_parse_tuple_buy(self):
        old_fn = function_from(self.base_frozen, "_market_prefix_state")
        new_fn = function_from(self.strict_frozen, "_market_prefix_state")
        malformed = (["BUY_PRODUCT", "MILK", 1],)
        args = (
            malformed,
            {"money": 100, "hires_today": 0, "unlocked_quadrants": []},
            {"shed": {}},
            {"inventory": {}, "params": None},
            [],
            {"shedCapacity": 100},
            0,
            {},
            0,
        )
        self.assertEqual(old_fn(*args)["unsupported_index"], 0)
        self.assertIsNone(new_fn(*args)["unsupported_index"])

    def test_same_turn_funding_refuses_tuple_market_before_accounting(self):
        new_fn = function_from(self.strict_frozen, "fund_same_turn_acquisition")
        orders, info = new_fn(
            (["BUY_PRODUCT", "MILK", 1],),
            {}, {}, {}, [], {}, 0, set(), {},
        )
        self.assertEqual(orders, [])
        self.assertEqual(info, {"applied": False, "reason": "non-list-market"})

    def test_funding_trace_treats_tuple_current_market_as_empty(self):
        new_fn = function_from(self.strict_frozen, "_funding_trace", {"copy": copy})
        result = new_fn(
            {"step": 0, "market": {"inventory": {}, "params": None}},
            {"shedCapacity": 100, "maxMarketOrdersPerTurn": 1},
            {"money": 100, "hires_today": 0, "hands": [], "unlocked_quadrants": []},
            {"shed": {}, "inventories": [], "seeds": {}},
            [], 0, 0,
            (["BUY_PRODUCT", "MILK", 1],),
            stress_units=0,
        )
        self.assertEqual(result["acquisitions"], [])
        self.assertEqual(result["executed_sales"], [])
        self.assertEqual(result["cash"], 100)

    def test_joint_resource_callback_normalizes_tuple_market_before_budgeting(self):
        parent = SimpleNamespace(
            DECISIONS=[],
            PASS={"farmer": ["PASS"], "hands": [], "market": []},
        )
        new_fn = function_from(self.strict_frozen, "joint_resource_bound", {"parent": parent})
        route = [parent.PASS, parent.PASS, parent.PASS]
        result = new_fn(
            {"step": 0},
            {"shedCapacity": 100, "maxMarketOrdersPerTurn": 1,
             "turnsPerDay": 24, "episodeSteps": 720},
            {"market": (["BUY_ANIMAL", "COW", 1],)},
            {"tiles": [{} for _ in range(10)], "money": 100,
             "hires_today": 0, "unlocked_quadrants": []},
            {"shed": {}}, route, 1,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["fixed_cost"], 0)
        self.assertEqual(result["stock_upper"], {})

    def test_joint_queue_passes_only_engine_executable_rows_to_shared_slot_ledger(self):
        materialize = function_from(self.strict_frozen, "materialize_sales")
        sale_quantities = function_from(self.strict_frozen, "sale_quantities")
        seen = {}

        def shared_slot(plans, orders_by_step, cap):
            seen["rows"] = orders_by_step(0)
            seen["cap"] = cap
            return {"plans": plans, "cap": cap}

        new_fn = function_from(
            self.strict_frozen,
            "joint_queue_ledger",
            {
                "PRODUCTS": {"MILK"},
                "sale_quantities": sale_quantities,
                "materialize_sales": materialize,
                "shared_slot_ledger": shared_slot,
            },
        )
        result = new_fn(
            {"MILK": [(0, 0)]}, {"MILK": 0}, {}, {"MILK": 1},
            {"stock_upper": {"MILK": 1}},
            lambda _t: (["SELL", "MILK", 1],),
            0, 0, 1,
        )
        self.assertIsNotNone(result)
        self.assertEqual(seen["rows"], [])
        self.assertEqual(seen["cap"], 1)

    def test_strict_source_removes_known_coercing_consumers(self):
        self.assertIn(strict.STRICT_MARKER, self.strict_frozen)
        self.assertNotIn("for order in list(orders_at(t))[:max_orders]:", self.strict_frozen)
        self.assertNotIn("sale_quantities(list(orders_at(t))[:max_orders])", self.strict_frozen)
        self.assertNotIn("shared_slot_ledger(all_plans,orders_at,max_orders)", self.strict_frozen)
        self.assertEqual(
            self.strict_frozen.count("orders = orders if isinstance(orders,list) else []"),
            2,
        )
        compile(self.strict_frozen, "<strict-prefix-regression>", "exec")

    def test_authenticated_base_snapshot_survives_post_hash_path_swap(self):
        approved = (HERE / "compose_current_native.py").read_bytes()
        approved_blob = strict.git_blob(approved)
        original_path = strict.BASE_PATH
        original_git_blob = strict.git_blob
        with tempfile.TemporaryDirectory() as tmp:
            swap_path = Path(tmp) / "compose_current_native.py"
            swap_path.write_bytes(approved)
            swapped = {"done": False}

            def swapping_hash(data: bytes) -> str:
                result = original_git_blob(data)
                if not swapped["done"] and data == approved:
                    swapped["done"] = True
                    swap_path.write_text("raise RuntimeError('swapped base executed')\n")
                return result

            strict.BASE_PATH = swap_path
            strict.git_blob = swapping_hash
            try:
                scheduler_out, frozen_out, receipt = strict.compose_pair(
                    self.loom_scheduler_b, self.loom_frozen_b
                )
            finally:
                strict.BASE_PATH = original_path
                strict.git_blob = original_git_blob

            self.assertTrue(swapped["done"])
            self.assertIn(b"swapped base executed", swap_path.read_bytes())
            self.assertEqual(receipt["base_composer"]["git_blob"], approved_blob)
            compile(scheduler_out, "<strict-snapshot-scheduler>", "exec")
            compile(frozen_out, "<strict-snapshot-frozen>", "exec")

    def test_strict_current_loom_and_h3_preimages_compose_and_emit_receipts(self):
        so, fo, loom = strict.compose_pair(self.loom_scheduler_b, self.loom_frozen_b)
        so_h3, fo_h3, h3 = strict.compose_pair(self.loom_scheduler_b, self.h3_frozen_b)
        self.assertEqual(so, so_h3)
        self.assertNotEqual(fo, fo_h3)
        self.assertIn(strict.STRICT_MARKER.encode(), fo)
        self.assertIn(strict.STRICT_MARKER.encode(), fo_h3)
        compile(so, "<strict-scheduler-output>", "exec")
        compile(fo, "<strict-frozen-output>", "exec")
        compile(fo_h3, "<strict-frozen-h3-output>", "exec")
        self.assertTrue(loom["list_only_market_normalization"])
        self.assertTrue(h3["list_only_market_normalization"])
        print("PREFIX_STRICT_RECEIPT_LOOM=" + json.dumps(loom, sort_keys=True))
        print("PREFIX_STRICT_RECEIPT_H3=" + json.dumps(h3, sort_keys=True))

    def test_reapplication_refuses(self):
        with self.assertRaises(ValueError):
            strict._harden_frozen(self.strict_frozen, base)


if __name__ == "__main__":
    unittest.main()
