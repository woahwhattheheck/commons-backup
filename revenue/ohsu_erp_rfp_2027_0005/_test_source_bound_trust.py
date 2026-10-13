from __future__ import annotations

from ._test_source_bound_support import *


class TrustBoundaryTests(SourceBoundTestCase):
    def test_confirmed_partner_cannot_equal_canonical_respondent(self):
        payload = facts(commitment=True, all_satisfied=True)
        payload["teaming_commitment"]["partner_ref"] = s.RESPONDENT_REF
        with self.assertRaisesRegex(s.ContractError, "must differ from canonical respondent"):
            s._compile_at(payload, self.before_intent())

    def test_prime_respondent_identity_is_code_pinned(self):
        payload = facts(route="PRIME", all_satisfied=True)
        payload["requirements"][0]["entity_ref"] = "borrowed-prime.example"
        with self.assertRaisesRegex(s.ContractError, "canonical respondent"):
            s._compile_at(payload, self.before_intent())

    def test_prime_cannot_compose_borrowed_entities(self):
        payload = facts(route="PRIME", all_satisfied=True)
        for index, row in enumerate(payload["requirements"]):
            row["entity_ref"] = f"outside-organization-{index}.example"
        with self.assertRaisesRegex(s.ContractError, "canonical respondent"):
            s._compile_at(payload, self.before_intent())

    def test_teaming_respondent_rows_remain_bound_to_respondent(self):
        payload = facts(commitment=True, all_satisfied=True)
        payload["requirements"][0]["entity_ref"] = "uncommitted-subcontractor.example"
        with self.assertRaisesRegex(s.ContractError, "canonical respondent"):
            s._compile_at(payload, self.before_intent())

    def test_unverified_predeadline_receipt_cannot_clear_postdeadline_hold(self):
        payload = facts(route="PRIME", all_satisfied=True)
        payload["intent_receipt"] = {
            "provider_event_sha256": A,
            "submitted_at": "2026-09-16T23:59:59Z",
        }
        packet = s._compile_at(payload, self.at_intent())
        self.assertEqual(packet["status"], "HOLD_INTENT_RECEIPT_UNVERIFIED")
        self.assertIn("INTENT_RECEIPT_NOT_PROVIDER_AUTHENTICATED", packet["blockers"])
        self.assertFalse(packet["source_policy"]["intent_receipt_trust_root_configured"])
        self.assertFalse(packet["truth_boundary"]["unverified_intent_receipt_clears_deadline_hold"])

    def test_exact_pinned_provider_receipt_can_clear_deadline_hold(self):
        payload = facts(route="PRIME", all_satisfied=True)
        payload["intent_receipt"] = {
            "provider_event_sha256": A,
            "submitted_at": "2026-09-16T23:59:59Z",
        }
        old_sha = s.VERIFIED_INTENT_RECEIPT_SHA256
        old_time = s.VERIFIED_INTENT_RECEIPT_SUBMITTED_AT
        s.VERIFIED_INTENT_RECEIPT_SHA256 = A
        s.VERIFIED_INTENT_RECEIPT_SUBMITTED_AT = "2026-09-16T23:59:59Z"
        try:
            packet = s._compile_at(payload, self.at_intent())
        finally:
            s.VERIFIED_INTENT_RECEIPT_SHA256 = old_sha
            s.VERIFIED_INTENT_RECEIPT_SUBMITTED_AT = old_time
        self.assertEqual(packet["status"], "READY_FOR_OWNER_PRIME_REVIEW")
        self.assertTrue(packet["source_policy"]["intent_receipt_trust_root_configured"])

    def test_packet_v3_advertises_psc_and_trust_boundaries(self):
        packet = s._compile_at(facts(), self.before_intent())
        self.assertEqual(packet["schema"], "ohsu-erp-source-bound-owner-review/v3")
        self.assertFalse(packet["source_policy"]["intent_receipt_trust_root_configured"])
        self.assertTrue(packet["truth_boundary"]["respondent_identity_code_pinned"])
        self.assertTrue(packet["truth_boundary"]["professional_services_contract_hash_pinned"])
        self.assertFalse(packet["truth_boundary"]["contract_terms_accepted"])
        self.assertFalse(packet["truth_boundary"]["unverified_intent_receipt_clears_deadline_hold"])

    def test_verify_stales_packet_if_contract_review_projection_is_forged(self):
        payload = facts()
        bound = self.before_intent()
        packet = s._compile_at(payload, bound)
        packet["contract_review"]["source_conflicts"] = []
        with self.assertRaisesRegex(s.ContractError, "integrity does not match"):
            s.verify_current(packet, payload)

    def test_verify_stales_forged_receipt_packet_at_deadline(self):
        payload = facts(route="PRIME", all_satisfied=True)
        payload["intent_receipt"] = {
            "provider_event_sha256": A,
            "submitted_at": "2026-09-16T23:59:59Z",
        }
        just_before = dt.datetime(2026, 9, 16, 23, 59, 59, tzinfo=dt.timezone.utc)
        packet = s._compile_at(payload, just_before)
        original = s._now_utc
        s._now_utc = lambda: self.at_intent()
        try:
            with self.assertRaisesRegex(s.ContractError, "operational state is stale"):
                s.verify_current(packet, payload)
        finally:
            s._now_utc = original
