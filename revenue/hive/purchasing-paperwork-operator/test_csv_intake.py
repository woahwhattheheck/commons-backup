"""Real-file CSV intake regressions; no network or accounting-system writes."""

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import purchasing_operator as app


class CSVIntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "input.csv"

    def read(self, text, required=None):
        self.path.write_bytes(text.encode("utf-8"))
        return app._read_csv(self.path, {"a", "b"} if required is None else required)

    def test_duplicate_required_header_is_rejected(self):
        with self.assertRaisesRegex(app.PurchasingError, "duplicate.*columns"):
            self.read("a,b,a\noriginal,value,replacement\n")

    def test_duplicate_extension_header_is_rejected(self):
        with self.assertRaisesRegex(app.PurchasingError, "duplicate.*columns"):
            self.read("a,b,note,note\none,two,left,right\n")

    def test_blank_header_is_rejected(self):
        for header in ("a,b,", "a,b,   "):
            with self.subTest(header=header):
                with self.assertRaisesRegex(app.PurchasingError, "blank.*column"):
                    self.read(header + "\none,two,extra\n")

    def test_internal_line_header_is_rejected(self):
        with self.assertRaisesRegex(app.PurchasingError, "reserved.*_line"):
            self.read("a,b,_line\none,two,999\n")

    def test_surplus_cell_is_a_domain_error_with_location(self):
        with self.assertRaisesRegex(app.PurchasingError, r"input.csv:2:.*expected 2.*got 3"):
            self.read("a,b\none,two,extra\n")

    def test_missing_cell_is_not_silently_replaced_by_empty_string(self):
        with self.assertRaisesRegex(app.PurchasingError, r"input.csv:2:.*expected 2.*got 1"):
            self.read("a,b\none\n")

    def test_explicit_empty_cell_is_valid(self):
        self.assertEqual([{"a": "one", "b": "", "_line": "2"}], self.read("a,b\none,\n"))

    def test_missing_required_header_keeps_diagnostic(self):
        with self.assertRaisesRegex(app.PurchasingError, "missing columns.*b"):
            self.read("a,c\none,two\n")

    def test_empty_file_is_missing_columns(self):
        with self.assertRaisesRegex(app.PurchasingError, "missing columns"):
            self.read("")

    def test_header_only_file_is_valid_empty_input(self):
        self.assertEqual([], self.read("a,b\n"))

    def test_bom_crlf_unicode_quotes_and_extension_column_remain_valid(self):
        rows = self.read('\ufeffa,b,note\r\n  alpha  ,"Caf\u00e9, ""quoted""", keep \r\n')
        self.assertEqual([{"a": "alpha", "b": 'Caf\u00e9, "quoted"', "note": "keep", "_line": "2"}], rows)

    def test_quoted_multiline_records_keep_physical_start_line(self):
        rows = self.read('a,b\n"line one\nline two",first\nsecond,last\n')
        self.assertEqual("line one\nline two", rows[0]["a"])
        self.assertEqual(["2", "4"], [row["_line"] for row in rows])

    def test_blank_records_are_skipped_without_losing_source_lines(self):
        rows = self.read("a,b\n\none,two\n\nthree,four\n")
        self.assertEqual(["3", "5"], [row["_line"] for row in rows])

    def test_ragged_row_after_multiline_reports_physical_line(self):
        with self.assertRaisesRegex(app.PurchasingError, r"input.csv:4:.*expected 2.*got 1"):
            self.read('a,b\n"one\ntwo",ok\nshort\n')

    def test_unclosed_quote_is_domain_error(self):
        with self.assertRaisesRegex(app.PurchasingError, "invalid CSV"):
            self.read('a,b\n"unclosed,two\n')

    def test_junk_after_closing_quote_is_domain_error(self):
        with self.assertRaisesRegex(app.PurchasingError, "invalid CSV"):
            self.read('a,b\n"one"junk,two\n')

    def test_invalid_utf8_is_domain_error(self):
        self.path.write_bytes(b"a,b\none,\xff\n")
        with self.assertRaisesRegex(app.PurchasingError, "invalid CSV"):
            app._read_csv(self.path, {"a", "b"})

    def test_parser_field_limit_is_domain_error(self):
        previous = csv.field_size_limit(16)
        self.addCleanup(csv.field_size_limit, previous)
        with self.assertRaisesRegex(app.PurchasingError, "invalid CSV"):
            self.read("a,b\n" + "x" * 17 + ",two\n")

    def test_missing_file_is_domain_error(self):
        with self.assertRaisesRegex(app.PurchasingError, "cannot read"):
            app._read_csv(self.path, {"a", "b"})

    def test_vendor_loader_uses_strict_intake(self):
        self.path.write_text("supplier_id,canonical_name,aliases,aliases\nS,Acme,left,right\n")
        with self.assertRaisesRegex(app.PurchasingError, "duplicate.*columns"):
            app.load_vendors(self.path)

    def test_cli_exits_cleanly_and_preserves_existing_output(self):
        vendors = self.root / "vendors.csv"
        vendors.write_text("supplier_id,canonical_name,aliases\nS,Acme,Alias,unexpected\n")
        po = self.root / "po.csv"
        po.write_text("unused\n")
        invoices = self.root / "invoices.csv"
        invoices.write_text("unused\n")
        out = self.root / "out"
        out.mkdir()
        sentinel = out / "reconciliation.json"
        sentinel.write_bytes(b"previous accepted output\n")
        result = subprocess.run(
            [sys.executable, str(Path(app.__file__).resolve()), "--vendors", str(vendors),
             "--purchase-orders", str(po), "--invoices", str(invoices), "--out-dir", str(out)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual("", result.stdout)
        self.assertEqual(b"previous accepted output\n", sentinel.read_bytes())
        self.assertEqual([sentinel], list(out.iterdir()))


if __name__ == "__main__":
    unittest.main()
