import copy
import json
import unittest

from tools.outbound_send_guard import connector_capability_lease as v3
from tools.outbound_send_guard.atomic_lease import LeaseError


CLAIM = {
    "repo": "woahwhattheheck/commons",
    "buyer_scope": "example.com",
    "offer_scope": "inventory-cycle-count-variance-desk",
    "claimant": "Z-Test-Worker",
    "claim_id": "v3-test-20260914",
    "claim_started_at": "2026-09-14T22:30:00Z",
    "anchor_sha": "1" * 40,
    "preflight_sha256": "2" * 64,
}
COMMIT = "3" * 40


class ConnectorCapabilityLeaseTests(unittest.TestCase):
    def prepared(self):
        private = []
        plan = v3.prepare_acquisition(CLAIM, retain_capability=private.append)
        self.assertEqual(len(private), 1)
        return plan, private.pop()

    def held(self):
        plan, cap = self.prepared()
        intent = v3.bind_lease_commit(plan, COMMIT)
        receipt = v3.receipt_from_readback(
            intent,
            observed_branch_sha=COMMIT,
            observed_parent_sha=CLAIM["anchor_sha"],
            observed_metadata_json=plan["metadata_json"],
        )
        return plan, intent, receipt, cap

    def test_exact_holder_success(self):
        plan, intent, receipt, cap = self.held()
        self.assertTrue(v3.verify_plan(plan))
        self.assertTrue(v3.verify_intent(intent))
        self.assertTrue(v3.verify_receipt(receipt))
        self.assertTrue(receipt["lease_held_by_claimant"])
        self.assertFalse(receipt["external_send_authorized"])
        self.assertTrue(v3.verify_possession(
            receipt,
            claim_capability=cap,
            live_branch_sha=COMMIT,
            live_parent_sha=CLAIM["anchor_sha"],
            live_metadata_json=plan["metadata_json"],
        ))

    def test_copied_public_winner_wrong_capability_fails(self):
        plan, _intent, receipt, _cap = self.held()
        self.assertFalse(v3.verify_possession(
            receipt,
            claim_capability="4" * 64,
            live_branch_sha=COMMIT,
            live_parent_sha=CLAIM["anchor_sha"],
            live_metadata_json=plan["metadata_json"],
        ))

    def test_capability_retention_failure_prevents_plan(self):
        calls = []
        def fail(secret):
            calls.append(secret)
            raise RuntimeError("no private store")
        with self.assertRaisesRegex(LeaseError, "retention failed"):
            v3.prepare_acquisition(CLAIM, retain_capability=fail)
        self.assertEqual(len(calls), 1)

    def test_raw_capability_absent_from_public_structures(self):
        plan, intent, receipt, cap = self.held()
        self.assertTrue(v3.public_capability_absent(plan, cap))
        self.assertTrue(v3.public_capability_absent(intent, cap))
        self.assertTrue(v3.public_capability_absent(receipt, cap))
        self.assertNotIn(cap, plan["metadata_json"])

    def test_deterministic_seam_and_namespace_separation(self):
        plan_a, _ = self.prepared()
        plan_b, _ = self.prepared()
        self.assertEqual(plan_a["seam_sha256"], plan_b["seam_sha256"])
        self.assertEqual(plan_a["branch_name"], plan_b["branch_name"])
        self.assertTrue(plan_a["lease_ref"].startswith("refs/heads/outbound-lease-v3/"))
        self.assertNotIn("outbound-lease-v1", plan_a["lease_ref"])
        self.assertNotIn("outbound-lease-v2", plan_a["lease_ref"])
        self.assertNotEqual(plan_a["claim_capability_sha256"], plan_b["claim_capability_sha256"])

    def test_other_head_holds(self):
        plan, _cap = self.prepared()
        intent = v3.bind_lease_commit(plan, COMMIT)
        receipt = v3.receipt_from_readback(
            intent,
            observed_branch_sha="5" * 40,
            observed_parent_sha=CLAIM["anchor_sha"],
            observed_metadata_json=plan["metadata_json"],
        )
        self.assertFalse(receipt["lease_held_by_claimant"])
        self.assertEqual(receipt["decision"], "HOLD")
        self.assertEqual(receipt["reason"], "HELD_BY_OTHER_OR_REF_DRIFT")

    def test_wrong_parent_holds_and_live_verify_fails(self):
        plan, intent, receipt, cap = self.held()
        held_bad = v3.receipt_from_readback(
            intent,
            observed_branch_sha=COMMIT,
            observed_parent_sha="6" * 40,
            observed_metadata_json=plan["metadata_json"],
        )
        self.assertFalse(held_bad["lease_held_by_claimant"])
        self.assertEqual(held_bad["reason"], "ANCHOR_PARENT_MISMATCH")
        self.assertFalse(v3.verify_possession(
            receipt,
            claim_capability=cap,
            live_branch_sha=COMMIT,
            live_parent_sha="6" * 40,
            live_metadata_json=plan["metadata_json"],
        ))

    def test_metadata_tamper_holds_and_live_verify_fails(self):
        plan, intent, receipt, cap = self.held()
        meta = json.loads(plan["metadata_json"])
        meta["offer_scope"] = "other-offer"
        tampered = json.dumps(meta, sort_keys=True, separators=(",", ":")) + "\n"
        hold = v3.receipt_from_readback(
            intent,
            observed_branch_sha=COMMIT,
            observed_parent_sha=CLAIM["anchor_sha"],
            observed_metadata_json=tampered,
        )
        self.assertFalse(hold["lease_held_by_claimant"])
        self.assertEqual(hold["reason"], "METADATA_MISMATCH")
        self.assertFalse(v3.verify_possession(
            receipt,
            claim_capability=cap,
            live_branch_sha=COMMIT,
            live_parent_sha=CLAIM["anchor_sha"],
            live_metadata_json=tampered,
        ))

    def test_plan_tamper_rejected(self):
        plan, _ = self.prepared()
        bad = copy.deepcopy(plan)
        bad["buyer_scope"] = "evil.example"
        with self.assertRaises(LeaseError):
            v3.verify_plan(bad)

    def test_intent_tamper_rejected(self):
        plan, _ = self.prepared()
        intent = v3.bind_lease_commit(plan, COMMIT)
        bad = copy.deepcopy(intent)
        bad["lease_commit_sha"] = "7" * 40
        with self.assertRaises(LeaseError):
            v3.verify_intent(bad)

    def test_receipt_tamper_rejected(self):
        _plan, _intent, receipt, _cap = self.held()
        bad = copy.deepcopy(receipt)
        bad["external_send_authorized"] = True
        with self.assertRaises(LeaseError):
            v3.verify_receipt(bad)

    def test_unknown_fields_fail_closed(self):
        plan, _ = self.prepared()
        bad = dict(plan)
        bad["extra"] = "x"
        with self.assertRaisesRegex(LeaseError, "exact fields"):
            v3.verify_plan(bad)

    def test_malformed_capability_fails(self):
        plan, _intent, receipt, _cap = self.held()
        with self.assertRaises(LeaseError):
            v3.verify_possession(
                receipt,
                claim_capability="not-a-capability",
                live_branch_sha=COMMIT,
                live_parent_sha=CLAIM["anchor_sha"],
                live_metadata_json=plan["metadata_json"],
            )

    def test_missing_provider_evidence_fails(self):
        plan, _intent, receipt, cap = self.held()
        self.assertFalse(v3.verify_possession(
            receipt,
            claim_capability=cap,
            live_branch_sha=None,
            live_parent_sha=CLAIM["anchor_sha"],
            live_metadata_json=plan["metadata_json"],
        ))

    def test_duplicate_metadata_key_is_not_canonical_plan_metadata(self):
        plan, _ = self.prepared()
        bad = copy.deepcopy(plan)
        bad["metadata_json"] = plan["metadata_json"].rstrip("\n")[:-1] + ',"schema":"x"}\n'
        bad["metadata_sha256"] = v3._text_sha256(bad["metadata_json"])
        material = dict(bad)
        material.pop("plan_sha256")
        bad["plan_sha256"] = v3._sha256(material)
        with self.assertRaisesRegex(LeaseError, "metadata content mismatch"):
            v3.verify_plan(bad)


if __name__ == "__main__":
    unittest.main()
