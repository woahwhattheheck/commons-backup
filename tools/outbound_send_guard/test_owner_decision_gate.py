from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from tools.outbound_send_guard import owner_decision_gate as gate
except ModuleNotFoundError:  # direct-file development fallback
    import owner_decision_gate as gate

NOW = datetime(2026, 9, 14, 3, 20, 0, tzinfo=timezone.utc)
A = "a" * 64
B = "b" * 64
C = "c" * 64


def request() -> dict:
    return {
        "schema_version": gate.REQUEST_SCHEMA,
        "request_id": "req-001",
        "mailbox": "TokenJunkieLabs@GMAIL.com",
        "thread_id": "thread-123",
        "inbound_event": {
            "event_id": "gmail-inbound-456",
            "event_sha256": A,
            "observed_at": "2026-09-14T03:18:00Z",
        },
        "decision_type": "PAID_SCOPE",
        "buyer_scope": "example-buyer.test",
        "opportunity_id": "opportunity-789",
        "prior_offers": [
            {
                "offer_id": "offer-24k",
                "amount_minor": 2400000,
                "currency": "USD",
                "status": "PROPOSED_NOT_ACCEPTED",
                "evidence_event_id": "gmail-outbound-123",
            }
        ],
        "prior_promises": [
            {
                "summary": "Send one technical workshare exhibit for review.",
                "evidence_event_id": "gmail-outbound-123",
            }
        ],
        "evidenced_amounts": [
            {
                "label": "proposed fixed scope",
                "amount_minor": 2400000,
                "currency": "USD",
                "evidence_event_id": "gmail-outbound-123",
            }
        ],
        "deadlines": [
            {
                "label": "buyer review window",
                "deadline_at": "2026-09-16T17:00:00Z",
                "evidence_event_id": "gmail-inbound-456",
            }
        ],
        "recommendation": {
            "action": "Keep the thread quiet; prepare only the exact scope question for owner ruling.",
            "rationale": "Buyer asked for review time and no new provider event has superseded that state.",
        },
        "ruling_needed": "May the next human reply discuss the existing $24,000 scope without changing price or terms?",
    }


def snapshot() -> dict:
    event = {
        "event_id": "gmail-inbound-456",
        "event_sha256": A,
        "observed_at": "2026-09-14T03:18:00Z",
    }
    return {
        "schema_version": gate.SNAPSHOT_SCHEMA,
        "complete": True,
        "mailbox": "tokenjunkielabs@gmail.com",
        "thread_id": "thread-123",
        "captured_at": "2026-09-14T03:19:30Z",
        "latest_inbound": copy.deepcopy(event),
        "latest_provider_event": copy.deepcopy(event),
        "history_digest": B,
        "relationship_generation": 17,
        "relationship_disposition": "ACTIONABLE",
        "relationship_state": "HUMAN_REPLY_NEEDS_OWNER_DECISION",
    }


