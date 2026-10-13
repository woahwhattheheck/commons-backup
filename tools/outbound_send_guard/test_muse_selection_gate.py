from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from tools.outbound_send_guard import muse_selection_gate as gate

MUSE = "U0C0TKRTQHZ"
DM = "D0C1U7TUZEC"
SENDER = "U0BRETUB5TK"
H = "a" * 64
J = "b" * 64
K = "c" * 64
L = "d" * 64


def z(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def candidate(now=None, worker="ZXC-P6T9", candidate_id="cand-a", message_sha=J):
    now = now or datetime.now(timezone.utc)
    return {
        "schema_version": gate.CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "worker_id": worker,
        "buyer_scope_sha256": H,
        "recipient_fingerprint": K,
        "offer_scope": "inventory-variance-desk-v1",
        "route_kind": "EMAIL",
        "message_sha256": message_sha,
        "requested_at": z(now - timedelta(seconds=30)),
        "lease": {
            "schema": gate.LEASE_RECEIPT_SCHEMA,
            "claimant": worker,
            "claim_id": "claim-001" if worker == "ZXC-P6T9" else "claim-002",
            "lease_ref": "refs/heads/outbound-lease-v3/" + ("1" if worker == "ZXC-P6T9" else "2") * 64,
            "claim_capability_sha256": L if worker == "ZXC-P6T9" else "e" * 64,
            "receipt_sha256": "f" * 64 if worker == "ZXC-P6T9" else "0" * 64,
        },
    }


def event(c, kind, message_id, observed_at, sender=None):
    n = gate.normalize_candidate(c)
    return {
        "message_id": message_id,
        "sender_user_id": sender or (MUSE if kind != "CANDIDATE" else SENDER),
        "observed_at": observed_at,
        "event_type": kind,
        "publication_key": gate.publication_key(n),
        "candidate_digest": gate.candidate_digest(n),
        "candidate_id": n["candidate_id"],
        "worker_id": n["worker_id"],
    }


def snapshot(c, now=None, extra_events=None, **updates):
    now = now or datetime.now(timezone.utc)
    events = [
        event(c, "CANDIDATE", "1789432205.000001", z(now - timedelta(seconds=25))),
        event(c, "SELECTED", "1789432215.000002", z(now - timedelta(seconds=15))),
    ]
    if extra_events:
        events.extend(extra_events)
    value = {
        "schema_version": gate.SNAPSHOT_SCHEMA,
        "complete": True,
        "conversation_id": DM,
        "arbiter_user_id": MUSE,
        "coverage_started_at": z(now - timedelta(seconds=60)),
        "captured_at": z(now - timedelta(seconds=5)),
        "events": events,
    }
    value.update(updates)
    return value


class MuseSelectionCurrentAuthorityTests(unittest.TestCase):
    def compile(self, c=None, s=None, **kwargs):
        now = datetime.now(timezone.utc)
        c = c or candidate(now)
        s = s or snapshot(c, now)
        return gate.compile_selection(c, s, expected_conversation_id=DM, expected_arbiter_user_id=MUSE, **kwargs)

    def test_raw_happy_snapshot_is_hold_not_selected(self):
        r = self.compile()
        self.assertEqual(r["decision"], gate.HOLD)
        self.assertIn(gate.UNAUTHENTICATED_SNAPSHOT_REASON, r["reasons"])
        self.assertIn(gate.CURRENT_POSITIVE_DISABLED_REASON, r["reasons"])
        self.assertFalse(r["snapshot_authenticated"])
        self.assertFalse(r["side_effects_authorized"])
        self.assertTrue(gate.verify_receipt(r))
        self.assertFalse(gate.verify_selected_binding(candidate(), r))

    def test_caller_supplied_now_is_not_an_api(self):
        now = datetime.now(timezone.utc)
        c = candidate(now)
        with self.assertRaises(TypeError):
            gate.compile_selection(c, snapshot(c, now), expected_conversation_id=DM, expected_arbiter_user_id=MUSE, now=now - timedelta(days=1))

    def test_fabricated_two_event_snapshot_cannot_select(self):
        now = datetime.now(timezone.utc)
        c = candidate(now)
        r = gate.compile_selection(c, snapshot(c, now), expected_conversation_id=DM, expected_arbiter_user_id=MUSE)
        self.assertEqual(r["decision"], gate.HOLD)
        self.assertIn("SNAPSHOT_AUTHORITY_UNVERIFIED", r["reasons"])

    def test_legacy_v1_receipt_never_verifies_current(self):
        now = datetime.now(timezone.utc)
        c = candidate(now)
        s = snapshot(c, now)
        r = gate._build_receipt(gate.normalize_candidate(c), gate.normalize_snapshot(s), gate.HOLD, ["legacy"], now)
        r["schema_version"] = gate.LEGACY_RECEIPT_SCHEMA
        material = dict(r)
        material.pop("receipt_digest")
        r["receipt_digest"] = gate.digest_object(material)
        self.assertFalse(gate.verify_receipt(r))

    def test_current_selected_receipt_is_fail_closed_even_if_digest_is_recomputed(self):
        now = datetime.now(timezone.utc)
        c = gate.normalize_candidate(candidate(now))
        s = gate.normalize_snapshot(snapshot(c, now))
        selected = next(e for e in s["events"] if e["event_type"] == gate.SELECTED)
        r = gate._build_receipt(c, s, gate.SELECTED, [], now, selected, selection_ttl_seconds=600)
        self.assertIsNotNone(r["valid_until"])
        self.assertFalse(gate.verify_receipt(r))
        self.assertFalse(gate.verify_selected_binding(c, r))

    def test_selected_binding_binds_valid_until(self):
        now = datetime.now(timezone.utc)
        c = gate.normalize_candidate(candidate(now))
        s = gate.normalize_snapshot(snapshot(c, now))
        selected = next(e for e in s["events"] if e["event_type"] == gate.SELECTED)
        r = gate._build_receipt(c, s, gate.SELECTED, [], now, selected, selection_ttl_seconds=600)
        old_binding = r["selection_binding_sha256"]
        r["valid_until"] = z(now + timedelta(hours=1))
        material = dict(r)
        material.pop("receipt_digest")
        r["receipt_digest"] = gate.digest_object(material)
        self.assertEqual(old_binding, r["selection_binding_sha256"])
        self.assertFalse(gate.verify_receipt(r))

    def test_stale_snapshot_holds(self):
        now = datetime.now(timezone.utc)
        c = candidate(now)
        s = snapshot(c, now, captured_at=z(now - timedelta(minutes=10)))
        r = gate.compile_selection(c, s, expected_conversation_id=DM, expected_arbiter_user_id=MUSE)
        self.assertEqual(r["decision"], gate.HOLD)
        self.assertIn("SNAPSHOT_STALE", r["reasons"])

    def test_future_snapshot_holds(self):
        now = datetime.now(timezone.utc)
        c = candidate(now)
        s = snapshot(c, now, captured_at=z(now + timedelta(minutes=2)))
        r = gate.compile_selection(c, s, expected_conversation_id=DM, expected_arbiter_user_id=MUSE)
        self.assertEqual(r["decision"], gate.HOLD)
        self.assertIn("SNAPSHOT_IN_FUTURE", r["reasons"])

    def test_incomplete_snapshot_holds(self):
        now = datetime.now(timezone.utc)
        c = candidate(now)
        s = snapshot(c, now, complete=False)
        r = gate.compile_selection(c, s, expected_conversation_id=DM, expected_arbiter_user_id=MUSE)
        self.assertEqual(r["decision"], gate.HOLD)
        self.assertIn("SNAPSHOT_INCOMPLETE", r["reasons"])

    def test_wrong_conversation_holds(self):
        now = datetime.now(timezone.utc)
        c = candidate(now)
        s = snapshot(c, now, conversation_id="D0OTHER12345")
        r = gate.compile_selection(c, s, expected_conversation_id=DM, expected_arbiter_user_id=MUSE)
        self.assertEqual(r["decision"], gate.HOLD)
        self.assertIn("WRONG_CONVERSATION", r["reasons"])

    def test_non_arbiter_decision_holds(self):
        now = datetime.now(timezone.utc)
        c = candidate(now)
        s = snapshot(c, now)
        s["events"][1]["sender_user_id"] = "U0OTHER12345"
        r = gate.compile_selection(c, s, expected_conversation_id=DM, expected_arbiter_user_id=MUSE)
        self.assertEqual(r["decision"], gate.HOLD)
        self.assertTrue(any(x.startswith("DECISION_NOT_FROM_ARBITER") for x in r["reasons"]))

    def test_other_worker_selected_can_return_not_selected(self):
        now = datetime.now(timezone.utc)
        a = candidate(now)
        b = candidate(now, "Z-OTHER", "cand-b", "9" * 64)
        s = {
            "schema_version": gate.SNAPSHOT_SCHEMA,
            "complete": True,
            "conversation_id": DM,
            "arbiter_user_id": MUSE,
            "coverage_started_at": z(now - timedelta(seconds=60)),
            "captured_at": z(now - timedelta(seconds=5)),
            "events": [
                event(a, "CANDIDATE", "1789432205.000011", z(now - timedelta(seconds=25))),
                event(b, "SELECTED", "1789432215.000012", z(now - timedelta(seconds=15))),
            ],
        }
        r = gate.compile_selection(a, s, expected_conversation_id=DM, expected_arbiter_user_id=MUSE)
        self.assertEqual(r["decision"], gate.NOT_SELECTED)
        self.assertTrue(gate.verify_receipt(r))

    def test_selected_then_cancelled_is_not_selected(self):
        now = datetime.now(timezone.utc)
        c = candidate(now)
        cancel = event(c, "CANCELLED", "1789432216.000003", z(now - timedelta(seconds=10)))
        s = snapshot(c, now, extra_events=[cancel])
        r = gate.compile_selection(c, s, expected_conversation_id=DM, expected_arbiter_user_id=MUSE)
        self.assertEqual(r["decision"], gate.NOT_SELECTED)
        self.assertTrue(gate.verify_receipt(r))

    def test_multiple_distinct_winners_hold(self):
        now = datetime.now(timezone.utc)
        a = candidate(now)
        b = candidate(now, "Z-OTHER", "cand-b", "9" * 64)
        s = snapshot(a, now, extra_events=[event(b, "SELECTED", "1789432216.000013", z(now - timedelta(seconds=10)))])
        r = gate.compile_selection(a, s, expected_conversation_id=DM, expected_arbiter_user_id=MUSE)
        self.assertEqual(r["decision"], gate.HOLD)
        self.assertIn("MULTIPLE_DISTINCT_WINNERS", r["reasons"])

    def test_conflicting_duplicate_message_id_holds(self):
        now = datetime.now(timezone.utc)
        c = candidate(now)
        s = snapshot(c, now)
        conflict = copy.deepcopy(s["events"][1])
        conflict["event_type"] = "NOT_SELECTED"
        s["events"].append(conflict)
        r = gate.compile_selection(c, s, expected_conversation_id=DM, expected_arbiter_user_id=MUSE)
        self.assertEqual(r["decision"], gate.HOLD)
        self.assertTrue(any(x.startswith("CONFLICTING_MESSAGE_ID") for x in r["reasons"]))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(gate.DuplicateKeyError):
            gate.parse_json_bytes(b'{"a":1,"a":2}', "x")

    def test_unknown_candidate_field_rejected(self):
        c = candidate()
        c["mystery"] = True
        with self.assertRaises(gate.MuseSelectionError):
            gate.normalize_candidate(c)

    def test_lease_claimant_must_equal_worker(self):
        c = candidate()
        c["lease"]["claimant"] = "Z-OTHER"
        with self.assertRaises(gate.MuseSelectionError):
            gate.normalize_candidate(c)

    def test_publication_key_collides_across_worker_and_copy(self):
        now = datetime.now(timezone.utc)
        a = gate.normalize_candidate(candidate(now))
        b = gate.normalize_candidate(candidate(now, "Z-OTHER", "cand-b", "9" * 64))
        self.assertEqual(gate.publication_key(a), gate.publication_key(b))
        self.assertNotEqual(gate.candidate_digest(a), gate.candidate_digest(b))

    def test_tampered_hold_receipt_fails_verification(self):
        r = self.compile()
        self.assertTrue(gate.verify_receipt(r))
        r["worker_id"] = "Z-TAMPER"
        self.assertFalse(gate.verify_receipt(r))

    def test_recomputed_digest_cannot_turn_hold_into_selected(self):
        r = self.compile()
        r["decision"] = gate.SELECTED
        r["reasons"] = []
        material = dict(r)
        material.pop("receipt_digest")
        r["receipt_digest"] = gate.digest_object(material)
        self.assertFalse(gate.verify_receipt(r))

    def test_future_compiled_at_fails_current_verification(self):
        r = self.compile()
        r["compiled_at"] = z(datetime.now(timezone.utc) + timedelta(minutes=5))
        material = dict(r)
        material.pop("receipt_digest")
        r["receipt_digest"] = gate.digest_object(material)
        self.assertFalse(gate.verify_receipt(r))

    def test_cli_happy_raw_snapshot_exits_hold(self):
        now = datetime.now(timezone.utc)
        c = candidate(now)
        s = snapshot(c, now)
        with tempfile.TemporaryDirectory() as td:
            cp = os.path.join(td, "candidate.json")
            sp = os.path.join(td, "snapshot.json")
            with open(cp, "w", encoding="utf-8") as f:
                json.dump(c, f)
            with open(sp, "w", encoding="utf-8") as f:
                json.dump(s, f)
            env = dict(os.environ)
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [os.getcwd(), env.get("PYTHONPATH")]))
            proc = subprocess.run([sys.executable, "-m", "tools.outbound_send_guard.muse_selection_gate", "--candidate", cp, "--snapshot", sp, "--conversation-id", DM, "--arbiter-user-id", MUSE], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)
            self.assertEqual(proc.returncode, 4, proc.stderr.decode())
            parsed = json.loads(proc.stdout)
            self.assertEqual(parsed["decision"], gate.HOLD)
            self.assertIn(gate.UNAUTHENTICATED_SNAPSHOT_REASON, parsed["reasons"])


if __name__ == "__main__":
    unittest.main()
