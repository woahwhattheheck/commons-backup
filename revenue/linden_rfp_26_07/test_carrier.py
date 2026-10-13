from __future__ import annotations

import json
from pathlib import Path
import unittest

from revenue.linden_rfp_26_07.carrier import (
    CarrierError,
    compile_packet,
    example_owner_input,
    loads_strict,
    source_manifest_digest,
    verify_packet,
)

DIGESTS = [f"{i:064x}"[-64:] for i in range(1, 6)]
SOURCE = json.loads(
    Path(__file__).with_name("source_manifest.json").read_text(encoding="utf-8")
)


def complete_input():
    payload = example_owner_input()
    payload["controlling_package"] = {
        "acquired": True,
        "sha256": DIGESTS[0],
        "addenda_complete": True,
        "requirement_register_bound": True,
    }
    payload["qualification"].update(
        {
            "entity_eligibility_evidence_digest": DIGESTS[1],
            "insurance_evidence_digest": DIGESTS[2],
            "references_evidence_digest": DIGESTS[3],
            "housing_authority_experience_evidence_digest": DIGESTS[4],
            "conflict_disclosure": "NO_KNOWN_CONFLICT",
        }
    )
    payload["commercial"].update(
        {
            "currency": "USD",
            "price_minor": 1,
            "owner_price_confirmed": True,
            "structure_matches_controlling_package": True,
        }
    )
    payload["submission"].update(
        {
            "portal_account_verified": True,
            "forms_complete": True,
            "owner_ruling": "PROCEED_INTERNAL_ONLY",
            "fresh_portal_state_observed": True,
        }
    )
    return payload


class CarrierTest(unittest.TestCase):
    def test_public_notice_is_not_controlling_package(self):
        sources = SOURCE["sources"]
        self.assertEqual(sources["official_rfp_package"]["status"], "NOT_ACQUIRED")
        self.assertIsNone(sources["official_rfp_package"]["sha256"])
        self.assertIsNone(SOURCE["buyer_facts"]["evaluation_weights"])
        self.assertIsNone(SOURCE["buyer_facts"]["required_forms"])
        self.assertIsNone(SOURCE["buyer_facts"]["addenda"])
        self.assertFalse(SOURCE["buyer_facts"]["hard_copy_submission_allowed"])

    def test_empty_owner_profile_holds_without_inventing(self):
        owner = example_owner_input()
        packet = compile_packet(owner)
        self.assertEqual(packet["posture"], "HOLD_CONTROLLING_PACKAGE")
        self.assertIn("CONTROLLING_PACKAGE_NOT_BOUND", packet["blockers"])
        self.assertIn("OWNER_CREDENTIAL_EVIDENCE_INCOMPLETE", packet["blockers"])
        self.assertIn("OWNER_PRICING_INCOMPLETE", packet["blockers"])
        self.assertIn("EVALUATION_REGISTER_UNKNOWN", packet["blockers"])
        self.assertTrue(all(value is False for value in packet["authority"].values()))
        self.assertTrue(verify_packet(packet, owner))

    def test_complete_internal_packet_never_becomes_submission_authority(self):
        owner = complete_input()
        packet = compile_packet(owner)
        self.assertIn("EVALUATION_REGISTER_UNKNOWN", packet["blockers"])
        self.assertIn("FORM_REGISTER_UNKNOWN", packet["blockers"])
        self.assertIn("ADDENDA_REGISTER_UNKNOWN", packet["blockers"])
        self.assertNotEqual(
            packet["posture"], "OWNER_REVIEW_PACKET_COMPLETE_NOT_SUBMISSION_AUTHORITY"
        )
        self.assertFalse(packet["authority"]["submission_authorized"])
        self.assertFalse(packet["authority"]["pricing_commitment_authorized"])
        self.assertFalse(packet["authority"]["buyer_contact_authorized"])
        self.assertFalse(packet["authority"]["portal_registration_authorized"])

    def test_unacquired_package_cannot_claim_hash(self):
        owner = example_owner_input()
        owner["controlling_package"]["sha256"] = DIGESTS[0]
        with self.assertRaises(CarrierError):
            compile_packet(owner)

    def test_acquired_package_requires_hash(self):
        owner = example_owner_input()
        owner["controlling_package"]["acquired"] = True
        with self.assertRaises(CarrierError):
            compile_packet(owner)

    def test_price_bool_alias_rejected(self):
        owner = complete_input()
        owner["commercial"]["price_minor"] = True
        with self.assertRaises(CarrierError):
            compile_packet(owner)

    def test_wrong_channel_holds(self):
        owner = complete_input()
        owner["submission"]["channel"] = "email to Executive Director"
        packet = compile_packet(owner)
        self.assertIn("SUBMISSION_CHANNEL_MISMATCH", packet["blockers"])

    def test_deadline_passed_is_terminal(self):
        owner = complete_input()
        owner["evaluated_at"] = "2026-10-09T14:30:01-04:00"
        packet = compile_packet(owner)
        self.assertEqual(packet["posture"], "NO_BID_DEADLINE_PASSED")
        self.assertIn("PROPOSAL_DEADLINE_PASSED", packet["blockers"])
        self.assertFalse(packet["authority"]["submission_authorized"])

    def test_offset_conversion_is_real(self):
        owner = complete_input()
        owner["evaluated_at"] = "2026-10-09T18:29:59+00:00"
        packet = compile_packet(owner)
        self.assertNotIn("PROPOSAL_DEADLINE_PASSED", packet["blockers"])
        owner["evaluated_at"] = "2026-10-09T18:30:01+00:00"
        packet = compile_packet(owner)
        self.assertIn("PROPOSAL_DEADLINE_PASSED", packet["blockers"])

    def test_questions_window_is_distinct(self):
        owner = complete_input()
        owner["evaluated_at"] = "2026-09-21T15:30:01-04:00"
        packet = compile_packet(owner)
        self.assertFalse(packet["buyer"]["questions_open_at_evaluation"])
        self.assertNotIn("PROPOSAL_DEADLINE_PASSED", packet["blockers"])

    def test_source_manifest_digest_is_required(self):
        owner = complete_input()
        owner["source_manifest_digest"] = "0" * 64
        with self.assertRaises(CarrierError):
            compile_packet(owner)
        self.assertEqual(len(source_manifest_digest()), 64)

    def test_packet_tamper_does_not_verify(self):
        owner = example_owner_input()
        packet = compile_packet(owner)
        packet["posture"] = "SUBMISSION_READY"
        self.assertFalse(verify_packet(packet, owner))

    def test_duplicate_json_keys_fail_closed(self):
        with self.assertRaises(CarrierError):
            loads_strict('{"candidate": {}, "candidate": {}}')

    def test_extra_authority_claim_rejected(self):
        owner = complete_input()
        owner["submission"]["send_authorized"] = True
        with self.assertRaises(CarrierError):
            compile_packet(owner)

    def test_lineage_preserves_original_owner(self):
        self.assertEqual(
            SOURCE["lineage"]["original_opportunity_owner"],
            "Z-SteinhausMoraine-2315-Q4V8",
        )


if __name__ == "__main__":
    unittest.main()
