import copy
import csv
import io
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import analyze  # noqa: E402


def load(name):
    return analyze.read_csv(str(ROOT / name))


class OutcomeMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.recs = load("recommendations.csv")
        self.register = load("measure_register.csv")
        self.observations = load("examples/measurements.csv")

    def test_synthetic_pack_has_three_recommendations_and_six_comparisons(self):
        findings, comparisons = analyze.validate_and_compare(
            self.recs, self.register, self.observations
        )
        self.assertFalse([f for f in findings if f.level == "ERROR"])
        self.assertEqual(len(self.recs), 3)
        self.assertEqual(len(comparisons), 6)

    def test_each_recommendation_keeps_adoption_and_outcome_separate(self):
        findings, comparisons = analyze.validate_and_compare(
            self.recs, self.register, self.observations
        )
        self.assertFalse(
            [
                f
                for f in findings
                if f.code in {"ADOPTION_MEASURE_MISSING", "OUTCOME_MEASURE_MISSING"}
            ]
        )
        by_rec = {}
        for comparison in comparisons:
            by_rec.setdefault(comparison.recommendation_id, set()).add(
                comparison.measure_class
            )
        self.assertTrue(all(classes == {"adoption", "outcome"} for classes in by_rec.values()))

    def test_expected_rates_are_recomputed_from_counts(self):
        _, comparisons = analyze.validate_and_compare(
            self.recs, self.register, self.observations
        )
        by_id = {c.measure_id: c for c in comparisons}
        self.assertAlmostEqual(by_id["DEV-A1"].baseline_rate_pct, 40.0)
        self.assertAlmostEqual(by_id["DEV-A1"].followup_rate_pct, 85.0)
        self.assertAlmostEqual(by_id["DEV-A1"].absolute_change_pp, 45.0)
        self.assertEqual(by_id["DEV-A1"].directional_signal, "FAVORABLE_DIRECTION")
        self.assertAlmostEqual(by_id["OPS-O1"].baseline_rate_pct, 25.0)
        self.assertAlmostEqual(by_id["OPS-O1"].followup_rate_pct, 100.0 * 3 / 22)
        self.assertEqual(by_id["OPS-O1"].directional_signal, "FAVORABLE_DIRECTION")

    def test_population_definition_change_suppresses_comparison(self):
        observations = copy.deepcopy(self.observations)
        for row in observations:
            if row["measure_id"] == "DEV-A1" and row["period_role"] == "followup":
                row["population_definition"] = "Different synthetic population definition"
        findings, comparisons = analyze.validate_and_compare(
            self.recs, self.register, observations
        )
        dev = next(c for c in comparisons if c.measure_id == "DEV-A1")
        self.assertEqual(dev.comparability, "NOT_COMPARABLE")
        self.assertIsNone(dev.absolute_change_pp)
        self.assertTrue(any(f.code == "POPULATION_CHANGED" for f in findings))

    def test_missing_followup_stays_missing_not_zero(self):
        observations = [
            row
            for row in copy.deepcopy(self.observations)
            if not (row["measure_id"] == "SEC-O1" and row["period_role"] == "followup")
        ]
        findings, comparisons = analyze.validate_and_compare(
            self.recs, self.register, observations
        )
        sec = next(c for c in comparisons if c.measure_id == "SEC-O1")
        self.assertEqual(sec.directional_signal, "INSUFFICIENT_DATA")
        self.assertIsNone(sec.followup_rate_pct)
        self.assertTrue(any(f.code == "FOLLOWUP_MISSING" for f in findings))

    def test_report_contains_noncausal_boundary(self):
        findings, comparisons = analyze.validate_and_compare(
            self.recs, self.register, self.observations
        )
        report = analyze.render_markdown(self.recs, comparisons, findings)
        self.assertIn("does not establish causality", report)
        self.assertIn("Adoption and outcome rows are intentionally not averaged", report)
        self.assertIn("REC-DEV-01", report)


if __name__ == "__main__":
    unittest.main()
