#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CALCULATOR_PATH = HERE / "calculator.py"
FIXTURE = HERE / "fixtures" / "synthetic_deployments.csv"

spec = importlib.util.spec_from_file_location("uiowa64_calculator", CALCULATOR_PATH)
calc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = calc
assert spec.loader is not None
spec.loader.exec_module(calc)

START = calc._required_time("2026-09-01T00:00:00Z", "start")
END = calc._required_time("2026-09-15T00:00:00Z", "end")


class CalculatorTests(unittest.TestCase):
    def test_fixture_expected_outputs(self):
        report = calc.calculate(
            calc.load_deployments(FIXTURE),
            window_start=START,
            window_end=END,
        )
        metrics = report["metrics"]
        self.assertEqual(report["scope"]["deployment_count"], 8)
        self.assertEqual(metrics["deployment_frequency"]["deployments_per_week"], 4.0)
        self.assertEqual(metrics["deployment_frequency"]["median_interdeployment_hours"], 46.0)
        self.assertEqual(metrics["change_lead_time"]["median"], 11.0)
        self.assertEqual(metrics["change_lead_time"]["mean"], 14.875)
        self.assertEqual(metrics["failed_deployment_recovery_time"]["median"], 3.0)
        self.assertEqual(metrics["failed_deployment_recovery_time"]["mean"], 3.0)
        self.assertEqual(metrics["change_fail_rate"]["percent"], 25.0)
        self.assertEqual(metrics["deployment_rework_rate"]["percent"], 25.0)

    def _mutated_csv(self, mutate):
        with FIXTURE.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        mutate(rows)
        tmp = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", suffix=".csv", delete=False
        )
        with tmp:
            writer = csv.DictWriter(tmp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return Path(tmp.name)

    def test_multiple_services_require_filter(self):
        path = self._mutated_csv(lambda rows: rows[-1].update(service="other-service"))
        with self.assertRaises(calc.DataError):
            calc.calculate(calc.load_deployments(path), window_start=START, window_end=END)

    def test_missing_commit_marks_lead_time_partial(self):
        path = self._mutated_csv(lambda rows: rows[0].update(commit_at=""))
        report = calc.calculate(calc.load_deployments(path), window_start=START, window_end=END)
        coverage = report["metrics"]["change_lead_time"]["coverage"]
        self.assertEqual(coverage["status"], "PARTIAL")
        self.assertEqual(coverage["used"], 7)
        self.assertEqual(coverage["missing"], 1)

    def test_failed_deployment_missing_recovery_marks_partial(self):
        path = self._mutated_csv(lambda rows: rows[1].update(recovered_at=""))
        report = calc.calculate(calc.load_deployments(path), window_start=START, window_end=END)
        coverage = report["metrics"]["failed_deployment_recovery_time"]["coverage"]
        self.assertEqual(coverage["status"], "PARTIAL")
        self.assertEqual(coverage["used"], 1)
        self.assertEqual(coverage["missing"], 1)

    def test_blank_rates_mark_partial(self):
        def mutate(rows):
            rows[0]["intervention_required"] = ""
            rows[0]["unplanned_rework"] = ""
        path = self._mutated_csv(mutate)
        report = calc.calculate(calc.load_deployments(path), window_start=START, window_end=END)
        self.assertEqual(report["metrics"]["change_fail_rate"]["coverage"]["status"], "PARTIAL")
        self.assertEqual(report["metrics"]["deployment_rework_rate"]["coverage"]["status"], "PARTIAL")

    def test_commit_after_deploy_rejected(self):
        path = self._mutated_csv(
            lambda rows: rows[0].update(commit_at="2026-09-01T13:00:00Z")
        )
        with self.assertRaises(calc.DataError):
            calc.load_deployments(path)


if __name__ == "__main__":
    unittest.main()
