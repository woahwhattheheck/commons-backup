import copy
import unittest

from intake_gate import IntakeError, build_receipt, canonical_json, validate_intake, verify_receipt

BASE = {
    "offer_id": "tenderproof-rfp-evidence-sprint-v1",
    "buyer": {"organization": "Synthetic Federal Services LLC", "contact_route": "demo@example.invalid"},
    "buyer_yes": True,
    "scope_accepted": True,
    "buyer_authorized_inputs": True,
    "funding": {"payment_received": True, "amount_usd": "2500.00", "receipt_ref": "redacted-demo-receipt"},
    "solicitation": {
        "title": "Synthetic IT Services RFP",
        "source_ref": "buyer-authorized://synthetic-rfp",
        "content_sha256": "a" * 64,
    },
    "evidence_register": [
        {"id": "E-001", "source_ref": "buyer-authorized://capability-statement", "buyer_supplied": True}
    ],
}


class IntakeGateTests(unittest.TestCase):
    def test_ready_only_when_every_gate_is_satisfied(self):
        result = validate_intake(BASE)
        self.assertEqual(result.state, "READY_FOR_DELIVERY")
        self.assertEqual(result.blockers, ())

    def test_no_buyer_yes_has_highest_precedence(self):
        data = copy.deepcopy(BASE)
        data["buyer_yes"] = False
        self.assertEqual(validate_intake(data).state, "HOLD_NO_BUYER_YES")

    def test_scope_must_be_accepted(self):
        data = copy.deepcopy(BASE)
        data["scope_accepted"] = False
        self.assertEqual(validate_intake(data).state, "HOLD_SCOPE_NOT_ACCEPTED")

    def test_unpaid_is_blocked(self):
        data = copy.deepcopy(BASE)
        data["funding"]["payment_received"] = False
        data["funding"]["amount_usd"] = "0"
        data["funding"]["receipt_ref"] = None
        result = validate_intake(data)
        self.assertEqual(result.state, "HOLD_UNFUNDED")
        self.assertIn("PAYMENT_REQUIRED", result.blockers)

    def test_wrong_amount_is_blocked(self):
        data = copy.deepcopy(BASE)
        data["funding"]["amount_usd"] = "2499.99"
        self.assertIn("PAYMENT_AMOUNT_MISMATCH", validate_intake(data).blockers)

    def test_paid_claim_requires_receipt_reference(self):
        data = copy.deepcopy(BASE)
        data["funding"]["receipt_ref"] = ""
        self.assertIn("PAYMENT_RECEIPT_REQUIRED", validate_intake(data).blockers)

    def test_payment_boolean_is_strict(self):
        data = copy.deepcopy(BASE)
        data["funding"]["payment_received"] = 1
        with self.assertRaises(IntakeError):
            validate_intake(data)

    def test_buyer_input_authorization_required(self):
        data = copy.deepcopy(BASE)
        data["buyer_authorized_inputs"] = False
        result = validate_intake(data)
        self.assertEqual(result.state, "HOLD_INPUTS")
        self.assertIn("BUYER_INPUT_AUTHORIZATION_REQUIRED", result.blockers)

    def test_solicitation_hash_must_be_exact_sha256_shape(self):
        data = copy.deepcopy(BASE)
        data["solicitation"]["content_sha256"] = "abc"
        self.assertIn("SOLICITATION_SHA256_REQUIRED", validate_intake(data).blockers)

    def test_evidence_register_cannot_be_empty(self):
        data = copy.deepcopy(BASE)
        data["evidence_register"] = []
        self.assertIn("EVIDENCE_REGISTER_REQUIRED", validate_intake(data).blockers)

    def test_duplicate_evidence_ids_rejected(self):
        data = copy.deepcopy(BASE)
        data["evidence_register"].append(copy.deepcopy(data["evidence_register"][0]))
        with self.assertRaises(IntakeError):
            validate_intake(data)

    def test_evidence_buyer_supplied_boolean_is_strict(self):
        data = copy.deepcopy(BASE)
        data["evidence_register"][0]["buyer_supplied"] = "true"
        with self.assertRaises(IntakeError):
            validate_intake(data)

    def test_receipt_verifies(self):
        self.assertTrue(verify_receipt(build_receipt(BASE)))

    def test_receipt_is_deterministic(self):
        self.assertEqual(canonical_json(build_receipt(BASE)), canonical_json(build_receipt(copy.deepcopy(BASE))))

    def test_tampered_gate_fails_verification(self):
        receipt = build_receipt(BASE)
        receipt["gate"]["state"] = "HOLD_UNFUNDED"
        self.assertFalse(verify_receipt(receipt))

    def test_resealed_authority_escalation_still_fails(self):
        from intake_gate import sha256_text
        receipt = build_receipt(BASE)
        receipt["authority"]["proposal_submission_authorized"] = True
        bare = dict(receipt)
        bare.pop("receipt", None)
        receipt["receipt"]["payload_sha256"] = sha256_text(canonical_json(bare))
        self.assertFalse(verify_receipt(receipt))

    def test_gate_never_recognizes_revenue(self):
        receipt = build_receipt(BASE)
        self.assertFalse(receipt["authority"]["revenue_recognition_authorized_by_gate"])


if __name__ == "__main__":
    unittest.main()
