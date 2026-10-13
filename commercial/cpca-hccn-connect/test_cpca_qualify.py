import copy
import json
import unittest
from pathlib import Path

import cpca_qualify as q

ROOT = Path(__file__).resolve().parent
SPEC = json.loads((ROOT / "qualification_spec.json").read_text())
CURRENT = {
    "schema": "cpca-hccn-evidence/v1",
    "source_packet": {
        "gmail_message_id": "1a0a1017913c03e8",
        "filename": "2026.09.03_CPCA HCCN Connect Marketplace RFP.pdf",
        "sha256": "37c61b76500fee4639e1499d7683d4882da294f65d77e5e59c224ada3fc52529",
    },
    "current_time": "2026-09-14T17:45:00-04:00",
    "domain": "artificial_intelligence",
    "service_type": "technical_assistance",
    "bid_model": "direct_prime",
    "gate_status": {
        "virtual_or_california_presence": "HOLD",
        "reporting_invoicing_oversight": "HOLD",
        "delivery_capacity": "HOLD",
        "subject_matter_expertise": "HOLD",
        "technical_assistance_track_record": "HOLD",
        "regulatory_standards_knowledge": "HOLD",
        "sample_work_products": "HOLD",
        "single_pdf_submission": "HOLD",
        "submission_authority": "HOLD",
        "licensing_insurance": "HOLD",
        "cultural_competency": "HOLD",
        "client_references": "MISSING",
        "named_personnel": "HOLD",
        "personnel_comparable_engagements": "MISSING",
        "recent_domain_engagements": "MISSING",
        "safety_net_experience": "MISSING",
        "rate_sheet": "MISSING",
        "signed_attestation": "MISSING",
    },
    "gate_sources": {},
    "client_references": [],
    "comparable_engagements": [],
}


def proven_fixture():
    e = copy.deepcopy(CURRENT)
    e["gate_status"] = {
        g["id"]: "PROVEN" for g in SPEC["mandatory_direct_prime_gates"]
    }
    e["gate_sources"] = {
        g["id"]: [f"urn:test:gate:{g['id']}"]
        for g in SPEC["mandatory_direct_prime_gates"]
        if g["id"] not in q.DERIVED_SOURCE_GATES
    }
    e["client_references"] = [
        {"reference_id": "r1", "name": "r1", "source": "urn:test:r1"},
        {"reference_id": "r2", "name": "r2", "source": "urn:test:r2"},
        {"reference_id": "r3", "name": "r3", "source": "urn:test:r3"},
    ]
    e["comparable_engagements"] = [
        {
            "engagement_id": "e1",
            "domains": ["artificial_intelligence"],
            "state": "COMPLETED",
            "end_date": "2026-06-01",
            "source": "urn:test:e1",
            "safety_net_primary_care": True,
        },
        {
            "engagement_id": "e2",
            "domains": ["artificial_intelligence"],
            "state": "ACTIVE",
            "end_date": "2026-09-01",
            "source": "urn:test:e2",
            "safety_net_primary_care": False,
        },
    ]
    return e


