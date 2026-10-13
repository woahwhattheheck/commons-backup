"""Real-file and CLI regressions for the shared supplier-reorder CSV reader."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import reorder_assistant as engine

STOCK = "sku,name,on_hand,on_order,allocated,unit\nFILTER-A,Filter cartridge,3,2,1,each\nBELT-B,Drive belt,0,0,0,each\n"
RULES = "sku,reorder_at,target_stock,preferred_supplier\nFILTER-A,5,13,SUP-1\nBELT-B,1,4,SUP-1\n"
CATALOG = "supplier_id,supplier_sku,sku,description,unit_cost,available_qty,lead_days,alternative_for_sku\nSUP-1,F-101,FILTER-A,Filter cartridge,4.25,25,2,\nSUP-1,B-100,BELT-B,Original drive belt,8.00,0,3,\nSUP-2,B-ALT,BELT-C,Alternative belt,7.50,8,5,BELT-B\n"


class CSVFixtures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, content):
        path = self.root / name
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        return path

    def read(self, content, required=None):
        return engine._read_csv(self.write("input.csv", content), {"sku"} if required is None else required)


class CSVReaderTests(CSVFixtures):
    def test_extra_field_is_domain_error(self):
        with self.assertRaisesRegex(engine.ReorderError, "extra field"):
            self.read("sku,name\nA,Item,unexpected\n")

    def test_extra_empty_field_is_still_detected(self):
        with self.assertRaisesRegex(engine.ReorderError, "extra field"):
            self.read("sku,name\nA,Item,\n")

    def test_duplicate_required_header_is_not_silently_overwritten(self):
        with self.assertRaisesRegex(engine.ReorderError, "duplicate column"):
            self.read("sku,sku,name\nA,B,Item\n")

    def test_duplicate_optional_header_is_detected(self):
        with self.assertRaisesRegex(engine.ReorderError, "duplicate column"):
            self.read("sku,note,note\nA,first,second\n")

    def test_blank_header_is_detected(self):
        with self.assertRaisesRegex(engine.ReorderError, "blank column"):
            self.read("sku,\nA,something\n")

    def test_whitespace_only_header_is_detected(self):
        with self.assertRaisesRegex(engine.ReorderError, "blank column"):
            self.read("sku,   \nA,something\n")

    def test_short_row_is_not_padded_with_empty_strings(self):
        with self.assertRaisesRegex(engine.ReorderError, "missing field"):
            self.read("sku,note\nA\n")

    def test_short_catalog_optional_alternative_is_detected(self):
        short = CATALOG.replace("4.25,25,2,\n", "4.25,25,2\n")
        with self.assertRaisesRegex(engine.ReorderError, "missing field"):
            engine.load_catalog(self.write("catalog.csv", short))

    def test_short_rules_optional_supplier_is_detected(self):
        short = RULES.replace("FILTER-A,5,13,SUP-1", "FILTER-A,5,13")
        with self.assertRaisesRegex(engine.ReorderError, "missing field"):
            engine.load_rules(self.write("rules.csv", short))

    def test_invalid_utf8_is_domain_error(self):
        with self.assertRaisesRegex(engine.ReorderError, "cannot read"):
            self.read(b"sku,name\nA,\xff\n")

    def test_unclosed_quote_is_domain_error(self):
        with self.assertRaisesRegex(engine.ReorderError, "cannot read"):
            self.read('sku,note\nA,"unterminated\n')

    def test_trailing_characters_after_quoted_field_are_detected(self):
        with self.assertRaisesRegex(engine.ReorderError, "cannot read"):
            self.read('sku,note\n"A"x,Item\n')

    def test_csv_field_size_error_is_domain_error(self):
        with self.assertRaisesRegex(engine.ReorderError, "cannot read"):
            self.read("sku,note\nA," + "x" * (csv.field_size_limit() + 1) + "\n")

    def test_explicit_blank_value_remains_valid(self):
        self.assertEqual(self.read("sku,note\nA,\n"), [{"sku": "A", "note": "", "_line": "2"}])

    def test_utf8_bom_crlf_and_unicode_remain_valid(self):
        data = "\ufeffsku,name\r\nA,Piñón japonés\r\n".encode("utf-8")
        self.assertEqual(self.read(data)[0]["name"], "Piñón japonés")

    def test_quoted_commas_newlines_and_escaped_quotes_remain_valid(self):
        parsed = self.read('sku,note\nA,"top, middle\nand ""bottom"""\n')
        self.assertEqual(parsed, [{"sku": "A", "note": 'top, middle\nand "bottom"', "_line": "2"}])

    def test_value_whitespace_normalization_is_unchanged(self):
        self.assertEqual(self.read("sku,note\n A ,  detail  \n")[0], {"sku": "A", "note": "detail", "_line": "2"})

    def test_header_only_is_still_an_empty_dataset(self):
        self.assertEqual(self.read("sku,note\n"), [])

    def test_empty_file_reports_required_columns(self):
        with self.assertRaisesRegex(engine.ReorderError, "missing columns"):
            self.read("")

    def test_missing_required_columns_are_unchanged(self):
        with self.assertRaisesRegex(engine.ReorderError, "missing columns.*sku"):
            self.read("name\nItem\n")

    def test_unknown_named_metadata_column_is_preserved(self):
        self.assertEqual(self.read("sku,note,source\nA,Item,export-7\n")[0]["source"], "export-7")

    def test_duplicate_sku_still_uses_existing_validation(self):
        with self.assertRaisesRegex(engine.ReorderError, "duplicate sku"):
            engine.load_stock(self.write("stock.csv", STOCK + "FILTER-A,Other,1,0,0,each\n"))

    def test_missing_file_error_is_unchanged(self):
        with self.assertRaisesRegex(engine.ReorderError, "cannot read"):
            engine._read_csv(self.root / "absent.csv", {"sku"})

    def test_later_invalid_row_raises_instead_of_returning_partial_data(self):
        with self.assertRaisesRegex(engine.ReorderError, ":3:.*extra field"):
            self.read("sku,note\nA,valid\nB,invalid,extra\n")

    def test_blank_physical_lines_remain_supported(self):
        self.assertEqual([row["sku"] for row in self.read("sku,note\n\nA,one\n\nB,two\n")], ["A", "B"])

    def test_quoted_empty_sku_still_reaches_existing_validation(self):
        content = STOCK.replace("FILTER-A,Filter", '"",Filter', 1)
        with self.assertRaisesRegex(engine.ReorderError, "blank or duplicate sku"):
            engine.load_stock(self.write("stock.csv", content))


