from __future__ import annotations

import json
import unittest
from pathlib import Path

from rating_model import ModelError, compose, normalize_criteria

ROOT = Path(__file__).resolve().parent


def load_case(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class RatingCompositionTests(unittest.TestCase):
    def test_critical_gap_overrides_strong_observed_pattern(self) -> None:
        result = compose(load_case("synthetic_case_critical_gap.json"))
        summary = result["area_summaries"]["security"]

        self.assertEqual(summary["composition_status"], "critical_gap_present")
        self.assertEqual(summary["coverage"], 1.0)
        self.assertEqual(summary["critical_gap_ids"], ["SEC-A5"])
        self.assertEqual(
            summary["maturity_distribution_by_rank"],
            {"1": 1, "4": 4},
        )
        self.assertNotIn("average_maturity", summary)
        self.assertNotIn("composite_score", summary)

    def test_low_coverage_blocks_area_characterization(self) -> None:
        result = compose(load_case("synthetic_case_low_coverage.json"))
        summary = result["area_summaries"]["software_development"]

        self.assertEqual(summary["composition_status"], "insufficient_coverage")
        self.assertAlmostEqual(summary["coverage"], 0.40)
        self.assertEqual(summary["counts"]["assessed"], 4)
        self.assertEqual(summary["counts"]["unassessed"], 6)
        self.assertEqual(summary["counts"]["not_applicable"], 2)
        self.assertEqual(len(summary["unassessed_ids"]), 6)

    def test_mixed_service_pattern_is_preserved(self) -> None:
        result = compose(load_case("synthetic_case_mixed_services.json"))
        area = result["area_summaries"]["deployment_operations"]

        self.assertEqual(area["composition_status"], "mixed_practice")
        self.assertEqual(area["maturity_range"]["lowest_rank"], 1)
        self.assertEqual(area["maturity_range"]["highest_rank"], 4)
        self.assertEqual(area["maturity_range"]["spread"], 3)

        ess = result["service_summaries"]["deployment_operations::ESS"]
        ris = result["service_summaries"]["deployment_operations::RIS"]
        iam = result["service_summaries"]["deployment_operations::IAM"]
        self.assertEqual(ess["composition_status"], "coherent_pattern")
        self.assertEqual(ris["composition_status"], "coherent_pattern")
        self.assertEqual(iam["composition_status"], "coherent_pattern")
        self.assertEqual(ris["maturity_distribution_by_rank"], {"1": 2})

    def test_confidence_does_not_change_maturity(self) -> None:
        payload = load_case("synthetic_case_critical_gap.json")
        payload["criteria"][0]["confidence"] = "low"
        result = compose(payload)
        summary = result["area_summaries"]["security"]

        self.assertEqual(summary["maturity_distribution_by_rank"], {"1": 1, "4": 4})
        self.assertEqual(summary["minimum_confidence"], "low")
        self.assertEqual(summary["confidence_distribution"]["low"], 1)

    def test_all_unassessed_is_distinct_from_not_applicable(self) -> None:
        payload = {
            "criteria": [
                {
                    "criterion_id": "U1",
                    "area": "ai_readiness",
                    "service": "IAM",
                    "assessment_status": "unassessed",
                    "criticality": "important",
                },
                {
                    "criterion_id": "N1",
                    "area": "ai_readiness",
                    "service": "ESS",
                    "assessment_status": "not_applicable",
                    "criticality": "supporting",
                    "applicability_reason": "Synthetic case: no in-scope AI use.",
                },
            ]
        }
        result = compose(payload)
        area = result["area_summaries"]["ai_readiness"]
        self.assertEqual(area["composition_status"], "unassessed")
        self.assertEqual(area["counts"]["eligible"], 1)
        self.assertEqual(area["counts"]["not_applicable"], 1)
        self.assertEqual(area["coverage"], 0.0)

    def test_unassessed_cannot_carry_maturity_rank_zero(self) -> None:
        payload = {
            "criteria": [
                {
                    "criterion_id": "BAD",
                    "area": "security",
                    "service": "ESS",
                    "assessment_status": "unassessed",
                    "criticality": "important",
                    "maturity_rank": 0,
                }
            ]
        }
        with self.assertRaisesRegex(ModelError, "maturity_rank must be empty"):
            normalize_criteria(payload)

    def test_duplicate_criterion_id_rejected(self) -> None:
        row = {
            "criterion_id": "DUP",
            "area": "security",
            "service": "ESS",
            "assessment_status": "unassessed",
            "criticality": "important",
        }
        with self.assertRaisesRegex(ModelError, "duplicate criterion_id"):
            normalize_criteria({"criteria": [row, dict(row)]})


if __name__ == "__main__":
    unittest.main()
