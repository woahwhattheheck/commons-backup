import csv
import json
import tempfile
import unittest
from pathlib import Path

import purchasing_operator as app


class PurchasingOperatorTests(unittest.TestCase):
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

    def fixtures(self, invoice_overrides=None):
        vendors = self.write_csv("vendors.csv", ["supplier_id", "canonical_name", "aliases"], [
            {"supplier_id": "SUP-1", "canonical_name": "Acme Industrial LLC", "aliases": "Acme|ACME Industrial"},
        ])
        pos = self.write_csv("purchase_orders.csv", ["po_number", "po_line", "supplier_id", "po_date", "currency", "sku", "description", "quantity", "unit_price"], [
            {"po_number": "PO-100", "po_line": "1", "supplier_id": "SUP-1", "po_date": "2026-09-01", "currency": "USD", "sku": "FILTER-A", "description": "Filter A", "quantity": "4", "unit_price": "12.50"},
        ])
        invoice = {"invoice_number": "INV-9", "line_number": "1", "vendor_name": "Acme", "invoice_date": "2026-09-07", "due_date": "2026-10-07", "currency": "USD", "po_number": "PO-100", "po_line": "1", "sku": "FILTER-A", "description": "Filter A", "quantity": "4", "unit_price": "12.50"}
        invoice.update(invoice_overrides or {})
        invoices = self.write_csv("invoices.csv", ["invoice_number", "line_number", "vendor_name", "invoice_date", "due_date", "currency", "po_number", "po_line", "sku", "description", "quantity", "unit_price"], [invoice])
        return vendors, pos, invoices

    def reconcile(self, overrides=None):
        vendors, pos, invoices = self.fixtures(overrides)
        vendor_ref, po_ref, invoice_ref = app._source(vendors), app._source(pos), app._source(invoices)
        vendor_map, names = app.load_vendors(vendors)
        return app.reconcile(vendor_map, names, app.load_purchase_orders(pos), app.load_invoices(invoices), vendors_source=vendor_ref, po_source=po_ref, invoice_source=invoice_ref)

    def test_exact_invoice_and_po_match(self):
        report, accounting, drafts = self.reconcile()
        self.assertEqual("MATCHED_REVIEW_READY", report["records"][0]["status"])
        self.assertEqual("50.00", accounting[0]["line_total"])
        self.assertEqual("REVIEW_READY_NOT_POSTED", accounting[0]["status"])
        self.assertEqual([], drafts)

    def test_quantity_discrepancy_becomes_unsent_draft(self):
        report, accounting, drafts = self.reconcile({"quantity": "5"})
        self.assertEqual([], accounting)
        self.assertIn("quantity_mismatch:invoice=5,po=4", report["records"][0]["issues"])
        self.assertEqual("DRAFT_NOT_SENT", drafts[0]["status"])

    def test_price_discrepancy_is_exact_decimal_comparison(self):
        report, accounting, drafts = self.reconcile({"unit_price": "12.51"})
        self.assertEqual([], accounting)
        self.assertIn("unit_price_mismatch:invoice=12.51,po=12.50", drafts[0]["issues"])

    def test_unknown_vendor_is_review_only(self):
        report, accounting, drafts = self.reconcile({"vendor_name": "Unknown Parts"})
        self.assertEqual([], accounting)
        self.assertEqual("", report["records"][0]["supplier_id"])
        self.assertIn("vendor_unmatched", drafts[0]["issues"])

    def test_ambiguous_alias_is_review_only(self):
        vendors, pos, invoices = self.fixtures()
        with vendors.open("a", encoding="utf-8") as handle:
            handle.write("SUP-2,Other Supplier,Acme\n")
        vendor_map, names = app.load_vendors(vendors)
        report, accounting, drafts = app.reconcile(vendor_map, names, app.load_purchase_orders(pos), app.load_invoices(invoices), vendors_source=app._source(vendors), po_source=app._source(pos), invoice_source=app._source(invoices))
        self.assertEqual([], accounting)
        self.assertEqual("vendor_ambiguous:SUP-1|SUP-2", drafts[0]["issues"][0])

    def test_missing_po_line_is_actionable(self):
        report, accounting, drafts = self.reconcile({"po_line": "99"})
        self.assertEqual([], accounting)
        self.assertIn("po_line_not_found", drafts[0]["issues"])
        self.assertEqual("review sources, correct or approve, then rerun reconciliation", drafts[0]["recommended_action"])

    def test_originals_remain_hash_linked(self):
        report, accounting, drafts = self.reconcile({"quantity": "5"})
        sources = report["sources"]
        self.assertEqual(64, len(sources["invoices"]["sha256"]))
        self.assertEqual(sources["invoices"]["sha256"], report["records"][0]["invoice_source"]["sha256"])
        self.assertEqual(2, drafts[0]["sources"][0]["line"])
        self.assertEqual(sources["purchase_orders"]["sha256"], drafts[0]["sources"][1]["sha256"])

    def test_duplicate_invoice_line_rejected(self):
        vendors, pos, invoices = self.fixtures()
        text = invoices.read_text()
        invoices.write_text(text + text.splitlines()[-1] + "\n")
        with self.assertRaisesRegex(app.PurchasingError, "duplicate invoice line"):
            app.load_invoices(invoices)

    def test_run_writes_valid_outputs_without_posting(self):
        vendors, pos, invoices = self.fixtures({"unit_price": "13.00"})
        paths = app.run(vendors, pos, invoices, self.root / "out")
        report = json.loads(paths["report"].read_text())
        drafts = json.loads(paths["drafts"].read_text())
        self.assertEqual(0, report["summary"]["accounting_rows_posted"])
        self.assertEqual(0, report["summary"]["drafts_sent"])
        self.assertEqual(1, len(drafts["drafts"]))
        with paths["accounting"].open(newline="") as handle:
            self.assertEqual([], list(csv.DictReader(handle)))


if __name__ == "__main__":
    unittest.main()