class CLITests(CSVFixtures):
    def command(self, stock=STOCK, rules=RULES, catalog=CATALOG):
        for name, content in (("stock", stock), ("rules", rules), ("catalog", catalog)):
            self.write(name + ".csv", content)
        return [sys.executable, "-B", str(Path(engine.__file__).resolve()), "plan", "--stock", str(self.root / "stock.csv"),
                "--rules", str(self.root / "rules.csv"), "--catalog", str(self.root / "catalog.csv"),
                "--as-of", "2026-09-08", "--out", str(self.root / "plan.json")]

    def assert_cli_error(self, command):
        output = self.write("plan.json", "keep-existing-output\n")
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("error:", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertEqual(output.read_text(), "keep-existing-output\n")

    def test_cli_extra_stock_field_has_no_traceback_or_output_overwrite(self):
        self.assert_cli_error(self.command(stock=STOCK.replace("3,2,1,each", "3,2,1,each,unexpected")))

    def test_cli_invalid_utf8_has_no_traceback_or_output_overwrite(self):
        self.assert_cli_error(self.command(stock=b"sku,name,on_hand,on_order,allocated,unit\nA,\xff,1,0,0,each\n"))

    def test_cli_short_rule_has_no_output_overwrite(self):
        self.assert_cli_error(self.command(rules=RULES.replace("FILTER-A,5,13,SUP-1", "FILTER-A,5,13")))

    def test_cli_unterminated_catalog_quote_has_no_output_overwrite(self):
        self.assert_cli_error(self.command(catalog=CATALOG + 'SUP-9,F-9,FILTER-A,"unterminated'))

    def test_cli_valid_plan_and_receipt_workflow(self):
        completed = subprocess.run(self.command(), capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        plan = json.loads((self.root / "plan.json").read_text())
        self.assertEqual(plan["summary"], {"draft_purchase_orders": 1, "draft_lines": 1, "review_required": 1, "orders_sent": 0})
        self.assertEqual(plan["purchase_orders"][0]["lines"][0]["quantity"], 9)
        self.assertEqual(plan["purchase_orders"][0]["total"], "38.25")
        self.assertEqual(plan["exceptions"][0]["alternative_suggestions"][0]["supplier_sku"], "B-ALT")
        receipt = self.write("receipts.csv", "receipt_id,received_at,supplier_id,supplier_sku,sku,quantity\nR1,2026-09-08,SUP-1,F-101,FILTER-A,4\n")
        command = [sys.executable, "-B", str(Path(engine.__file__).resolve()), "receive", "--stock", str(self.root / "stock.csv"),
                   "--plan", str(self.root / "plan.json"), "--receipts", str(receipt), "--out-stock", str(self.root / "updated.csv"),
                   "--out-log", str(self.root / "receipts.json")]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        stock = engine.load_stock(self.root / "updated.csv")
        self.assertEqual((stock["FILTER-A"].on_hand, stock["FILTER-A"].on_order), (7, 2))
        log = json.loads((self.root / "receipts.json").read_text())
        self.assertEqual(log["count"], 1)
        self.assertFalse(log["pipeline_includes_draft"])

    def test_cli_invalid_receipt_keeps_both_existing_outputs(self):
        completed = subprocess.run(self.command(), capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0)
        self.write("updated.csv", "keep-stock\n")
        self.write("receipts.json", "keep-log\n")
        receipt = self.write("receipts.csv", "receipt_id,received_at,supplier_id,supplier_sku,sku,quantity\nR1,2026-09-08,SUP-1,F-101,FILTER-A,4,extra\n")
        command = [sys.executable, "-B", str(Path(engine.__file__).resolve()), "receive", "--stock", str(self.root / "stock.csv"),
                   "--plan", str(self.root / "plan.json"), "--receipts", str(receipt), "--out-stock", str(self.root / "updated.csv"),
                   "--out-log", str(self.root / "receipts.json")]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertEqual((self.root / "updated.csv").read_text(), "keep-stock\n")
        self.assertEqual((self.root / "receipts.json").read_text(), "keep-log\n")



if __name__ == "__main__":
    unittest.main()
