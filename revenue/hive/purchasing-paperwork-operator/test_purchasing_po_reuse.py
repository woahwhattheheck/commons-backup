"""Real CSV/CLI regressions for repeated PO-line references within one batch.

Synthetic inputs only. No network calls, external accounting writes, or payment.
Place alongside purchasing_operator.py, then run python -m unittest -v.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import purchasing_operator as app


PO = dict(po_number="PO-100", po_line="1", supplier_id="SUP-1",
          po_date="2026-09-01", currency="USD", sku="FILTER-A",
          description="Synthetic filter", quantity="4", unit_price="12.50")
INVOICE = dict(invoice_number="INV-A", line_number="1", vendor_name="Acme",
               invoice_date="2026-09-07", due_date="2026-10-07", currency="USD",
               po_number="PO-100", po_line="1", sku="FILTER-A",
               description="Synthetic filter", quantity="4", unit_price="12.50")


class POReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_csv(self, name, fields, rows):
        path = self.root / name
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def inputs(self, invoice_overrides=({},), po_overrides=({},)):
        vendors = self.write_csv("vendors.csv", ["supplier_id", "canonical_name", "aliases"], [
            dict(supplier_id="SUP-1", canonical_name="Acme Industrial", aliases="Acme|ACME LLC")])
        pos = self.write_csv("purchase_orders.csv", list(PO), [{**PO, **x} for x in po_overrides])
        invoices = self.write_csv("invoices.csv", list(INVOICE), [{**INVOICE, **x} for x in invoice_overrides])
        return vendors, pos, invoices

    def run_case(self, invoice_overrides=({},), po_overrides=({},)):
        inputs = self.inputs(invoice_overrides, po_overrides)
        before = {p: p.read_bytes() for p in inputs}
        paths = app.run(*inputs, self.root / "out")
        self.assertEqual(before, {p: p.read_bytes() for p in inputs})
        report = json.loads(paths["report"].read_text(encoding="utf-8"))
        drafts = json.loads(paths["drafts"].read_text(encoding="utf-8"))["drafts"]
        with paths["accounting"].open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(app.ACCOUNTING_FIELDS, reader.fieldnames)
            accounting = list(reader)
        self.assertEqual(0, report["summary"]["accounting_rows_posted"])
        self.assertEqual(0, report["summary"]["drafts_sent"])
        self.assertEqual(len(report["records"]), len(accounting) + len(drafts))
        return report, accounting, drafts

    def assert_held(self, report, accounting, drafts, count):
        self.assertEqual([], accounting, "reused PO lines must not reach accounting export")
        self.assertEqual(count, len(drafts))
        self.assertEqual(0, report["summary"]["matched_lines"])
        self.assertEqual(count, report["summary"]["exception_lines"])
        issue = f"po_line_reused_in_batch:count={count}"
        for record, draft in zip(report["records"], drafts):
            self.assertEqual("EXCEPTION_REVIEW_REQUIRED", record["status"])
            self.assertIn(issue, record["issues"])
            self.assertEqual("DRAFT_NOT_SENT", draft["status"])
            self.assertIn(issue, draft["issues"])

    def test_single_full_invoice_remains_review_ready(self):
        report, rows, drafts = self.run_case()
        self.assertEqual(1, len(rows))
        self.assertEqual("50.00", rows[0]["line_total"])
        self.assertEqual([], report["records"][0]["issues"])
        self.assertEqual([], drafts)

    def test_two_distinct_invoices_cannot_both_consume_same_po_line(self):
        self.assert_held(*self.run_case([{}, {"invoice_number": "INV-B"}]), 2)

    def test_two_distinct_lines_of_one_invoice_are_both_held(self):
        self.assert_held(*self.run_case([{}, {"line_number": "2"}]), 2)

    def test_three_references_report_full_count(self):
        self.assert_held(*self.run_case([{"invoice_number": x} for x in ("A", "B", "C")]), 3)

    def test_unrelated_po_line_remains_exportable(self):
        report, rows, drafts = self.run_case(
            [{}, {"invoice_number": "INV-B"}, {"invoice_number": "INV-C", "po_line": "2"}],
            [{}, {"po_line": "2"}])
        self.assertEqual(["INV-C"], [row["invoice_number"] for row in rows])
        self.assertEqual(2, len(drafts))
        self.assertEqual(1, report["summary"]["matched_lines"])

    def test_different_pos_with_same_line_number_do_not_collide(self):
        report, rows, drafts = self.run_case(
            [{}, {"invoice_number": "INV-B", "po_number": "PO-200"}],
            [{}, {"po_number": "PO-200"}])
        self.assertEqual(2, len(rows))
        self.assertEqual([], drafts)

    def test_same_po_with_different_line_numbers_does_not_collide(self):
        report, rows, drafts = self.run_case(
            [{}, {"line_number": "2", "po_line": "2"}], [{}, {"po_line": "2"}])
        self.assertEqual(2, len(rows))
        self.assertEqual([], drafts)

    def test_tuple_keys_do_not_alias_delimiter_characters(self):
        _, rows, drafts = self.run_case(
            [{"po_number": "A|B", "po_line": "C"},
             {"invoice_number": "INV-B", "po_number": "A", "po_line": "B|C"}],
            [{"po_number": "A|B", "po_line": "C"}, {"po_number": "A", "po_line": "B|C"}])
        self.assertEqual(2, len(rows))
        self.assertEqual([], drafts)

    def test_repeated_missing_po_keeps_existing_missing_reference_error(self):
        report, rows, drafts = self.run_case(
            [{"po_number": "MISSING"}, {"invoice_number": "INV-B", "po_number": "MISSING"}])
        self.assertEqual([], rows)
        self.assertEqual(2, len(drafts))
        for record in report["records"]:
            self.assertEqual(["po_line_not_found"], record["issues"])

    def test_vendor_aliases_do_not_hide_po_reuse(self):
        self.assert_held(*self.run_case([{}, {"invoice_number": "INV-B", "vendor_name": "ACME LLC"}]), 2)

    def test_existing_quantity_mismatch_is_preserved(self):
        result = self.run_case([{}, {"invoice_number": "INV-B", "quantity": "5"}])
        self.assert_held(*result, 2)
        self.assertIn("quantity_mismatch:invoice=5,po=4", result[0]["records"][1]["issues"])

    def test_unknown_vendor_does_not_choose_an_automatic_winner(self):
        result = self.run_case([{}, {"invoice_number": "INV-B", "vendor_name": "Unknown"}])
        self.assert_held(*result, 2)
        self.assertIn("vendor_unmatched", result[0]["records"][1]["issues"])

    def test_partial_invoices_stay_explicit_review_not_silent_allocation(self):
        result = self.run_case([{"quantity": "2"}, {"invoice_number": "INV-B", "quantity": "2"}])
        self.assert_held(*result, 2)
        for record in result[0]["records"]:
            self.assertIn("quantity_mismatch:invoice=2,po=4", record["issues"])

    def test_drafts_keep_original_hashes_and_physical_csv_lines(self):
        result = self.run_case([{"description": "First line\nsecond line"}, {"invoice_number": "INV-B"}])
        self.assert_held(*result, 2)
        report, _, drafts = result
        digest = hashlib.sha256((self.root / "invoices.csv").read_bytes()).hexdigest()
        self.assertEqual([2, 4], [row["invoice_source"]["line"] for row in report["records"]])
        self.assertEqual([2, 4], [draft["sources"][0]["line"] for draft in drafts])
        for draft in drafts:
            self.assertEqual(digest, draft["sources"][0]["sha256"])
            self.assertEqual(2, draft["sources"][1]["line"])

    def test_cli_export_has_only_header_for_reused_po(self):
        paths = self.inputs([{}, {"invoice_number": "INV-B"}])
        result = subprocess.run(
            [sys.executable, str(Path(app.__file__).resolve()), "--vendors", str(paths[0]),
             "--purchase-orders", str(paths[1]), "--invoices", str(paths[2]),
             "--out-dir", str(self.root / "cli-out")],
            capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        output = json.loads(result.stdout)
        with Path(output["accounting"]).open(newline="", encoding="utf-8") as handle:
            self.assertEqual([], list(csv.DictReader(handle)))
        report = json.loads(Path(output["report"]).read_text())
        self.assertEqual(2, report["summary"]["exception_lines"])
        self.assertEqual("RECONCILED_NOT_POSTED", report["status"])

    def test_all_permutations_hold_every_colliding_line_without_first_winner(self):
        invoices = [{}, {"invoice_number": "INV-B"},
                    {"invoice_number": "INV-C", "po_line": "2"}]
        for order in itertools.permutations(invoices):
            with self.subTest(order=order):
                report, rows, drafts = self.run_case(order, [{}, {"po_line": "2"}])
                self.assertEqual(["INV-C"], [row["invoice_number"] for row in rows])
                self.assertEqual({"INV-A", "INV-B"}, {draft["invoice_number"] for draft in drafts})
                self.assertEqual([row.get("invoice_number", "INV-A") for row in order],
                                 [row["invoice_number"] for row in report["records"]])

    def test_empty_invoice_batch_keeps_valid_empty_outputs(self):
        report, rows, drafts = self.run_case([])
        self.assertEqual([], report["records"])
        self.assertEqual([], rows)
        self.assertEqual([], drafts)

    def test_rerun_is_byte_deterministic(self):
        inputs = self.inputs([{}, {"invoice_number": "INV-B"}])
        first = app.run(*inputs, self.root / "out")
        before = {key: path.read_bytes() for key, path in first.items()}
        second = app.run(*inputs, self.root / "out")
        self.assertEqual(before, {key: path.read_bytes() for key, path in second.items()})

    def test_duplicate_invoice_identity_is_still_a_loader_error(self):
        inputs = self.inputs([{}, {}])
        out = self.root / "out"
        out.mkdir()
        old = out / "reconciliation.json"
        old.write_text("preserve previous output\n")
        with self.assertRaisesRegex(app.PurchasingError, "duplicate invoice line"):
            app.run(*inputs, out)
        self.assertEqual("preserve previous output\n", old.read_text())

    def test_no_cross_batch_payment_ledger_is_claimed_or_introduced(self):
        first = self.run_case([{}])
        second = self.run_case([{"invoice_number": "INV-B"}])
        self.assertEqual(1, len(first[1]))
        self.assertEqual(1, len(second[1]))

    def test_two_independent_reuse_groups_are_all_held(self):
        report, rows, drafts = self.run_case(
            [{}, {"invoice_number": "INV-B"},
             {"invoice_number": "INV-C", "po_line": "2"},
             {"invoice_number": "INV-D", "po_line": "2"}], [{}, {"po_line": "2"}])
        self.assertEqual([], rows)
        self.assertEqual(4, len(drafts))
        for record in report["records"]:
            self.assertIn("po_line_reused_in_batch:count=2", record["issues"])


    def test_peer_unicode_vendor_matching_is_retained(self):
        self.assertEqual("café", app._name_key("CAFÉ"))
        self.assertEqual(app._name_key("Café"), app._name_key("Cafe\u0301"))
        self.assertNotEqual(app._name_key("Café"), app._name_key("Cafe"))
        self.assertEqual("供应商", app._name_key("供应商"))

    def test_peer_output_input_alias_guard_is_retained(self):
        inputs = list(self.inputs())
        replacement = self.root / "accounting_import.csv"
        inputs[2].rename(replacement)
        inputs[2] = replacement
        before = {path: path.read_bytes() for path in inputs}
        with self.assertRaisesRegex(app.PurchasingError, "overlaps input"):
            app.run(*inputs, self.root)
        self.assertEqual(before, {path: path.read_bytes() for path in inputs})
        self.assertFalse((self.root / "reconciliation.json").exists())

    def test_peer_symlink_source_alias_guard_is_retained(self):
        inputs = self.inputs()
        out = self.root / "out"
        out.mkdir()
        alias = out / "exception_drafts.json"
        alias.symlink_to(inputs[0])
        before = {path: path.read_bytes() for path in inputs}
        with self.assertRaisesRegex(app.PurchasingError, "overlaps input"):
            app.run(*inputs, out)
        self.assertEqual(before, {path: path.read_bytes() for path in inputs})
        self.assertTrue(alias.is_symlink())
        self.assertFalse((out / "reconciliation.json").exists())

    def test_peer_hardlink_source_alias_guard_is_retained(self):
        inputs = self.inputs()
        out = self.root / "out"
        out.mkdir()
        alias = out / "reconciliation.json"
        alias.hardlink_to(inputs[1])
        before = {path: path.read_bytes() for path in inputs}
        with self.assertRaisesRegex(app.PurchasingError, "overlaps input"):
            app.run(*inputs, out)
        self.assertEqual(before, {path: path.read_bytes() for path in inputs})
        self.assertFalse((out / "accounting_import.csv").exists())

    def test_peer_output_to_output_alias_guard_is_retained(self):
        inputs = self.inputs()
        out = self.root / "out"
        out.mkdir()
        report = out / "reconciliation.json"
        report.write_text("existing report\n")
        (out / "exception_drafts.json").hardlink_to(report)
        with self.assertRaisesRegex(app.PurchasingError, "overlaps output"):
            app.run(*inputs, out)
        self.assertEqual("existing report\n", report.read_text())
        self.assertFalse((out / "accounting_import.csv").exists())

    def test_correction_then_rerun_releases_remaining_single_invoice(self):
        self.assert_held(*self.run_case([{}, {"invoice_number": "INV-B"}]), 2)
        report, rows, drafts = self.run_case([{}])
        self.assertEqual(1, len(rows))
        self.assertEqual("INV-A", rows[0]["invoice_number"])
        self.assertEqual([], drafts)
        self.assertEqual(0, report["summary"]["exception_lines"])

    def test_currency_mismatch_is_not_hidden_by_reuse(self):
        result = self.run_case([{}, {"invoice_number": "INV-B", "currency": "EUR"}])
        self.assert_held(*result, 2)
        self.assertIn("currency_mismatch:invoice=EUR,po=USD", result[0]["records"][1]["issues"])

    def test_price_mismatch_is_not_hidden_by_reuse(self):
        result = self.run_case([{}, {"invoice_number": "INV-B", "unit_price": "12.51"}])
        self.assert_held(*result, 2)
        self.assertIn("unit_price_mismatch:invoice=12.51,po=12.50", result[0]["records"][1]["issues"])


if __name__ == "__main__":
    unittest.main()
