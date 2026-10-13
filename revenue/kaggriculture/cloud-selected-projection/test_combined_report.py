#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Self-contained report-parser fixtures, not gameplay or execution evidence."""
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


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def log(n, status="OK", trailer=""):
    return f"test_fixture ... ok\n\n----------------------------------------------------------------------\nRan {n} tests in 0.100s\n\n{status}\n{trailer}"


def fixture(directory):
    paths = {row[2] for row in subject.SUITES}
    paths.update(subject.LAB + p for p in (
        "selected_action_sell.py", "selected_sell_core.py", "mechanics.py",
        "reference/decision/decision.py", "ordered_selected_sell.py",
        "reference/evaluator/evaluate.py", "reference/evaluator/loader.py",
        "reference/engine/kaggriculture.py", "reference/engine/kaggriculture.json",
        "reference/engine/utils.py"))
    paths.add(subject.PROJECTION + "projection.py")
    snapshot = dict(checkout="a" * 40, run_id="123", attempt="1", python="fixture",
                    files={p: {"sha256": sha(p)} for p in paths})
    save(directory / "SOURCE-SNAPSHOT.json", snapshot)
    counts = dict(original=16, projection=21, market=14, loader=7, empty_lot=15, joined_wrapper=6)
    for key, name, _, _, _ in subject.SUITES:
        (directory / name).write_text(log(counts[key]), encoding="utf-8")
    engine = {p: sha(subject.LAB + "reference/engine/" + p)
              for p in ("kaggriculture.py", "kaggriculture.json", "utils.py")}
    save(directory / "projection-results.json", dict(tests_run=21, failures=0, errors=0,
        differential_cases=144, interpreter_transitions=378, engine_sha256=engine,
        seller_sha256=sha(subject.LAB + "selected_action_sell.py"),
        projection_sha256=sha(subject.PROJECTION + "projection.py")))
    save(directory / "market-results.json", dict(test_methods=14, failures=0, errors=0,
        successful=True, official_market_cases=28, engine_sha256=engine,
        sources={p: sha(subject.LAB + p) for p in (
            "selected_action_sell.py", "selected_sell_core.py", "mechanics.py", "reference/decision/decision.py")}))
    save(directory / "loader-results.json", dict(test_methods=7, failures=0, errors=0,
        successful=True, official_market_cases=4, source_sha256=dict(
            checker=sha(subject.MARKET + "check_market_contracts.py"),
            evaluator=sha(subject.LAB + "reference/evaluator/evaluate.py"),
            loader=sha(subject.LAB + "reference/evaluator/loader.py"))))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        fixture(self.path)

    def report(self, **kwargs):
        return subject.build_report(self.path, **kwargs)

    def mutate(self, name, change):
        path = self.path / name
        value = json.loads(path.read_text())
        change(value)
        save(path, value)

    def test_six_suites_total_79_instead_of_legacy_51(self):
        report = self.report()
        self.assertTrue(report["successful"], report["problems"])
        self.assertTrue(report["complete"])
        self.assertEqual(report["total_tests"], 79)
        self.assertEqual(report["legacy_three_suite_tests"], 51)
        self.assertEqual(report["suite_count"], 6)
        self.assertEqual(report["full_games"], 0)

    def test_reporter_suite_is_explicit_and_counted_when_requested(self):
        self.mutate("SOURCE-SNAPSHOT.json", lambda d: d["files"].update({subject.REPORTER[2]: {"sha256": sha("reporter")}}))
        (self.path / "reporter-tests.log").write_text(log(20))
        report = self.report(include_reporter=True)
        self.assertTrue(report["successful"], report["problems"])
        self.assertEqual(report["total_tests"], 99)
        self.assertEqual(report["reporter_tests"], 20)
        self.assertEqual(self.report()["total_tests"], 79)

    def add_funded_fixture(self):
        names = (subject.FUNDED_JOIN[2], subject.LAB + "integrated_selected.py",
                 subject.LAB + "selected_action_sell.py", subject.LAB + "reference/engine/kaggriculture.py")
        self.mutate("SOURCE-SNAPSHOT.json", lambda d: d["files"].update({p: {"sha256": sha(p)} for p in names}))
        (self.path / "funded-join-tests.log").write_text(log(16))
        save(self.path / "funded-join-results.json", dict(test_methods=16, failures=0,
            errors=0, successful=True, official_transitions=16, full_games=0,
            workflow_run="123", workflow_attempt="1",
            sources={p[len(subject.ROOT):]: {"sha256": sha(p)} for p in names}))

    def test_funded_suite_is_preserved_and_included(self):
        self.add_funded_fixture()
        report = self.report(include_funded_join=True)
        self.assertTrue(report["successful"], report["problems"])
        self.assertEqual(report["total_tests"], 95)
        self.assertEqual(report["funded_join_tests"], 16)
        self.assertEqual(report["funded_join_transitions"], 16)

    def test_funded_missing_source_or_mixed_run_cannot_pass(self):
        self.add_funded_fixture()
        original = (self.path / "funded-join-results.json").read_text()
        for change in (lambda d: d.update(sources={}), lambda d: d.update(workflow_run="124")):
            with self.subTest(change=change):
                (self.path / "funded-join-results.json").write_text(original)
                self.mutate("funded-join-results.json", change)
                self.assertFalse(self.report(include_funded_join=True)["successful"])

    def add_runtime_fixtures(self):
        paths = [row[2] for row in subject.RUNTIME_REGRESSIONS]
        paths += [subject.ROOT + "cloud-market-game-theory/adaptive/runtime.py",
                  ".github/workflows/titan-selected-projection.yml"]
        self.mutate("SOURCE-SNAPSHOT.json", lambda d: d["files"].update({p: {"sha256": sha(p)} for p in paths}))
        for row, count in zip(subject.RUNTIME_REGRESSIONS, (19, 5, 8)):
            (self.path / row[1]).write_text(log(count))
        save(self.path / "capture-binding-results.json", dict(
            tests=dict(run=19, failures=0, errors=0, success=True),
            runtime_sha256=sha(subject.ROOT + "cloud-market-game-theory/adaptive/runtime.py"),
            optimizer_sha256=sha(subject.LAB + "selected_sell_core.py")))

    def test_runtime_regressions_count_nested_capture_summary(self):
        self.add_runtime_fixtures()
        report = self.report(include_runtime_regressions=True)
        self.assertTrue(report["successful"], report["problems"])
        self.assertEqual(report["total_tests"], 111)
        self.assertEqual(report["capture_binding_tests"], 19)
        self.assertEqual(report["score_schedule_tests"], 5)
        self.assertEqual(report["workflow_bindings_tests"], 8)
        self.assertEqual(self.report()["total_tests"], 79)

    def test_capture_count_and_optimizer_bindings_cannot_drift(self):
        self.add_runtime_fixtures()
        original = (self.path / "capture-binding-results.json").read_text()
        for change in (lambda d: d["tests"].update(run=18),
                       lambda d: d.update(optimizer_sha256="0" * 64),
                       lambda d: d.update(tests=[])):
            with self.subTest(change=change):
                (self.path / "capture-binding-results.json").write_text(original)
                self.mutate("capture-binding-results.json", change)
                self.assertFalse(self.report(include_runtime_regressions=True)["successful"])

    def add_cancellation_fixture(self):
        names = (subject.CANCELLATION[2], subject.ROOT + "cloud-economic-stress/deadline_adapter.py")
        self.mutate("SOURCE-SNAPSHOT.json", lambda d: d["files"].update({p: {"sha256": sha(p)} for p in names}))
        (self.path / "deadline-cancellation-tests.log").write_text(log(18))
        save(self.path / "deadline-cancellation.json", dict(tests_run=18,
            new_regression_methods=15, unchanged_upstream_guard_methods=3,
            adapter_sha256=sha(names[1]), failures=[], errors=[], skipped=[]))

    def test_cancellation_arrays_and_partition_are_supported(self):
        self.add_cancellation_fixture()
        report = self.report(include_cancellation=True)
        self.assertTrue(report["successful"], report["problems"])
        self.assertEqual(report["total_tests"], 97)
        self.assertEqual(report["deadline_cancellation_tests"], 18)
        self.assertEqual(report["cancellation_new_regression_methods"], 15)
        self.assertEqual(report["cancellation_retained_guard_methods"], 3)

    def test_cancellation_nonempty_or_wrong_error_arrays_fail(self):
        self.add_cancellation_fixture()
        original = (self.path / "deadline-cancellation.json").read_text()
        for field in ("failures", "errors", "skipped"):
            for value in (["case"], 0, None):
                with self.subTest(field=field, value=value):
                    (self.path / "deadline-cancellation.json").write_text(original)
                    self.mutate("deadline-cancellation.json", lambda d: d.update({field: value}))
                    self.assertFalse(self.report(include_cancellation=True)["successful"])

    def test_cancellation_adapter_binding_cannot_drift(self):
        self.add_cancellation_fixture()
        self.mutate("deadline-cancellation.json", lambda d: d.update(adapter_sha256="0" * 64))
        self.assertFalse(self.report(include_cancellation=True)["successful"])

    def test_cancellation_method_partition_cannot_inflate_count(self):
        self.add_cancellation_fixture()
        for value in (16, -1, True, None):
            with self.subTest(value=value):
                self.mutate("deadline-cancellation.json", lambda d: d.update(new_regression_methods=value))
                self.assertFalse(self.report(include_cancellation=True)["successful"])

    def test_missing_cancellation_log_retains_known_counts(self):
        self.add_cancellation_fixture()
        (self.path / "deadline-cancellation-tests.log").unlink()
        report = self.report(include_cancellation=True)
        self.assertFalse(report["successful"])
        self.assertIsNone(report["total_tests"])
        self.assertEqual(report["observed_tests"], 79)

    def test_cancellation_is_opt_in_and_not_double_counted(self):
        self.add_cancellation_fixture()
        self.add_funded_fixture()
        self.add_runtime_fixtures()
        legacy = self.report(include_funded_join=True, include_runtime_regressions=True)
        included = self.report(include_funded_join=True, include_runtime_regressions=True, include_cancellation=True)
        self.assertTrue(included["successful"], included["problems"])
        self.assertEqual(included["total_tests"], legacy["total_tests"] + 18)
        self.assertNotIn("deadline_cancellation_tests", legacy)

    def add_ledger_fixture(self):
        self.mutate("SOURCE-SNAPSHOT.json", lambda d: d["files"].update({subject.LEDGER_SCHEDULE[2]: {"sha256": sha("ledger-tests")}}))
        (self.path / "ledger-schedule-tests.log").write_text(log(20))
        market = json.loads((self.path / "market-results.json").read_text())
        save(self.path / "ledger-schedule-results.json", dict(test_methods=20,
            failures=0, errors=0, skipped=0, successful=True,
            sources_sha256=market["sources"], engine_sha256=market["engine_sha256"],
            counts={"fixture_cases": 4}, reference_method_sha256=sha("reported-reference")))

    def test_ledger_counts_are_opt_in_and_source_bound(self):
        self.add_ledger_fixture()
        report = self.report(include_ledger_schedule=True)
        self.assertTrue(report["successful"], report["problems"])
        self.assertEqual(report["total_tests"], 99)
        self.assertEqual(report["ledger_schedule_tests"], 20)
        self.assertEqual(report["ledger_schedule_case_counts"], {"fixture_cases": 4})
        self.assertEqual(self.report()["total_tests"], 79)

    def test_ledger_engine_and_runtime_drift_are_detected(self):
        self.add_ledger_fixture()
        original = (self.path / "ledger-schedule-results.json").read_text()
        changes = [lambda d: d["engine_sha256"].update({"utils.py": "0" * 64}),
                   lambda d: d.update(sources_sha256={})]
        for change in changes:
            with self.subTest(change=change):
                (self.path / "ledger-schedule-results.json").write_text(original)
                self.mutate("ledger-schedule-results.json", change)
                self.assertFalse(self.report(include_ledger_schedule=True)["successful"])

    def test_ledger_count_disagreement_skips_and_bad_cases_fail(self):
        self.add_ledger_fixture()
        original = (self.path / "ledger-schedule-results.json").read_text()
        for change in ({"test_methods": 19}, {"skipped": 1}, {"skipped": False},
                       {"counts": []}, {"counts": {"cases": -1}}, {"counts": {"cases": True}}):
            with self.subTest(change=change):
                (self.path / "ledger-schedule-results.json").write_text(original)
                self.mutate("ledger-schedule-results.json", lambda d: d.update(change))
                self.assertFalse(self.report(include_ledger_schedule=True)["successful"])

    def test_ledger_and_cancellation_remain_separate_suites(self):
        self.add_ledger_fixture()
        self.add_cancellation_fixture()
        report = self.report(include_ledger_schedule=True, include_cancellation=True)
        self.assertTrue(report["successful"], report["problems"])
        self.assertEqual(report["total_tests"], 117)
        self.assertEqual(report["suite_count"], 8)
        self.assertEqual(report["legacy_three_suite_tests"], 51)

    def test_missing_extended_suites_preserve_known_51_not_complete(self):
        for name in ("loader-tests.log", "empty-lot-tests.log", "joined-wrapper-tests.log", "loader-results.json"):
            (self.path / name).unlink()
        report = self.report()
        self.assertFalse(report["successful"])
        self.assertFalse(report["complete"])
        self.assertEqual(report["observed_tests"], 51)
        self.assertIsNone(report["total_tests"])
        self.assertIsNone(report["loader_tests"])

    def test_missing_reporter_does_not_silently_pass(self):
        report = self.report(include_reporter=True)
        self.assertFalse(report["successful"])
        self.assertIsNone(report["reporter_tests"])

    def test_failed_suite_is_not_counted_as_pass(self):
        (self.path / "empty-lot-tests.log").write_text(log(15, "FAILED (failures=1)"))
        report = self.report()
        self.assertFalse(report["successful"])
        self.assertEqual(report["total_tests"], 79)
        self.assertEqual(report["suites"]["empty_lot"]["failures"], 1)

    def test_skipped_or_expected_failure_is_not_a_full_pass(self):
        for status in ("OK (skipped=1)", "OK (expected failures=1)"):
            with self.subTest(status=status):
                (self.path / "original-seller-tests.log").write_text(log(16, status))
                self.assertFalse(self.report()["successful"])

    def test_zero_methods_do_not_pass(self):
        (self.path / "empty-lot-tests.log").write_text(log(0))
        self.assertFalse(self.report()["successful"])

    def test_truncated_and_duplicate_run_summaries_do_not_pass(self):
        for text in (log(15).replace("\nOK\n", "\n"), log(15) + log(15), log(15) + "\nRan 2 tests in 0.1s\n"):
            with self.subTest(text=text[-60:]):
                (self.path / "empty-lot-tests.log").write_text(text)
                report = self.report()
                self.assertFalse(report["successful"])
                self.assertIsNone(report["empty_lot_tests"])

    def test_trailing_report_accepted_but_traceback_not_accepted(self):
        self.assertTrue(subject.parse_unittest(log(2, trailer='{"test_methods":2}\n'))["successful"])
        with self.assertRaises(ValueError):
            subject.parse_unittest(log(2, trailer="Traceback (most recent call last):\nRuntimeError: stopped\n"))

    def test_json_log_count_mismatch(self):
        self.mutate("market-results.json", lambda d: d.update(test_methods=13))
        self.assertFalse(self.report()["successful"])

    def test_failed_json_cannot_be_hidden_by_ok_log(self):
        self.mutate("projection-results.json", lambda d: d.update(errors=1))
        self.assertFalse(self.report()["successful"])

    def test_seller_drift_and_projection_drift(self):
        for field in ("seller_sha256", "projection_sha256"):
            with self.subTest(field=field):
                fixture(self.path)
                self.mutate("projection-results.json", lambda d: d.update({field: "0" * 64}))
                self.assertFalse(self.report()["successful"])

    def test_engine_json_agreement_alone_does_not_replace_snapshot_binding(self):
        for name in ("projection-results.json", "market-results.json"):
            self.mutate(name, lambda d: d["engine_sha256"].update({"utils.py": "0" * 64}))
        report = self.report()
        self.assertFalse(report["same_engine"])
        self.assertFalse(report["successful"])

    def test_loader_hash_is_bound_to_recorded_source(self):
        self.mutate("loader-results.json", lambda d: d["source_sha256"].update(loader="0" * 64))
        self.assertFalse(self.report()["successful"])

    def test_missing_suite_source_row_is_explicit(self):
        self.mutate("SOURCE-SNAPSHOT.json", lambda d: d["files"].pop(subject.LAB + "test_ordered_selected_sell.py"))
        report = self.report()
        self.assertFalse(report["successful"])
        self.assertIsNone(report["suites"]["joined_wrapper"]["test_source_sha256"])

    def test_duplicate_json_keys_are_not_silently_overwritten(self):
        (self.path / "loader-results.json").write_text('{"test_methods":0,"test_methods":7}')
        self.assertFalse(self.report()["successful"])

    def test_malformed_snapshot_has_an_explicit_report(self):
        (self.path / "SOURCE-SNAPSHOT.json").write_text('{"files":[')
        report = self.report()
        self.assertFalse(report["successful"])
        self.assertTrue(report["problems"])

    def test_boolean_counts_do_not_equal_integer_evidence(self):
        self.mutate("market-results.json", lambda d: d.update(failures=False))
        self.assertFalse(self.report()["successful"])

    def test_outputs_are_deterministic_and_inputs_unchanged(self):
        before = {p.name: p.read_bytes() for p in self.path.iterdir()}
        first = self.report()
        self.assertEqual(first, self.report())
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.path.iterdir()})
        self.assertEqual(first["input_sha256"]["empty-lot-tests.log"], hashlib.sha256(before["empty-lot-tests.log"]).hexdigest())

    def test_cli_exit_and_serialized_partial_report(self):
        output = self.path / "output.json"
        cmd = [sys.executable, str(Path(subject.__file__)), "--directory", str(self.path), "--output", str(output)]
        ok = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(output.read_text())["total_tests"], 79)
        (self.path / "joined-wrapper-tests.log").unlink()
        bad = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1, bad.stderr)
        self.assertIsNone(json.loads(output.read_text())["total_tests"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
