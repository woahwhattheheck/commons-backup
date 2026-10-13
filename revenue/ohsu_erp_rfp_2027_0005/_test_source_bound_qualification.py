from __future__ import annotations

from ._test_source_bound_support import *


class QualificationSourceBoundTests(SourceBoundTestCase):
    def test_manifest_matches_all_three_compiler_source_constants(self):
        manifest = json.loads((ROOT / "source_manifest.json").read_text())
        self.assertEqual(
            manifest["received_sources"]["controlling_rfp_workbook"]["sha256"],
            s.CONTROLLING_PACK_SHA256,
        )
        self.assertEqual(
            manifest["received_sources"]["supplier_qa_workbook"]["sha256"],
            s.SUPPLIER_QA_SHA256,
        )
        self.assertEqual(
            manifest["received_sources"]["professional_services_contract"]["sha256"],
            s.PROFESSIONAL_SERVICES_CONTRACT_SHA256,
        )
        self.assertEqual(
            {row["requirement_id"] for row in manifest["normalized_minimum_gates"]},
            set(s.REQUIREMENT_IDS),
        )

    def test_unconfirmed_team_route_is_candidate_not_ready(self):
        packet = s._compile_at(facts(), self.before_intent())
        self.assertEqual(packet["status"], "TEAMING_CANDIDATE")
        self.assertIn("NO_NAMED_COMMITTED_TEAM_PARTNER", packet["blockers"])
        self.assertEqual(packet["qualification_basis_counts"]["UNSATISFIED"], len(s.REQUIREMENT_IDS))
        self.assertEqual(packet["workshare"]["fixed_price_usd"], 12500)
        self.assertEqual(packet["workshare"]["commercial_status"], "PROPOSED_NOT_ACCEPTED")
        self.assertTrue(all(value is False for value in packet["authority"].values()))

    def test_wrong_controlling_pack_digest_fails_closed(self):
        payload = facts()
        payload["source_binding"]["controlling_pack_sha256"] = A
        with self.assertRaisesRegex(s.ContractError, "controlling pack digest"):
            s._compile_at(payload, self.before_intent())

    def test_wrong_supplier_qa_digest_fails_closed(self):
        payload = facts()
        payload["source_binding"]["supplier_qa_sha256"] = A
        with self.assertRaisesRegex(s.ContractError, "supplier Q&A digest"):
            s._compile_at(payload, self.before_intent())

    def test_missing_psc_binding_fails_closed(self):
        payload = facts()
        del payload["source_binding"]["professional_services_contract_sha256"]
        with self.assertRaisesRegex(s.ContractError, "keys mismatch"):
            s._compile_at(payload, self.before_intent())

    def test_wrong_psc_digest_fails_closed(self):
        payload = facts()
        payload["source_binding"]["professional_services_contract_sha256"] = A
        with self.assertRaisesRegex(s.ContractError, "professional services contract digest"):
            s._compile_at(payload, self.before_intent())

    def test_contract_review_exposes_source_conflict_without_acceptance(self):
        packet = s._compile_at(facts(), self.before_intent())
        self.assertEqual(
            packet["contract_review"]["professional_services_contract_sha256"],
            s.PROFESSIONAL_SERVICES_CONTRACT_SHA256,
        )
        self.assertIn(
            "PAYMENT_TERMS_SOURCE_CONFLICT_RFP_NET60_PSC_NET30",
            packet["contract_review"]["source_conflicts"],
        )
        self.assertTrue(packet["contract_review"]["owner_review_required_before_contract_acceptance"])
        self.assertFalse(packet["authority"]["contract_accepted"])
        self.assertFalse(packet["truth_boundary"]["payment_terms_source_conflict_resolved"])

    def test_registry_cannot_omit_minimum_gate(self):
        payload = facts()
        payload["requirements"].pop()
        with self.assertRaisesRegex(s.ContractError, "exact normalized gate set"):
            s._compile_at(payload, self.before_intent())

    def test_unconfirmed_target_contributes_zero_qualifications(self):
        payload = facts()
        payload["requirements"][0].update({
            "state": "SATISFIED",
            "basis": "NAMED_COMMITTED_TEAM_PARTNER",
            "entity_ref": "prime.example",
            "evidence_sha256": A,
        })
        with self.assertRaisesRegex(s.ContractError, "unconfirmed outreach target contributes zero"):
            s._compile_at(payload, self.before_intent())

    def test_partner_evidence_must_match_committed_partner(self):
        payload = facts(commitment=True, all_satisfied=True, partner_gates={s.REQUIREMENT_IDS[0]})
        payload["requirements"][0]["entity_ref"] = "different.prime"
        with self.assertRaisesRegex(s.ContractError, "does not match confirmed partner"):
            s._compile_at(payload, self.before_intent())

    def test_prime_route_cannot_inherit_partner_basis(self):
        payload = facts(route="PRIME", all_satisfied=True)
        payload["requirements"][0].update({
            "basis": "NAMED_COMMITTED_TEAM_PARTNER",
            "entity_ref": "prime.example",
            "evidence_sha256": B,
        })
        with self.assertRaisesRegex(s.ContractError, "forbidden outside TEAMING"):
            s._compile_at(payload, self.before_intent())

    def test_confirmed_team_can_compose_qualification(self):
        payload = facts(
            commitment=True,
            all_satisfied=True,
            partner_gates={s.REQUIREMENT_IDS[0], s.REQUIREMENT_IDS[1], s.REQUIREMENT_IDS[5]},
        )
        packet = s._compile_at(payload, self.before_intent())
        self.assertEqual(packet["status"], "READY_FOR_OWNER_TEAMING_REVIEW")
        self.assertEqual(packet["qualification_basis_counts"]["NAMED_COMMITTED_TEAM_PARTNER"], 3)
        self.assertFalse(packet["truth_boundary"]["external_send_authorized"])
        self.assertFalse(packet["truth_boundary"]["contract_terms_accepted"])

    def test_confirmed_team_with_gap_holds(self):
        payload = facts(commitment=True, all_satisfied=True, partner_gates={s.REQUIREMENT_IDS[0]})
        payload["requirements"][-1] = {
            "requirement_id": s.REQUIREMENT_IDS[-1],
            "state": "UNKNOWN",
            "basis": "NONE",
            "entity_ref": None,
            "evidence_sha256": None,
        }
        packet = s._compile_at(payload, self.before_intent())
        self.assertEqual(packet["status"], "HOLD_TEAM_QUALIFICATION")

    def test_direct_prime_gaps_are_explicit_hold(self):
        packet = s._compile_at(facts(route="PRIME"), self.before_intent())
        self.assertEqual(packet["status"], "HOLD_PRIME_QUALIFICATION")
        self.assertFalse(packet["authority"]["prime_eligibility_verified_by_ohsu"])

    def test_direct_prime_all_respondent_evidence_only_owner_review(self):
        packet = s._compile_at(facts(route="PRIME", all_satisfied=True), self.before_intent())
        self.assertEqual(packet["status"], "READY_FOR_OWNER_PRIME_REVIEW")
        self.assertFalse(packet["authority"]["prime_eligibility_verified_by_ohsu"])
        self.assertTrue(packet["truth_boundary"]["respondent_identity_code_pinned"])

    def test_commitment_revocation_invalidates_partner_evidence(self):
        payload = facts(
            commitment=True,
            all_satisfied=True,
            partner_gates={s.REQUIREMENT_IDS[0]},
        )
        s._compile_at(payload, self.before_intent())
        payload["teaming_commitment"] = {
            "status": "UNCONFIRMED",
            "partner_ref": None,
            "evidence_sha256": None,
        }
        with self.assertRaisesRegex(
            s.ContractError, "unconfirmed outreach target contributes zero"
        ):
            s._compile_at(payload, self.before_intent())

    def test_exact_intent_deadline_holds_without_receipt(self):
        packet = s._compile_at(facts(), self.at_intent())
        self.assertEqual(packet["status"], "HOLD_INTENT_DEADLINE")

    def test_after_deadline_receipt_holds_chronology(self):
        payload = facts(commitment=True, all_satisfied=True)
        payload["intent_receipt"] = {
            "provider_event_sha256": A,
            "submitted_at": "2026-09-17T00:00:01Z",
        }
        packet = s._compile_at(
            payload, dt.datetime(2026, 9, 17, 1, 0, tzinfo=dt.timezone.utc)
        )
        self.assertEqual(packet["status"], "HOLD_INTENT_CHRONOLOGY")