class QualificationTests(unittest.TestCase):
    def test_current_evidence_holds(self):
        result = q.evaluate(SPEC, CURRENT)
        self.assertEqual("HOLD", result["state"])
        self.assertIn("safety_net_experience", result["blockers"])
        self.assertIn("client_references", result["blockers"])
        self.assertFalse(result["authority"]["proposal_submitted"])

    def test_source_digest_must_match(self):
        e = copy.deepcopy(CURRENT)
        e["source_packet"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source packet mismatch"):
            q.evaluate(SPEC, e)

    def test_cannot_claim_references_without_sources(self):
        e = proven_fixture()
        e["client_references"] = [{"reference_id": "r1", "name": "r1", "source": "urn:test:r1"}]
        with self.assertRaisesRegex(ValueError, "client_references cannot be PROVEN"):
            q.evaluate(SPEC, e)

    def test_duplicate_reference_identity_does_not_count(self):
        e = proven_fixture()
        e["client_references"][2]["reference_id"] = "r1"
        with self.assertRaisesRegex(ValueError, "distinct source-bound references"):
            q.evaluate(SPEC, e)

    def test_emerging_domain_needs_two_engagements(self):
        e = proven_fixture()
        e["comparable_engagements"] = e["comparable_engagements"][:1]
        with self.assertRaisesRegex(ValueError, "recent_domain_engagements cannot be PROVEN"):
            q.evaluate(SPEC, e)

    def test_old_completed_engagement_does_not_count(self):
        e = proven_fixture()
        e["comparable_engagements"][0]["end_date"] = "2020-06-01"
        with self.assertRaisesRegex(ValueError, "lookback window"):
            q.evaluate(SPEC, e)

    def test_cross_domain_engagement_does_not_count(self):
        e = proven_fixture()
        e["comparable_engagements"][0]["domains"] = ["data_management_and_analytics"]
        with self.assertRaisesRegex(ValueError, "recent_domain_engagements"):
            q.evaluate(SPEC, e)

    def test_safety_net_engagement_must_match_selected_domain(self):
        e = proven_fixture()
        e["comparable_engagements"][0]["domains"] = ["data_management_and_analytics"]
        e["gate_status"]["recent_domain_engagements"] = "MISSING"
        with self.assertRaisesRegex(ValueError, "safety_net_experience"):
            q.evaluate(SPEC, e)

    def test_duplicate_engagement_identity_rejected(self):
        e = proven_fixture()
        e["comparable_engagements"][1]["engagement_id"] = "e1"
        with self.assertRaisesRegex(ValueError, "duplicate comparable engagement identity"):
            q.evaluate(SPEC, e)

    def test_non_count_proven_gate_requires_source(self):
        e = proven_fixture()
        e["gate_sources"].pop("subject_matter_expertise")
        with self.assertRaisesRegex(ValueError, "subject_matter_expertise cannot be PROVEN"):
            q.evaluate(SPEC, e)

    def test_full_source_bound_fixture_prime_ready(self):
        result = q.evaluate(SPEC, proven_fixture())
        self.assertEqual("PRIME_READY", result["state"])
        self.assertEqual([], result["blockers"])

    def test_established_domain_requires_three_recent_completed(self):
        e = proven_fixture()
        e["domain"] = "data_management_and_analytics"
        e["comparable_engagements"] = [
            {"engagement_id": "d1", "domains": [e["domain"]], "state": "COMPLETED", "end_date": "2026-01-01", "source": "urn:test:d1", "safety_net_primary_care": True},
            {"engagement_id": "d2", "domains": [e["domain"]], "state": "COMPLETED", "end_date": "2025-01-01", "source": "urn:test:d2", "safety_net_primary_care": False},
            {"engagement_id": "d3", "domains": [e["domain"]], "state": "COMPLETED", "end_date": "2024-01-01", "source": "urn:test:d3", "safety_net_primary_care": False},
        ]
        self.assertEqual("PRIME_READY", q.evaluate(SPEC, e)["state"])
        e["comparable_engagements"][2]["end_date"] = "2023-09-13"
        with self.assertRaisesRegex(ValueError, "lookback window"):
            q.evaluate(SPEC, e)

    def test_established_domain_requires_completed_not_substantially_completed(self):
        e = proven_fixture()
        e["domain"] = "data_management_and_analytics"
        e["comparable_engagements"] = [
            {"engagement_id": "d1", "domains": [e["domain"]], "state": "COMPLETED", "end_date": "2026-01-01", "source": "urn:test:d1", "safety_net_primary_care": True},
            {"engagement_id": "d2", "domains": [e["domain"]], "state": "COMPLETED", "end_date": "2025-01-01", "source": "urn:test:d2", "safety_net_primary_care": False},
            {"engagement_id": "d3", "domains": [e["domain"]], "state": "SUBSTANTIALLY_COMPLETED", "end_date": "2024-01-01", "source": "urn:test:d3", "safety_net_primary_care": False},
        ]
        with self.assertRaisesRegex(ValueError, "recent_domain_engagements"):
            q.evaluate(SPEC, e)

    def test_deadline_passed_is_no_bid(self):
        e = proven_fixture()
        e["current_time"] = "2026-09-18T17:00:01-07:00"
        result = q.evaluate(SPEC, e)
        self.assertEqual("NO_BID", result["state"])
        self.assertEqual("deadline_passed", result["reason"])

    def test_teaming_requires_named_prime_and_support_proof(self):
        e = proven_fixture()
        e["bid_model"] = "healthcare_prime_subcontract"
        e["healthcare_prime"] = {
            "name": "Example Qualified Health Prime",
            "eligibility_source": "urn:test:eligibility",
            "safety_net_experience_source": "urn:test:safety-net",
            "relationship_authority": True,
        }
        e["tjlabs_support_gate_ids"] = ["subject_matter_expertise", "technical_assistance_track_record"]
        result = q.evaluate(SPEC, e)
        self.assertEqual("TEAMING_READY", result["state"])

    def test_teaming_without_authorized_prime_holds(self):
        e = proven_fixture()
        e["bid_model"] = "healthcare_prime_subcontract"
        e["healthcare_prime"] = {}
        e["tjlabs_support_gate_ids"] = ["subject_matter_expertise"]
        result = q.evaluate(SPEC, e)
        self.assertEqual("HOLD", result["state"])
        self.assertIn("named_healthcare_prime", result["blockers"])

    def test_receipt_is_stable(self):
        result = q.evaluate(SPEC, CURRENT)
        self.assertEqual(q.canonical_digest(result), q.canonical_digest(copy.deepcopy(result)))


if __name__ == "__main__":
    unittest.main()