class DecisionGateTests(unittest.TestCase):
    def compile(self, req=None, snap=None, priors=()):
        return gate.compile_decision(
            req or request(), snap or snapshot(), priors, prior_ledger_complete=True, _now=NOW
        )

    def test_fresh_unique_is_ready_but_never_authorizes_side_effects(self):
        out = self.compile()
        self.assertEqual(out["decision"], gate.READY)
        self.assertTrue(out["owner_alert_allowed"])
        self.assertFalse(out["side_effects_authorized"])
        self.assertIn("$24,000.00 USD", out["owner_brief_markdown"])
        self.assertIn("canonical atomic send lease", out["owner_brief_markdown"])

    def test_mailbox_casefolds_into_same_identity(self):
        first = self.compile()
        req = request()
        req["mailbox"] = "tokenjunkielabs@gmail.com"
        second = self.compile(req=req)
        self.assertEqual(first["decision_key"], second["decision_key"])
        self.assertEqual(first["request_digest"], second["request_digest"])

    def test_incomplete_history_holds(self):
        snap = snapshot()
        snap["complete"] = False
        out = self.compile(snap=snap)
        self.assertEqual(out["decision"], gate.HOLD)
        self.assertIn("PROVIDER_HISTORY_INCOMPLETE", out["reasons"])
        self.assertFalse(out["owner_alert_allowed"])

    def test_newer_provider_event_holds(self):
        snap = snapshot()
        snap["latest_provider_event"] = {
            "event_id": "gmail-outbound-after-inbound",
            "event_sha256": C,
            "observed_at": "2026-09-14T03:19:00Z",
        }
        out = self.compile(snap=snap)
        self.assertEqual(out["decision"], gate.HOLD)
        self.assertIn("NEWER_OR_DIFFERENT_PROVIDER_EVENT_EXISTS", out["reasons"])

    def test_latest_inbound_mismatch_holds(self):
        snap = snapshot()
        snap["latest_inbound"] = {
            "event_id": "new-inbound",
            "event_sha256": C,
            "observed_at": "2026-09-14T03:19:00Z",
        }
        snap["latest_provider_event"] = copy.deepcopy(snap["latest_inbound"])
        out = self.compile(snap=snap)
        self.assertIn("CONTROLLING_INBOUND_NOT_LATEST_INBOUND", out["reasons"])

    def test_thread_mismatch_holds(self):
        snap = snapshot()
        snap["thread_id"] = "different-thread"
        out = self.compile(snap=snap)
        self.assertIn("MAILBOX_THREAD_MISMATCH", out["reasons"])

    def test_closed_relationship_holds(self):
        snap = snapshot()
        snap["relationship_disposition"] = "CLOSED"
        snap["relationship_state"] = "HARD_DNR"
        out = self.compile(snap=snap)
        self.assertIn("RELATIONSHIP_CLOSED", out["reasons"])

    def test_hold_relationship_holds(self):
        snap = snapshot()
        snap["relationship_disposition"] = "HOLD"
        out = self.compile(snap=snap)
        self.assertIn("RELATIONSHIP_HOLD", out["reasons"])

    def test_stale_snapshot_holds(self):
        snap = snapshot()
        snap["captured_at"] = "2026-09-14T02:00:00Z"
        out = self.compile(snap=snap)
        self.assertIn("PROVIDER_SNAPSHOT_STALE", out["reasons"])

    def test_capture_before_provider_head_holds(self):
        snap = snapshot()
        snap["captured_at"] = "2026-09-14T03:17:59Z"
        out = self.compile(snap=snap)
        self.assertIn("SNAPSHOT_CAPTURE_PRECEDES_LATEST_PROVIDER_EVENT", out["reasons"])

    def test_future_event_holds(self):
        req = request()
        snap = snapshot()
        future = {
            "event_id": "future",
            "event_sha256": C,
            "observed_at": "2026-09-14T04:00:00Z",
        }
        req["inbound_event"] = copy.deepcopy(future)
        snap["latest_inbound"] = copy.deepcopy(future)
        snap["latest_provider_event"] = copy.deepcopy(future)
        snap["captured_at"] = "2026-09-14T04:00:01Z"
        out = self.compile(req=req, snap=snap)
        self.assertIn("PROVIDER_EVENT_IN_FUTURE", out["reasons"])
        self.assertIn("SNAPSHOT_CAPTURE_IN_FUTURE", out["reasons"])

    def test_exact_prior_is_duplicate_and_suppresses_owner_alert(self):
        first = self.compile()
        second = self.compile(priors=[first])
        self.assertEqual(second["decision"], gate.DUPLICATE)
        self.assertFalse(second["owner_alert_allowed"])
        self.assertEqual(second["reasons"], ["EXACT_DECISION_ALREADY_COMPILED"])

    def test_same_decision_key_with_changed_payload_holds_conflict(self):
        first = self.compile()
        req = request()
        req["recommendation"]["rationale"] = "Changed rationale on same controlling inbound."
        second = self.compile(req=req, priors=[first])
        self.assertEqual(second["decision"], gate.HOLD)
        self.assertIn("EXISTING_DECISION_KEY_CONFLICT", second["reasons"])

    def test_same_decision_key_with_changed_provider_generation_holds(self):
        first = self.compile()
        snap = snapshot()
        snap["relationship_generation"] = 18
        snap["history_digest"] = C
        second = self.compile(snap=snap, priors=[first])
        self.assertIn("EXISTING_DECISION_KEY_CONFLICT", second["reasons"])

    def test_distinct_decision_type_gets_distinct_key(self):
        first = self.compile()
        req = request()
        req["decision_type"] = "OWNER_TIME"
        second = self.compile(req=req, priors=[first])
        self.assertEqual(second["decision"], gate.READY)
        self.assertNotEqual(second["decision_key"], first["decision_key"])

    def test_tampered_prior_receipt_is_rejected(self):
        first = self.compile()
        first["decision"] = gate.HOLD
        with self.assertRaises(gate.DecisionGateError):
            self.compile(priors=[first])

    def test_prior_with_side_effects_true_is_rejected_even_if_rehashed(self):
        first = self.compile()
        first["side_effects_authorized"] = True
        first["receipt_digest"] = gate.digest_object(gate._brief_unsigned(first))
        with self.assertRaises(gate.DecisionGateError):
            self.compile(priors=[first])

    def test_duplicate_json_key_rejected(self):
        raw = b'{"schema_version":"owner-commercial-decision-request/v1","request_id":"a","request_id":"b"}'
        with self.assertRaises(gate.DuplicateKeyError):
            gate.parse_json_bytes(raw, "request")

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(gate.DecisionGateError):
            gate.parse_json_bytes(b'{"x":NaN}', "request")

    def test_unknown_request_field_rejected(self):
        req = request()
        req["send_now"] = True
        with self.assertRaises(gate.DecisionGateError):
            self.compile(req=req)

    def test_boolean_amount_is_not_integer(self):
        req = request()
        req["prior_offers"][0]["amount_minor"] = True
        with self.assertRaises(gate.DecisionGateError):
            self.compile(req=req)

    def test_uppercase_hash_rejected(self):
        req = request()
        req["inbound_event"]["event_sha256"] = "A" * 64
        with self.assertRaises(gate.DecisionGateError):
            self.compile(req=req)

    def test_naive_timestamp_rejected(self):
        snap = snapshot()
        snap["captured_at"] = "2026-09-14T03:19:30"
        with self.assertRaises(gate.DecisionGateError):
            self.compile(snap=snap)

    def test_receipt_digest_is_self_consistent(self):
        out = self.compile()
        self.assertEqual(out["receipt_digest"], gate.digest_object(gate._brief_unsigned(out)))

    def test_incomplete_prior_ledger_holds(self):
        out = gate.compile_decision(request(), snapshot(), [], prior_ledger_complete=False, _now=NOW)
        self.assertEqual(out["decision"], gate.HOLD)
        self.assertIn("OWNER_DECISION_LEDGER_INCOMPLETE", out["reasons"])
        self.assertFalse(out["owner_alert_allowed"])

    def test_ready_exposes_stable_atomic_owner_alert_lease_key(self):
        out = self.compile()
        self.assertEqual(out["owner_alert_lease_key"], f"owner-decision-lease/v1/{out['decision_key']}")
        self.assertFalse(out["side_effects_authorized"])

    def test_cli_ready_exit_zero_and_strict_json(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            current = datetime.now(timezone.utc)
            event_at = gate.format_time(current - timedelta(seconds=30))
            captured_at = gate.format_time(current - timedelta(seconds=5))
            req = request()
            snap = snapshot()
            req["inbound_event"]["observed_at"] = event_at
            snap["latest_inbound"]["observed_at"] = event_at
            snap["latest_provider_event"]["observed_at"] = event_at
            snap["captured_at"] = captured_at
            (td / "request.json").write_text(json.dumps(req), encoding="utf-8")
            (td / "snapshot.json").write_text(json.dumps(snap), encoding="utf-8")
            (td / "prior.json").write_text(json.dumps({"schema_version": gate.BRIEF_SET_SCHEMA, "complete": True, "briefs": []}), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("owner_decision_gate.py")), "--request", str(td / "request.json"), "--provider-snapshot", str(td / "snapshot.json"), "--prior-briefs", str(td / "prior.json")],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            parsed = json.loads(proc.stdout)
            self.assertEqual(parsed["decision"], gate.READY)
            self.assertFalse(parsed["side_effects_authorized"])

    def test_cli_hold_exit_four(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            current = datetime.now(timezone.utc)
            event_at = gate.format_time(current - timedelta(seconds=30))
            captured_at = gate.format_time(current - timedelta(seconds=5))
            req = request()
            snap = snapshot()
            req["inbound_event"]["observed_at"] = event_at
            snap["latest_inbound"]["observed_at"] = event_at
            snap["latest_provider_event"]["observed_at"] = event_at
            snap["captured_at"] = captured_at
            snap["complete"] = False
            (td / "request.json").write_text(json.dumps(req), encoding="utf-8")
            (td / "snapshot.json").write_text(json.dumps(snap), encoding="utf-8")
            (td / "prior.json").write_text(json.dumps({"schema_version": gate.BRIEF_SET_SCHEMA, "complete": True, "briefs": []}), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("owner_decision_gate.py")), "--request", str(td / "request.json"), "--provider-snapshot", str(td / "snapshot.json"), "--prior-briefs", str(td / "prior.json")],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 4)
            self.assertEqual(json.loads(proc.stdout)["decision"], gate.HOLD)


if __name__ == "__main__":
    unittest.main()