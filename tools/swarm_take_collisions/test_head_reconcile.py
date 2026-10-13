"""Focused source-lease branch-delta boundary checks."""
import unittest
from head_reconcile import reconcile

OLD = "a" * 40
NEW = "b" * 40


def fixture(**changes):
    row = dict(
        operation_id="GF-SDK273-OP1", repo="Example/SDK", branch="feat/source-fix",
        owner="source-agent", origin="slack:1791442028.601809", lease_kind="source",
        expected_head=OLD, observed_head=NEW,
        claimed_paths=["src/validation"], touched_paths=["src/validation/parser.ts"],
        comparison_complete=True, stale=True, provider_readback="github:compare/abc123",
    )
    row.update(changes)
    return row


class LeaseBoundaryTests(unittest.TestCase):
    def test_overlapping_delta_needs_content_proof(self):
        out = reconcile(fixture())
        self.assertEqual(out["status"], "COLLISION_RECONCILIATION")
        self.assertFalse(out["retire_source_lease"])
        self.assertTrue(out["claim_custody_unchanged"])

    def test_verified_completion_retires_only_source_lease(self):
        out = reconcile(fixture(completion_proof={"verified": True, "reference": "github:blob/evidence"}))
        self.assertEqual(out["status"], "VERIFIED_COMPLETION")
        self.assertTrue(out["retire_source_lease"])
        self.assertTrue(out["publication_lease_unchanged"])
        self.assertTrue(out["claim_custody_unchanged"])

    def test_orthogonal_concurrent_advance_rebases_with_cas(self):
        out = reconcile(fixture(touched_paths=["src/another/parser.ts"]))
        self.assertEqual(out["status"], "ORTHOGONAL_ADVANCE")
        self.assertEqual(out["next_expected_head"], NEW)
        self.assertFalse(out["retire_source_lease"])

    def test_stale_but_same_branch_head(self):
        out = reconcile(fixture(observed_head=OLD))
        self.assertEqual(out["status"], "UNCHANGED_STALE")
        self.assertIsNone(out["next_expected_head"])

    def test_incomplete_compare_fails_closed(self):
        out = reconcile(fixture(comparison_complete=False))
        self.assertEqual(out["status"], "INCOMPLETE_EVIDENCE")
        self.assertFalse(out["retire_source_lease"])

    def test_path_prefix_segment_boundaries(self):
        out = reconcile(fixture(claimed_paths=["src/test"], touched_paths=["src/testing/x.ts"]))
        self.assertEqual(out["status"], "ORTHOGONAL_ADVANCE")

    def test_short_sha_does_not_authorize_cas(self):
        out = reconcile(fixture(observed_head="b" * 8))
        self.assertEqual(out["status"], "INCOMPLETE_EVIDENCE")

    def test_claim_lease_cannot_be_closed_by_source_proof(self):
        out = reconcile(fixture(lease_kind="claim", completion_proof={"verified": True, "reference": "receipt"}))
        self.assertEqual(out["status"], "SEPARATE_CUSTODY")
        self.assertFalse(out["retire_source_lease"])

    def test_missing_reference_cannot_prove_completion(self):
        out = reconcile(fixture(completion_proof={"verified": True, "reference": None}))
        self.assertEqual(out["status"], "COLLISION_RECONCILIATION")


if __name__ == "__main__":
    unittest.main()
