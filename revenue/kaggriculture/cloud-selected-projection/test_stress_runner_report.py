#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the existing report's explicit actual-runner CI binding.

No policy is imported or executed. Synthetic fixture counts are parser inputs,
not runtime evidence; the workflow runs the unchanged boundary CLI separately.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import build_combined_report as subject
import test_combined_report as retained

STRESS = subject.ROOT + "cloud-economic-stress/"
DECLARATIONS = (
    ("stress_runner_boundary", "stress-runner-boundary-tests.log", STRESS + "test_runner_guard_join.py", 20),
    ("stress_runner_existing", "stress-runner-existing-tests.log", STRESS + "test_runner.py", 2),
    ("stress_runner_reporter", "stress-runner-reporter-tests.log", subject.PROJECTION + "test_stress_runner_report.py", 13),
)


class StressRunnerReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)
        retained.fixture(self.path)
        self.original = subject.build_report(self.path)
        snapshot_path = self.path / "SOURCE-SNAPSHOT.json"
        snapshot = json.loads(snapshot_path.read_text())
        paths = [row[2] for row in DECLARATIONS]
        paths += [STRESS + "runner.py", STRESS + "deadline_adapter.py"]
        snapshot["files"].update({p: {"sha256": retained.sha(p)} for p in paths})
        retained.save(snapshot_path, snapshot)
        for _, name, _, count in DECLARATIONS:
            (self.path / name).write_text(retained.log(count))
        self.boundary = dict(tests_run=20, failures=[], errors=[], skipped=[],
                             runner_sha256=retained.sha(STRESS + "runner.py"),
                             adapter_sha256=retained.sha(STRESS + "deadline_adapter.py"),
                             test_sha256=retained.sha(DECLARATIONS[0][2]),
                             actual_source=False, full_games=0, new_game_seeds=[])
        self.save_boundary()

    def save_boundary(self):
        retained.save(self.path / "stress-runner-boundary.json", self.boundary)

    def build(self):
        return subject.build_report(self.path, include_stress_runner=True)

    def test_named_suites_count_separately(self):
        result = self.build()
        self.assertTrue(result["successful"], result["problems"])
        self.assertEqual(result["suite_count"], 9)
        self.assertEqual(result["total_tests"], 79 + 20 + 2 + 13)
        for key, _, _, count in DECLARATIONS:
            self.assertEqual(result[key + "_tests"], count)
        self.assertEqual(result["stress_runner_binding"]["actual_source"], False)

    def test_new_evidence_is_opt_in_and_legacy_values_stay_equal(self):
        without = subject.build_report(self.path)
        for key in ("total_tests", "suites", "suite_count", "complete", "successful",
                    "engine_sha256", "legacy_three_suite_tests"):
            self.assertEqual(without[key], self.original[key])
        self.assertNotIn("stress_runner_binding", without)

    def test_all_three_executed_byte_bindings_are_required(self):
        original = dict(self.boundary)
        for field in ("runner_sha256", "adapter_sha256", "test_sha256"):
            with self.subTest(field=field):
                self.boundary = dict(original); self.boundary[field] = "0" * 64
                self.save_boundary()
                result = self.build()
                self.assertFalse(result["successful"])
                self.assertTrue(any(field in p for p in result["problems"]))

    def test_json_log_count_mismatch_and_boolean_count_fail(self):
        for count in (23, True, None):
            with self.subTest(count=count):
                self.boundary["tests_run"] = count; self.save_boundary()
                self.assertFalse(self.build()["successful"])

    def test_error_and_skip_arrays_must_exist_and_be_empty(self):
        original = dict(self.boundary)
        for field in ("failures", "errors", "skipped"):
            for value in (["failure"], 0, None):
                with self.subTest(field=field, value=value):
                    self.boundary = dict(original); self.boundary[field] = value
                    self.save_boundary()
                    self.assertFalse(self.build()["successful"])

    def test_local_actual_state_receipt_cannot_be_called_hosted_boundary(self):
        for value in (True, None, 0, "false"):
            with self.subTest(value=value):
                self.boundary["actual_source"] = value; self.save_boundary()
                self.assertFalse(self.build()["successful"])

    def test_games_and_seed_claims_are_not_accepted(self):
        for field, value in (("full_games", 1), ("full_games", False),
                             ("full_games", None), ("new_game_seeds", [17]),
                             ("new_game_seeds", None), ("new_game_seeds", {})):
            with self.subTest(field=field, value=value):
                self.boundary.update(full_games=0, new_game_seeds=[])
                self.boundary[field] = value; self.save_boundary()
                self.assertFalse(self.build()["successful"])

    def test_missing_each_log_is_partial_not_silent_success(self):
        for key, name, _, _ in DECLARATIONS:
            path = self.path / name; original = path.read_bytes(); path.unlink()
            with self.subTest(name=name):
                result = self.build()
                self.assertFalse(result["successful"])
                self.assertIsNone(result["total_tests"])
                self.assertIsNone(result[key + "_tests"])
            path.write_bytes(original)

    def test_failed_retained_runner_log_cannot_pass(self):
        (self.path / DECLARATIONS[1][1]).write_text(retained.log(2, "FAILED (errors=1)"))
        result = self.build()
        self.assertFalse(result["successful"])
        self.assertEqual(result["suites"]["stress_runner_existing"]["errors"], 1)

    def test_missing_runtime_or_test_snapshot_binding_fails(self):
        path = self.path / "SOURCE-SNAPSHOT.json"; original = path.read_text()
        for name in (STRESS + "runner.py", STRESS + "deadline_adapter.py", *(r[2] for r in DECLARATIONS)):
            with self.subTest(path=name):
                snapshot = json.loads(original); snapshot["files"].pop(name)
                retained.save(path, snapshot)
                self.assertFalse(self.build()["successful"])

    def test_malformed_or_duplicate_json_is_rejected(self):
        for text in ('{"tests_run":20,', '{"tests_run":20,"tests_run":23}'):
            with self.subTest(text=text):
                (self.path / "stress-runner-boundary.json").write_text(text)
                self.assertFalse(self.build()["successful"])

    def test_reader_leaves_evidence_unchanged_and_is_deterministic(self):
        before = {p.name: p.read_bytes() for p in self.path.iterdir()}
        self.assertEqual(self.build(), self.build())
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.path.iterdir()})

    def test_existing_cli_flag_writes_complete_then_partial_report(self):
        output = self.path / "out.json"
        cmd = [sys.executable, "-B", subject.__file__, "--directory", str(self.path),
               "--include-stress-runner", "--output", str(output)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(output.read_text())["stress_runner_boundary_tests"], 20)
        (self.path / DECLARATIONS[0][1]).unlink()
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIsNone(json.loads(output.read_text())["total_tests"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
