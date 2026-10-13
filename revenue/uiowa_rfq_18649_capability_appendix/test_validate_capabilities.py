from __future__ import annotations

import copy
import unittest

from validate_capabilities import DEFAULT_DATA, load, repo_root, validate


class CapabilityAppendixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = load(DEFAULT_DATA)
        cls.root = repo_root()

    def test_pinned_sources_match_checked_out_bytes(self) -> None:
        result = validate(self.payload, self.root)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["capabilities"], 4)
        self.assertEqual(result["verified_blobs"], result["sources"])
        self.assertGreaterEqual(result["sources"], 12)

    def test_capability_ids_are_unique(self) -> None:
        ids = [row["capability_id"] for row in self.payload["capabilities"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_three_evidence_classes_are_explicit(self) -> None:
        classes = self.payload["evidence_classification"]
        self.assertIn("synthetic_demonstrations", classes)
        self.assertIn("original_engineering", classes)
        self.assertIn("client_validation", classes)
        self.assertIn("No client outcome", classes["client_validation"])

    def test_observations_preserve_unknowns(self) -> None:
        evidence = next(
            row for row in self.payload["capabilities"]
            if row["capability_id"] == "CAP-EVIDENCE-ORGANIZATION"
        )
        counts = evidence["provider_observation"]["fact_state_counts"]
        self.assertGreater(counts["unknown"], 0)
        self.assertEqual(sum(counts.values()), evidence["provider_observation"]["facts"])

    def test_comparison_has_required_proof_cases(self) -> None:
        comparison = next(
            row for row in self.payload["capabilities"]
            if row["capability_id"] == "CAP-COMPARISON"
        )
        statuses = {
            case["expected_composition"]
            for case in comparison["provider_observation"]["cases"]
        }
        self.assertEqual(
            statuses,
            {"critical_gap_present", "insufficient_coverage", "mixed_practice"},
        )

    def test_byte_drift_fails_closed(self) -> None:
        broken = copy.deepcopy(self.payload)
        broken["capabilities"][0]["sources"][0]["blob_sha"] = "0" * 40
        result = validate(broken, self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("source byte drift" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
