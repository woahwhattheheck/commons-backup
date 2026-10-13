from __future__ import annotations

import copy
import unittest

from revenue.scdhhs_mcde_5400030026.qualification import (
    QualificationError,
    SOURCE_CONTRACT,
    compile_qualification,
    verify_receipt,
)


def source_observation():
    return {
        "solicitation_number": SOURCE_CONTRACT["solicitation"]["number"],
        "attachment_count": len(SOURCE_CONTRACT["attachment_manifest"]),
        "attachments": copy.deepcopy(SOURCE_CONTRACT["attachment_manifest"]),
        "controlling_document": {
            "name": SOURCE_CONTRACT["controlling_document"]["name"],
            "posted_at": SOURCE_CONTRACT["controlling_document"]["posted_at"],
        },
    }


def security(value=True):
    return {
        key: {
            "ready": value,
            "evidence_refs": [f"evidence:security:{key}"] if value else [],
        }
        for key in SOURCE_CONTRACT["proposal_readiness"]["security_controls"]
    }


def entity(name):
    return {
        "entity_name": name,
        "as_prime_contractor": True,
        "similar_size_scope": True,
        "evidence_refs": [f"evidence:{name}"],
    }


def implementation(lives=1_000_000):
    return {
        "environment": "state-health-plan",
        "covered_lives": lives,
        "successful": True,
        "evidence_refs": ["evidence:adt-implementation"],
    }


def subcontractor(*, triggered=True, qualification_refs=None):
    return {
        "business_name": "Evidence Subcontractor",
        "business_address": "owner-private:address-record",
        "phone": "owner-private:phone-record",
        "point_of_contact": "owner-private:poc-record",
        "taxpayer_id_evidence_ref": "owner-private:taxpayer-id-record",
        "taxpayer_id_evidence_sha256": "2" * 64,
        "identification_evidence_refs": ["owner-private:complete-subcontractor-id-packet"],
        "scope": "ADT platform and interoperability",
        "cost_share_percent": 15 if triggered else 5,
        "government_information_access": triggered,
        "critical_services": triggered,
        "relationship_explained": True,
        "qualification_evidence_refs": list(qualification_refs or []),
    }


def prime_packet():
    return {
        "route": "prime_offeror",
        "offeror": {
            "legal_name": "Evidence Test Offeror",
            "prime_contractor_months": 36,
            "prime_experience_evidence_refs": ["evidence:prime-history"],
            "similar_healthcare_entities": [entity("A"), entity("B"), entity("C")],
            "realtime_adt_months": 36,
            "healthcare_adt_months": 24,
            "adt_experience_evidence_refs": ["evidence:adt-history"],
            "adt_implementations": [implementation()],
        },
        "subcontractors": [],
        "proposal_readiness": {
            "project_manager_mcde_months": 36,
            "project_manager_healthcare_months": 24,
            "project_manager_evidence_refs": ["evidence:project-manager"],
            "security_controls": security(True),
        },
    }


