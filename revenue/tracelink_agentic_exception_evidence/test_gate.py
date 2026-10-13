from __future__ import annotations

import copy
import unittest

from revenue.tracelink_agentic_exception_evidence.acceptance import AS_OF, VERIFY_AT, _approval_digest, _partner_digest, base_packet, run_acceptance
from revenue.tracelink_agentic_exception_evidence.gate import EvidenceError, canonical_json, evaluate, normalize_packet, sha256, verify_decision


class GateTests(unittest.TestCase):
    def code(self, expected, fn):
        with self.assertRaises(EvidenceError) as ctx:
            fn()
        self.assertEqual(ctx.exception.code, expected)

    def test_acceptance_contract_140(self):
        result = run_acceptance()
        self.assertEqual((result["review_ready_count"], result["hold_count"]), (112, 28))
        self.assertEqual(set(result["reason_counts"].values()), {4})

    def test_ready_packet(self):
        decision = evaluate(base_packet(1))
        self.assertEqual(decision["status"], "REVIEW_READY")
        self.assertEqual(decision["hold_reasons"], [])
        self.assertTrue(all(value is False for value in decision["authority"].values()))

    def test_untrusted_partner(self):
        p = base_packet(2); p["partner"]["authenticated"] = False
        p["partner"]["identity_digest"] = _partner_digest(p["partner"]["partner_id"], False, p["partner"]["trust_state"])
        self.assertEqual(evaluate(p)["hold_reasons"], ["UNTRUSTED_PARTNER"])

    def test_stale_snapshot(self):
        p = base_packet(3); p["snapshot"]["captured_at"] = "2026-09-13T10:00:00Z"
        p["snapshot"]["snapshot_digest"] = sha256({"object_version": p["snapshot"]["object_version"], "data_snapshot_version": p["snapshot"]["data_snapshot_version"], "captured_at": p["snapshot"]["captured_at"]})
        self.assertEqual(evaluate(p)["hold_reasons"], ["STALE_SNAPSHOT"])

    def test_po_asn_mismatch(self):
        p = base_packet(4); p["recommendation"]["origin_po_id"] = "PO-WRONG"
        self.assertEqual(evaluate(p)["hold_reasons"], ["PO_ASN_MISMATCH"])

    def test_missing_agent_profile(self):
        p = base_packet(5); p["agent"]["agent_profile_version"] = ""
        self.assertEqual(evaluate(p)["hold_reasons"], ["MISSING_AGENT_PROFILE_VERSION"])

    def test_permission_out_of_scope(self):
        p = base_packet(6); p["permission"]["granted_permissions"] = ["exception.review"]
        self.assertEqual(evaluate(p)["hold_reasons"], ["PERMISSION_OUT_OF_SCOPE"])

    def test_missing_approval(self):
        p = base_packet(7); p["approval"]["approved"] = False; p["approval"]["approver_id"] = ""
        p["approval"]["approval_digest"] = _approval_digest(False, "", p["approval"]["approved_action_hash"])
        self.assertEqual(evaluate(p)["hold_reasons"], ["MISSING_HUMAN_APPROVAL"])

    def test_final_action_hash_mismatch(self):
        p = base_packet(8); p["final_action"]["action_hash"] = "9" * 64
        self.assertEqual(evaluate(p)["hold_reasons"], ["FINAL_ACTION_HASH_MISMATCH"])

    def test_final_action_recommendation_binding(self):
        p = base_packet(9); p["final_action"]["recommendation_hash"] = "9" * 64
        self.assertEqual(evaluate(p)["hold_reasons"], ["FINAL_ACTION_HASH_MISMATCH"])

    def test_approval_binds_final_action(self):
        p = base_packet(10); p["approval"]["approved_action_hash"] = "9" * 64
        p["approval"]["approval_digest"] = _approval_digest(True, p["approval"]["approver_id"], p["approval"]["approved_action_hash"])
        self.assertEqual(evaluate(p)["hold_reasons"], ["FINAL_ACTION_HASH_MISMATCH"])

    def test_multiple_reasons_have_fixed_order(self):
        p = base_packet(11)
        p["partner"]["authenticated"] = False
        p["partner"]["identity_digest"] = _partner_digest(p["partner"]["partner_id"], False, p["partner"]["trust_state"])
        p["agent"]["agent_profile_version"] = ""
        p["permission"]["granted_permissions"] = ["exception.review"]
        self.assertEqual(evaluate(p)["hold_reasons"], ["UNTRUSTED_PARTNER", "MISSING_AGENT_PROFILE_VERSION", "PERMISSION_OUT_OF_SCOPE"])

    def test_list_order_canonicalized(self):
        p = base_packet(12); q = copy.deepcopy(p)
        q["origin"]["epcis_event_ids"].reverse(); q["permission"]["granted_permissions"].reverse(); q["basis"].reverse()
        self.assertEqual(evaluate(p), evaluate(q))

    def test_input_not_mutated(self):
        p = base_packet(13); before = copy.deepcopy(p)
        evaluate(p)
        self.assertEqual(p, before)

    def test_unknown_packet_field_rejected(self):
        p = base_packet(14); p["note"] = "nope"
        self.code("PACKET_FIELDS", lambda: evaluate(p))

    def test_bad_snapshot_digest_rejected(self):
        p = base_packet(15); p["snapshot"]["snapshot_digest"] = "9" * 64
        self.code("SNAPSHOT_DIGEST_MISMATCH", lambda: evaluate(p))

    def test_bad_recommendation_digest_rejected(self):
        p = base_packet(16); p["recommendation"]["action_hash"] = "9" * 64
        self.code("RECOMMENDATION_HASH_MISMATCH", lambda: evaluate(p))

    def test_duplicate_basis_source_rejected(self):
        p = base_packet(17); p["basis"].append(copy.deepcopy(p["basis"][0]))
        self.code("DUPLICATE_BASIS_SOURCE", lambda: evaluate(p))

    def test_duplicate_permission_rejected(self):
        p = base_packet(18); p["permission"]["granted_permissions"].append("exception.approve")
        self.code("DUPLICATE_PERMISSION", lambda: evaluate(p))

    def test_future_snapshot_rejected(self):
        p = base_packet(19); p["snapshot"]["captured_at"] = "2026-09-13T12:00:01Z"
        p["snapshot"]["snapshot_digest"] = sha256({"object_version": p["snapshot"]["object_version"], "data_snapshot_version": p["snapshot"]["data_snapshot_version"], "captured_at": p["snapshot"]["captured_at"]})
        self.code("EVIDENCE_AFTER_AS_OF", lambda: evaluate(p))

    def test_noncanonical_timestamp_rejected(self):
        p = base_packet(20); p["as_of"] = "2026-09-13T12:00:00+00:00"
        self.code("NONCANONICAL_TIMESTAMP", lambda: evaluate(p))

    def test_strict_boolean(self):
        p = base_packet(21); p["partner"]["authenticated"] = 1
        self.code("BOOLEAN_REQUIRED", lambda: evaluate(p))

    def test_snapshot_policy_override_rejected(self):
        p = base_packet(29); p["snapshot_policy"]["max_age_minutes"] = 1440
        self.code("SNAPSHOT_POLICY_MISMATCH", lambda: evaluate(p))

    def test_partner_digest_tamper_rejected(self):
        p = base_packet(30); p["partner"]["identity_digest"] = "9" * 64
        self.code("PARTNER_IDENTITY_DIGEST_MISMATCH", lambda: evaluate(p))

    def test_approval_digest_tamper_rejected(self):
        p = base_packet(31); p["approval"]["approval_digest"] = "9" * 64
        self.code("APPROVAL_DIGEST_MISMATCH", lambda: evaluate(p))

    def test_verifier_success(self):
        p = base_packet(22); d = evaluate(p)
        result = verify_decision(p, d, verify_at=VERIFY_AT)
        self.assertTrue(result["valid"] and result["fresh"])
        self.assertEqual(result["age_minutes"], 30)

    def test_verifier_rejects_decision_tamper(self):
        p = base_packet(23); d = evaluate(p); d["status"] = "HOLD"
        self.code("DECISION_MISMATCH", lambda: verify_decision(p, d, verify_at=VERIFY_AT))

    def test_verifier_rejects_source_tamper(self):
        p = base_packet(24); d = evaluate(p); p["partner"]["authenticated"] = False
        p["partner"]["identity_digest"] = _partner_digest(p["partner"]["partner_id"], False, p["partner"]["trust_state"])
        self.code("DECISION_MISMATCH", lambda: verify_decision(p, d, verify_at=VERIFY_AT))

    def test_verifier_rejects_stale_decision(self):
        p = base_packet(25); d = evaluate(p)
        self.code("DECISION_STALE", lambda: verify_decision(p, d, verify_at="2026-09-15T12:00:01Z", max_decision_age_minutes=1440))

    def test_verifier_rejects_time_travel(self):
        p = base_packet(26); d = evaluate(p)
        self.code("VERIFY_BEFORE_AS_OF", lambda: verify_decision(p, d, verify_at="2026-09-13T11:59:59Z"))

    def test_receipt_deterministic(self):
        p = base_packet(27)
        self.assertEqual(canonical_json(evaluate(p)), canonical_json(evaluate(copy.deepcopy(p))))

    def test_normalized_packet_has_canonical_sorted_sets(self):
        p = base_packet(28); p["permission"]["granted_permissions"].reverse(); p["basis"].reverse()
        normalized = normalize_packet(p)
        self.assertEqual(normalized["permission"]["granted_permissions"], ["exception.approve", "exception.review"])
        self.assertEqual(normalized["basis"][0]["source_id"], "po-asn-ledger")
        self.assertEqual(normalized["as_of"], AS_OF)


if __name__ == "__main__":
    unittest.main()
