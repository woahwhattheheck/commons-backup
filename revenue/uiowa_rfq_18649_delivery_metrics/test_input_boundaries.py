"""Contract regressions for UIOWA-064. Set UIOWA64_TARGET for exact-head review."""
from __future__ import annotations

import contextlib
import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone, tzinfo
import importlib.util
import io
import itertools
import os
from pathlib import Path
import sys
import tempfile
import unittest

TARGET = Path(os.environ.get("UIOWA64_TARGET", str(Path(__file__).with_name("calculator.py"))))
SPEC = importlib.util.spec_from_file_location("uiowa64_boundary_target", TARGET)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load calculator under test")
calc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = calc
SPEC.loader.exec_module(calc)
HEADERS = ["deployment_id", "service", "commit_at", "deployed_at", "intervention_required", "recovered_at", "unplanned_rework", "notes"]
START = datetime(2026, 9, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 15, tzinfo=timezone.utc)
GOOD = ["D1", "synthetic-service", "2026-09-01T00:00:00Z", "2026-09-01T01:00:00Z", "true", "2026-09-01T02:00:00Z", "false", "SYNTHETIC event"]


class NoOffset(tzinfo):
    def utcoffset(self, dt):
        return None


class SyntheticFoldZone(tzinfo):
    """A deterministic repeated-hour clock; no host timezone database needed."""
    def utcoffset(self, dt):
        return timedelta(hours=-5 if dt is not None and dt.fold else -4)

    def dst(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return "SYNTHETIC-FOLD"


class InputBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def csv_path(self, rows=None, headers=None):
        path = self.root / "input.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADERS if headers is None else headers)
            writer.writerows([GOOD] if rows is None else rows)
        return path

    def good(self):
        return calc.load_deployments(self.csv_path())[0]

    def report(self, rows):
        return calc.calculate(rows, window_start=START, window_end=END)

    def recovery(self, rows):
        return self.report(rows)["metrics"]["failed_deployment_recovery_time"]

    def test_unknown_eligibility_does_not_report_complete_recovery(self):
        known = self.good()
        unknown = replace(known, deployment_id="D2", intervention_required=None, recovered_at=None)
        result = self.recovery([known, unknown])
        self.assertEqual(result["coverage"]["status"], "PARTIAL")
        self.assertEqual(result["median"], 1.0)

    def test_all_unknown_failure_classifications_are_partial_not_not_observed(self):
        row = replace(self.good(), intervention_required=None, recovered_at=None)
        result = self.recovery([row])
        self.assertEqual(result["coverage"]["status"], "PARTIAL")
        self.assertIsNone(result["median"])

    def test_eligibility_unknown_is_separate_from_known_recovery_missing(self):
        known = self.good()
        unfinished = replace(known, deployment_id="D2", recovered_at=None)
        unknown = replace(known, deployment_id="D3", intervention_required=None, recovered_at=None)
        coverage = self.recovery([known, unfinished, unknown])["coverage"]
        self.assertEqual(coverage["eligible"], 2)
        self.assertEqual(coverage["used"], 1)
        self.assertEqual(coverage["missing"], 1)
        self.assertEqual(coverage.get("eligibility_unknown"), 1)

    def test_known_no_failures_stays_not_observed(self):
        row = replace(self.good(), intervention_required=False, recovered_at=None)
        self.assertEqual(self.recovery([row])["coverage"]["status"], "NOT_OBSERVED")
        self.assertIsNone(self.recovery([row])["median"])

    def test_all_known_recovery_stays_complete(self):
        self.assertEqual(self.recovery([self.good()])["coverage"]["status"], "COMPLETE")

    def test_unknown_outside_window_does_not_degrade_selected_cohort(self):
        row = self.good()
        other = replace(row, deployment_id="OUT", deployed_at=END, intervention_required=None, recovered_at=None)
        self.assertEqual(self.recovery([row, other])["coverage"]["status"], "COMPLETE")

    def test_unknown_other_service_does_not_degrade_selected_cohort(self):
        row = self.good()
        other = replace(row, deployment_id="OTHER", service="other", intervention_required=None, recovered_at=None)
        result = calc.calculate([row, other], window_start=START, window_end=END, service=row.service)
        self.assertEqual(result["metrics"]["failed_deployment_recovery_time"]["coverage"]["status"], "COMPLETE")

    def test_duplicate_csv_headers_rejected(self):
        path = self.csv_path(rows=[GOOD + ["replacement-service"]], headers=HEADERS + ["service"])
        with self.assertRaises(calc.DataError):
            calc.load_deployments(path)

    def test_blank_csv_header_rejected(self):
        path = self.csv_path(rows=[GOOD + ["extra"]], headers=HEADERS + [""])
        with self.assertRaises(calc.DataError):
            calc.load_deployments(path)

    def test_short_csv_row_is_data_error_not_attribute_error(self):
        path = self.csv_path(rows=[GOOD[:-1]])
        with self.assertRaises(calc.DataError):
            calc.load_deployments(path)

    def test_overflow_csv_row_rejected(self):
        path = self.csv_path(rows=[GOOD + ["unheaded value"]])
        with self.assertRaises(calc.DataError):
            calc.load_deployments(path)

    def test_extra_named_metadata_column_remains_supported(self):
        path = self.csv_path(rows=[GOOD + ["metadata"]], headers=HEADERS + ["provenance"])
        self.assertEqual(len(calc.load_deployments(path)), 1)

    def test_blank_optional_cells_preserve_unknown(self):
        row = GOOD.copy()
        row[2] = row[4] = row[5] = row[6] = ""
        loaded = calc.load_deployments(self.csv_path(rows=[row]))[0]
        self.assertIsNone(loaded.commit_at)
        self.assertIsNone(loaded.intervention_required)
        self.assertIsNone(loaded.unplanned_rework)

    def test_direct_duplicate_events_rejected(self):
        row = self.good()
        with self.assertRaises(calc.DataError):
            self.report([row, row])

    def test_direct_negative_lead_time_rejected(self):
        row = self.good()
        with self.assertRaises(calc.DataError):
            self.report([replace(row, commit_at=row.deployed_at + timedelta(hours=1))])

    def test_direct_negative_recovery_time_rejected(self):
        row = self.good()
        with self.assertRaises(calc.DataError):
            self.report([replace(row, recovered_at=row.deployed_at - timedelta(hours=1))])

    def test_direct_recovery_without_failure_rejected(self):
        with self.assertRaises(calc.DataError):
            self.report([replace(self.good(), intervention_required=False)])

    def test_direct_string_classification_rejected(self):
        with self.assertRaises(calc.DataError):
            self.report([replace(self.good(), intervention_required="true")])

    def test_direct_integer_classification_rejected(self):
        with self.assertRaises(calc.DataError):
            self.report([replace(self.good(), intervention_required=1)])

    def test_direct_string_rework_rejected(self):
        with self.assertRaises(calc.DataError):
            self.report([replace(self.good(), unplanned_rework="false")])

    def test_direct_blank_identity_rejected(self):
        with self.assertRaises(calc.DataError):
            self.report([replace(self.good(), deployment_id=" ")])

    def test_direct_blank_service_rejected(self):
        with self.assertRaises(calc.DataError):
            self.report([replace(self.good(), service=" ")])

    def test_direct_naive_timestamp_is_data_error(self):
        row = self.good()
        with self.assertRaises(calc.DataError):
            self.report([replace(row, deployed_at=row.deployed_at.replace(tzinfo=None))])

    def test_window_with_no_utc_offset_is_data_error(self):
        with self.assertRaises(calc.DataError):
            calc.calculate([self.good()], window_start=START.replace(tzinfo=NoOffset()), window_end=END)

    def test_dst_fold_lead_time_uses_elapsed_utc_not_wall_time(self):
        ny = SyntheticFoldZone()
        row = replace(self.good(),
                      commit_at=datetime(2026, 11, 1, 1, 0, tzinfo=ny, fold=0),
                      deployed_at=datetime(2026, 11, 1, 1, 30, tzinfo=ny, fold=1),
                      intervention_required=False, recovered_at=None)
        result = calc.calculate([row],
            window_start=datetime(2026, 11, 1, tzinfo=timezone.utc),
            window_end=datetime(2026, 11, 2, tzinfo=timezone.utc))
        self.assertEqual(result["metrics"]["change_lead_time"]["median"], 1.5)

    def cli(self, path, *extra):
        return calc.main([str(path), "--window-start", START.isoformat(), "--window-end", END.isoformat(), *extra])

    def test_output_oserror_has_exit_two_without_traceback(self):
        out = self.root / "missing-directory" / "report.json"
        with contextlib.redirect_stderr(io.StringIO()) as error:
            status = self.cli(self.csv_path(), "--output", str(out))
        self.assertEqual(status, 2)
        self.assertIn("ERROR:", error.getvalue())

    def test_invalid_utf8_has_exit_two_without_traceback(self):
        path = self.root / "input.csv"
        path.write_bytes(b"\xff\xfe\x80")
        with contextlib.redirect_stderr(io.StringIO()) as error:
            status = self.cli(path)
        self.assertEqual(status, 2)
        self.assertIn("ERROR:", error.getvalue())

    def test_unclosed_csv_quote_rejected_by_cli(self):
        path = self.root / "input.csv"
        path.write_text(",".join(HEADERS) + "\n" + ",".join(GOOD[:-1]) + ',"unclosed', encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            status = self.cli(path)
        self.assertEqual(status, 2)

    def test_exhaustive_recovery_cohorts_match_independent_oracle(self):
        seed = self.good()
        # Failure classification and recovery availability are distinct dimensions.
        states = [(False, None), (None, None), (True, None),
                  (True, seed.recovered_at), (None, seed.recovered_at)]
        for combination in itertools.product(states, repeat=3):
            with self.subTest(combination=combination):
                rows = [replace(seed, deployment_id=f"D{i}",
                                intervention_required=state[0], recovered_at=state[1])
                        for i, state in enumerate(combination)]
                metric = self.recovery(rows)
                failed = sum(s[0] is True for s in combination)
                used = sum(s[0] is True and s[1] is not None for s in combination)
                unknown = sum(s[0] is None for s in combination)
                expected_status = (
                    "PARTIAL" if unknown or failed > used else
                    "COMPLETE" if failed else "NOT_OBSERVED"
                )
                coverage = metric["coverage"]
                self.assertEqual(coverage["status"], expected_status)
                self.assertEqual(coverage["eligible"], failed)
                self.assertEqual(coverage["used"], used)
                self.assertEqual(coverage["missing"], failed - used)
                self.assertEqual(coverage.get("eligibility_unknown"), unknown)
                self.assertEqual(metric["median"], 1.0 if used else None)

    def test_csv_and_direct_api_agree_for_all_125_recovery_cohorts(self):
        seed = self.good()
        states = [(False, None), (None, None), (True, None),
                  (True, seed.recovered_at), (None, seed.recovered_at)]
        def timestamp(value):
            return "" if value is None else value.isoformat()
        def classification(value):
            return "" if value is None else str(value).lower()
        for combination in itertools.product(states, repeat=3):
            rows = [replace(seed, deployment_id=f"D{i}",
                            intervention_required=state[0], recovered_at=state[1])
                    for i, state in enumerate(combination)]
            csv_rows = [[r.deployment_id, r.service, timestamp(r.commit_at),
                         timestamp(r.deployed_at), classification(r.intervention_required),
                         timestamp(r.recovered_at), classification(r.unplanned_rework), r.notes]
                        for r in rows]
            imported = calc.load_deployments(self.csv_path(rows=csv_rows))
            self.assertEqual(self.report(imported), self.report(rows))

    def test_fixture_numbers_unchanged(self):
        fixture = TARGET.parent / "fixtures" / "synthetic_deployments.csv"
        report = self.report(calc.load_deployments(fixture))
        metrics = report["metrics"]
        self.assertEqual(metrics["deployment_frequency"]["deployments_per_week"], 4.0)
        self.assertEqual(metrics["change_lead_time"]["median"], 11.0)
        self.assertEqual(metrics["change_lead_time"]["mean"], 14.875)
        self.assertEqual(metrics["failed_deployment_recovery_time"]["median"], 3.0)
        self.assertEqual(metrics["change_fail_rate"]["percent"], 25.0)
        self.assertEqual(metrics["deployment_rework_rate"]["percent"], 25.0)


if __name__ == "__main__":
    unittest.main()