class QualificationTests(unittest.TestCase):
    def test_matching_snapshot_never_asserts_live_currentness(self):
        receipt = compile_qualification(prime_packet(), source_observation=source_observation())
        self.assertEqual(receipt["decision"], "PRIME_EVIDENCE_READY_FOR_LIVE_SOURCE_REVIEW")
        self.assertTrue(receipt["source_snapshot_match"])
        self.assertFalse(receipt["source_current"])
        self.assertTrue(receipt["live_source_review_required"])
        self.assertEqual(receipt["deadline_status"], "NOT_EVALUATED")
        self.assertTrue(receipt["prime_evidence_ready"])
        self.assertFalse(receipt["prime_qualification_candidate"])
        self.assertIsNone(receipt["teaming_prime_legal_name"])
        self.assertFalse(receipt["submission_authorized"])
        self.assertTrue(all(value is False for value in receipt["authority"].values()))
        self.assertTrue(
            verify_receipt(
                prime_packet(), source_observation=source_observation(), receipt=receipt
            )
        )

    def test_original_rfp_cannot_replace_amendment_one_snapshot(self):
        obs = source_observation()
        obs["controlling_document"] = {
            "name": "_MCDE RFP.pdf",
            "posted_at": "2026-07-31T17:34:53-04:00",
        }
        receipt = compile_qualification(prime_packet(), source_observation=obs)
        self.assertEqual(receipt["decision"], "HOLD_SOURCE_SNAPSHOT_MISMATCH")
        self.assertIn("SOURCE_SNAPSHOT_CONTROLLING_DOCUMENT_MISMATCH", receipt["reasons"])
        self.assertFalse(receipt["source_current"])

    def test_new_or_missing_attachment_fails_snapshot_match(self):
        for mutate in ("missing", "extra"):
            with self.subTest(mutate=mutate):
                obs = source_observation()
                if mutate == "missing":
                    obs["attachments"].pop()
                else:
                    obs["attachments"].append(
                        {"name": "Amendment 2.pdf", "posted_at": "2026-09-14T09:00:00-04:00"}
                    )
                obs["attachment_count"] = len(obs["attachments"])
                receipt = compile_qualification(prime_packet(), source_observation=obs)
                self.assertEqual(receipt["decision"], "HOLD_SOURCE_SNAPSHOT_MISMATCH")
                self.assertIn("SOURCE_SNAPSHOT_ATTACHMENT_MANIFEST_MISMATCH", receipt["reasons"])
                self.assertFalse(receipt["source_current"])

    def test_candidate_threshold_override_is_bound_but_has_no_authority(self):
        packet = prime_packet()
        packet["candidate_claimed_minimums"] = {
            "prime_contractor_months": 1,
            "similar_size_scope_healthcare_entities": 1,
            "successful_adt_min_lives": 1,
        }
        packet["offeror"]["prime_contractor_months"] = 1
        packet["offeror"]["similar_healthcare_entities"] = [entity("A")]
        packet["offeror"]["adt_implementations"] = [implementation(1)]
        receipt = compile_qualification(packet, source_observation=source_observation())
        self.assertEqual(receipt["decision"], "SNAPSHOT_MANDATORY_EVIDENCE_GAP")
        self.assertIn("MANDATORY_PRIME_CONTRACTOR_EXPERIENCE", receipt["reasons"])
        self.assertIn("MANDATORY_THREE_SIMILAR_HEALTHCARE_ENTITIES", receipt["reasons"])
        self.assertIn("MANDATORY_SUCCESSFUL_ONE_MILLION_LIVES_ADT", receipt["reasons"])

    def test_snapshot_gap_never_emits_current_no_go(self):
        packet = prime_packet()
        packet["offeror"]["prime_contractor_months"] = 0
        receipt = compile_qualification(packet, source_observation=source_observation())
        self.assertFalse(receipt["source_current"])
        self.assertTrue(receipt["live_source_review_required"])
        self.assertEqual(receipt["decision"], "SNAPSHOT_MANDATORY_EVIDENCE_GAP")
        self.assertNotIn("NO_GO", receipt["decision"])

    def test_three_entities_must_each_be_prime_contracts(self):
        packet = prime_packet()
        packet["offeror"]["similar_healthcare_entities"][2]["as_prime_contractor"] = False
        receipt = compile_qualification(packet, source_observation=source_observation())
        self.assertEqual(receipt["decision"], "SNAPSHOT_MANDATORY_EVIDENCE_GAP")
        self.assertIn("MANDATORY_THREE_SIMILAR_HEALTHCARE_ENTITIES", receipt["reasons"])

    def test_claimed_months_without_evidence_do_not_pass(self):
        packet = prime_packet()
        packet["offeror"]["prime_experience_evidence_refs"] = []
        packet["offeror"]["adt_experience_evidence_refs"] = []
        receipt = compile_qualification(packet, source_observation=source_observation())
        self.assertEqual(receipt["decision"], "SNAPSHOT_MANDATORY_EVIDENCE_GAP")
        self.assertIn("MANDATORY_PRIME_CONTRACTOR_EXPERIENCE", receipt["reasons"])
        self.assertIn("MANDATORY_REALTIME_ADT_EXPERIENCE", receipt["reasons"])
        self.assertIn("MANDATORY_HEALTHCARE_ADT_EXPERIENCE", receipt["reasons"])

    def test_partner_experience_cannot_cure_offeror_prime_history(self):
        packet = prime_packet()
        packet["offeror"]["prime_contractor_months"] = 0
        packet["subcontractors"] = [
            subcontractor(qualification_refs=["partner:many-prime-contracts", "partner:million-lives"])
        ]
        receipt = compile_qualification(packet, source_observation=source_observation())
        self.assertEqual(receipt["decision"], "SNAPSHOT_MANDATORY_EVIDENCE_GAP")
        self.assertFalse(receipt["prime_qualification_candidate"])
        self.assertFalse(receipt["prime_evidence_ready"])

    def test_team_route_arbitrary_prime_labels_never_mint_team_ready(self):
        packet = prime_packet()
        packet["route"] = "subcontractor_to_qualified_prime"
        packet["teaming"] = {
            "prospective_prime_legal_name": "Qualified Prime Candidate",
            "relationship_explained": True,
            "prime_review_evidence_refs": ["prime:qualification-matrix"],
        }
        receipt = compile_qualification(packet, source_observation=source_observation())
        self.assertEqual(receipt["decision"], "TEAMING_DISCOVERY")
        self.assertEqual(receipt["teaming_prime_legal_name"], "Qualified Prime Candidate")
        self.assertIn("QUALIFIED_PRIME_REVIEW_REQUIRED", receipt["reasons"])
        self.assertTrue(receipt["teaming_evidence_candidate"])
        self.assertFalse(receipt["prime_qualification_candidate"])
        self.assertFalse(receipt["submission_authorized"])

    def test_team_route_requires_relationship_and_prime_review_evidence(self):
        packet = prime_packet()
        packet["route"] = "subcontractor_to_qualified_prime"
        packet["teaming"] = {
            "prospective_prime_legal_name": "Partner",
            "relationship_explained": False,
            "prime_review_evidence_refs": [],
        }
        receipt = compile_qualification(packet, source_observation=source_observation())
        self.assertEqual(receipt["decision"], "TEAMING_DISCOVERY")
        self.assertIn("TEAMING_PRIME_EVIDENCE_OR_RELATIONSHIP_INCOMPLETE", receipt["reasons"])
        self.assertFalse(receipt["teaming_evidence_candidate"])

    def test_proposal_readiness_is_separate_from_mandatory_minimums(self):
        packet = prime_packet()
        packet["proposal_readiness"]["project_manager_mcde_months"] = 35
        packet["proposal_readiness"]["security_controls"]["hipaa_baa"] = {
            "ready": False,
            "evidence_refs": [],
        }
        receipt = compile_qualification(packet, source_observation=source_observation())
        self.assertEqual(receipt["decision"], "SNAPSHOT_PROPOSAL_EVIDENCE_GAP")
        self.assertIn("READINESS_PROJECT_MANAGER_MCDE_EXPERIENCE", receipt["reasons"])
        self.assertIn("READINESS_SECURITY_HIPAA_BAA", receipt["reasons"])

    def test_security_true_without_evidence_is_not_ready(self):
        packet = prime_packet()
        packet["proposal_readiness"]["security_controls"]["hipaa_compliance"]["evidence_refs"] = []
        receipt = compile_qualification(packet, source_observation=source_observation())
        self.assertEqual(receipt["decision"], "SNAPSHOT_PROPOSAL_EVIDENCE_GAP")
        self.assertIn("READINESS_SECURITY_HIPAA_COMPLIANCE", receipt["reasons"])

    def test_subcontractor_relationship_needed_only_when_qualification_evidence_relied_on(self):
        packet = prime_packet()
        sub = subcontractor(triggered=False)
        sub.update(
            {
                "business_address": None,
                "phone": None,
                "point_of_contact": None,
                "taxpayer_id_evidence_ref": None,
                "taxpayer_id_evidence_sha256": None,
                "identification_evidence_refs": [],
                "relationship_explained": False,
            }
        )
        packet["subcontractors"] = [sub]
        receipt = compile_qualification(packet, source_observation=source_observation())
        self.assertEqual(receipt["decision"], "PRIME_EVIDENCE_READY_FOR_LIVE_SOURCE_REVIEW")

        packet["subcontractors"][0]["qualification_evidence_refs"] = ["sub:qualification-evidence"]
        receipt = compile_qualification(packet, source_observation=source_observation())
        self.assertEqual(receipt["decision"], "SNAPSHOT_PROPOSAL_EVIDENCE_GAP")
        self.assertIn("SUBCONTRACTOR_RELATIONSHIP_UNEXPLAINED", receipt["reasons"])

    def test_subcontractor_identification_bare_boolean_cannot_clear_gate(self):
        packet = prime_packet()
        sub = subcontractor()
        for key in (
            "business_address",
            "phone",
            "point_of_contact",
            "taxpayer_id_evidence_ref",
            "taxpayer_id_evidence_sha256",
        ):
            sub[key] = None
        sub["identification_evidence_refs"] = []
        sub["identification_complete"] = True  # legacy self-attestation must have no authority
        packet["subcontractors"] = [sub]
        receipt = compile_qualification(packet, source_observation=source_observation())
        self.assertEqual(receipt["decision"], "SNAPSHOT_PROPOSAL_EVIDENCE_GAP")
        self.assertIn("SUBCONTRACTOR_IDENTIFICATION_INCOMPLETE", receipt["reasons"])

    def test_each_required_subcontractor_identity_component_is_fail_closed(self):
        missing_cases = {
            "business_address": None,
            "phone": None,
            "point_of_contact": None,
            "taxpayer_id_evidence_ref": None,
            "taxpayer_id_evidence_sha256": None,
            "identification_evidence_refs": [],
        }
        for field, missing in missing_cases.items():
            with self.subTest(field=field):
                packet = prime_packet()
                sub = subcontractor()
                sub[field] = missing
                packet["subcontractors"] = [sub]
                receipt = compile_qualification(packet, source_observation=source_observation())
                self.assertEqual(receipt["decision"], "SNAPSHOT_PROPOSAL_EVIDENCE_GAP")
                self.assertIn("SUBCONTRACTOR_IDENTIFICATION_INCOMPLETE", receipt["reasons"])

    def test_complete_privacy_safe_subcontractor_identity_packet_still_requires_trusted_review(self):
        packet = prime_packet()
        packet["subcontractors"] = [subcontractor()]
        receipt = compile_qualification(packet, source_observation=source_observation())
        self.assertEqual(receipt["decision"], "SNAPSHOT_PROPOSAL_EVIDENCE_GAP")
        self.assertNotIn("SUBCONTRACTOR_IDENTIFICATION_INCOMPLETE", receipt["reasons"])
        self.assertIn("SUBCONTRACTOR_IDENTIFICATION_REVIEW_REQUIRED", receipt["reasons"])

    def test_taxpayer_evidence_digest_is_strict(self):
        packet = prime_packet()
        sub = subcontractor()
        sub["taxpayer_id_evidence_sha256"] = "not-a-digest"
        packet["subcontractors"] = [sub]
        with self.assertRaises(QualificationError):
            compile_qualification(packet, source_observation=source_observation())

    def test_strict_types_reject_bool_as_months_and_string_boolean(self):
        packet = prime_packet()
        packet["offeror"]["prime_contractor_months"] = True
        with self.assertRaises(QualificationError):
            compile_qualification(packet, source_observation=source_observation())

        packet = prime_packet()
        packet["proposal_readiness"]["security_controls"]["hipaa_baa"]["ready"] = "true"
        with self.assertRaises(QualificationError):
            compile_qualification(packet, source_observation=source_observation())

    def test_duplicate_source_attachment_name_holds_snapshot(self):
        obs = source_observation()
        obs["attachments"][1] = copy.deepcopy(obs["attachments"][0])
        receipt = compile_qualification(prime_packet(), source_observation=obs)
        self.assertEqual(receipt["decision"], "HOLD_SOURCE_SNAPSHOT_MISMATCH")
        self.assertIn("SOURCE_SNAPSHOT_DUPLICATE_ATTACHMENT_NAME", receipt["reasons"])

    def test_receipt_is_deterministic_and_tamper_evident(self):
        packet = prime_packet()
        obs = source_observation()
        first = compile_qualification(packet, source_observation=obs)
        second = compile_qualification(copy.deepcopy(packet), source_observation=copy.deepcopy(obs))
        self.assertEqual(first, second)

        tampered = copy.deepcopy(first)
        tampered["source_current"] = True
        tampered["submission_authorized"] = True
        self.assertFalse(verify_receipt(packet, source_observation=obs, receipt=tampered))

        packet["offeror"]["prime_contractor_months"] = 35
        self.assertFalse(verify_receipt(packet, source_observation=obs, receipt=first))


if __name__ == "__main__":
    unittest.main()
