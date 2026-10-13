#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Queue-copy CI report fixtures; these synthetic counts are not policy runs."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import build_combined_report as subject
import test_combined_report as retained

QUEUE = ("queue_copy", "queue-copy-tests.log", subject.MARKET + "test_queue_copy.py")
READER = ("queue_copy_reporter", "queue-copy-reporter-tests.log", subject.PROJECTION + "test_queue_copy_report.py")
CASE_KEYS = ("queue_comparisons", "replacement_comparisons", "complete_transform_comparisons", "feasibility_comparisons")


class QueueCopyReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)
        retained.fixture(self.path)
        self.original = subject.build_report(self.path)
        snap = self.path / "SOURCE-SNAPSHOT.json"
        snapshot = json.loads(snap.read_text())
        snapshot["files"].update({row[2]: {"sha256": retained.sha(row[2])} for row in (QUEUE, READER)})
        retained.save(snap, snapshot)
        (self.path / QUEUE[1]).write_text(retained.log(23))
        (self.path / READER[1]).write_text(retained.log(14))
        self.packet = dict(schema="titan.queue-copy.final.v1", methods=23,
            failures=0, errors=0, passed=True,
            source_sha256=retained.sha(subject.LAB + "selected_action_sell.py"),
            counts=dict(zip(CASE_KEYS, (247, 420, 32, 2210))),
            new_games=0, engine_transitions=0, log=retained.log(23))
        self.save()

    def save(self):
        retained.save(self.path / "queue-copy-results.json", self.packet)

    def build(self):
        return subject.build_report(self.path, include_queue_copy=True)

    def test_counts_and_sources_are_separate(self):
        r = self.build()
        self.assertTrue(r["successful"], r["problems"])
        self.assertEqual(r["total_tests"], 79 + 23 + 14)
        self.assertEqual(r["suite_count"], 8)
        self.assertEqual(r["queue_copy_tests"], 23)
        self.assertEqual(r["queue_copy_reporter_tests"], 14)
        self.assertEqual(r["queue_copy_binding"]["source_sha256"], self.packet["source_sha256"])
        self.assertEqual(r["queue_copy_case_counts"], self.packet["counts"])

    def test_opt_in_leaves_complete_old_report_equal(self):
        # Ignore new files until explicitly requested; the source-snapshot digest
        # changed in setUp, so compare the two calls on that same updated input.
        before = subject.build_report(self.path)
        self.packet["passed"] = False; self.save()
        self.assertEqual(before, subject.build_report(self.path))
        self.assertNotIn("queue_copy_binding", before)
        self.assertEqual(before["total_tests"], self.original["total_tests"])

    def test_wrong_seller_and_missing_test_source_fail(self):
        self.packet["source_sha256"] = "0" * 64; self.save()
        self.assertTrue(any("queue copy seller" in p for p in self.build()["problems"]))
        self.packet["source_sha256"] = retained.sha(subject.LAB + "selected_action_sell.py"); self.save()
        snap = self.path / "SOURCE-SNAPSHOT.json"
        raw = json.loads(snap.read_text())
        for row in (QUEUE, READER):
            changed = copy.deepcopy(raw); del changed["files"][row[2]]; retained.save(snap, changed)
            with self.subTest(path=row[2]): self.assertFalse(self.build()["successful"])

    def test_counts_pass_flag_and_failure_fields_are_exact(self):
        original = copy.deepcopy(self.packet)
        for field, values in (("methods", [24, True, None]), ("passed", [False, 1, None]),
                              ("failures", [1, False, None]), ("errors", [1, False, None])):
            for value in values:
                self.packet = copy.deepcopy(original); self.packet[field] = value; self.save()
                with self.subTest(field=field, value=value): self.assertFalse(self.build()["successful"])

    def test_missing_and_malformed_json_are_unsuccessful(self):
        path = self.path / "queue-copy-results.json"
        for data in (None, "{", "[]", '{"methods":23,"methods":23}'):
            if data is None: path.unlink()
            else: path.write_text(data)
            with self.subTest(data=data): self.assertFalse(self.build()["successful"])

    def test_missing_each_log_keeps_counts_incomplete(self):
        for row in (QUEUE, READER):
            path = self.path / row[1]; raw = path.read_bytes(); path.unlink()
            result = self.build()
            self.assertIsNone(result["total_tests"])
            self.assertIsNone(result[row[0] + "_tests"])
            self.assertFalse(result["successful"])
            path.write_bytes(raw)

    def test_skipped_failed_and_duplicated_logs_fail(self):
        path = self.path / QUEUE[1]
        for text in (retained.log(23).replace("OK", "OK (skipped=1)"),
                     retained.log(23).replace("OK", "FAILED (failures=1)"),
                     retained.log(23) * 2):
            path.write_text(text)
            with self.subTest(text=text): self.assertFalse(self.build()["successful"])

    def test_inner_log_must_agree_with_outer_completed_log(self):
        for text in (retained.log(24), retained.log(23).replace("OK", "FAILED (errors=1)"), None, ""):
            self.packet["log"] = text; self.save()
            with self.subTest(text=text): self.assertFalse(self.build()["successful"])

    def test_schema_and_zero_execution_claims(self):
        original = copy.deepcopy(self.packet)
        for field, value in (("schema", "unknown"), ("new_games", 1), ("new_games", False),
                             ("engine_transitions", 1), ("engine_transitions", None)):
            self.packet = copy.deepcopy(original); self.packet[field] = value; self.save()
            with self.subTest(field=field,value=value): self.assertFalse(self.build()["successful"])

    def test_case_counts_are_typed_not_strength_claims(self):
        original = copy.deepcopy(self.packet)
        for values in (None, [], {}, {**self.packet["counts"], "queue_comparisons": True},
                       {**self.packet["counts"], "replacement_comparisons": -1}):
            self.packet = copy.deepcopy(original); self.packet["counts"] = values; self.save()
            with self.subTest(values=values): self.assertFalse(self.build()["successful"])

    def test_results_are_deterministic_and_input_files_unchanged(self):
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.path.iterdir()}
        self.assertEqual(self.build(), self.build())
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.path.iterdir()}
        self.assertEqual(before, after)

    def test_cli_exit_and_json_match_library(self):
        command = [sys.executable, "-B", subject.__file__, "--directory", str(self.path), "--include-queue-copy"]
        good = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout), self.build())
        self.packet["passed"] = False; self.save()
        bad = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(bad.returncode, 1, bad.stderr)
        self.assertFalse(json.loads(bad.stdout)["successful"])


class QueueCopyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(__file__).resolve().parents[3]
        self.workflow = (self.repo / ".github/workflows/titan-selected-projection.yml").read_text()

    def test_unchanged_queue_cli_and_report_flag_are_wired_once(self):
        self.assertEqual(self.workflow.count("python3 -B revenue/kaggriculture/cloud-selected-market-checks/test_queue_copy.py"), 1)
        self.assertIn('--lab "$LAB"', self.workflow)
        self.assertIn('--report "$RUNNER_TEMP/projection-validation/queue-copy-results.json"', self.workflow)
        self.assertIn('tee "$RUNNER_TEMP/projection-validation/queue-copy-tests.log"', self.workflow)
        self.assertEqual(self.workflow.count("--include-queue-copy"), 1)
        self.assertNotIn("--benchmark", self.workflow)

    def test_reporter_and_source_roots_are_in_same_workflow(self):
        self.assertIn("python3 -B -m unittest -v test_queue_copy_report", self.workflow)
        self.assertIn('tee "$RUNNER_TEMP/projection-validation/queue-copy-reporter-tests.log"', self.workflow)
        self.assertIn("'revenue/kaggriculture/cloud-selected-market-checks/**'", self.workflow)
        self.assertIn("/revenue/kaggriculture/cloud-selected-market-checks/", self.workflow)
        self.assertIn("/revenue/kaggriculture/cloud-selected-projection/", self.workflow)
        self.assertIn("ref: ${{ github.sha }}", self.workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
