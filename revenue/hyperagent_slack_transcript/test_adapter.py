from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import hashlib
import hmac
import tempfile
import unittest

from revenue.hyperagent_slack_transcript.adapter import (
    ApprovalError,
    ConflictError,
    TranscriptProjector,
    ValidationError,
    canonical_bytes,
    load_strict_json,
    normalize_event,
    project_fixture,
)
from revenue.hyperagent_slack_transcript.cli import main as cli_main

ROOT = Path(__file__).resolve().parent
TEST_APPROVAL_KEY = b"hyperagent-test-approval-authority-32bytes"
OTHER_APPROVAL_KEY = b"hyperagent-other-approval-authority-key"


def fixture():
    return load_strict_json((ROOT / "fixture.json").read_bytes())


def mutation_event(event_id="m1", run_id="mut-run", action="send", generation=2):
    return {
        "backend": "stream",
        "run_id": run_id,
        "event_id": event_id,
        "seq": 1,
        "kind": "MUTATING_ACTION",
        "payload": {
            "thread": "mut",
            "text": "would mutate provider",
            "action_id": action,
            "generation": generation,
        },
    }


def _event_semantics_sha256(event: dict) -> str:
    return hashlib.sha256(canonical_bytes(normalize_event(event).semantics())).hexdigest()


def approval_for(
    event,
    *,
    signing_key=TEST_APPROVAL_KEY,
    generation=2,
    issued="2020-01-01T00:00:00Z",
    expires="2099-01-01T00:00:00Z",
    **overrides,
):
    raw = f"run\x1fstream\x1f{event['run_id']}".encode()
    run_id = "run_" + hashlib.sha256(raw).hexdigest()[:24]
    signed = {
        "approval_id": "ap-1",
        "run_id": run_id,
        "action_id": event["payload"]["action_id"],
        "generation": generation,
        "event_semantics_sha256": _event_semantics_sha256(event),
        "decision": "APPROVE",
        "issued_at": issued,
        "expires_at": expires,
        "evidence_sha256": "a" * 64,
    }
    signed.update(overrides)
    signed["authority_tag"] = hmac.new(
        signing_key,
        canonical_bytes(signed),
        hashlib.sha256,
    ).hexdigest()
    return signed


def trusted_projector():
    return TranscriptProjector(approval_auth_key=TEST_APPROVAL_KEY)


