"""Receipt-plan regressions using synthetic plans and real CLI output files."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import reorder_assistant as app


class ReceiptPlanValidationTests(unittest.TestCase):
    def setUp(self):
        self.stock = {"ITEM": app.Stock("ITEM", "Example item", 2, 3, 1, "each")}
        self.plan = {
            "schema": app.SCHEMA,
            "purchase_orders": [{
                "supplier_id": "SUP", "lines": [{
                    "supplier_sku": "SUP-ITEM", "sku": "ITEM", "quantity": 3,
                }],
            }],
        }
        self.receipt = {
            "receipt_id": "R1", "received_at": "2026-09-08",
            "supplier_id": "SUP", "supplier_sku": "SUP-ITEM",
            "sku": "ITEM", "quantity": "1",
        }

    def reject(self, plan, message):
        stock_before = copy.deepcopy(self.stock)
        plan_before = copy.deepcopy(plan)
        with self.assertRaisesRegex(app.ReorderError, message):
            app.apply_receipts(self.stock, plan, [self.receipt])
        self.assertEqual(stock_before, self.stock)
        # NaN does not compare equal to itself; compare stable reprs instead.
        self.assertEqual(repr(plan_before), repr(plan))

    def quantity(self, value):
        plan = copy.deepcopy(self.plan)
        plan["purchase_orders"][0]["lines"][0]["quantity"] = value
        return plan

    def test_fractional_quantities_are_not_truncated(self):
        for value in (1.9, 2.5, "1.9", Decimal("2.5")):
            with self.subTest(value=value):
                self.reject(self.quantity(value), r"quantity.*integer")

    def test_boolean_quantities_are_not_one_or_zero(self):
        for value in (True, False):
            with self.subTest(value=value):
                self.reject(self.quantity(value), r"quantity.*integer")

    def test_nonpositive_quantities_are_rejected_even_without_receipts(self):
        for value in (0, -1, "0", "-2"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(app.ReorderError, r"quantity"):
                    app.apply_receipts(self.stock, self.quantity(value), [])

    def test_nonfinite_quantities_use_reorder_error(self):
        for value in (float("nan"), float("inf"), float("-inf"), "NaN", "Infinity"):
            with self.subTest(value=value):
                self.reject(self.quantity(value), r"quantity")

    def test_nonnumeric_quantities_use_reorder_error(self):
        for value in (None, [], {}, "many", ""):
            with self.subTest(value=value):
                self.reject(self.quantity(value), r"quantity")

    def test_missing_quantity_has_context(self):
        plan = self.quantity(3)
        del plan["purchase_orders"][0]["lines"][0]["quantity"]
        self.reject(plan, r"purchase_orders\[0\].lines\[0\].quantity")

    def test_root_must_be_an_object(self):
        for value in (None, [], "plan", 1, False):
            with self.subTest(value=value):
                self.reject(value, "plan must be an object")

    def test_schema_contract_is_preserved(self):
        for value in ({}, {"schema": "other"}, {"schema": []}):
            with self.subTest(value=value):
                self.reject(value, "plan schema is not supported")

    def test_purchase_orders_must_be_an_array(self):
        for value in (None, {}, "", 3, False):
            with self.subTest(value=value):
                self.reject({"schema": app.SCHEMA, "purchase_orders": value}, "purchase_orders must be an array")

    def test_each_order_must_be_an_object(self):
        for value in (None, [], "order", 3, False):
            with self.subTest(value=value):
                self.reject({"schema": app.SCHEMA, "purchase_orders": [value]}, r"purchase_orders\[0\] must be an object")

    def test_order_lines_must_be_an_array(self):
        for value in (None, {}, "", 3, False):
            with self.subTest(value=value):
                plan = copy.deepcopy(self.plan)
                plan["purchase_orders"][0]["lines"] = value
                self.reject(plan, r"lines must be an array")
        plan = copy.deepcopy(self.plan)
        del plan["purchase_orders"][0]["lines"]
        self.reject(plan, "lines must be an array")

    def test_each_line_must_be_an_object(self):
        for value in (None, [], "line", 3, False):
            with self.subTest(value=value):
                plan = copy.deepcopy(self.plan)
                plan["purchase_orders"][0]["lines"] = [value]
                self.reject(plan, r"lines\[0\] must be an object")

    def test_supplier_id_must_be_nonblank_text(self):
        for value in (None, "", "  ", 7, [], {}, True):
            with self.subTest(value=value):
                plan = copy.deepcopy(self.plan)
                plan["purchase_orders"][0]["supplier_id"] = value
                self.reject(plan, r"supplier_id must be a nonblank string")
        plan = copy.deepcopy(self.plan)
        del plan["purchase_orders"][0]["supplier_id"]
        self.reject(plan, "supplier_id must be a nonblank string")

    def test_line_identifiers_must_be_nonblank_text(self):
        for name in ("supplier_sku", "sku"):
            for value in (None, "", "  ", 7, [], {}, True):
                with self.subTest(name=name, value=value):
                    plan = copy.deepcopy(self.plan)
                    plan["purchase_orders"][0]["lines"][0][name] = value
                    self.reject(plan, name + " must be a nonblank string")
            plan = copy.deepcopy(self.plan)
            del plan["purchase_orders"][0]["lines"][0][name]
            self.reject(plan, name + " must be a nonblank string")

    def test_integral_legacy_quantities_remain_accepted(self):
        for value in (3, "3", " +3 ", 3.0):
            with self.subTest(value=value):
                updated, log = app.apply_receipts(self.stock, self.quantity(value), [self.receipt])
                self.assertEqual(updated["ITEM"].on_hand, 3)
                self.assertEqual(updated["ITEM"].on_order, 3)
                self.assertEqual(log["count"], 1)
                self.assertEqual(self.stock["ITEM"].on_hand, 2)

    def test_repeated_draft_lines_still_aggregate(self):
        plan = self.quantity(1)
        second = copy.deepcopy(plan["purchase_orders"][0])
        second["lines"][0]["quantity"] = 2
        plan["purchase_orders"].append(second)
        received = dict(self.receipt, quantity="3")
        updated, log = app.apply_receipts(self.stock, plan, [received])
        self.assertEqual(updated["ITEM"].on_hand, 5)
        self.assertEqual(log["count"], 1)
        with self.assertRaisesRegex(app.ReorderError, "exceeds drafted quantity"):
            app.apply_receipts(self.stock, plan, [dict(received, quantity="4")])

    def test_cumulative_receipts_and_pipeline_behavior_are_unchanged(self):
        receipts = [dict(self.receipt, quantity="2"), dict(self.receipt, receipt_id="R2")]
        updated, log = app.apply_receipts(self.stock, self.plan, receipts, pipeline_includes_draft=True)
        self.assertEqual((updated["ITEM"].on_hand, updated["ITEM"].on_order), (5, 0))
        self.assertTrue(log["pipeline_includes_draft"])
        self.assertEqual(log["count"], 2)
        with self.assertRaisesRegex(app.ReorderError, "exceeds drafted quantity"):
            app.apply_receipts(self.stock, self.plan, receipts + [dict(self.receipt, receipt_id="R3")])

    def test_duplicate_receipts_remain_rejected(self):
        with self.assertRaisesRegex(app.ReorderError, "duplicate receipt_id"):
            app.apply_receipts(self.stock, self.plan, [self.receipt, self.receipt])

    def test_all_draft_lines_are_validated_before_receipts(self):
        plan = copy.deepcopy(self.plan)
        plan["purchase_orders"][0]["lines"].append({"supplier_sku": "OTHER", "sku": "OTHER", "quantity": 1.9})
        self.reject(plan, r"lines\[1\].quantity")

    def test_identifiers_are_not_silently_normalized(self):
        plan = copy.deepcopy(self.plan)
        plan["purchase_orders"][0]["supplier_id"] = " SUP "
        with self.assertRaisesRegex(app.ReorderError, "not present in the draft"):
            app.apply_receipts(self.stock, plan, [self.receipt])
        # The landed history feature trims receipt fields; draft identifiers
        # still retain their exact spelling rather than being rewritten here.
        self.assertEqual(app._drafted_quantities(plan), {(" SUP ", "SUP-ITEM", "ITEM"): 3})

    def test_empty_legacy_plan_remains_a_noop(self):
        for plan in ({"schema": app.SCHEMA}, {"schema": app.SCHEMA, "purchase_orders": []}):
            updated, log = app.apply_receipts(self.stock, plan, [])
            self.assertEqual(updated, self.stock)
            self.assertEqual(log["count"], 0)

    def test_real_generated_plan_roundtrips_through_json(self):
        rules = {"ITEM": app.Rule("ITEM", 4, 7, "SUP")}
        offers = [app.Offer("SUP", "SUP-ITEM", "ITEM", "Example", Decimal("4.25"), 20, 2, "")]
        plan = app.build_plan(self.stock, rules, offers, "2026-09-08")
        plan = json.loads(json.dumps(plan))
        self.assertEqual(plan["purchase_orders"][0]["lines"][0]["quantity"], 3)
        updated, log = app.apply_receipts(self.stock, plan, [dict(self.receipt, quantity="3")])
        self.assertEqual(updated["ITEM"].on_hand, 5)
        self.assertEqual(plan["summary"]["orders_sent"], 0)
        self.assertEqual(log["applied_receipts"][0]["quantity"], 3)

    def test_landed_history_continuation_remains_compatible(self):
        first, log1 = app.apply_receipts(self.stock, self.plan, [self.receipt])
        receipt2 = dict(self.receipt, receipt_id="R2", quantity="2")
        second, log2 = app.apply_receipts(first, self.plan, [receipt2], prior_log=log1)
        self.assertEqual(second["ITEM"].on_hand, 5)
        self.assertEqual((log2["count"], log2["new_count"]), (2, 1))
        retried, retry_log = app.apply_receipts(second, self.plan, [receipt2], prior_log=log2)
        self.assertEqual(retried, second)
        self.assertEqual(retry_log["new_count"], 0)
        self.assertEqual(retry_log["replayed_receipt_ids"], ["R2"])
        with self.assertRaisesRegex(app.ReorderError, "exceeds drafted quantity"):
            app.apply_receipts(second, self.plan, [dict(self.receipt, receipt_id="R3")], prior_log=log2)
        with self.assertRaisesRegex(app.ReorderError, "quantity.*integer"):
            app.apply_receipts(second, self.quantity(1.9), [], prior_log=log2)
        # The history hash requires JSON-compatible plans; the intake helper
        # does not change that separate, already-landed contract.
        with self.assertRaisesRegex(app.ReorderError, "finite JSON values"):
            app.apply_receipts(self.stock, self.quantity(Decimal("3")), [self.receipt])

    def test_cli_rejects_bad_plan_without_touching_output_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stock, plan, receipts = root / "stock.csv", root / "plan.json", root / "receipts.csv"
            stock.write_text("sku,name,on_hand,on_order,allocated,unit\nITEM,Example item,2,3,1,each\n", encoding="utf-8")
            plan.write_text(json.dumps(self.quantity(1.9)), encoding="utf-8")
            receipts.write_text("receipt_id,received_at,supplier_id,supplier_sku,sku,quantity\nR1,2026-09-08,SUP,SUP-ITEM,ITEM,1\n", encoding="utf-8")
            out_stock, out_log = root / "updated.csv", root / "receipt-log.json"
            for preexisting in (False, True):
                with self.subTest(preexisting=preexisting):
                    if preexisting:
                        out_stock.write_bytes(b"previous stock\n")
                        out_log.write_bytes(b"previous log\n")
                    result = subprocess.run([
                        sys.executable, "-B", str(Path(app.__file__).resolve()), "receive",
                        "--stock", str(stock), "--plan", str(plan), "--receipts", str(receipts),
                        "--out-stock", str(out_stock), "--out-log", str(out_log),
                    ], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn("quantity must be an integer", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    if preexisting:
                        self.assertEqual(out_stock.read_bytes(), b"previous stock\n")
                        self.assertEqual(out_log.read_bytes(), b"previous log\n")
                    else:
                        self.assertFalse(out_stock.exists())
                        self.assertFalse(out_log.exists())


if __name__ == "__main__":
    unittest.main()
