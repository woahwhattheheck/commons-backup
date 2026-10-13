from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
import unittest

import materialize
from slot_reservation import (
    LedgerError,
    build_witness,
    planned_slot_reservations,
    predecessor_feasible,
    reservation_aware_feasible,
    settle_current_extras,
)


ORDERS_9 = [["BUY_SEED", "WHEAT", 1] for _ in range(9)]


class ReservationSemanticsTests(unittest.TestCase):
    def test_current_predecessor_admits_detached_chosen_plan(self):
        self.assertTrue(predecessor_feasible(orders=ORDERS_9, cap=10, item="MILK", quantity=1))
        emitted = settle_current_extras(
            orders=ORDERS_9,
            cap=10,
            desired={"CARROT": 1, "MILK": 1},
            available={"CARROT": 1, "MILK": 1},
        )
        products = [row[1] for row in emitted if row and row[0] == "SELL"]
        self.assertEqual(products, ["CARROT"])
        self.assertNotIn("MILK", products)

    def test_current_successor_reserves_due_other_product(self):
        decision = reservation_aware_feasible(
            orders=ORDERS_9,
            cap=10,
            item="MILK",
            quantity=1,
            planned={"CARROT": [(100, 1)]},
            now=100,
            step=100,
            current_quantities={"CARROT": 1, "MILK": 1},
        )
        self.assertFalse(decision.feasible)
        self.assertEqual(decision.prior_reservations, 1)
        self.assertEqual(decision.reason, "SLOT_RESERVED")

    def test_future_successor_prevents_two_calls_claiming_same_slot(self):
        decision = reservation_aware_feasible(
            orders=ORDERS_9,
            cap=10,
            item="MILK",
            quantity=1,
            planned={"CARROT": [(101, 1)]},
            now=100,
            step=101,
        )
        self.assertFalse(decision.feasible)

    def test_two_free_rows_support_prior_and_candidate(self):
        decision = reservation_aware_feasible(
            orders=ORDERS_9[:8],
            cap=10,
            item="MILK",
            quantity=1,
            planned={"CARROT": [(101, 1)]},
            now=100,
            step=101,
        )
        self.assertTrue(decision.feasible)
        self.assertEqual(decision.reason, "FREE_RESERVED_SLOT")

    def test_same_item_plan_is_replaced_not_double_reserved(self):
        count = planned_slot_reservations(
            {"MILK": [(101, 4)]}, candidate_item="MILK", now=100, step=101
        )
        self.assertEqual(count, 0)
        decision = reservation_aware_feasible(
            orders=ORDERS_9,
            cap=10,
            item="MILK",
            quantity=4,
            planned={"MILK": [(101, 4)]},
            now=100,
            step=101,
        )
        self.assertTrue(decision.feasible)

    def test_inherited_same_item_row_needs_no_new_slot(self):
        orders = ORDERS_9 + [["SELL", "MILK", 2]]
        decision = reservation_aware_feasible(
            orders=orders,
            cap=10,
            item="MILK",
            quantity=2,
            planned={"CARROT": [(100, 1)]},
            now=100,
            step=100,
            current_quantities={"CARROT": 1, "MILK": 2},
        )
        self.assertTrue(decision.feasible)
        self.assertFalse(decision.candidate_needs_extra_row)
        self.assertEqual(decision.reason, "INHERITED_ROW")

    def test_inherited_row_growth_still_needs_slot(self):
        orders = ORDERS_9 + [["SELL", "MILK", 1]]
        decision = reservation_aware_feasible(
            orders=orders,
            cap=10,
            item="MILK",
            quantity=2,
            planned={},
            now=100,
            step=100,
        )
        self.assertFalse(decision.feasible)

    def test_overdue_row_reserves_current_and_future_until_retired(self):
        planned = {"CARROT": [(98, 1)]}
        self.assertEqual(planned_slot_reservations(planned, candidate_item="MILK", now=100, step=100), 1)
        self.assertEqual(planned_slot_reservations(planned, candidate_item="MILK", now=100, step=101), 1)

    def test_future_due_boundary_and_later_retention(self):
        planned = {"CARROT": [(102, 1)]}
        self.assertEqual(planned_slot_reservations(planned, candidate_item="MILK", now=100, step=101), 0)
        self.assertEqual(planned_slot_reservations(planned, candidate_item="MILK", now=100, step=102), 1)
        self.assertEqual(planned_slot_reservations(planned, candidate_item="MILK", now=100, step=103), 1)

    def test_multiple_rows_one_product_consume_one_slot(self):
        planned = {"CARROT": [(101, 1), (101, 2)]}
        self.assertEqual(planned_slot_reservations(planned, candidate_item="MILK", now=100, step=101), 1)

    def test_zero_quantity_does_not_reserve(self):
        self.assertEqual(planned_slot_reservations({"CARROT": [(101, 0)]}, candidate_item="MILK", now=100, step=101), 0)

    def test_each_other_product_reserves_one(self):
        planned = {"CARROT": [(101, 1)], "EGG": [(101, 9)], "MILK": [(101, 5)]}
        self.assertEqual(planned_slot_reservations(planned, candidate_item="MILK", now=100, step=101), 2)


    def test_zero_stock_other_product_does_not_reserve_current(self):
        count = planned_slot_reservations(
            {"CARROT": [(100, 1)]},
            candidate_item="MILK",
            now=100,
            step=100,
            current_quantities={"MILK": 1},
            orders=ORDERS_9,
        )
        self.assertEqual(count, 0)

    def test_zero_stock_other_product_still_reserves_future(self):
        count = planned_slot_reservations(
            {"CARROT": [(101, 1)]},
            candidate_item="MILK",
            now=100,
            step=101,
            current_quantities={"MILK": 1},
            orders=ORDERS_9,
        )
        self.assertEqual(count, 1)

    def test_inherited_other_product_row_can_absorb_due_quantity(self):
        orders = ORDERS_9 + [["SELL", "CARROT", 2]]
        count = planned_slot_reservations(
            {"CARROT": [(100, 1)]},
            candidate_item="MILK",
            now=100,
            step=100,
            current_quantities={"CARROT": 2, "MILK": 1},
            orders=orders,
        )
        self.assertEqual(count, 0)

    def test_malformed_ledger_fails_closed(self):
        bad = [
            {"CARROT": "101,1"},
            {"CARROT": [(101,)]},
            {"CARROT": [(True, 1)]},
            {"CARROT": [(101, -1)]},
        ]
        for planned in bad:
            with self.subTest(planned=planned):
                with self.assertRaises(LedgerError):
                    planned_slot_reservations(planned, candidate_item="MILK", now=100, step=101)

    def test_witness_is_deterministic_and_discriminating(self):
        first = build_witness()
        second = build_witness()
        self.assertEqual(first, second)
        self.assertTrue(first["current_turn"]["predecessor_admits"])
        self.assertFalse(first["current_turn"]["successor"]["feasible"])
        self.assertFalse(first["current_turn"]["chosen_item_emitted"])
        self.assertTrue(first["future_turn"]["predecessor_admits"])
        self.assertFalse(first["future_turn"]["successor"]["feasible"])
        self.assertTrue(first["overdue_future_turn"]["predecessor_admits"])
        self.assertFalse(first["overdue_future_turn"]["successor"]["feasible"])


