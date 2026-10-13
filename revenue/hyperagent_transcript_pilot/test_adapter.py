from __future__ import annotations

import ast
import copy
from pathlib import Path
import unittest

from .adapter import EventConflict, ProjectionLedger, SchemaError, load_fixture, normalize_event


HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture.json"


class HyperagentTranscriptPilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = load_fixture(FIXTURE)

    def test_acceptance_fixture_is_30_events_three_backends_six_transcripts(self) -> None:
        self.assertEqual(30, len(self.events))
        self.assertEqual({"alpha", "beta", "gamma"}, {normalize_event(e).backend for e in self.events})
        ledger = ProjectionLedger()
        result = ledger.project_batch(self.events)
        self.assertEqual(30, len(result.new_messages))
        self.assertEqual(0, result.duplicate_event_count)
        self.assertEqual((), result.rejected)
        snapshot = ledger.snapshot()
        self.assertEqual(6, snapshot["transcript_count"])
        self.assertEqual(30, snapshot["message_count"])
        self.assertTrue(all(len(item["messages"]) == 5 for item in snapshot["transcripts"]))

    def test_full_replay_emits_zero_duplicate_logical_messages(self) -> None:
        ledger = ProjectionLedger()
        ledger.project_batch(self.events)
        before = ledger.snapshot_bytes()
        replay = ledger.project_batch(self.events)
        self.assertEqual((), replay.new_messages)
        self.assertEqual(30, replay.duplicate_event_count)
        self.assertEqual(before, ledger.snapshot_bytes())

    def test_clean_projections_are_byte_identical_even_when_input_order_changes(self) -> None:
        a = ProjectionLedger()
        b = ProjectionLedger()
        a.project_batch(self.events)
        b.project_batch(list(reversed(self.events)))
        self.assertEqual(a.snapshot_bytes(), b.snapshot_bytes())

    def test_same_source_id_changed_semantics_fails_atomically(self) -> None:
        ledger = ProjectionLedger()
        ledger.project_batch([self.events[0]])
        before = ledger.snapshot_bytes()
        new_event = copy.deepcopy(self.events[1])
        conflict = copy.deepcopy(self.events[0])
        conflict["text"] = "tampered text"
        with self.assertRaises(EventConflict):
            ledger.project_batch([new_event, conflict])
        self.assertEqual(before, ledger.snapshot_bytes())

    def test_invalid_approvals_fail_closed_with_zero_outbound(self) -> None:
        action = next(copy.deepcopy(e) for e in self.events if normalize_event(e).backend == "alpha" and normalize_event(e).kind == "action")
        cases = []
        missing = copy.deepcopy(action)
        missing.pop("approval")
        cases.append(missing)
        foreign = copy.deepcopy(action)
        foreign["approval"]["run_id"] = "foreign-run"
        cases.append(foreign)
        stale = copy.deepcopy(action)
        stale["approval"]["generation"] = 0
        cases.append(stale)
        denied = copy.deepcopy(action)
        denied["approval"]["decision"] = "denied"
        cases.append(denied)
        extra = copy.deepcopy(action)
        extra["approval"]["unexpected"] = True
        cases.append(extra)

        for candidate in cases:
            with self.subTest(candidate=candidate):
                ledger = ProjectionLedger()
                result = ledger.project_batch([candidate])
                self.assertEqual((), result.new_messages)
                self.assertEqual(1, len(result.rejected))
                self.assertEqual(0, ledger.snapshot()["message_count"])

    def test_approval_is_detached_from_caller_owned_nested_graph(self) -> None:
        action = next(copy.deepcopy(e) for e in self.events if e["backend"] == "alpha" and e.get("kind") == "action")
        canonical = normalize_event(action)
        original_digest = canonical.semantic_digest()
        action["approval"]["decision"] = "denied"
        self.assertEqual("approved", canonical.approval["decision"])
        self.assertEqual(original_digest, canonical.semantic_digest())

    def test_rejected_source_id_cannot_be_reused_with_changed_approval(self) -> None:
        action = next(copy.deepcopy(e) for e in self.events if e["backend"] == "alpha" and e.get("kind") == "action")
        invalid = copy.deepcopy(action)
        invalid["approval"]["decision"] = "denied"
        ledger = ProjectionLedger()
        first = ledger.project_batch([invalid])
        self.assertEqual((), first.new_messages)
        self.assertEqual(1, len(first.rejected))
        with self.assertRaises(EventConflict):
            ledger.project_batch([action])
        self.assertEqual(0, ledger.snapshot()["message_count"])

    def test_duplicate_inside_one_batch_is_one_message_and_one_duplicate(self) -> None:
        event = self.events[0]
        ledger = ProjectionLedger()
        result = ledger.project_batch([event, copy.deepcopy(event)])
        self.assertEqual(1, len(result.new_messages))
        self.assertEqual(1, result.duplicate_event_count)
        self.assertEqual(1, ledger.snapshot()["message_count"])

    def test_bad_schema_and_unknown_backend_fail_before_state_change(self) -> None:
        ledger = ProjectionLedger()
        bad = copy.deepcopy(self.events[0])
        bad["backend"] = "unknown"
        with self.assertRaises(SchemaError):
            ledger.project_batch([bad])
        self.assertEqual(0, ledger.snapshot()["message_count"])

    def test_adapter_has_no_network_provider_imports(self) -> None:
        tree = ast.parse((HERE / "adapter.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue({"socket", "requests", "urllib", "http", "slack_sdk"}.isdisjoint(imported))


if __name__ == "__main__":
    unittest.main()
