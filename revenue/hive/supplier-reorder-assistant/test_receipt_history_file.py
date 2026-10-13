"""Real CLI coverage for explicitly supplied receipt-history files."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import reorder_assistant as app


class ReceiptHistoryFileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.stock = {"FILTER-A": app.Stock("FILTER-A", "Filter A", 3, 0, 2, "each")}
        self.plan = app.build_plan(
            self.stock,
            {"FILTER-A": app.Rule("FILTER-A", 2, 10, "SUP-1")},
            [app.Offer("SUP-1", "FA-100", "FILTER-A", "Filter A", Decimal("4.25"), 20, 2, "")],
            "2026-09-08",
        )
        self.row = {
            "receipt_id": "R-1", "received_at": "2026-09-09", "supplier_id": "SUP-1",
            "supplier_sku": "FA-100", "sku": "FILTER-A", "quantity": "4",
        }
        updated, self.log = app.apply_receipts(self.stock, self.plan, [self.row])
        app.write_stock(self.root / "stock.csv", updated)
        (self.root / "plan.json").write_text(json.dumps(self.plan), encoding="utf-8")
        self.write_receipts([self.row])
        (self.root / "history.json").write_text(json.dumps(self.log), encoding="utf-8")

    def write_receipts(self, rows):
        with (self.root / "receipts.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.row))
            writer.writeheader()
            writer.writerows(rows)

    def run_cli(self, *, with_history=True, pipeline=False):
        command = [sys.executable, "-B", str(Path(app.__file__).resolve()), "receive",
                   "--stock", str(self.root / "stock.csv"), "--plan", str(self.root / "plan.json"),
                   "--receipts", str(self.root / "receipts.csv"),
                   "--out-stock", str(self.root / "next.csv"),
                   "--out-log", str(self.root / "next.json")]
        if with_history:
            command += ["--prior-log", str(self.root / "history.json")]
        if pipeline:
            command += ["--pipeline-includes-draft"]
        return subprocess.run(command, capture_output=True, text=True, timeout=10)

    def snapshot(self):
        return {path.name: path.read_bytes() for path in self.root.iterdir() if path.is_file()}

    def assert_rejected(self, *, existing=True, pipeline=False):
        if existing:
            (self.root / "next.csv").write_bytes(b"previous complete stock output\n")
            (self.root / "next.json").write_bytes(b"previous complete history output\n")
        before = self.snapshot()
        result = self.run_cli(pipeline=pipeline)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual("", result.stdout)
        self.assertEqual(before, self.snapshot(), "a rejected import changed an input or output")
        return result

    def test_null_history_cannot_silently_reapply_delivery(self):
        (self.root / "history.json").write_text("null", encoding="utf-8")
        result = self.assert_rejected()
        self.assertIn("prior log must be a JSON object", result.stderr)

    def test_null_history_creates_neither_output(self):
        (self.root / "history.json").write_text("null", encoding="utf-8")
        self.assert_rejected(existing=False)

    def test_null_history_cannot_decrement_pipeline_again(self):
        current = {"FILTER-A": app.Stock("FILTER-A", "Filter A", 7, 5, 2, "each")}
        app.write_stock(self.root / "stock.csv", current)
        (self.root / "history.json").write_text("null", encoding="utf-8")
        self.assert_rejected(pipeline=True)

    def test_null_history_is_rejected_even_with_no_receipt_rows(self):
        self.write_receipts([])
        (self.root / "history.json").write_text("null", encoding="utf-8")
        self.assert_rejected()

    def test_whitespace_wrapped_null_is_not_omitted_history(self):
        (self.root / "history.json").write_text(" \r\n\tnull\r\n ", encoding="utf-8")
        self.assert_rejected()

    def test_other_nonobject_json_roots_remain_errors(self):
        for value in ([], [self.row], "ledger", 0, 1.5, True, False):
            with self.subTest(value=value):
                (self.root / "history.json").write_text(json.dumps(value), encoding="utf-8")
                result = self.assert_rejected()
                self.assertIn("prior log", result.stderr)

    def test_invalid_utf8_history_is_a_clean_cli_error(self):
        (self.root / "history.json").write_bytes(b'\xff{"schema": "invalid encoding"}')
        result = self.assert_rejected()
        self.assertIn("cannot read prior log", result.stderr)
        self.assertIn("history.json", result.stderr)

    def test_malformed_json_still_rejects_before_outputs(self):
        (self.root / "history.json").write_text('{"applied_receipts":', encoding="utf-8")
        self.assert_rejected()

    def test_missing_history_still_rejects_before_outputs(self):
        (self.root / "history.json").unlink()
        self.assert_rejected()

    def test_empty_object_does_not_bypass_version_and_plan_checks(self):
        (self.root / "history.json").write_text("{}", encoding="utf-8")
        self.assert_rejected()

    def test_valid_history_replays_without_stock_or_pipeline_changes(self):
        before = (self.root / "stock.csv").read_bytes()
        result = self.run_cli(pipeline=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, (self.root / "next.csv").read_bytes())
        log = json.loads((self.root / "next.json").read_text())
        self.assertEqual(0, log["new_count"])
        self.assertEqual(["R-1"], log["replayed_receipt_ids"])
        self.assertEqual(self.log["applied_receipts"], log["applied_receipts"])

    def test_valid_later_delivery_still_extends_history(self):
        self.write_receipts([{**self.row, "receipt_id": "R-2", "quantity": "5"}])
        result = self.run_cli()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(12, app.load_stock(self.root / "next.csv")["FILTER-A"].on_hand)
        log = json.loads((self.root / "next.json").read_text())
        self.assertEqual(2, log["count"])
        self.assertEqual(1, log["new_count"])
        self.assertEqual(self.log["plan_sha256"], log["plan_sha256"])

    def test_cumulative_overreceipt_still_rejects_before_outputs(self):
        self.write_receipts([{**self.row, "receipt_id": "R-2", "quantity": "6"}])
        result = self.assert_rejected()
        self.assertIn("exceeds drafted quantity", result.stderr)

    def test_conflicting_replay_still_rejects_before_outputs(self):
        self.write_receipts([{**self.row, "quantity": "3"}])
        result = self.assert_rejected()
        self.assertIn("conflicts with prior history", result.stderr)

    def test_omitting_flag_keeps_existing_stateless_cli_contract(self):
        result = self.run_cli(with_history=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(11, app.load_stock(self.root / "next.csv")["FILTER-A"].on_hand)
        self.assertEqual(1, json.loads((self.root / "next.json").read_text())["new_count"])

    def test_direct_none_keeps_existing_stateless_api_contract(self):
        current = app.load_stock(self.root / "stock.csv")
        updated, log = app.apply_receipts(current, self.plan, [self.row], prior_log=None)
        self.assertEqual(11, updated["FILTER-A"].on_hand)
        self.assertEqual(1, log["new_count"])


if __name__ == "__main__":
    unittest.main()