class MaterializerTests(unittest.TestCase):
    def fixture(self) -> str:
        return """def prefix():\n    return 1\n\n\nclass SellScheduler:\n    def act(self, base, route, config, now, item):\n        def receipt_feasible(plan):return True\n        if True:\n            def feasible(plan):\n                for t,q in plan:\n                    if q<=0:continue\n                    orders=base['market'] if t==now else route[t].get('market',[]) if t<len(route) else []\n                    if len(orders)>=int(config.get('maxMarketOrdersPerTurn',10)):\n                        offered=sum(max(0,int(o[2])) for o in orders if o and o[0]=='SELL' and o[1]==item)\n                        if q>offered:return False\n                return receipt_feasible(plan)\n            return feasible\n"""

    def test_patch_is_unique_parseable_and_nonempty(self):
        source = self.fixture()
        patched = materialize.patch_source(source, expected_blob=None)
        ast.parse(patched)
        self.assertNotEqual(source, patched)
        self.assertEqual(patched.count("def _planned_slot_reservations("), 1)
        self.assertIn("len(orders)+reserved", patched)

    def test_duplicate_patch_is_rejected(self):
        patched = materialize.patch_source(self.fixture(), expected_blob=None)
        with self.assertRaises(ValueError):
            materialize.patch_source(patched, expected_blob=None)

    def test_ambiguous_preimage_is_rejected(self):
        source = self.fixture()
        duplicated = source + "\n" + materialize.OLD_BLOCK + "\n"
        with self.assertRaises(ValueError):
            materialize.patch_source(duplicated, expected_blob=None)

    def test_wrong_blob_is_rejected(self):
        with self.assertRaises(ValueError):
            materialize.patch_source(self.fixture(), expected_blob="0" * 40)

    def test_cli_paths_are_distinct_and_receipt_is_stable_shape(self):
        # Exercise deterministic receipt primitives without bypassing exact CLI
        # source binding, which is covered on the repository checkout in CI.
        source = self.fixture().encode()
        patched = materialize.patch_source(source.decode(), expected_blob=None).encode()
        self.assertNotEqual(materialize.git_blob_sha(source), materialize.git_blob_sha(patched))
        self.assertEqual(len(materialize.sha256(source)), 64)
        self.assertEqual(len(materialize.sha256(patched)), 64)


if __name__ == "__main__":
    unittest.main()
