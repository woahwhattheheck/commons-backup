from __future__ import annotations

import inspect
import re
import unittest

from .qualification import current_qualification


class QualificationTests(unittest.TestCase):
    def test_current_state_is_teaming_required(self):
        result = current_qualification()
        self.assertEqual(result["status"], "TEAMING_REQUIRED")
        self.assertIn("CONTROLLING_PACKET_NOT_RETAINED", result["holds"])
        self.assertIn("THREE_SIMILAR_REFERENCES_NOT_EVIDENCED", result["holds"])

    def test_gate_accepts_no_runtime_evidence(self):
        self.assertEqual(list(inspect.signature(current_qualification).parameters), [])
        with self.assertRaises(TypeError):
            current_qualification({"controlling_packet_sha256": "a" * 64})

    def test_opportunity_is_pinned(self):
        self.assertEqual(current_qualification()["opportunity_id"], "OSUTUL-RFP-001864-2027")

    def test_current_retained_evidence_is_explicit(self):
        evidence = current_qualification()["retained_evidence"]
        self.assertIsNone(evidence["controlling_packet_sha256"])
        self.assertEqual(evidence["similar_reference_receipt_count"], 0)
        self.assertFalse(evidence["non_collusion_owner_confirmed"])
        self.assertFalse(evidence["portal_registration_confirmed"])
        self.assertFalse(evidence["pricing_owner_confirmed"])

    def test_submission_and_contact_never_authorized(self):
        result = current_qualification()
        self.assertFalse(result["submission_authorized"])
        self.assertFalse(result["buyer_contact_authorized"])
        self.assertFalse(result["award_or_payment_claimed"])

    def test_result_mutation_cannot_upgrade_future_call(self):
        first = current_qualification()
        first["status"] = "PRIME_EVIDENCE_READY"
        first["holds"].clear()
        first["retained_evidence"]["similar_reference_receipt_count"] = 3
        second = current_qualification()
        self.assertEqual(second["status"], "TEAMING_REQUIRED")
        self.assertTrue(second["holds"])
        self.assertEqual(second["retained_evidence"]["similar_reference_receipt_count"], 0)

    def test_digest_is_deterministic(self):
        self.assertEqual(current_qualification()["evidence_digest"], current_qualification()["evidence_digest"])

    def test_digest_is_sha256(self):
        self.assertRegex(current_qualification()["evidence_digest"], re.compile(r"^[0-9a-f]{64}$"))

    def test_schema_is_v2(self):
        self.assertEqual(current_qualification()["schema"], "osuchsh-gme-qualification-v2")

    def test_all_current_holds_are_present(self):
        self.assertEqual(
            current_qualification()["holds"],
            [
                "CONTROLLING_PACKET_NOT_RETAINED",
                "THREE_SIMILAR_REFERENCES_NOT_EVIDENCED",
                "NON_COLLUSION_OWNER_CONFIRMATION_MISSING",
                "PORTAL_REGISTRATION_NOT_CONFIRMED",
                "PRICING_OWNER_CONFIRMATION_MISSING",
            ],
        )


if __name__ == "__main__":
    unittest.main()
