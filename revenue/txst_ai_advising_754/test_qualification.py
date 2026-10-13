import hashlib
import json
import unittest
from datetime import datetime, timezone

from revenue.txst_ai_advising_754 import qualification as q

def b(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

def candidate(**owner_overrides):
    owner = {gate: "UNKNOWN" for gate in q.OWNER_GATES}
    owner.update(owner_overrides)
    return {
        "opportunity_id": q.SOLICITATION_ID,
        "requested_posture": "AUTO",
        "owner_claims": owner,
        "partner_claims": {"status": "NONE", "cures": []},
        "commercial": {
            "pricing_status": "OWNER_DECISION_REQUIRED",
            "staffing_status": "OWNER_DECISION_REQUIRED",
        },
    }

def official():
    doc_sha = "1" * 64
    return {
        "schema": "txst-ai-advising-official-authority/v1",
        "solicitation_id": q.SOLICITATION_ID,
        "title": q.SOLICITATION_TITLE,
        "packet_generation": "event-1443681-v1",
        "packet_complete": True,
        "captured_at_utc": "2026-09-16T22:00:00Z",
        "deadline_utc": "2026-09-28T22:00:00Z",
        "source_url": "https://bids.sciquest.com/example",
        "documents": [
            {
                "document_id": "RFP",
                "sha256": doc_sha,
                "source_url": "https://bids.sciquest.com/example/rfp",
            }
        ],
        "requirements": [
            {
                "requirement_id": "R1",
                "category": "qualification",
                "mandatory": True,
                "source_document_id": "RFP",
                "source_sha256": doc_sha,
            }
        ],
    }

def evidence(schema, gates):
    return {
        "schema": schema,
        "opportunity_id": q.SOLICITATION_ID,
        "generation": "g1",
        "records": [
            {
                "record_id": f"r-{gate}",
                "gate": gate,
                "evidence_sha256": hashlib.sha256(gate.encode()).hexdigest(),
                "status": "PROVEN",
            }
            for gate in gates
        ],
    }

class QualificationTests(unittest.TestCase):
    def test_current_public_carrier_holds_without_official_root(self):
        report = q.compile_current(b(candidate()))
        self.assertEqual(report["state"], "HOLD_OFFICIAL_PACKET_REQUIRED")
        self.assertFalse(report["official_packet_retained"])
        self.assertTrue(all(v is False for v in report["authority"].values()))

    def test_candidate_claims_do_not_mint_readiness(self):
        c = candidate(**{gate: "CLAIMED_SUPPORTED" for gate in q.OWNER_GATES})
        c["partner_claims"] = {"status": "CLAIMED_COMMITTED", "cures": list(q.OWNER_GATES)}
        report = q.compile_current(b(c))
        self.assertEqual(report["state"], "HOLD_OFFICIAL_PACKET_REQUIRED")
        self.assertEqual(report["owner_evidence_proven_gates"], [])
        self.assertTrue(any("ignored" in w for w in report["warnings"]))

    def test_private_historical_path_can_prove_prime_with_independent_roots(self):
        c_raw = b(candidate())
        o_raw = b(official())
        e_raw = b(evidence("txst-ai-advising-owner-evidence/v1", q.OWNER_GATES))
        report = q._compile_at(
            c_raw, o_raw, e_raw, None,
            now=datetime(2026, 9, 16, 22, 0, tzinfo=timezone.utc),
            trusted_official_sha=q.sha256(o_raw),
            trusted_owner_sha=q.sha256(e_raw),
            trusted_partner_sha=None,
            historical=True,
        )
        self.assertEqual(report["state"], "READY_FOR_OWNER_PRIME_REVIEW")
        self.assertEqual(report["evaluation_class"], "HISTORICAL_INTEGRITY_ONLY")
        self.assertFalse(report["authority"]["proposal_submission_authorized"])

    def test_teaming_can_cure_only_with_retained_partner_evidence(self):
        c = candidate()
        o_raw = b(official())
        owner_gates = q.OWNER_GATES[:4]
        partner_gates = q.OWNER_GATES[4:]
        owner_raw = b(evidence("txst-ai-advising-owner-evidence/v1", owner_gates))
        partner_raw = b(evidence("txst-ai-advising-partner-evidence/v1", partner_gates))
        report = q._compile_at(
            b(c), o_raw, owner_raw, partner_raw,
            now=datetime(2026, 9, 16, 22, 0, tzinfo=timezone.utc),
            trusted_official_sha=q.sha256(o_raw),
            trusted_owner_sha=q.sha256(owner_raw),
            trusted_partner_sha=q.sha256(partner_raw),
            historical=True,
        )
        self.assertEqual(report["route_states"]["TEAMING"], "READY_FOR_OWNER_TEAMING_REVIEW")
        self.assertNotEqual(report["route_states"]["PRIME"], "READY_FOR_OWNER_PRIME_REVIEW")

    def test_requirement_digest_mismatch_rejected(self):
        o = official()
        o["requirements"][0]["source_sha256"] = "2" * 64
        o_raw = b(o)
        with self.assertRaises(q.ContractError):
            q._compile_at(
                b(candidate()), o_raw, None, None,
                now=datetime(2026, 9, 16, 22, 0, tzinfo=timezone.utc),
                trusted_official_sha=q.sha256(o_raw),
                trusted_owner_sha=None,
                trusted_partner_sha=None,
                historical=True,
            )

    def test_nonofficial_packet_host_rejected(self):
        o = official()
        o["source_url"] = "https://evil.example/rfp"
        o_raw = b(o)
        with self.assertRaises(q.ContractError):
            q._compile_at(
                b(candidate()), o_raw, None, None,
                now=datetime(2026, 9, 16, 22, 0, tzinfo=timezone.utc),
                trusted_official_sha=q.sha256(o_raw),
                trusted_owner_sha=None,
                trusted_partner_sha=None,
                historical=True,
            )

    def test_arbitrary_matching_metadata_without_retained_root_does_not_count(self):
        o_raw = b(official())
        report = q._compile_at(
            b(candidate()), o_raw, None, None,
            now=datetime(2026, 9, 16, 22, 0, tzinfo=timezone.utc),
            trusted_official_sha=None,
            trusted_owner_sha=None,
            trusted_partner_sha=None,
            historical=True,
        )
        self.assertEqual(report["state"], "HOLD_OFFICIAL_PACKET_REQUIRED")

    def test_duplicate_key_json_rejected(self):
        raw = b'{"opportunity_id":"x","opportunity_id":"y"}'
        with self.assertRaises(q.ContractError):
            q.strict_loads(raw)

    def test_bool_int_and_unknown_key_shapes_rejected(self):
        c = candidate()
        c["extra"] = True
        with self.assertRaises(q.ContractError):
            q.compile_current(b(c))

    def test_invalid_owner_claim_state_is_rejected_by_requirement_name(self):
        c = candidate()
        first = q.OWNER_GATES[0]
        c["owner_claims"][first] = "YES"
        with self.assertRaises(q.ContractError) as ctx:
            q.compile_current(b(c))
        message = str(ctx.exception)
        self.assertIn("invalid owner claim state", message)
        self.assertIn(first, message)


    def test_unverified_discovery_deadline_never_closes_current_carrier(self):
        report = q._compile_at(
            b(candidate()), None, None, None,
            now=datetime(2026, 9, 29, 1, 0, tzinfo=timezone.utc),
            trusted_official_sha=None,
            trusted_owner_sha=None,
            trusted_partner_sha=None,
            historical=True,
        )
        self.assertEqual(report["state"], "HOLD_OFFICIAL_PACKET_REQUIRED")
        self.assertIsNone(report["solicitation"]["official_deadline_utc"])

    def test_deadline_closes_routes_even_with_complete_evidence(self):
        o_raw = b(official())
        e_raw = b(evidence("txst-ai-advising-owner-evidence/v1", q.OWNER_GATES))
        report = q._compile_at(
            b(candidate()), o_raw, e_raw, None,
            now=datetime(2026, 9, 29, 1, 0, tzinfo=timezone.utc),
            trusted_official_sha=q.sha256(o_raw),
            trusted_owner_sha=q.sha256(e_raw),
            trusted_partner_sha=None,
            historical=True,
        )
        self.assertEqual(report["state"], "NO_RESPONSE_DEADLINE_PASSED")
        self.assertEqual(report["route_states"]["PRIME"], "CLOSED")

    def test_receipt_tamper_detected(self):
        report = q.compile_current(b(candidate()))
        tampered = dict(report)
        tampered["state"] = "READY_FOR_OWNER_PRIME_REVIEW"
        with self.assertRaises(q.ContractError):
            q.verify_report(b(candidate()), b(tampered))

    def test_duplicate_evidence_gate_rejected(self):
        o_raw = b(official())
        e = evidence("txst-ai-advising-owner-evidence/v1", [q.OWNER_GATES[0]])
        duplicate = dict(e["records"][0])
        duplicate["record_id"] = "r-duplicate"
        e["records"].append(duplicate)
        e_raw = b(e)
        with self.assertRaises(q.ContractError):
            q._compile_at(
                b(candidate()), o_raw, e_raw, None,
                now=datetime(2026, 9, 16, 22, 0, tzinfo=timezone.utc),
                trusted_official_sha=q.sha256(o_raw),
                trusted_owner_sha=q.sha256(e_raw),
                trusted_partner_sha=None,
                historical=True,
            )

    def test_re_receipted_semantic_tamper_does_not_match_current(self):
        report = q.compile_current(b(candidate()))
        tampered = dict(report)
        tampered["warnings"] = ["invented warning"]
        unsigned = dict(tampered)
        unsigned.pop("receipt_sha256", None)
        tampered["receipt_sha256"] = q.sha256(q.canonical_bytes(unsigned))
        verdict = q.verify_report(b(candidate()), b(tampered))
        self.assertTrue(verdict["integrity_valid"])
        self.assertFalse(verdict["current_semantics_match"])

    def test_verify_current_unchanged_hold(self):
        report = q.compile_current(b(candidate()))
        verdict = q.verify_report(b(candidate()), b(report))
        self.assertTrue(verdict["integrity_valid"])
        self.assertTrue(verdict["current_semantics_match"])
        self.assertEqual(verdict["current_state"], "HOLD_OFFICIAL_PACKET_REQUIRED")

if __name__ == "__main__":
    unittest.main()
