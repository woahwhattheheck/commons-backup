#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Caller-handler combined-report contracts; no signal tests or game execution."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import build_combined_report as subject
import test_combined_report as base


WORKFLOW = (Path(__file__).resolve().parents[3] /
            ".github/workflows/titan-selected-projection.yml")


class CallerHandlerReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        base.fixture(self.path)
        self.add_fixture()

    def mutate(self, name, change):
        path = self.path / name
        value = json.loads(path.read_text())
        change(value)
        base.save(path, value)

    def add_fixture(self):
        adapter = subject.ROOT + "cloud-economic-stress/deadline_adapter.py"
        test = subject.CALLER_HANDLER[2]
        self.mutate("SOURCE-SNAPSHOT.json", lambda d: d["files"].update({
            adapter: {"sha256": base.sha(adapter)},
            test: {"sha256": base.sha(test)},
        }))
        (self.path / subject.CALLER_HANDLER[1]).write_text(base.log(23), encoding="utf-8")
        base.save(self.path / subject.CALLER_HANDLER[3], {
            "tests_run": 23,
            "failures": [], "errors": [], "skipped": [],
            "adapter_sha256": base.sha(adapter),
            "test_sha256": base.sha(test),
            "games": 0,
            "measurements": [
                {"phase": "production", "handler_preserved": True,
                 "diagnostics": {"status": "deadline_fallback"}},
                {"phase": "transform", "handler_preserved": True,
                 "diagnostics": {"status": "deadline_fallback"}},
            ],
            "scope": "fixture only; no policy or game execution",
        })

    def report(self):
        return subject.build_report(self.path, include_caller_handler=True)

    def test_caller_handler_is_source_bound_counted_and_opt_in(self):
        report = self.report()
        self.assertTrue(report["successful"], report["problems"])
        self.assertTrue(report["complete"])
        self.assertEqual(report["total_tests"], 102)
        self.assertEqual(report["caller_handler_tests"], 23)
        self.assertEqual(report["caller_handler_measurements"], 2)
        self.assertEqual(report["caller_handler_binding"]["games"], 0)
        legacy = subject.build_report(self.path)
        self.assertTrue(legacy["successful"], legacy["problems"])
        self.assertEqual(legacy["total_tests"], 79)
        self.assertNotIn("caller_handler_tests", legacy)

    def test_json_and_log_counts_must_match(self):
        self.mutate(subject.CALLER_HANDLER[3], lambda d: d.update(tests_run=22))
        report = self.report()
        self.assertFalse(report["successful"])
        self.assertIn("caller_handler: JSON/log test counts differ", report["problems"])

    def test_failure_error_and_skip_arrays_must_be_empty_lists(self):
        original = (self.path / subject.CALLER_HANDLER[3]).read_text()
        for field in ("failures", "errors", "skipped"):
            for value in (["case"], 0, None):
                with self.subTest(field=field, value=value):
                    (self.path / subject.CALLER_HANDLER[3]).write_text(original)
                    self.mutate(subject.CALLER_HANDLER[3],
                                lambda d, field=field, value=value: d.update({field: value}))
                    self.assertFalse(self.report()["successful"])

    def test_adapter_and_test_hashes_cannot_drift(self):
        original = (self.path / subject.CALLER_HANDLER[3]).read_text()
        for field in ("adapter_sha256", "test_sha256"):
            with self.subTest(field=field):
                (self.path / subject.CALLER_HANDLER[3]).write_text(original)
                self.mutate(subject.CALLER_HANDLER[3],
                            lambda d, field=field: d.update({field: "0" * 64}))
                self.assertFalse(self.report()["successful"])

    def test_games_must_be_exact_zero_integer(self):
        original = (self.path / subject.CALLER_HANDLER[3]).read_text()
        for value in (1, -1, False, None):
            with self.subTest(value=value):
                (self.path / subject.CALLER_HANDLER[3]).write_text(original)
                self.mutate(subject.CALLER_HANDLER[3], lambda d, value=value: d.update(games=value))
                self.assertFalse(self.report()["successful"])

    def test_measurements_must_retain_handler_and_fallback(self):
        original = (self.path / subject.CALLER_HANDLER[3]).read_text()
        changes = (
            lambda d: d.update(measurements=[]),
            lambda d: d.update(measurements={}),
            lambda d: d["measurements"][0].update(handler_preserved=False),
            lambda d: d["measurements"][0].update(diagnostics={"status": "completed"}),
            lambda d: d["measurements"].append("bad"),
        )
        for change in changes:
            with self.subTest(change=change):
                (self.path / subject.CALLER_HANDLER[3]).write_text(original)
                self.mutate(subject.CALLER_HANDLER[3], change)
                self.assertFalse(self.report()["successful"])

    def test_missing_log_preserves_known_counts_but_is_incomplete(self):
        (self.path / subject.CALLER_HANDLER[1]).unlink()
        report = self.report()
        self.assertFalse(report["successful"])
        self.assertFalse(report["complete"])
        self.assertEqual(report["observed_tests"], 79)
        self.assertIsNone(report["total_tests"])
        self.assertIsNone(report["caller_handler_tests"])

    def test_cli_flag_publishes_the_bound_suite(self):
        output = self.path / "combined.json"
        command = [sys.executable, str(Path(subject.__file__)),
                   "--directory", str(self.path), "--include-caller-handler",
                   "--output", str(output)]
        completed = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(output.read_text())
        self.assertEqual(report["total_tests"], 102)
        self.assertEqual(report["caller_handler_tests"], 23)

    def test_existing_workflow_executes_and_declares_same_suite(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(text.count("- name: Caller handler replacement boundary tests"), 1)
        self.assertIn("caller-handler-results.json", text)
        self.assertIn("caller-handler-tests.log", text)
        self.assertIn("test_combined_report test_report_publication test_caller_handler_report", text)
        self.assertIn("--include-caller-handler", text)
        self.assertNotIn("caller_handler=23", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
