from __future__ import annotations

import json
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import gate

NOW = datetime(2026, 9, 13, 9, 55, tzinfo=timezone.utc)


def z(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def d(label: str) -> str:
    return gate.sha256_json({"label": label})


def packet() -> dict:
    return gate.make_packet(
        workflow_id="wf-1",
        request_id="req-1",
        principal_id="principal-1",
        resource_scope="tenant-a/system-b",
        operation="UPDATE",
        target="record/7",
        payload_digest=d("payload"),
        policy_version="v1",
        policy_digest=d("policy"),
        snapshot_digest=d("snapshot"),
        captured_at=z(NOW - timedelta(minutes=3)),
        max_age_seconds=900,
        approver_id="approver-1",
        role="change-approver",
        approved_at=z(NOW - timedelta(minutes=2)),
        expires_at=z(NOW + timedelta(hours=1)),
    )


def success(p: dict, *, suffix: str = "1") -> dict:
    return {
        "attempt_id": f"attempt-{suffix}",
        "idempotency_key": gate.expected_idempotency_key(p),
        "dispatched_at": z(NOW - timedelta(minutes=1)),
        "transport_result": "SUCCESS",
        "provider_effect_id": f"effect-{suffix}",
        "provider_state_digest": d(f"state-{suffix}"),
        "reconciled_at": None,
        "reconciliation": "NONE",
    }


class GateTests(unittest.TestCase):
    def compile(self, p: dict) -> dict:
        return gate.compile_trace(p, trusted_now=z(NOW))

    def test_preflight_ready(self):
        self.assertEqual(self.compile(packet())["status"], "PREFLIGHT_EVIDENCE_READY")

    def test_successful_execution(self):
        p = packet(); p["attempts"] = [success(p)]
        receipt = self.compile(p)
        self.assertEqual(receipt["status"], "EXECUTION_EVIDENCE_VALID")
        self.assertTrue(receipt["facts"]["provider_effect_confirmed"])
        self.assertFalse(receipt["external_action_authorized"])
        self.assertTrue(gate.verify_receipt(p, trusted_now=z(NOW), receipt=receipt))

    def test_receipt_tamper_rejected(self):
        p = packet(); p["attempts"] = [success(p)]
        receipt = self.compile(p); receipt["status"] = "HOLD"
        self.assertFalse(gate.verify_receipt(p, trusted_now=z(NOW), receipt=receipt))

    def test_stale_snapshot_holds(self):
        p = packet(); p["snapshot"]["captured_at"] = z(NOW - timedelta(hours=2))
        self.assertIn("SNAPSHOT_STALE", self.compile(p)["holds"])

    def test_future_snapshot_holds(self):
        p = packet(); p["snapshot"]["captured_at"] = z(NOW + timedelta(seconds=1))
        self.assertIn("SNAPSHOT_FROM_FUTURE", self.compile(p)["holds"])

    def test_approval_binding_mismatch(self):
        p = packet(); p["approval"]["action_digest"] = d("wrong")
        self.assertIn("APPROVAL_ACTION_BINDING_MISMATCH", self.compile(p)["holds"])

    def test_expired_approval(self):
        p = packet(); p["approval"]["expires_at"] = z(NOW - timedelta(seconds=1))
        self.assertIn("APPROVAL_EXPIRED", self.compile(p)["holds"])

    def test_approval_predates_snapshot(self):
        p = packet(); p["approval"]["approved_at"] = z(NOW - timedelta(minutes=4))
        self.assertIn("APPROVAL_PREDATES_SNAPSHOT", self.compile(p)["holds"])

    def test_unknown_outcome_requires_reconciliation(self):
        p = packet(); a = success(p); a.update({"transport_result": "UNKNOWN", "provider_effect_id": None, "provider_state_digest": None, "reconciliation": "NONE", "reconciled_at": None}); p["attempts"] = [a]
        self.assertIn("ATTEMPT_0_UNKNOWN_NOT_RECONCILED", self.compile(p)["holds"])

    def test_unknown_reconciled_success_valid(self):
        p = packet(); a = success(p); a.update({"transport_result": "UNKNOWN", "reconciliation": "SUCCEEDED", "reconciled_at": z(NOW - timedelta(seconds=30))}); p["attempts"] = [a]
        self.assertEqual(self.compile(p)["status"], "EXECUTION_EVIDENCE_VALID")

    def test_unknown_reconciled_not_found_then_retry_success(self):
        p = packet(); a = success(p, suffix="a"); a.update({"transport_result": "UNKNOWN", "provider_effect_id": None, "provider_state_digest": None, "reconciliation": "NOT_FOUND", "reconciled_at": z(NOW - timedelta(seconds=45))}); b = success(p, suffix="b"); b["dispatched_at"] = z(NOW - timedelta(seconds=20)); p["attempts"] = [a, b]
        self.assertEqual(self.compile(p)["status"], "EXECUTION_EVIDENCE_VALID")

    def test_ambiguous_reconciliation_blocks_retry(self):
        p = packet(); a = success(p, suffix="a"); a.update({"transport_result": "UNKNOWN", "provider_effect_id": None, "provider_state_digest": None, "reconciliation": "AMBIGUOUS", "reconciled_at": z(NOW - timedelta(seconds=45))}); b = success(p, suffix="b"); b["dispatched_at"] = z(NOW - timedelta(seconds=20)); p["attempts"] = [a, b]
        holds = self.compile(p)["holds"]
        self.assertIn("ATTEMPT_0_RECONCILIATION_AMBIGUOUS", holds)
        self.assertIn("ATTEMPT_1_DISPATCH_AFTER_UNRESOLVED_UNKNOWN", holds)

    def test_retry_after_success_holds(self):
        p = packet(); a = success(p, suffix="a"); b = success(p, suffix="b"); b["dispatched_at"] = z(NOW - timedelta(seconds=20)); p["attempts"] = [a, b]
        holds = self.compile(p)["holds"]
        self.assertIn("ATTEMPT_1_DISPATCH_AFTER_EFFECT_CONFIRMED", holds)
        self.assertIn("MULTIPLE_PROVIDER_EFFECTS", holds)

    def test_wrong_idempotency_key_holds(self):
        p = packet(); a = success(p); a["idempotency_key"] = d("wrong-idem"); p["attempts"] = [a]
        self.assertIn("ATTEMPT_0_IDEMPOTENCY_KEY_MISMATCH", self.compile(p)["holds"])

    def test_duplicate_attempt_id_holds(self):
        p = packet(); a = success(p, suffix="same"); b = deepcopy(a); b["transport_result"] = "FAILURE"; b["provider_effect_id"] = None; b["provider_state_digest"] = None; b["dispatched_at"] = z(NOW - timedelta(seconds=30)); p["attempts"] = [a, b]
        self.assertIn("ATTEMPT_1_DUPLICATE_ATTEMPT_ID", self.compile(p)["holds"])

    def test_failure_cannot_claim_effect(self):
        p = packet(); a = success(p); a["transport_result"] = "FAILURE"; p["attempts"] = [a]
        self.assertIn("ATTEMPT_0_FAILURE_HAS_EFFECT_EVIDENCE", self.compile(p)["holds"])

    def test_success_requires_effect_evidence(self):
        p = packet(); a = success(p); a["provider_effect_id"] = None; a["provider_state_digest"] = None; p["attempts"] = [a]
        self.assertIn("ATTEMPT_0_SUCCESS_MISSING_PROVIDER_EVIDENCE", self.compile(p)["holds"])

    def test_timezone_less_instant_rejected(self):
        p = packet(); p["snapshot"]["captured_at"] = "2026-09-13T09:52:00"
        with self.assertRaises(gate.GateError): self.compile(p)

    def test_integer_equivalent_float_rejected(self):
        p = packet(); p["snapshot"]["max_age_seconds"] = 900.0
        with self.assertRaises(gate.GateError): self.compile(p)

    def test_plain_dict_required(self):
        class Sneaky(dict):
            pass
        p = packet(); p["action"] = Sneaky(p["action"])
        with self.assertRaises(gate.GateError): self.compile(p)

    def test_unknown_fields_rejected(self):
        p = packet(); p["surprise"] = True
        with self.assertRaises(gate.GateError): self.compile(p)

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(gate.GateError): gate.load_json_strict('{"x": NaN}')

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(gate.GateError): gate.load_json_strict('{"x":1,"x":2}')

    def test_action_digest_changes_with_scope(self):
        a = packet(); b = packet(); b["resource_scope"] = "tenant-other/system-b"
        self.assertNotEqual(gate.expected_action_digest(a), gate.expected_action_digest(b))

    def test_idempotency_changes_with_request(self):
        a = packet(); b = packet(); b["request_id"] = "req-2"; b["approval"]["action_digest"] = gate.expected_action_digest(b)
        self.assertNotEqual(gate.expected_idempotency_key(a), gate.expected_idempotency_key(b))

    def test_receipt_deterministic(self):
        p = packet(); p["attempts"] = [success(p)]
        first = json.dumps(self.compile(p), sort_keys=True, separators=(",", ":"))
        second = json.dumps(self.compile(deepcopy(p)), sort_keys=True, separators=(",", ":"))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
