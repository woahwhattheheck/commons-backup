from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = json.loads((HERE / "qualification_spec.json").read_text(encoding="utf-8"))
module_spec = importlib.util.spec_from_file_location("alcorn_qualification", HERE / "qualification.py")
q = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(q)

PACKET = {
    "gmail_message_id": "1a0a0186cbd89b53",
    "filename": "RFP#5588 NVIDIA v3.pdf",
    "sha256": "107f0cc3ae880e4000ad89f0d6db6ad4908600afcdafcaf8d66ff4303170f688",
    "page_count": 41,
}
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64


def artifacts(present: bool = True):
    if present:
        return {
            "section_viii_cost_information": {"state": "PRESENT_SOURCE_BOUND", "sha256": DIGEST_A, "evidence_id": "buyer:sec-viii"},
            "section_ix_references": {"state": "PRESENT_SOURCE_BOUND", "sha256": DIGEST_B, "evidence_id": "buyer:sec-ix"},
            "section_vii_item_12_requirements_matrix": {"state": "PRESENT_SOURCE_BOUND", "sha256": DIGEST_C, "evidence_id": "buyer:sec-vii-item12"},
        }
    return {key: {"state": "MISSING_BUYER_ARTIFACT"} for key in q.MISSING_ARTIFACTS}


def nvidia_partner(*, committed: bool = False):
    row = {
        "name": "Example Qualified NVIDIA Prime",
        "status": "ACTIVE",
        "authorization_evidence_id": "provider:nvidia-partner-record:example",
        "authorization_sha256": DIGEST_A,
        "effective_date": "2026-01-01",
        "expires_date": "2027-01-01",
        "scope": ["DGX SPARK", "LAB DESIGN"],
    }
    if committed:
        row.update({
            "commitment_evidence_id": "partner:commitment:example",
            "commitment_current": True,
            "commitment_revoked": False,
        })
    return row


def operational():
    return {
        "legal_entity_evidence_id": "corp:entity",
        "certificate_of_liability_insurance_evidence_id": "corp:coi",
        "everify_evidence_id": "corp:everify",
        "taxpayer_id_confirmation_evidence_id": "private-confirmation:tin",
        "order_remit_address_evidence_id": "private-confirmation:addresses",
        "amendments_review_evidence_id": "buyer:amendments-review",
        "insurance_expires_date": "2027-01-01",
        "pricing_approved": True,
        "pricing_approval_evidence_id": "owner:pricing",
        "signature_officer_ready": True,
        "signature_officer_evidence_id": "owner:signature-officer",
        "sealed_delivery_plan_ready": True,
        "sealed_delivery_plan_evidence_id": "ops:sealed-delivery",
        "training_sample_ready": True,
        "training_sample_evidence_id": "delivery:training-sample",
        "warranty_support_ready": True,
        "warranty_support_evidence_id": "prime:warranty-support",
    }


def track_record():
    return [{
        "engagement_id": "ai-infra-1",
        "source": "prime:past-performance:1",
        "completed_at": "2026-06-01",
        "architected": True,
        "deployed": True,
        "rolled_out": True,
    }]


def references():
    return [{
        "reference_id": "ref-site-1",
        "source": "prime:reference:1",
        "site_available_within_7_days": True,
        "region": "SOUTHEAST",
    }]


def direct_ready():
    prime = {"nvidia_partner": nvidia_partner(), "ai_infrastructure_engagements": track_record(), "references": references()}
    prime.update(operational())
    return {
        "schema": q.EVIDENCE_SCHEMA,
        "source_packet": copy.deepcopy(PACKET),
        "current_time": "2026-09-14T21:00:00-04:00",
        "bid_model": "direct_prime",
        "buyer_artifacts": artifacts(True),
        "direct_prime": prime,
    }


def team_ready():
    prime = {"nvidia_partner": nvidia_partner(committed=True), "ai_infrastructure_engagements": track_record(), "references": references()}
    prime.update(operational())
    return {
        "schema": q.EVIDENCE_SCHEMA,
        "source_packet": copy.deepcopy(PACKET),
        "current_time": "2026-09-14T21:00:00-04:00",
        "bid_model": "nvidia_prime_subcontract",
        "buyer_artifacts": artifacts(True),
        "nvidia_prime": prime,
        "tjlabs_support": {
            "commitment_current": True,
            "commitment_evidence_id": "partner:tjlabs-commitment",
            "workshare_evidence_id": "repo:workshare",
            "capabilities": ["AI_TRAINING_PLAYBOOKS", "NIM_LLM_ENABLEMENT", "ACCEPTANCE_TESTING"],
        },
    }


