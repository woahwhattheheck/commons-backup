#!/usr/bin/env python3
"""Receipt-history pipeline-mode continuity regressions.

These fixtures are synthetic. No supplier, customer, purchase, payment, or
provider action occurs.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import reorder_assistant as app


class DirectModeContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = {
            "schema": app.SCHEMA,
            "purchase_orders": [
                {
                    "draft_id": "DRAFT-SYNTHETIC",
                    "supplier_id": "SUP-1",
                    "status": "DRAFT_NOT_SENT",
                    "lines": [
                        {
                            "supplier_sku": "FA-100",
                            "sku": "FILTER-A",
                            "quantity": 9,
                        }
                    ],
                }
            ],
        }
        self.stock = {
            "FILTER-A": app.Stock(
                sku="FILTER-A",
                name="Filter A",
                on_hand=0,
                on_order=9,
                allocated=0,
                unit="each",
            )
        }
        self.r4 = self.receipt("R-4", 4)
        self.r5 = self.receipt("R-5", 5)

    @staticmethod
    def receipt(receipt_id: str, quantity: int) -> dict[str, str]:
        return {
            "receipt_id": receipt_id,
            "received_at": "2026-09-13",
            "supplier_id": "SUP-1",
            "supplier_sku": "FA-100",
            "sku": "FILTER-A",
            "quantity": str(quantity),
        }

    def first(self, mode: bool):
        return app.apply_receipts(
            self.stock,
            self.plan,
            [self.r4],
            pipeline_includes_draft=mode,
        )

    def test_false_history_cannot_continue_in_true_mode(self) -> None:
        stock, log = self.first(False)
        with self.assertRaisesRegex(app.ReorderError, "pipeline.*mode|pipeline_includes_draft"):
            app.apply_receipts(
                stock,
                self.plan,
                [self.r5],
                pipeline_includes_draft=True,
                prior_log=log,
            )

    def test_true_history_cannot_continue_in_false_mode(self) -> None:
        stock, log = self.first(True)
        with self.assertRaisesRegex(app.ReorderError, "pipeline.*mode|pipeline_includes_draft"):
            app.apply_receipts(
                stock,
                self.plan,
                [self.r5],
                pipeline_includes_draft=False,
                prior_log=log,
            )

    def test_replay_only_cannot_relabel_history_mode(self) -> None:
        stock, log = self.first(False)
        with self.assertRaisesRegex(app.ReorderError, "pipeline.*mode|pipeline_includes_draft"):
            app.apply_receipts(
                stock,
                self.plan,
                [self.r4],
                pipeline_includes_draft=True,
                prior_log=log,
            )

    def test_false_mode_continuation_preserves_imported_pipeline(self) -> None:
        stock, log = self.first(False)
        updated, next_log = app.apply_receipts(
            stock,
            self.plan,
            [self.r5],
            pipeline_includes_draft=False,
            prior_log=log,
        )
        self.assertEqual((9, 9), (updated["FILTER-A"].on_hand, updated["FILTER-A"].on_order))
        self.assertIs(next_log["pipeline_includes_draft"], False)
        self.assertEqual(2, next_log["count"])

    def test_true_mode_continuation_decrements_the_same_pipeline(self) -> None:
        stock, log = self.first(True)
        updated, next_log = app.apply_receipts(
            stock,
            self.plan,
            [self.r5],
            pipeline_includes_draft=True,
            prior_log=log,
        )
        self.assertEqual((9, 0), (updated["FILTER-A"].on_hand, updated["FILTER-A"].on_order))
        self.assertIs(next_log["pipeline_includes_draft"], True)
        self.assertEqual(2, next_log["count"])

    def test_prior_history_requires_an_explicit_boolean_mode(self) -> None:
        _stock, log = self.first(False)
        for invalid in (None, 0, 1, "false", [], {}):
            with self.subTest(invalid=invalid):
                broken = deepcopy(log)
                broken["pipeline_includes_draft"] = invalid
                with self.assertRaisesRegex(app.ReorderError, "pipeline_includes_draft.*boolean|boolean.*pipeline"):
                    app.apply_receipts(
                        self.stock,
                        self.plan,
                        [],
                        pipeline_includes_draft=False,
                        prior_log=broken,
                    )
        missing = deepcopy(log)
        del missing["pipeline_includes_draft"]
        with self.assertRaisesRegex(app.ReorderError, "pipeline_includes_draft.*boolean|boolean.*pipeline"):
            app.apply_receipts(
                self.stock,
                self.plan,
                [],
                pipeline_includes_draft=False,
                prior_log=missing,
            )

    def test_current_mode_requires_a_real_boolean(self) -> None:
        for invalid in (None, 0, 1, "false", [], {}):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(app.ReorderError, "pipeline_includes_draft.*boolean|boolean.*pipeline"):
                    app.apply_receipts(
                        self.stock,
                        self.plan,
                        [],
                        pipeline_includes_draft=invalid,  # type: ignore[arg-type]
                    )


class CliModeContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.program = Path(app.__file__).resolve()
        self.plan = self.root / "plan.json"
        self.plan.write_text(
            json.dumps(
                {
                    "schema": app.SCHEMA,
                    "purchase_orders": [
                        {
                            "draft_id": "DRAFT-SYNTHETIC",
                            "supplier_id": "SUP-1",
                            "status": "DRAFT_NOT_SENT",
                            "lines": [
                                {
                                    "supplier_sku": "FA-100",
                                    "sku": "FILTER-A",
                                    "quantity": 9,
                                }
                            ],
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.initial_stock = self.root / "stock.csv"
        self.write_stock(self.initial_stock, on_hand=0, on_order=9)
        self.r4 = self.root / "r4.csv"
        self.r5 = self.root / "r5.csv"
        self.write_receipts(self.r4, [("R-4", 4)])
        self.write_receipts(self.r5, [("R-5", 5)])

    @staticmethod
    def write_stock(path: Path, *, on_hand: int, on_order: int) -> None:
        path.write_text(
            "sku,name,on_hand,on_order,allocated,unit\n"
            f"FILTER-A,Filter A,{on_hand},{on_order},0,each\n",
            encoding="utf-8",
        )

    @staticmethod
    def write_receipts(path: Path, rows: list[tuple[str, int]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["receipt_id", "received_at", "supplier_id", "supplier_sku", "sku", "quantity"])
            for receipt_id, quantity in rows:
                writer.writerow([receipt_id, "2026-09-13", "SUP-1", "FA-100", "FILTER-A", quantity])

    def run_receive(
        self,
        *,
        stock: Path,
        receipts: Path,
        out_stock: Path,
        out_log: Path,
        prior_log: Path | None = None,
        mode: bool,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(self.program),
            "receive",
            "--stock",
            str(stock),
            "--plan",
            str(self.plan),
            "--receipts",
            str(receipts),
            "--out-stock",
            str(out_stock),
            "--out-log",
            str(out_log),
        ]
        if prior_log is not None:
            command.extend(["--prior-log", str(prior_log)])
        if mode:
            command.append("--pipeline-includes-draft")
        return subprocess.run(command, capture_output=True, text=True, timeout=10)

    def first(self, mode: bool) -> tuple[Path, Path]:
        stock = self.root / ("first-true.csv" if mode else "first-false.csv")
        log = self.root / ("first-true.json" if mode else "first-false.json")
        result = self.run_receive(
            stock=self.initial_stock,
            receipts=self.r4,
            out_stock=stock,
            out_log=log,
            mode=mode,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return stock, log

    def assert_switch_rejected_without_output_mutation(self, *, first_mode: bool, next_mode: bool) -> None:
        stock, log = self.first(first_mode)
        out_stock = self.root / "next-stock.csv"
        out_log = self.root / "next-log.json"
        out_stock.write_bytes(b"stock sentinel\n")
        out_log.write_bytes(b"log sentinel\n")
        before = (out_stock.read_bytes(), out_log.read_bytes())
        result = self.run_receive(
            stock=stock,
            receipts=self.r5,
            out_stock=out_stock,
            out_log=out_log,
            prior_log=log,
            mode=next_mode,
        )
        self.assertEqual(2, result.returncode, (result.stdout, result.stderr))
        self.assertRegex(result.stderr, "pipeline.*mode|pipeline_includes_draft")
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(before, (out_stock.read_bytes(), out_log.read_bytes()))

    def test_cli_false_to_true_switch_is_fail_closed(self) -> None:
        self.assert_switch_rejected_without_output_mutation(first_mode=False, next_mode=True)

    def test_cli_true_to_false_switch_is_fail_closed(self) -> None:
        self.assert_switch_rejected_without_output_mutation(first_mode=True, next_mode=False)

    def test_cli_same_true_mode_continues_to_zero_pipeline(self) -> None:
        stock, log = self.first(True)
        out_stock = self.root / "final.csv"
        out_log = self.root / "final.json"
        result = self.run_receive(
            stock=stock,
            receipts=self.r5,
            out_stock=out_stock,
            out_log=out_log,
            prior_log=log,
            mode=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        loaded = app.load_stock(out_stock)["FILTER-A"]
        self.assertEqual((9, 0), (loaded.on_hand, loaded.on_order))
        self.assertIs(json.loads(out_log.read_text(encoding="utf-8"))["pipeline_includes_draft"], True)


if __name__ == "__main__":
    unittest.main()
