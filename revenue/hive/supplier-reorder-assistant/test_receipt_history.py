"""Receipt-history regressions against the real planner and command-line product."""

import copy
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import reorder_assistant as app


class ReceiptHistoryTests(unittest.TestCase):
    def setUp(self):
        self.stock = {"FILTER-A": app.Stock("FILTER-A", "Filter A", 3, 0, 2, "each")}
        self.plan = app.build_plan(
            self.stock,
            {"FILTER-A": app.Rule("FILTER-A", 2, 10, "SUP-1")},
            [app.Offer("SUP-1", "FA-100", "FILTER-A", "Filter A", Decimal("4.25"), 20, 2, "")],
            "2026-09-08",
        )

    def receipt(self, receipt_id="R-1", quantity="4", **changes):
        row = {
            "receipt_id": receipt_id, "received_at": "2026-09-09", "supplier_id": "SUP-1",
            "supplier_sku": "FA-100", "sku": "FILTER-A", "quantity": quantity,
        }
        row.update(changes)
        return row

    def first(self):
        return app.apply_receipts(self.stock, self.plan, [self.receipt()])

    def test_first_log_is_versioned_bound_and_cumulative(self):
        updated, log = self.first()
        expected = hashlib.sha256(json.dumps(self.plan, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        self.assertEqual(7, updated["FILTER-A"].on_hand)
        self.assertEqual(1, log["receipt_history_version"])
        self.assertEqual(expected, log["plan_sha256"])
        self.assertEqual(1, log["count"])
        self.assertEqual(1, log["new_count"])
        self.assertEqual([], log["replayed_receipt_ids"])

    def test_reimport_does_not_add_inventory_again(self):
        updated, log = self.first()
        replayed, next_log = app.apply_receipts(updated, self.plan, [self.receipt()], prior_log=log)
        self.assertEqual(updated, replayed)
        self.assertEqual(7, replayed["FILTER-A"].on_hand)
        self.assertEqual(0, next_log["new_count"])
        self.assertEqual(["R-1"], next_log["replayed_receipt_ids"])
        self.assertEqual(log["applied_receipts"], next_log["applied_receipts"])

    def test_distinct_later_receipt_respects_cumulative_quantity(self):
        updated, log = self.first()
        final, next_log = app.apply_receipts(updated, self.plan, [self.receipt("R-2", "5")], prior_log=log)
        self.assertEqual(12, final["FILTER-A"].on_hand)
        self.assertEqual(2, next_log["count"])
        self.assertEqual(1, next_log["new_count"])
        self.assertEqual(9, sum(row["quantity"] for row in next_log["applied_receipts"]))

    def test_cross_import_overreceipt_is_rejected(self):
        updated, log = self.first()
        with self.assertRaisesRegex(app.ReorderError, "exceeds drafted quantity"):
            app.apply_receipts(updated, self.plan, [self.receipt("R-2", "6")], prior_log=log)

    def test_mixed_replays_and_new_receipts_apply_only_new_units(self):
        updated, log = self.first()
        final, next_log = app.apply_receipts(updated, self.plan, [self.receipt(), self.receipt("R-2", "5")], prior_log=log)
        self.assertEqual(12, final["FILTER-A"].on_hand)
        self.assertEqual(1, next_log["new_count"])
        self.assertEqual(["R-1"], next_log["replayed_receipt_ids"])

    def test_reused_id_with_changed_quantity_is_rejected(self):
        updated, log = self.first()
        with self.assertRaisesRegex(app.ReorderError, "conflicts with prior history"):
            app.apply_receipts(updated, self.plan, [self.receipt(quantity="3")], prior_log=log)

    def test_reused_id_with_changed_identity_or_date_is_rejected(self):
        updated, log = self.first()
        for field in ("received_at", "supplier_id", "supplier_sku", "sku"):
            with self.subTest(field=field), self.assertRaisesRegex(app.ReorderError, "conflicts with prior history"):
                app.apply_receipts(updated, self.plan, [self.receipt(**{field: "different"})], prior_log=log)

    def test_duplicate_ids_within_batch_still_rejected(self):
        for previous in (False, True):
            with self.subTest(previous=previous):
                stock, log = self.first() if previous else (self.stock, None)
                with self.assertRaisesRegex(app.ReorderError, "duplicate receipt_id"):
                    app.apply_receipts(stock, self.plan, [self.receipt(), self.receipt()], prior_log=log)

    def test_malformed_prior_log_is_rejected(self):
        updated, log = self.first()
        variants = [[], "log", {}, {**log, "schema": "wrong"}, {**log, "applied_receipts": None},
                    {**log, "applied_receipts": {}}, {**log, "receipt_history_version": 2},
                    {**log, "receipt_history_version": True}]
        for bad in variants:
            with self.subTest(prior=bad), self.assertRaises(app.ReorderError):
                app.apply_receipts(updated, self.plan, [], prior_log=bad)

    def test_malformed_history_record_is_rejected(self):
        updated, log = self.first()
        for bad in (None, [], {}, {**log["applied_receipts"][0], "received_at": ""}):
            with self.subTest(record=bad), self.assertRaises(app.ReorderError):
                app.apply_receipts(updated, self.plan, [], prior_log={**log, "applied_receipts": [bad]})

    def test_history_quantity_is_validated_not_truncated(self):
        updated, log = self.first()
        for bad in ("1.5", "NaN", "Infinity", "-1", 0, True, None):
            row = {**log["applied_receipts"][0], "quantity": bad}
            with self.subTest(quantity=bad), self.assertRaises(app.ReorderError):
                app.apply_receipts(updated, self.plan, [], prior_log={**log, "applied_receipts": [row]})

    def test_history_overreceipt_is_rejected(self):
        updated, log = self.first()
        bad = {**log, "applied_receipts": [self.receipt(quantity="10")]}
        with self.assertRaisesRegex(app.ReorderError, "exceeds drafted quantity"):
            app.apply_receipts(updated, self.plan, [], prior_log=bad)

    def test_duplicate_history_ids_are_not_double_counted(self):
        updated, log = self.first()
        bad = {**log, "applied_receipts": log["applied_receipts"] * 2}
        with self.assertRaisesRegex(app.ReorderError, "duplicate receipt_id"):
            app.apply_receipts(updated, self.plan, [], prior_log=bad)

    def test_changed_plan_with_same_draft_id_is_rejected(self):
        updated, log = self.first()
        changed = copy.deepcopy(self.plan)
        changed["purchase_orders"][0]["lines"][0]["quantity"] = 10
        self.assertEqual(self.plan["purchase_orders"][0]["draft_id"], changed["purchase_orders"][0]["draft_id"])
        with self.assertRaisesRegex(app.ReorderError, "different saved plan"):
            app.apply_receipts(updated, changed, [], prior_log=log)

    def test_json_key_order_does_not_change_plan_binding(self):
        updated, log = self.first()
        reordered = dict(reversed(list(self.plan.items())))
        final, next_log = app.apply_receipts(updated, reordered, [self.receipt()], prior_log=log)
        self.assertEqual(updated, final)
        self.assertEqual(log["plan_sha256"], next_log["plan_sha256"])

    def test_failed_batch_does_not_mutate_inputs(self):
        updated, log = self.first()
        original_stock, original_log, original_plan = copy.deepcopy((updated, log, self.plan))
        with self.assertRaises(app.ReorderError):
            app.apply_receipts(updated, self.plan, [self.receipt("R-2", "5"), self.receipt("R-3", "1")], prior_log=log)
        self.assertEqual(original_stock, updated)
        self.assertEqual(original_log, log)
        self.assertEqual(original_plan, self.plan)

    def test_pipeline_decrement_does_not_repeat_on_replay(self):
        current = {"FILTER-A": app.Stock("FILTER-A", "Filter A", 3, 9, 2, "each")}
        updated, log = app.apply_receipts(current, self.plan, [self.receipt()], pipeline_includes_draft=True)
        replayed, _ = app.apply_receipts(updated, self.plan, [self.receipt()], pipeline_includes_draft=True, prior_log=log)
        self.assertEqual(5, updated["FILTER-A"].on_order)
        self.assertEqual(updated, replayed)

    def test_no_history_mode_remains_stateless_for_compatibility(self):
        updated, _ = self.first()
        second, log = app.apply_receipts(updated, self.plan, [self.receipt()])
        self.assertEqual(11, second["FILTER-A"].on_hand)
        self.assertEqual(1, log["new_count"])

    def test_unbound_legacy_log_is_not_silently_assigned_to_plan(self):
        updated, log = self.first()
        legacy = {k: v for k, v in log.items() if k in ("schema", "applied_receipts", "count", "pipeline_includes_draft")}
        with self.assertRaisesRegex(app.ReorderError, "versioned receipt history"):
            app.apply_receipts(updated, self.plan, [], prior_log=legacy)

    def test_empty_batch_preserves_cumulative_history(self):
        updated, log = self.first()
        final, next_log = app.apply_receipts(updated, self.plan, [], prior_log=log)
        self.assertEqual(updated, final)
        self.assertEqual(log["applied_receipts"], next_log["applied_receipts"])
        self.assertEqual(0, next_log["new_count"])

    def write_receipts(self, path, rows):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.receipt()))
            writer.writeheader()
            writer.writerows(rows)

    def cli(self, root, stock, rows, output, prior=None):
        receipt_path = root / (output + "-receipts.csv")
        self.write_receipts(receipt_path, rows)
        command = [sys.executable, str(Path(app.__file__).resolve()), "receive", "--stock", str(stock),
                   "--plan", str(root / "plan.json"), "--receipts", str(receipt_path),
                   "--out-stock", str(root / (output + ".csv")), "--out-log", str(root / (output + ".json"))]
        if prior is not None:
            command.extend(["--prior-log", str(prior)])
        return subprocess.run(command, capture_output=True, text=True, timeout=10)

    def test_real_cli_cumulative_import_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app.write_stock(root / "stock.csv", self.stock)
            (root / "plan.json").write_text(json.dumps(self.plan))
            first = self.cli(root, root / "stock.csv", [self.receipt()], "first")
            self.assertEqual(0, first.returncode, first.stderr)
            second = self.cli(root, root / "first.csv", [self.receipt(), self.receipt("R-2", "5")], "second", root / "first.json")
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(12, app.load_stock(root / "second.csv")["FILTER-A"].on_hand)
            log = json.loads((root / "second.json").read_text())
            self.assertEqual(2, log["count"])
            self.assertEqual(1, log["new_count"])
            third = self.cli(root, root / "second.csv", [self.receipt(), self.receipt("R-2", "5")], "third", root / "second.json")
            self.assertEqual(0, third.returncode, third.stderr)
            self.assertEqual((root / "second.csv").read_bytes(), (root / "third.csv").read_bytes())
            self.assertEqual(0, json.loads((root / "third.json").read_text())["new_count"])

    def test_cli_error_preserves_existing_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            updated, log = self.first()
            app.write_stock(root / "updated.csv", updated)
            (root / "plan.json").write_text(json.dumps(self.plan))
            (root / "history.json").write_text(json.dumps(log))
            (root / "next.csv").write_bytes(b"keep existing stock\n")
            (root / "next.json").write_bytes(b"keep existing log\n")
            result = self.cli(root, root / "updated.csv", [self.receipt("R-2", "6")], "next", root / "history.json")
            self.assertEqual(2, result.returncode)
            self.assertIn("exceeds drafted quantity", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(b"keep existing stock\n", (root / "next.csv").read_bytes())
            self.assertEqual(b"keep existing log\n", (root / "next.json").read_bytes())

    def test_three_generation_history_retains_first_id(self):
        updated, first = app.apply_receipts(self.stock, self.plan, [self.receipt(quantity="2")])
        updated, second = app.apply_receipts(updated, self.plan, [self.receipt("R-2", "2")], prior_log=first)
        final, third = app.apply_receipts(updated, self.plan, [self.receipt(quantity="2"), self.receipt("R-3", "5")], prior_log=second)
        self.assertEqual(12, final["FILTER-A"].on_hand)
        self.assertEqual(3, third["count"])
        self.assertEqual(["R-1"], third["replayed_receipt_ids"])

    def test_csv_line_number_and_integer_spelling_do_not_change_identity(self):
        updated, log = self.first()
        final, next_log = app.apply_receipts(updated, self.plan, [self.receipt(quantity="4.0", _line="99")], prior_log=log)
        self.assertEqual(updated, final)
        self.assertEqual(0, next_log["new_count"])

    def test_blank_receipt_identity_is_rejected(self):
        for field in ("receipt_id", "supplier_id", "supplier_sku", "sku", "received_at"):
            with self.subTest(field=field), self.assertRaises(app.ReorderError):
                app.apply_receipts(self.stock, self.plan, [self.receipt(**{field: " "})])

    def test_history_line_outside_plan_is_rejected(self):
        updated, log = self.first()
        bad = {**log, "applied_receipts": [self.receipt(supplier_sku="FA-UNKNOWN")]}
        with self.assertRaisesRegex(app.ReorderError, "not present in the draft plan"):
            app.apply_receipts(updated, self.plan, [], prior_log=bad)


if __name__ == "__main__":
    unittest.main()
