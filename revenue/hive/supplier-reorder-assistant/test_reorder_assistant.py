import csv
import json
import tempfile
import unittest
from pathlib import Path

import reorder_assistant as app


class ReorderAssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write_csv(self, name, fields, rows):
        path = self.root / name
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def fixtures(self):
        stock = self.write_csv(
            "stock.csv",
            ["sku", "name", "on_hand", "on_order", "allocated", "unit"],
            [
                {"sku": "FILTER-A", "name": "Filter A", "on_hand": 3, "on_order": 0, "allocated": 2, "unit": "each"},
                {"sku": "BELT-B", "name": "Belt B", "on_hand": 2, "on_order": 3, "allocated": 0, "unit": "each"},
            ],
        )
        rules = self.write_csv(
            "rules.csv",
            ["sku", "reorder_at", "target_stock", "preferred_supplier"],
            [
                {"sku": "FILTER-A", "reorder_at": 2, "target_stock": 10, "preferred_supplier": "SUP-1"},
                {"sku": "BELT-B", "reorder_at": 5, "target_stock": 8, "preferred_supplier": "SUP-1"},
            ],
        )
        catalog = self.write_csv(
            "catalog.csv",
            ["supplier_id", "supplier_sku", "sku", "description", "unit_cost", "available_qty", "lead_days", "alternative_for_sku"],
            [
                {"supplier_id": "SUP-1", "supplier_sku": "FA-100", "sku": "FILTER-A", "description": "Filter A", "unit_cost": "4.25", "available_qty": 20, "lead_days": 2, "alternative_for_sku": ""},
                {"supplier_id": "SUP-1", "supplier_sku": "BB-200", "sku": "BELT-B", "description": "Belt B", "unit_cost": "9.00", "available_qty": 0, "lead_days": 2, "alternative_for_sku": ""},
                {"supplier_id": "SUP-2", "supplier_sku": "BB-X", "sku": "BELT-X", "description": "Possible Belt B substitute", "unit_cost": "8.50", "available_qty": 7, "lead_days": 3, "alternative_for_sku": "BELT-B"},
            ],
        )
        return stock, rules, catalog

    def test_low_stock_creates_correct_unsent_draft(self):
        stock, rules, catalog = self.fixtures()
        plan = app.build_plan(app.load_stock(stock), app.load_rules(rules), app.load_catalog(catalog), "2026-09-08")
        order = plan["purchase_orders"][0]
        self.assertEqual("DRAFT_NOT_SENT", order["status"])
        self.assertEqual("FILTER-A", order["lines"][0]["sku"])
        self.assertEqual(9, order["lines"][0]["quantity"])
        self.assertEqual("38.25", order["total"])
        self.assertEqual(0, plan["summary"]["orders_sent"])

    def test_out_of_stock_exact_item_only_flags_alternative(self):
        stock, rules, catalog = self.fixtures()
        plan = app.build_plan(app.load_stock(stock), app.load_rules(rules), app.load_catalog(catalog), "2026-09-08")
        exception = next(item for item in plan["exceptions"] if item["sku"] == "BELT-B")
        self.assertEqual(3, exception["unfilled_qty"])
        self.assertEqual("review_required_no_order_created", exception["action"])
        self.assertTrue(exception["alternative_suggestions"][0]["requires_approval"])
        ordered_skus = {line["sku"] for order in plan["purchase_orders"] for line in order["lines"]}
        self.assertNotIn("BELT-X", ordered_skus)

    def test_inventory_position_counts_pipeline_once(self):
        stock, rules, catalog = self.fixtures()
        plan = app.build_plan(app.load_stock(stock), app.load_rules(rules), app.load_catalog(catalog), "2026-09-08")
        belt = next(row for row in plan["evaluated"] if row["sku"] == "BELT-B")
        self.assertEqual(5, belt["inventory_position"])
        self.assertEqual(3, belt["requested_qty"])

    def test_receipt_updates_stock_and_logs_source(self):
        stock_path, rules, catalog = self.fixtures()
        stock = app.load_stock(stock_path)
        plan = app.build_plan(stock, app.load_rules(rules), app.load_catalog(catalog), "2026-09-08")
        receipts = [{"receipt_id": "R-1", "received_at": "2026-09-09", "supplier_id": "SUP-1", "supplier_sku": "FA-100", "sku": "FILTER-A", "quantity": "4", "_line": "2"}]
        updated, log = app.apply_receipts(stock, plan, receipts)
        self.assertEqual(7, updated["FILTER-A"].on_hand)
        self.assertEqual(0, updated["FILTER-A"].on_order)
        self.assertEqual("R-1", log["applied_receipts"][0]["receipt_id"])

    def test_receipt_preserves_unrelated_pipeline_by_default(self):
        stock_path, rules, catalog = self.fixtures()
        stock = app.load_stock(stock_path)
        stock["FILTER-A"] = app.Stock("FILTER-A", "Filter A", 3, 2, 4, "each")
        plan = app.build_plan(stock, app.load_rules(rules), app.load_catalog(catalog), "2026-09-08")
        receipts = [{"receipt_id": "R-P", "received_at": "2026-09-09", "supplier_id": "SUP-1", "supplier_sku": "FA-100", "sku": "FILTER-A", "quantity": "2", "_line": "2"}]
        preserved, _ = app.apply_receipts(stock, plan, receipts)
        consumed, log = app.apply_receipts(stock, plan, receipts, pipeline_includes_draft=True)
        self.assertEqual(2, preserved["FILTER-A"].on_order)
        self.assertEqual(0, consumed["FILTER-A"].on_order)
        self.assertTrue(log["pipeline_includes_draft"])

    def test_receipt_cannot_exceed_draft(self):
        stock_path, rules, catalog = self.fixtures()
        stock = app.load_stock(stock_path)
        plan = app.build_plan(stock, app.load_rules(rules), app.load_catalog(catalog), "2026-09-08")
        receipts = [{"receipt_id": "R-2", "received_at": "2026-09-09", "supplier_id": "SUP-1", "supplier_sku": "FA-100", "sku": "FILTER-A", "quantity": "10", "_line": "2"}]
        with self.assertRaisesRegex(app.ReorderError, "exceeds drafted quantity"):
            app.apply_receipts(stock, plan, receipts)

    def test_rules_reject_unknown_sku(self):
        stock, rules, catalog = self.fixtures()
        loaded_rules = app.load_rules(rules)
        loaded_rules["MISSING"] = app.Rule("MISSING", 1, 2, "SUP-1")
        with self.assertRaisesRegex(app.ReorderError, "unknown stock"):
            app.build_plan(app.load_stock(stock), loaded_rules, app.load_catalog(catalog), "2026-09-08")

    def test_command_outputs_are_json_and_csv(self):
        stock, rules, catalog = self.fixtures()
        plan_path = self.root / "plan.json"
        app.command_plan(type("Args", (), {"stock": stock, "rules": rules, "catalog": catalog, "as_of": "2026-09-08", "out": plan_path}))
        plan = json.loads(plan_path.read_text())
        receipts = self.write_csv(
            "receipts.csv",
            ["receipt_id", "received_at", "supplier_id", "supplier_sku", "sku", "quantity"],
            [{"receipt_id": "R-3", "received_at": "2026-09-09", "supplier_id": "SUP-1", "supplier_sku": "FA-100", "sku": "FILTER-A", "quantity": 2}],
        )
        out_stock, out_log = self.root / "updated.csv", self.root / "receipt-log.json"
        app.command_receive(type("Args", (), {"stock": stock, "plan": plan_path, "receipts": receipts, "out_stock": out_stock, "out_log": out_log, "pipeline_includes_draft": False}))
        self.assertIn("FILTER-A", out_stock.read_text())
        self.assertEqual(1, json.loads(out_log.read_text())["count"])

    def test_plan_rejects_non_iso_date(self):
        stock, rules, catalog = self.fixtures()
        with self.assertRaisesRegex(app.ReorderError, "ISO date"):
            app.build_plan(app.load_stock(stock), app.load_rules(rules), app.load_catalog(catalog), "today")


if __name__ == "__main__":
    unittest.main()
