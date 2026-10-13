"""Physical source-line regressions using real supplier CSV files and CLI calls."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import reorder_assistant as engine


class CSVLocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, text):
        path = self.root / name
        path.write_bytes(text.encode("utf-8"))
        return path

    def read(self, text):
        return engine._read_csv(self.write("input.csv", text), {"sku"})

    def test_blank_lines_identify_next_physical_start(self):
        rows = self.read("sku,note\n\nA,one\n\n\nB,two\n")
        self.assertEqual([r["_line"] for r in rows], ["3", "6"])

    def test_multiline_record_identifies_its_start_not_end(self):
        rows = self.read('sku,note\nA,"first\nsecond\nthird"\nB,last\n')
        self.assertEqual([r["_line"] for r in rows], ["2", "5"])
        self.assertEqual(rows[0]["note"], "first\nsecond\nthird")

    def test_multiline_header_is_counted(self):
        rows = self.read('sku,"supplier\nnote"\nA,value\n')
        self.assertEqual(rows, [{"sku": "A", "supplier\nnote": "value", "_line": "3"}])

    def test_crlf_multiline_and_blanks(self):
        rows = self.read('\ufeffsku,note\r\n\r\nA,"one\r\ntwo"\r\n\r\nB,last\r\n')
        self.assertEqual([r["_line"] for r in rows], ["3", "6"])
        self.assertEqual(rows[0]["note"], "one\r\ntwo")

    def test_cr_only_lines(self):
        rows = self.read('sku,note\r\rA,"one\rtwo"\rB,last\r')
        self.assertEqual([r["_line"] for r in rows], ["3", "5"])

    def test_extra_fields_report_physical_start(self):
        with self.assertRaisesRegex(engine.ReorderError, r"input.csv:5: extra field"):
            self.read('sku,note\nA,"one\ntwo"\n\nB,last,extra\n')

    def test_short_multiline_record_reports_its_start(self):
        with self.assertRaisesRegex(engine.ReorderError, r"input.csv:3: missing field"):
            self.read('sku,note\n\n"A\nB"\n')

    def test_unclosed_quote_reports_record_start(self):
        with self.assertRaisesRegex(engine.ReorderError, r"cannot read .*input.csv:4:"):
            self.read('sku,note\nA,one\n\nB,"unfinished\nmore')

    def test_trailing_quote_junk_reports_record_start(self):
        with self.assertRaisesRegex(engine.ReorderError, r"cannot read .*input.csv:3:"):
            self.read('sku,note\n\n"A"x,note\n')

    def test_quoted_empty_record_is_not_a_blank_physical_line(self):
        rows = self.read('sku\n\n""\nA\n')
        self.assertEqual(rows, [{"sku": "", "_line": "3"}, {"sku": "A", "_line": "4"}])

    def test_explicit_empty_values_and_named_metadata_stay_intact(self):
        rows = self.read("sku,note,source\n\nA,,export-7\n")
        self.assertEqual(rows, [{"sku": "A", "note": "", "source": "export-7", "_line": "3"}])

    def test_header_only_and_trailing_blank_lines_remain_empty(self):
        self.assertEqual(self.read("sku,note\n\n\n"), [])

    def test_stock_duplicate_uses_actual_source_line(self):
        path = self.write("stock.csv", 'sku,name,on_hand,on_order,allocated,unit\nA,"one\ntwo",1,0,0,each\n\nA,Duplicate,1,0,0,each\n')
        with self.assertRaisesRegex(engine.ReorderError, r"stock.csv:5: blank or duplicate sku"):
            engine.load_stock(path)

    def test_rule_duplicate_uses_actual_source_line(self):
        path = self.write("rules.csv", "sku,reorder_at,target_stock,preferred_supplier\n\nA,1,3,S\n\nA,1,3,S\n")
        with self.assertRaisesRegex(engine.ReorderError, r"rules.csv:5: blank or duplicate rule sku"):
            engine.load_rules(path)

    def test_catalog_duplicate_uses_actual_source_line(self):
        path = self.write("catalog.csv", 'supplier_id,supplier_sku,sku,description,unit_cost,available_qty,lead_days,alternative_for_sku\nS,SA,A,"one\ntwo",1,5,1,\n\nS,SA,A,Duplicate,1,5,1,\n')
        with self.assertRaisesRegex(engine.ReorderError, r"catalog.csv:5: blank or duplicate supplier item"):
            engine.load_catalog(path)

    def test_valid_loaders_preserve_plan(self):
        stock = self.write("stock.csv", "sku,name,on_hand,on_order,allocated,unit\n\nA,Item,1,0,0,each\n")
        rules = self.write("rules.csv", "sku,reorder_at,target_stock,preferred_supplier\n\nA,1,3,S\n")
        catalog = self.write("catalog.csv", "supplier_id,supplier_sku,sku,description,unit_cost,available_qty,lead_days,alternative_for_sku\n\nS,SA,A,Item,1.25,5,1,\n")
        plan = engine.build_plan(engine.load_stock(stock), engine.load_rules(rules), engine.load_catalog(catalog), "2026-09-08")
        self.assertEqual(plan["purchase_orders"][0]["total"], "2.50")
        self.assertEqual(plan["purchase_orders"][0]["lines"][0]["quantity"], 2)
        self.assertEqual(plan["summary"]["orders_sent"], 0)

    def test_cli_stock_error_points_to_physical_line_and_preserves_output(self):
        stock = self.write("stock.csv", 'sku,name,on_hand,on_order,allocated,unit\nA,"one\ntwo",1,0,0,each\n\nA,Duplicate,1,0,0,each\n')
        rules = self.write("rules.csv", "sku,reorder_at,target_stock,preferred_supplier\nA,1,3,S\n")
        catalog = self.write("catalog.csv", "supplier_id,supplier_sku,sku,description,unit_cost,available_qty,lead_days,alternative_for_sku\n")
        output = self.write("plan.json", "existing plan\n")
        result = subprocess.run([sys.executable, "-B", str(Path(engine.__file__).resolve()), "plan", "--stock", str(stock), "--rules", str(rules), "--catalog", str(catalog), "--as-of", "2026-09-08", "--out", str(output)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("stock.csv:5:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(output.read_text(), "existing plan\n")

    def test_cli_receipt_error_preserves_both_outputs(self):
        stock = self.write("stock.csv", "sku,name,on_hand,on_order,allocated,unit\nA,Item,1,0,0,each\n")
        plan = self.write("plan.json", json.dumps({"schema": engine.SCHEMA, "purchase_orders": []}))
        receipts = self.write("receipts.csv", 'receipt_id,received_at,supplier_id,supplier_sku,sku,quantity\n\n\nR1,2026-09-08,S,SA,A,1,extra\n')
        out_stock = self.write("updated.csv", "existing stock\n")
        out_log = self.write("receipts.json", "existing log\n")
        result = subprocess.run([sys.executable, "-B", str(Path(engine.__file__).resolve()), "receive", "--stock", str(stock), "--plan", str(plan), "--receipts", str(receipts), "--out-stock", str(out_stock), "--out-log", str(out_log)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("receipts.csv:4:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(out_stock.read_text(), "existing stock\n")
        self.assertEqual(out_log.read_text(), "existing log\n")


if __name__ == "__main__":
    unittest.main()
