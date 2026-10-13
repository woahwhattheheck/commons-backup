import copy
import unittest

from revenue.nm_ocs_tprm.qualification import (
    ValidationError,
    compile_qualification,
    verify_receipt,
)


def payload():
    return {
        "schema": "tjlabs.nm-ocs-tprm.qualification.v1",
        "opportunity_id": "OCS2026.01",
        "controlling_packet": {
            "status": "UNVERIFIED",
            "sha256": None,
            "source_url": "https://example.invalid/controlling-rfq",
        },
        "prime_eligibility": {
            "status": "UNKNOWN",
            "evidence_sha256": None,
            "note": "No controlling packet evidence yet.",
        },
        "legal_scope": {
            "status": "UNBOUND",
            "evidence_sha256": None,
        },
        "owner_authorities": {
            "pricing": False,
            "submission": False,
            "external_contact": False,
            "signature": False,
        },
    }


class QualificationTests(unittest.TestCase):
    def test_public_only_state_fails_closed(self):
        receipt = compile_qualification(payload())
        self.assertTrue(verify_receipt(receipt))
        self.assertEqual(receipt["posture"], "TEAMING_RESEARCH_ONLY")
        self.assertIn("HOLD_CONTROLLING_RFQ_REQUIRED", receipt["holds"])
        self.assertIn("HOLD_PRIME_ELIGIBILITY_UNVERIFIED", receipt["holds"])
        self.assertFalse(receipt["authority"]["submission_authorized"])

    def test_not_eligible_becomes_teaming(self):
        x = payload()
        x["controlling_packet"] = {
            "status": "VERIFIED",
            "sha256": "1" * 64,
            "source_url": "https://example.invalid/controlling-rfq",
        }
        x["prime_eligibility"] = {
            "status": "NOT_ELIGIBLE",
            "evidence_sha256": "4" * 64,
            "note": "Synthetic negative eligibility evidence for test.",
        }
        x["legal_scope"] = {
            "status": "QUALIFIED_PARTNER_BOUND",
            "evidence_sha256": "2" * 64,
        }
        receipt = compile_qualification(x)
        self.assertEqual(receipt["posture"], "TEAMING_DRAFT_READY_FOR_OWNER_REVIEW")
        self.assertIn("DIRECT_PRIME_NOT_ELIGIBLE", receipt["holds"])

    def test_verified_prime_without_legal_partner_stays_technical_draft(self):
        x = payload()
        x["controlling_packet"] = {
            "status": "VERIFIED",
            "sha256": "1" * 64,
            "source_url": "https://example.invalid/controlling-rfq",
        }
        x["prime_eligibility"] = {
            "status": "VERIFIED",
            "evidence_sha256": "2" * 64,
            "note": "Synthetic positive eligibility evidence for test.",
        }
        receipt = compile_qualification(x)
        self.assertEqual(receipt["posture"], "PRIME_TECHNICAL_DRAFT_ONLY")
        self.assertIn("HOLD_LEGAL_SCOPE_PARTNER_UNBOUND", receipt["holds"])

    def test_verified_inputs_still_do_not_mint_submission_authority(self):
        x = payload()
        x["controlling_packet"] = {
            "status": "VERIFIED",
            "sha256": "1" * 64,
            "source_url": "https://example.invalid/controlling-rfq",
        }
        x["prime_eligibility"] = {
            "status": "VERIFIED",
            "evidence_sha256": "2" * 64,
            "note": "Synthetic positive eligibility evidence for test.",
        }
        x["legal_scope"] = {
            "status": "QUALIFIED_PARTNER_BOUND",
            "evidence_sha256": "3" * 64,
        }
        x["owner_authorities"] = {
            "pricing": True,
            "submission": True,
            "external_contact": True,
            "signature": True,
        }
        receipt = compile_qualification(x)
        self.assertEqual(receipt["posture"], "PRIME_DRAFT_READY_FOR_OWNER_REVIEW")
        self.assertTrue(all(v is False for v in receipt["authority"].values()))

    def test_tamper_breaks_receipt(self):
        receipt = compile_qualification(payload())
        receipt["posture"] = "PRIME_DRAFT_READY_FOR_OWNER_REVIEW"
        self.assertFalse(verify_receipt(receipt))

    def test_unverified_packet_cannot_carry_authoritative_digest(self):
        x = payload()
        x["controlling_packet"]["sha256"] = "1" * 64
        with self.assertRaises(ValidationError):
            compile_qualification(x)

    def test_verified_prime_requires_evidence_digest(self):
        x = payload()
        x["prime_eligibility"]["status"] = "VERIFIED"
        with self.assertRaises(ValidationError):
            compile_qualification(x)

    def test_not_eligible_requires_evidence_digest(self):
        x = payload()
        x["prime_eligibility"]["status"] = "NOT_ELIGIBLE"
        with self.assertRaises(ValidationError):
            compile_qualification(x)

    def test_legal_not_required_needs_verified_packet(self):
        x = payload()
        x["legal_scope"]["status"] = "NOT_REQUIRED_BY_VERIFIED_PACKET"
        with self.assertRaises(ValidationError):
            compile_qualification(x)

    def test_boolean_shape_is_exact(self):
        x = payload()
        x["owner_authorities"]["pricing"] = 1
        with self.assertRaises(ValidationError):
            compile_qualification(x)

    def test_unknown_field_rejected(self):
        x = payload()
        x["owner_authorities"]["portal_login"] = False
        with self.assertRaises(ValidationError):
            compile_qualification(x)


if __name__ == "__main__":
    unittest.main()
