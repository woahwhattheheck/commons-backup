"""Unicode supplier identity through actual CSV loading and reconciliation."""

import csv
import hashlib
import re
import tempfile
import unittest
from pathlib import Path

import purchasing_operator as app


class VendorNameUnicodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def csv_file(self, name, fields, rows):
        path = self.root / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def reconcile(self, vendor_rows, invoice_name, supplier="S-1"):
        vendors_path = self.csv_file(
            "vendors.csv", ["supplier_id", "canonical_name", "aliases"],
            [dict(supplier_id=sid, canonical_name=name, aliases=aliases)
             for sid, name, aliases in vendor_rows],
        )
        po_path = self.csv_file(
            "purchase_orders.csv",
            ["po_number", "po_line", "supplier_id", "po_date", "currency", "sku", "description", "quantity", "unit_price"],
            [dict(po_number="PO-1", po_line="1", supplier_id=supplier, po_date="2026-09-08",
                  currency="USD", sku="PART-1", description="Sample part", quantity="2", unit_price="7.25")],
        )
        invoice_path = self.csv_file(
            "invoices.csv",
            ["invoice_number", "line_number", "vendor_name", "invoice_date", "due_date", "currency",
             "po_number", "po_line", "sku", "description", "quantity", "unit_price"],
            [dict(invoice_number="INV-1", line_number="1", vendor_name=invoice_name,
                  invoice_date="2026-09-08", due_date="2026-10-08", currency="USD", po_number="PO-1",
                  po_line="1", sku="PART-1", description="Sample part", quantity="2", unit_price="7.25")],
        )
        vendors, names = app.load_vendors(vendors_path)
        report, accounting, drafts = app.reconcile(
            vendors, names, app.load_purchase_orders(po_path), app.load_invoices(invoice_path),
            vendors_source=app._source(vendors_path), po_source=app._source(po_path),
            invoice_source=app._source(invoice_path),
        )
        self.assertEqual(0, report["summary"]["accounting_rows_posted"])
        self.assertEqual(0, report["summary"]["drafts_sent"])
        self.assertEqual(hashlib.sha256(invoice_path.read_bytes()).hexdigest(),
                         report["records"][0]["invoice_source"]["sha256"])
        return vendors, report, accounting, drafts

    def assert_matched(self, result, supplier="S-1"):
        _, report, accounting, drafts = result
        self.assertEqual("MATCHED_REVIEW_READY", report["records"][0]["status"])
        self.assertEqual(supplier, report["records"][0]["supplier_id"])
        self.assertEqual("14.50", accounting[0]["line_total"])
        self.assertEqual("REVIEW_READY_NOT_POSTED", accounting[0]["status"])
        self.assertEqual([], drafts)

    def test_ascii_contract_is_unchanged(self):
        names = ["ACME, Inc.", "  ACME__PARTS-42  ", "O'Reilly / Co.", "a.b+c @ d",
                 "".join(chr(number) for number in range(128))]
        for name in names:
            with self.subTest(name=name):
                legacy = " ".join(re.findall(r"[a-z0-9]+", name.casefold()))
                self.assertEqual(legacy, app._name_key(name))

    def test_japanese_letters_are_not_discarded(self):
        self.assertEqual("東京商店", app._name_key("東京商店"))

    def test_arabic_letters_are_not_discarded(self):
        self.assertEqual("شركة النور", app._name_key("شركة النور"))

    def test_canonical_composition_and_casefold_agree(self):
        pairs = [("Café Parts", "CAFE\u0301 PARTS"), ("Å Parts", "A\u030a PARTS"),
                 ("ΟΣ", "ος"), ("Straße", "STRASSE")]
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                self.assertEqual(app._name_key(left), app._name_key(right))

    def test_accents_do_not_collapse_into_ascii_names(self):
        self.assertNotEqual(app._name_key("Café"), app._name_key("Caf"))
        self.assertNotEqual(app._name_key("Café"), app._name_key("Cafe"))

    def test_indic_vowel_marks_are_preserved(self):
        self.assertEqual("कमाल", app._name_key("कमाल"))
        self.assertNotEqual(app._name_key("कमल"), app._name_key("कमाल"))

    def test_non_ascii_punctuation_keeps_word_boundaries(self):
        self.assertEqual("café pièces 42", app._name_key("  CAFÉ—PIÈCES／42  "))

    def test_punctuation_and_orphan_marks_do_not_create_names(self):
        for name in ("", " — / _ ", "\u0301\u0308"):
            with self.subTest(name=name):
                self.assertEqual("", app._name_key(name))

    def test_non_latin_vendor_reaches_review_ready_through_real_csv(self):
        for name in ("東京商店", "شركة النور", "부품 상점"):
            with self.subTest(name=name):
                result = self.reconcile([("S-1", name, "")], name)
                self.assertEqual(name, result[0]["S-1"].canonical_name)
                self.assert_matched(result)

    def test_decomposed_invoice_and_vendor_match_in_both_directions(self):
        for vendor, invoice in (("Café Parts", "Cafe\u0301 Parts"), ("Cafe\u0301 Parts", "Café Parts")):
            with self.subTest(vendor=vendor):
                result = self.reconcile([("S-1", vendor, "")], invoice)
                self.assertEqual(vendor, result[0]["S-1"].canonical_name)
                self.assert_matched(result)

    def test_accented_and_ascii_vendors_remain_distinct(self):
        self.assert_matched(self.reconcile([("S-1", "Café", ""), ("S-2", "Caf", "")], "Café"))
        self.assert_matched(self.reconcile([("S-1", "Café", ""), ("S-2", "Caf", "")], "Caf", "S-2"), "S-2")

    def test_non_latin_vendors_are_distinct(self):
        self.assert_matched(self.reconcile([("S-1", "東京商店", ""), ("S-2", "大阪商店", "")], "大阪商店", "S-2"), "S-2")

    def test_indic_vendors_are_distinct(self):
        self.assert_matched(self.reconcile([("S-1", "कमल", ""), ("S-2", "कमाल", "")], "कमाल", "S-2"), "S-2")

    def test_unicode_alias_is_used_without_rewriting_original(self):
        result = self.reconcile([("S-1", "Example Parts", "東京商店|Café Parts")], "東京商店")
        self.assertEqual(("東京商店", "Café Parts"), result[0]["S-1"].aliases)
        self.assert_matched(result)

    def test_unknown_accented_name_does_not_match_ascii_vendor(self):
        _, report, accounting, drafts = self.reconcile([("S-1", "Caf", "")], "Café")
        self.assertEqual([], accounting)
        self.assertEqual("", report["records"][0]["supplier_id"])
        self.assertIn("vendor_unmatched", drafts[0]["issues"])
        self.assertEqual("DRAFT_NOT_SENT", drafts[0]["status"])

    def test_genuinely_shared_unicode_alias_stays_ambiguous(self):
        _, report, accounting, drafts = self.reconcile(
            [("S-1", "Alpha", "東京商店"), ("S-2", "Beta", "東京商店")], "東京商店")
        self.assertEqual([], accounting)
        self.assertIn("vendor_ambiguous:S-1|S-2", report["records"][0]["issues"])
        self.assertEqual("DRAFT_NOT_SENT", drafts[0]["status"])

    def test_known_unicode_name_with_wrong_po_vendor_stays_exception(self):
        _, report, accounting, drafts = self.reconcile(
            [("S-1", "東京商店", ""), ("S-2", "大阪商店", "")], "大阪商店")
        self.assertEqual([], accounting)
        self.assertIn("vendor_mismatch:invoice=S-2,po=S-1", report["records"][0]["issues"])
        self.assertEqual("DRAFT_NOT_SENT", drafts[0]["status"])


if __name__ == "__main__":
    unittest.main()