class QualificationTests(unittest.TestCase):
    def test_current_evidence_is_hold(self):
        evidence = q.load_json_strict(HERE / "current_evidence.json")
        result = q.evaluate(SPEC, evidence)
        self.assertEqual(result["state"], "HOLD")
        self.assertEqual(set(result["missing_buyer_artifacts"]), set(q.MISSING_ARTIFACTS))
        self.assertTrue(all(v is False for v in result["authority"].values()))

    def test_direct_prime_ready_fixture(self):
        result = q.evaluate(SPEC, direct_ready())
        self.assertEqual(result["state"], "PRIME_READY")
        self.assertEqual(result["blockers"], [])
        self.assertTrue(all(v is False for v in result["authority"].values()))

    def test_team_ready_fixture(self):
        result = q.evaluate(SPEC, team_ready())
        self.assertEqual(result["state"], "TEAMING_READY")
        self.assertEqual(result["blockers"], [])

    def test_each_missing_buyer_artifact_blocks(self):
        for artifact_id in q.MISSING_ARTIFACTS:
            with self.subTest(artifact_id=artifact_id):
                e = direct_ready()
                e["buyer_artifacts"][artifact_id] = {"state": "MISSING_BUYER_ARTIFACT"}
                result = q.evaluate(SPEC, e)
                self.assertEqual(result["state"], "HOLD")
                self.assertIn(f"buyer_artifact:{artifact_id}", result["blockers"])

    def test_missing_artifact_cannot_carry_fake_proof(self):
        e = direct_ready()
        e["buyer_artifacts"][q.MISSING_ARTIFACTS[0]] = {"state": "MISSING_BUYER_ARTIFACT", "sha256": DIGEST_A}
        with self.assertRaises(q.EvidenceError):
            q.evaluate(SPEC, e)

    def test_wrong_packet_digest_rejected(self):
        e = direct_ready(); e["source_packet"]["sha256"] = DIGEST_A
        with self.assertRaisesRegex(q.EvidenceError, "source packet mismatch"):
            q.evaluate(SPEC, e)

    def test_wrong_page_count_rejected(self):
        e = direct_ready(); e["source_packet"]["page_count"] = 40
        with self.assertRaisesRegex(q.EvidenceError, "page_count"):
            q.evaluate(SPEC, e)

    def test_bool_is_not_page_count_integer(self):
        e = direct_ready(); e["source_packet"]["page_count"] = True
        with self.assertRaisesRegex(q.EvidenceError, "bool"):
            q.evaluate(SPEC, e)

    def test_unrecognized_top_level_key_rejected(self):
        e = direct_ready(); e["magic_pass"] = True
        with self.assertRaisesRegex(q.EvidenceError, "unknown keys"):
            q.evaluate(SPEC, e)

    def test_unrecognized_prime_key_rejected(self):
        e = direct_ready()
        e["direct_prime"]["silent_credential_inheritance"] = True
        with self.assertRaisesRegex(q.EvidenceError, "unknown keys"):
            q.evaluate(SPEC, e)

    def test_inactive_nvidia_partner_blocks(self):
        e = direct_ready(); e["direct_prime"]["nvidia_partner"]["status"] = "INACTIVE"
        r = q.evaluate(SPEC, e)
        self.assertEqual(r["state"], "HOLD")
        self.assertIn("direct_prime.nvidia_partner.active_nvidia_partner", r["blockers"])

    def test_expired_nvidia_authorization_blocks(self):
        e = direct_ready(); e["direct_prime"]["nvidia_partner"]["expires_date"] = "2026-09-01"
        r = q.evaluate(SPEC, e)
        self.assertEqual(r["state"], "HOLD")
        self.assertIn("direct_prime.nvidia_partner.nvidia_authorization_current", r["blockers"])

    def test_nvidia_scope_must_cover_spark_and_lab_design(self):
        e = direct_ready(); e["direct_prime"]["nvidia_partner"]["scope"] = ["DGX SPARK"]
        r = q.evaluate(SPEC, e)
        self.assertIn("direct_prime.nvidia_partner.nvidia_scope_dgx_spark_lab_design", r["blockers"])

    def test_track_record_requires_architect_deploy_rollout_same_row(self):
        e = direct_ready(); e["direct_prime"]["ai_infrastructure_engagements"][0]["rolled_out"] = False
        r = q.evaluate(SPEC, e)
        self.assertIn("direct_prime.ai_infrastructure_engagements.architect_deploy_rollout_track_record", r["blockers"])

    def test_duplicate_track_record_identity_rejected(self):
        e = direct_ready(); e["direct_prime"]["ai_infrastructure_engagements"] *= 2
        with self.assertRaisesRegex(q.EvidenceError, "duplicate AI-infrastructure"):
            q.evaluate(SPEC, e)

    def test_reference_site_must_be_available_on_buyer_timing(self):
        e = direct_ready(); e["direct_prime"]["references"][0]["site_available_within_7_days"] = False
        r = q.evaluate(SPEC, e)
        self.assertIn("reference_site_available_within_7_days", " ".join(r["blockers"]))

    def test_does_not_invent_reference_count_from_missing_section_ix(self):
        e = direct_ready()
        self.assertEqual(len(e["direct_prime"]["references"]), 1)
        self.assertEqual(q.evaluate(SPEC, e)["state"], "PRIME_READY")

    def test_insurance_must_extend_through_due_date(self):
        e = direct_ready(); e["direct_prime"]["insurance_expires_date"] = "2026-09-20"
        r = q.evaluate(SPEC, e)
        self.assertIn("direct_prime.insurance_current_through_due_date", r["blockers"])

    def test_false_operational_gate_blocks_even_with_evidence_string(self):
        e = direct_ready(); e["direct_prime"]["pricing_approved"] = False
        r = q.evaluate(SPEC, e)
        self.assertIn("pricing_approved", r["blockers"])

    def test_true_operational_gate_requires_evidence_id(self):
        e = direct_ready(); del e["direct_prime"]["pricing_approval_evidence_id"]
        with self.assertRaises(q.EvidenceError):
            q.evaluate(SPEC, e)

    def test_team_requires_current_commitment(self):
        e = team_ready(); e["nvidia_prime"]["nvidia_partner"]["commitment_current"] = False
        r = q.evaluate(SPEC, e)
        self.assertEqual(r["state"], "HOLD")
        self.assertIn("nvidia_prime.nvidia_partner.commitment_current", r["blockers"])

    def test_team_rejects_revoked_commitment(self):
        e = team_ready(); e["nvidia_prime"]["nvidia_partner"]["commitment_revoked"] = True
        r = q.evaluate(SPEC, e)
        self.assertIn("nvidia_prime.nvidia_partner.commitment_not_revoked", r["blockers"])

    def test_tjlabs_cannot_inherit_nvidia_status(self):
        e = team_ready(); e["tjlabs_support"]["capabilities"].append("NVIDIA_PARTNER_STATUS")
        with self.assertRaisesRegex(q.EvidenceError, "inherit"):
            q.evaluate(SPEC, e)

    def test_tjlabs_cannot_inherit_oem_resale(self):
        e = team_ready(); e["tjlabs_support"]["capabilities"] = ["OEM_RESALE_AUTHORITY"]
        with self.assertRaisesRegex(q.EvidenceError, "inherit"):
            q.evaluate(SPEC, e)

    def test_deadline_passed_is_no_bid(self):
        e = direct_ready(); e["current_time"] = "2026-09-21T14:00:01-05:00"
        r = q.evaluate(SPEC, e)
        self.assertEqual(r["state"], "NO_BID")
        self.assertEqual(r["reason"], "deadline_passed")

    def test_exact_deadline_is_not_automatically_no_bid(self):
        e = direct_ready(); e["current_time"] = "2026-09-21T14:00:00-05:00"
        self.assertEqual(q.evaluate(SPEC, e)["state"], "PRIME_READY")

    def test_source_bound_explicit_disqualifier_is_no_bid(self):
        e = direct_ready(); e["explicit_disqualifier"] = {"fact": "buyer cancelled solicitation", "source": "buyer:addendum:cancel"}
        r = q.evaluate(SPEC, e)
        self.assertEqual(r["state"], "NO_BID")
        self.assertEqual(r["facts"]["disqualifying_source"], "buyer:addendum:cancel")

    def test_unsupported_bid_model_rejected(self):
        e = direct_ready(); e["bid_model"] = "wishful_thinking"
        with self.assertRaisesRegex(q.EvidenceError, "unsupported bid_model"):
            q.evaluate(SPEC, e)

    def test_naive_time_rejected(self):
        e = direct_ready(); e["current_time"] = "2026-09-14T21:00:00"
        with self.assertRaisesRegex(q.EvidenceError, "UTC offset"):
            q.evaluate(SPEC, e)

    def test_noncanonical_date_rejected(self):
        e = direct_ready(); e["direct_prime"]["insurance_expires_date"] = "2026-9-30"
        with self.assertRaises(q.EvidenceError):
            q.evaluate(SPEC, e)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaisesRegex(q.EvidenceError, "duplicate JSON key"):
                q.load_json_strict(p)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text('{"x":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(q.EvidenceError, "non-finite"):
                q.load_json_strict(p)

    def test_receipt_is_order_invariant(self):
        a = q.evaluate(SPEC, direct_ready())
        b = {k: a[k] for k in reversed(list(a.keys()))}
        self.assertEqual(q.canonical_digest(a), q.canonical_digest(b))

    def test_result_authority_is_always_false(self):
        for evidence in (direct_ready(), team_ready()):
            result = q.evaluate(SPEC, evidence)
            self.assertTrue(result["authority"])
            self.assertTrue(all(v is False for v in result["authority"].values()))


if __name__ == "__main__":
    unittest.main()
