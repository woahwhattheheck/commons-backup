import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_rehearsal  # noqa: E402


class PolicyPracticeRehearsalTests(unittest.TestCase):
    def test_merged_components_preserve_disagreement(self):
        result = run_rehearsal.build_result()
        self.assertEqual(result["confidence"]["validation"], "PASS")
        self.assertEqual(result["confidence"]["finding_state"], "UNRESOLVED")
        summary = result["rating"]["area_summaries"]["delivery"]
        self.assertEqual(summary["composition_status"], "unassessed")
        self.assertEqual(summary["coverage"], 0.0)
        self.assertEqual(summary["maturity_distribution_by_rank"], {})
        self.assertEqual(summary["maturity_distribution_by_label"], {})

    def test_policy_is_intent_not_direct_execution_evidence(self):
        rows = run_rehearsal.read_rows()
        policy = next(row for row in rows if row["source_type"] == "procedure")
        self.assertEqual(policy["directness"], "INDIRECT")
        self.assertEqual(policy["evidence_state"], "CONFLICTING")
        self.assertEqual(policy["confidence"], "UNRESOLVED")

    def test_operational_sample_keeps_scope_limit(self):
        rows = run_rehearsal.read_rows()
        sample = next(row for row in rows if row["source_type"] == "change_records")
        self.assertEqual(sample["representativeness"], "SAMPLED")
        self.assertIn("not a complete population", sample["scope_limit"])

    def test_all_three_sources_share_the_controlled_conflict(self):
        rows = run_rehearsal.read_rows()
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            {row["conflict_group"] for row in rows},
            {"CG-SYN-IAM-DEP-110"},
        )
        self.assertEqual(
            {row["finding_id"] for row in rows},
            {"FND-SYN-IAM-DEP-110"},
        )

    def test_review_result_requests_discriminating_follow_up(self):
        review = run_rehearsal.build_result()["review"]
        self.assertEqual(
            review["disposition"],
            "TARGETED_FOLLOW_UP_BEFORE_DEFINITIVE_PRACTICE_CHARACTERIZATION",
        )
        self.assertEqual(len(review["follow_up"]), 3)
        self.assertIn("Four sampled records differ", review["specific_uncertainty"])


if __name__ == "__main__":
    unittest.main()
