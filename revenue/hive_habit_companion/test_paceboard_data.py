from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from build_release import build
from paceboard import Clock, PaceboardError, Store, canonical_json, sha256_bytes
class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def advance(self, **kwargs: int) -> None:
        self.value += timedelta(**kwargs)


class StoreDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.clock = MutableClock(datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc))
        self.store = Store(Path(self.temporary.name) / "paceboard.sqlite3", clock=Clock(self.clock.now))

    def mutate(self, action: str, operation: str, payload: dict) -> dict:
        return self.store.mutate(action, operation, payload)

    def goal(self, operation: str = "operation-goal-0001", **overrides: object) -> str:
        payload = {
            "title": "Read ten minutes",
            "intention": "Leave work mode gently",
            "reminder_minutes": 30,
            "target_focus_minutes": 10,
        }
        payload.update(overrides)
        return self.mutate("goal.create", operation, payload)["goal_id"]

    def test_backup_is_deterministic_digest_bound_and_restoreable(self) -> None:
        goal_id = self.goal()
        self.mutate(
            "note.record",
            "operation-note-0001",
            {"goal_id": goal_id, "body": "Task ambiguity was the trigger."},
        )
        self.mutate(
            "checkin.record",
            "operation-checkin-0001",
            {"goal_id": goal_id, "kind": "DONE", "note": "Outlined the next step."},
        )
        first = self.store.backup_bytes()
        second = self.store.backup_bytes()
        self.assertEqual(first, second)
        document = json.loads(first)
        payload = {key: document[key] for key in ("format", "schema_version", "revision", "data")}
        self.assertEqual(document["content_sha256"], sha256_bytes(canonical_json(payload)))

        restored_path = Path(self.temporary.name) / "restored.sqlite3"
        restored = Store(restored_path, clock=Clock(self.clock.now))
        result = restored.mutate(
            "backup.restore",
            "operation-restore-0001",
            {"backup": document},
        )
        self.assertEqual(result["counts"]["goals"], 1)
        self.assertEqual({row["label"] for row in restored.snapshot()["history"]}, {"DONE", "TRIGGER_NOTE"})
        restored_document = restored.backup_document()
        self.assertEqual(restored_document["data"], document["data"])

    def test_backup_tamper_and_running_session_fail_closed(self) -> None:
        goal_id = self.goal()
        session = self.mutate(
            "focus.start",
            "operation-focus-start-backup",
            {"goal_id": goal_id, "planned_minutes": 10},
        )["session_id"]
        with self.assertRaisesRegex(PaceboardError, "Pause the running"):
            self.store.backup_bytes()
        self.mutate("focus.pause", "operation-focus-pause-backup", {"session_id": session})
        document = self.store.backup_document()
        document["data"]["goals"][0]["title"] = "Tampered"
        with self.assertRaisesRegex(PaceboardError, "digest"):
            self.mutate("backup.restore", "operation-restore-tamper", {"backup": document})

    def test_scoped_delete_cascade_and_full_erase(self) -> None:
        goal_id = self.goal()
        self.mutate(
            "note.record",
            "operation-note-delete-0001",
            {"goal_id": goal_id, "body": "Private note"},
        )
        self.mutate(
            "checkin.record",
            "operation-checkin-delete-0001",
            {"goal_id": goal_id, "kind": "DONE", "note": ""},
        )
        self.mutate("item.delete", "operation-delete-goal-0001", {"entity": "goal", "id": goal_id})
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot["goals"], [])
        self.assertEqual(snapshot["checkins"], [])
        self.assertEqual(snapshot["trigger_notes"][0]["goal_id"], None)
        with self.assertRaisesRegex(PaceboardError, "Type ERASE"):
            self.mutate("all.erase", "operation-erase-bad-0001", {"confirm": "erase"})
        self.mutate("all.erase", "operation-erase-good-0001", {"confirm": "ERASE PACEBOARD"})
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot["history"], [])
        self.assertEqual(snapshot["goals"], [])

    def test_csv_is_stable_and_has_private_timeline(self) -> None:
        goal_id = self.goal()
        self.mutate(
            "note.record",
            "operation-note-csv-0001",
            {"goal_id": goal_id, "body": "A private, comma-bearing note"},
        )
        first = self.store.timeline_csv_bytes()
        second = self.store.timeline_csv_bytes()
        self.assertEqual(first, second)
        text = first.decode()
        self.assertIn("created_at,type,id,goal_id,goal_title,label,detail\n", text)
        self.assertIn('"A private, comma-bearing note"', text)

    def test_archive_blocks_new_activity_and_running_focus_blocks_delete(self) -> None:
        goal_id = self.goal()
        session = self.mutate(
            "focus.start",
            "operation-focus-delete-0001",
            {"goal_id": goal_id, "planned_minutes": 5},
        )["session_id"]
        with self.assertRaisesRegex(PaceboardError, "active focus"):
            self.mutate("item.delete", "operation-delete-running-0001", {"entity": "goal", "id": goal_id})
        self.mutate("focus.finish", "operation-focus-finish-delete-0001", {"session_id": session})
        self.mutate("goal.archive", "operation-archive-0001", {"goal_id": goal_id, "state": "ARCHIVED"})
        with self.assertRaisesRegex(PaceboardError, "Archived goals"):
            self.mutate(
                "checkin.record",
                "operation-checkin-archived-0001",
                {"goal_id": goal_id, "kind": "DONE", "note": ""},
            )


class ReleasePackageTest(unittest.TestCase):
    def test_source_package_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "one.zip"
            second = Path(directory) / "two.zip"
            receipt_one = build(first)
            receipt_two = build(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(receipt_one["artifact_sha256"], receipt_two["artifact_sha256"])
            self.assertGreaterEqual(receipt_one["file_count"], 10)

if __name__ == "__main__":
    unittest.main()
