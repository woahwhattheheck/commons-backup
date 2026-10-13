from __future__ import annotations

import copy
import unittest

import feed_carry_oracle as o
from lean_feed_hardening import (
    AUTHORITY_ROOT_SCHEMA,
    analyze_authoritative_document,
)
from test_feed_carry_oracle import document


class PromotionGateHardeningTests(unittest.TestCase):
    def test_synthetic_candidate_is_source_blocked(self):
        report = analyze_authoritative_document(document())
        self.assertEqual(
            report["promotion"]["candidate_conclusion"],
            "PROMOTE_RESEARCH_CANDIDATE",
        )
        self.assertEqual(report["promotion"]["conclusion"], "SOURCE_MODEL_BLOCKED")
        self.assertFalse(report["promotion"]["authority_verified"])
        self.assertIsNone(report["promotion"]["selected_arm"])
        self.assertEqual(report["census"], [])
        self.assertEqual(report["paired_deltas"], [])
        self.assertEqual(report["runs"], [])
        self.assertFalse(report["authority"]["promotion_authorized"])
        self.assertEqual(report["authority"]["source_model_state"], "SOURCE_MODEL_BLOCKED")

    def test_conservative_candidate_stays_no_promotion(self):
        report = analyze_authoritative_document(document(cash_use=False))
        self.assertEqual(report["promotion"]["candidate_conclusion"], "NO_PROMOTION")
        self.assertEqual(report["promotion"]["conclusion"], "NO_PROMOTION")
        self.assertTrue(report["runs"])

    def test_duplicate_arm_row_is_rejected(self):
        evidence = document()
        duplicate = copy.deepcopy(evidence["runs"][0])
        duplicate["run_id"] += "-duplicate"
        evidence["runs"].append(duplicate)
        with self.assertRaises(o.EvidenceError):
            analyze_authoritative_document(evidence)

    def test_cross_arm_initial_snapshot_mismatch_is_rejected(self):
        evidence = document()
        target = next(row for row in evidence["runs"] if row["arm"] == o.ARM_CURRENT)
        target["decision_windows"][0]["snapshot"]["cash"] += 1
        with self.assertRaises(o.EvidenceError):
            analyze_authoritative_document(evidence)

    def test_empty_obligation_census_is_rejected(self):
        evidence = document()
        for row in evidence["runs"]:
            row["decision_windows"][0]["snapshot"]["obligations"] = []
        with self.assertRaises(o.EvidenceError):
            analyze_authoritative_document(evidence)

    def test_reused_liberation_id_in_one_run_is_rejected(self):
        evidence = document()
        target = next(row for row in evidence["runs"] if row["arm"] == o.ARM_MIN)
        second = copy.deepcopy(target["decision_windows"][0])
        second["window_id"] = "w2"
        target["decision_windows"].append(second)
        with self.assertRaises(o.EvidenceError):
            analyze_authoritative_document(evidence)

    def test_terminal_result_is_bound_into_run_evidence_digest(self):
        baseline = document(cash_use=False)
        changed = copy.deepcopy(baseline)
        target = changed["runs"][0]
        target["result"]["own"] += 2
        target["result"]["margin"] += 2

        first = analyze_authoritative_document(baseline)
        second = analyze_authoritative_document(changed)
        run_id = baseline["runs"][0]["run_id"]
        digest_a = next(row for row in first["runs"] if row["run_id"] == run_id)[
            "evidence_sha256"
        ]
        digest_b = next(row for row in second["runs"] if row["run_id"] == run_id)[
            "evidence_sha256"
        ]
        self.assertNotEqual(digest_a, digest_b)

    def test_caller_minted_authority_root_is_not_trusted(self):
        evidence = document()
        authority = evidence["authority"]
        selection = evidence["candidate_selection"]
        evidence["authority_root"] = {
            "schema": AUTHORITY_ROOT_SCHEMA,
            "archive_sha256": authority["archive_sha256"],
            "dev_manifest_sha256": authority["dev_manifest_sha256"],
            "holdout_manifest_sha256": authority["holdout_manifest_sha256"],
            "selection_manifest_sha256": selection["selection_manifest_sha256"],
            "evidence_sha256": o.sha256_json(
                {
                    "schema": evidence["schema"],
                    "authority": authority,
                    "candidate_selection": selection,
                    "runs": evidence["runs"],
                }
            ),
        }
        report = analyze_authoritative_document(evidence)
        self.assertFalse(report["promotion"]["authority_verified"])
        self.assertEqual(report["promotion"]["conclusion"], "SOURCE_MODEL_BLOCKED")
        self.assertIsNotNone(report["promotion"]["authority_root_sha256"])


if __name__ == "__main__":
    unittest.main()