class HyperagentTranscriptTests(unittest.TestCase):
    def test_fixture_30_events_to_exactly_six_artifacts(self):
        result = project_fixture(fixture())
        self.assertEqual(result["artifact_count"], 6)
        self.assertEqual(result["message_count"], 30)
        self.assertEqual(len(result["new_message_ids"]), 30)
        self.assertEqual(
            {artifact["thread_ref"] for artifact in result["artifacts"]},
            {"alpha", "beta", "gamma", "delta", "epsilon", "zeta"},
        )
        self.assertTrue(all(a["external_send_authorized"] is False for a in result["artifacts"]))

    def test_full_fixture_replay_emits_zero_duplicate_messages(self):
        f = fixture()
        projector = TranscriptProjector()
        first = projector.ingest(f["events"], f["approvals"])
        second = projector.ingest(f["events"], f["approvals"])
        self.assertEqual(len(first["new_message_ids"]), 30)
        self.assertEqual(second["new_message_ids"], [])
        self.assertEqual(second["message_count"], 30)
        ids = [m["message_id"] for a in second["artifacts"] for m in a["messages"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_changed_semantics_under_same_source_event_id_conflicts(self):
        f = fixture()
        projector = TranscriptProjector()
        projector.ingest([f["events"][0]], [])
        changed = deepcopy(f["events"][0])
        changed["payload"]["text"] = "changed bytes"
        with self.assertRaises(ConflictError):
            projector.ingest([changed], [])

    def test_mutation_without_approval_emits_no_artifact(self):
        event = mutation_event()
        result = trusted_projector().ingest([event], [])
        self.assertEqual(result["artifact_count"], 0)
        self.assertEqual(result["message_count"], 0)
        self.assertEqual(len(result["held"]), 1)

    def test_mutation_exact_authenticated_current_approval_emits(self):
        event = mutation_event()
        approval = approval_for(event)
        result = trusted_projector().ingest([event], [approval])
        self.assertEqual(result["artifact_count"], 1)
        self.assertEqual(result["message_count"], 1)
        message = result["artifacts"][0]["messages"][0]
        self.assertEqual(message["approval_id"], "ap-1")
        self.assertRegex(message["approval_receipt_sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(result["artifacts"][0]["external_send_authorized"])

    def test_valid_approval_does_not_authorize_fresh_event_with_changed_text(self):
        approved = mutation_event("m1")
        foreign = mutation_event("m2")
        foreign["payload"]["text"] = "different mutation payload"
        result = trusted_projector().ingest([foreign], [approval_for(approved)])
        self.assertEqual(result["message_count"], 0)
        self.assertEqual(len(result["held"]), 1)

    def test_valid_approval_does_not_authorize_changed_thread_or_sequence(self):
        approved = mutation_event("m1")
        foreign = mutation_event("m2")
        foreign["seq"] = 7
        foreign["payload"]["thread"] = "other-thread"
        result = trusted_projector().ingest([foreign], [approval_for(approved)])
        self.assertEqual(result["message_count"], 0)
        self.assertEqual(len(result["held"]), 1)

    def test_one_approval_cannot_amplify_across_two_distinct_events_same_action_tuple(self):
        approved = mutation_event("m1")
        foreign = mutation_event("m2")
        foreign["payload"]["text"] = "another action representation"
        result = trusted_projector().ingest(
            [approved, foreign],
            [approval_for(approved)],
        )
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(len(result["new_message_ids"]), 1)
        self.assertEqual(len(result["held"]), 1)
        message = result["artifacts"][0]["messages"][0]
        self.assertEqual(message["source"]["source_event_id"], "m1")

    def test_exact_mutating_event_replay_remains_idempotent(self):
        event = mutation_event()
        approval = approval_for(event)
        projector = trusted_projector()
        first = projector.ingest([event], [approval])
        second = projector.ingest([event], [approval])
        self.assertEqual(len(first["new_message_ids"]), 1)
        self.assertEqual(second["new_message_ids"], [])
        self.assertEqual(second["message_count"], 1)

    def test_signed_approval_without_retained_runtime_key_stays_held(self):
        event = mutation_event()
        result = TranscriptProjector().ingest([event], [approval_for(event)])
        self.assertEqual(result["message_count"], 0)
        self.assertEqual(result["held"][0]["reason"], "APPROVAL_AUTHORITY_UNAVAILABLE")

    def test_forged_approval_under_other_key_is_rejected(self):
        event = mutation_event()
        forged = approval_for(event, signing_key=OTHER_APPROVAL_KEY)
        with self.assertRaisesRegex(ApprovalError, "authentication failed"):
            trusted_projector().ingest([event], [forged])

    def test_tampered_signed_approval_is_rejected(self):
        event = mutation_event()
        approval = approval_for(event)
        approval["expires_at"] = "2098-01-01T00:00:00Z"
        with self.assertRaisesRegex(ApprovalError, "authentication failed"):
            trusted_projector().ingest([event], [approval])

    def test_tampered_event_semantics_digest_is_rejected(self):
        event = mutation_event()
        approval = approval_for(event)
        approval["event_semantics_sha256"] = "f" * 64
        with self.assertRaisesRegex(ApprovalError, "authentication failed"):
            trusted_projector().ingest([event], [approval])

    def test_held_mutation_can_emit_when_exact_authenticated_approval_arrives_later(self):
        event = mutation_event()
        projector = trusted_projector()
        first = projector.ingest([event], [])
        self.assertEqual(first["message_count"], 0)
        second = projector.ingest([event], [approval_for(event)])
        self.assertEqual(second["message_count"], 1)
        self.assertEqual(len(second["new_message_ids"]), 1)

    def test_foreign_generation_authenticated_approval_holds(self):
        event = mutation_event()
        approval = approval_for(event, generation=3)
        result = trusted_projector().ingest([event], [approval])
        self.assertEqual(result["artifact_count"], 0)

    def test_stale_authenticated_approval_holds_against_process_utc(self):
        event = mutation_event()
        approval = approval_for(
            event,
            issued="2000-01-01T00:00:00Z",
            expires="2001-01-01T00:00:00Z",
        )
        result = trusted_projector().ingest([event], [approval])
        self.assertEqual(result["artifact_count"], 0)

    def test_foreign_run_authenticated_approval_holds(self):
        event = mutation_event()
        approval = approval_for(event, run_id="run_deadbeefdeadbeefdeadbeef")
        result = trusted_projector().ingest([event], [approval])
        self.assertEqual(result["artifact_count"], 0)

    def test_denied_authenticated_approval_holds(self):
        event = mutation_event()
        approval = approval_for(event, decision="DENY")
        result = trusted_projector().ingest([event], [approval])
        self.assertEqual(result["artifact_count"], 0)

    def test_duplicate_authenticated_approval_id_changed_semantics_conflicts(self):
        event = mutation_event()
        first = approval_for(event)
        second = approval_for(event, generation=9)
        with self.assertRaises(ConflictError):
            trusted_projector().ingest([event], [first, second])

    def test_approval_id_changed_across_ingests_conflicts(self):
        event = mutation_event()
        first = approval_for(event)
        second = approval_for(event, evidence_sha256="b" * 64)
        projector = trusted_projector()
        projector.ingest([], [first])
        with self.assertRaises(ConflictError):
            projector.ingest([], [second])

    def test_public_ingest_has_no_caller_clock_parameter(self):
        event = mutation_event()
        with self.assertRaises(TypeError):
            trusted_projector().ingest(
                [event],
                [approval_for(event)],
                as_of="2000-01-01T00:00:00Z",
            )

    def test_synthetic_fixture_surface_cannot_backdate_action_approval(self):
        f = fixture()
        f["events"] = [mutation_event()]
        f["approvals"] = [approval_for(f["events"][0])]
        f["as_of"] = "2000-01-01T00:00:00Z"
        with self.assertRaises(ApprovalError):
            project_fixture(f)

    def test_input_order_does_not_change_artifact_bytes(self):
        f = fixture()
        first = project_fixture(f)
        reversed_fixture = deepcopy(f)
        reversed_fixture["events"].reverse()
        second = project_fixture(reversed_fixture)
        self.assertEqual(canonical_bytes(first["artifacts"]), canonical_bytes(second["artifacts"]))
        self.assertEqual(first["state_sha256"], second["state_sha256"])

    def test_clean_projection_is_byte_identical(self):
        f = fixture()
        self.assertEqual(canonical_bytes(project_fixture(f)), canonical_bytes(project_fixture(f)))

    def test_three_backend_shapes_are_required_strictly(self):
        f = fixture()
        for index in (0, 10, 20):
            bad = deepcopy(f["events"][index])
            bad["unexpected"] = True
            with self.assertRaises(ValidationError):
                TranscriptProjector().ingest([bad], [])

    def test_bool_does_not_alias_sequence_int(self):
        f = fixture()
        bad = deepcopy(f["events"][0])
        bad["seq"] = True
        with self.assertRaises(ValidationError):
            TranscriptProjector().ingest([bad], [])

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ValidationError):
            load_strict_json('{"a":1,"a":2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValidationError):
            load_strict_json('{"a":Infinity}')

    def test_cli_create_exclusive_and_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "fixture.json"
            src.write_bytes((ROOT / "fixture.json").read_bytes())
            out1 = td / "out1.json"
            out2 = td / "out2.json"
            self.assertEqual(cli_main([str(src), str(out1)]), 0)
            self.assertEqual(cli_main([str(src), str(out2)]), 0)
            self.assertEqual(out1.read_bytes(), out2.read_bytes())
            before = out1.read_bytes()
            self.assertEqual(cli_main([str(src), str(out1)]), 2)
            self.assertEqual(out1.read_bytes(), before)

    def test_same_backend_event_id_may_repeat_in_distinct_runs(self):
        f = fixture()
        first = deepcopy(f["events"][0])
        second = deepcopy(first)
        second["run_id"] = "s-run-2"
        result = TranscriptProjector().ingest([first, second], [])
        self.assertEqual(result["artifact_count"], 2)
        self.assertEqual(result["message_count"], 2)
        ids = [m["message_id"] for a in result["artifacts"] for m in a["messages"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_non_scalar_unicode_is_controlled_validation_error(self):
        f = fixture()
        bad = deepcopy(f["events"][0])
        bad["payload"]["text"] = "\ud800"
        with self.assertRaises(ValidationError):
            TranscriptProjector().ingest([bad], [])
        with self.assertRaises(ValidationError):
            canonical_bytes({"bad": "\ud800"})

    def test_cli_lone_surrogate_returns_two_without_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "bad.json"
            out = td / "out.json"
            raw = (ROOT / "fixture.json").read_text(encoding="utf-8")
            raw = raw.replace("alpha one", r"\ud800", 1)
            src.write_text(raw, encoding="utf-8")
            self.assertEqual(cli_main([str(src), str(out)]), 2)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
