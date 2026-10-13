from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
import unittest

from revenue.hyperagent_slack_transcript import ConflictError, TranscriptProjector, canonical_bytes
from revenue.hyperagent_slack_transcript.adapter import normalize_event
from revenue.hyperagent_slack_transcript import adapter as adapter_mod

TEST_APPROVAL_KEY = b"hyperagent-test-approval-authority-32bytes"


def mutation_event():
    return {
        "backend": "stream",
        "run_id": "mut-run",
        "event_id": "m1",
        "seq": 1,
        "kind": "MUTATING_ACTION",
        "payload": {
            "thread": "mut",
            "text": "would mutate provider",
            "action_id": "send",
            "generation": 2,
        },
    }


def approval_for(event, **overrides):
    raw = f"run\x1fstream\x1f{event['run_id']}".encode()
    run_id = "run_" + hashlib.sha256(raw).hexdigest()[:24]
    signed = {
        "approval_id": "ap-1",
        "run_id": run_id,
        "action_id": event["payload"]["action_id"],
        "generation": event["payload"]["generation"],
        "event_semantics_sha256": adapter_mod._legacy._sha(normalize_event(event).semantics()),
        "decision": "APPROVE",
        "issued_at": "2020-01-01T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
        "evidence_sha256": "a" * 64,
    }
    signed.update(overrides)
    signed["authority_tag"] = hmac.new(
        TEST_APPROVAL_KEY,
        canonical_bytes(signed),
        hashlib.sha256,
    ).hexdigest()
    return signed


def projector():
    return TranscriptProjector(approval_auth_key=TEST_APPROVAL_KEY)


class IncrementalAuthorityTests(unittest.TestCase):
    def test_held_action_can_emit_after_exact_approval_arrives(self):
        event = mutation_event()
        subject = projector()
        first = subject.ingest([event], [])
        self.assertEqual(first["message_count"], 0)
        second = subject.ingest([event], [approval_for(event)])
        self.assertEqual(second["message_count"], 1)
        self.assertEqual(len(second["new_message_ids"]), 1)
        self.assertFalse(second["artifacts"][0]["external_send_authorized"])
        self.assertRegex(
            second["artifacts"][0]["messages"][0]["approval_receipt_sha256"],
            r"^[0-9a-f]{64}$",
        )

    def test_changed_held_event_semantics_still_conflict(self):
        event = mutation_event()
        subject = projector()
        subject.ingest([event], [])
        changed = deepcopy(event)
        changed["payload"]["text"] = "changed"
        with self.assertRaises(ConflictError):
            subject.ingest([changed], [approval_for(event)])

    def test_approval_identity_is_immutable_across_ingests(self):
        event = mutation_event()
        first = approval_for(event)
        second = approval_for(event, evidence_sha256="b" * 64)
        subject = projector()
        subject.ingest([], [first])
        with self.assertRaises(ConflictError):
            subject.ingest([], [second])

    def test_emitted_event_replay_remains_idempotent(self):
        event = mutation_event()
        approval = approval_for(event)
        subject = projector()
        first = subject.ingest([event], [approval])
        second = subject.ingest([event], [approval])
        self.assertEqual(len(first["new_message_ids"]), 1)
        self.assertEqual(second["new_message_ids"], [])
        self.assertEqual(second["message_count"], 1)


if __name__ == "__main__":
    unittest.main()
