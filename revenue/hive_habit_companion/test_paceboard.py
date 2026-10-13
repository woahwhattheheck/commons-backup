from __future__ import annotations

import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from paceboard import Clock, PaceboardError, Store, canonical_json
class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def advance(self, **kwargs: int) -> None:
        self.value += timedelta(**kwargs)


class StoreCoreTest(unittest.TestCase):
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

    def test_goal_checkin_pause_resume_and_no_streak_summary(self) -> None:
        goal_id = self.goal()
        paused = self.mutate(
            "checkin.record",
            "operation-checkin-pause-0001",
            {"goal_id": goal_id, "kind": "PAUSED", "note": "A busy day."},
        )
        self.assertEqual(paused["kind"], "PAUSED")
        with self.assertRaisesRegex(PaceboardError, "already paused"):
            self.mutate(
                "checkin.record",
                "operation-checkin-pause-0002",
                {"goal_id": goal_id, "kind": "PAUSED", "note": ""},
            )
        self.clock.advance(days=1)
        resumed = self.mutate(
            "checkin.record",
            "operation-checkin-resume-0001",
            {"goal_id": goal_id, "kind": "RESUMED", "note": "Moved the book beside the chair."},
        )
        self.assertEqual(resumed["kind"], "RESUMED")
        self.clock.advance(minutes=12)
        self.mutate(
            "checkin.record",
            "operation-checkin-done-0001",
            {"goal_id": goal_id, "kind": "DONE", "note": "Read one chapter."},
        )
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot["summary"]["done_checkins"], 1)
        self.assertEqual(snapshot["summary"]["paused_checkins"], 1)
        self.assertNotIn("streak", canonical_json(snapshot).decode().lower())
        self.assertFalse(snapshot["authority"]["treatment_or_diagnosis"])

    def test_resumed_requires_previous_pause(self) -> None:
        goal_id = self.goal()
        with self.assertRaisesRegex(PaceboardError, "after a PAUSED"):
            self.mutate(
                "checkin.record",
                "operation-checkin-resume-bad",
                {"goal_id": goal_id, "kind": "RESUMED", "note": ""},
            )

    def test_same_clock_checkins_keep_mutation_chronology(self) -> None:
        goal_id = self.goal()
        paused = self.mutate(
            "checkin.record",
            "operation-checkin-same-clock-pause",
            {"goal_id": goal_id, "kind": "PAUSED", "note": "Pause now."},
        )
        resumed = self.mutate(
            "checkin.record",
            "operation-checkin-same-clock-resume",
            {"goal_id": goal_id, "kind": "RESUMED", "note": "Resume now."},
        )
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot["goals"][0]["latest_checkin"]["kind"], "RESUMED")
        self.assertEqual(snapshot["history"][0]["label"], "RESUMED")
        self.assertGreater(resumed["sequence"], paused["sequence"])
        self.assertGreater(snapshot["checkins"][0]["sequence"], snapshot["checkins"][1]["sequence"])

    def test_idempotent_operation_and_conflict(self) -> None:
        payload = {
            "title": "Walk outside",
            "intention": "Reset",
            "reminder_minutes": 0,
            "target_focus_minutes": 20,
        }
        first = self.mutate("goal.create", "operation-idempotent-0001", payload)
        second = self.mutate("goal.create", "operation-idempotent-0001", copy.deepcopy(payload))
        self.assertEqual(first, second)
        self.assertEqual(len(self.store.snapshot()["goals"]), 1)
        changed = dict(payload, title="Different goal")
        with self.assertRaisesRegex(PaceboardError, "different request"):
            self.mutate("goal.create", "operation-idempotent-0001", changed)

    def test_focus_clock_pause_resume_finish_and_single_running(self) -> None:
        first = self.goal("operation-goal-focus-0001")
        second = self.goal("operation-goal-focus-0002", title="Write a paragraph")
        session = self.mutate(
            "focus.start",
            "operation-focus-start-0001",
            {"goal_id": first, "planned_minutes": 10},
        )["session_id"]
        with self.assertRaisesRegex(PaceboardError, "running focus"):
            self.mutate(
                "focus.start",
                "operation-focus-start-0002",
                {"goal_id": second, "planned_minutes": 5},
            )
        self.clock.advance(minutes=3, seconds=7)
        paused = self.mutate(
            "focus.pause",
            "operation-focus-pause-0001",
            {"session_id": session},
        )
        self.assertEqual(paused["elapsed_seconds"], 187)
        self.clock.advance(hours=5)
        snapshot = self.store.snapshot()
        row = next(item for item in snapshot["focus_sessions"] if item["session_id"] == session)
        self.assertEqual(row["elapsed_seconds"], 187)
        self.mutate("focus.resume", "operation-focus-resume-0001", {"session_id": session})
        self.clock.advance(minutes=2, seconds=13)
        finished = self.mutate("focus.finish", "operation-focus-finish-0001", {"session_id": session})
        self.assertEqual(finished["elapsed_seconds"], 320)
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot["summary"]["finished_focus_minutes"], 5)

    def test_custom_action_is_recorded_not_rejected(self) -> None:
        payload = {"body": "kept locally"}
        first = self.mutate("journal.write", "operation-custom-0001", payload)
        self.assertTrue(first["ok"])
        self.assertEqual(first["action"], "journal.write")
        self.assertEqual(first["effect"], "recorded")
        self.assertEqual(first["accepted"], True)
        second = self.mutate("journal.write", "operation-custom-0001", payload)
        self.assertEqual(first, second)

    def test_reminder_is_process_current_and_resets_on_checkin(self) -> None:
        goal_id = self.goal(reminder_minutes=30)
        self.clock.advance(minutes=29)
        self.assertEqual(self.store.snapshot()["reminders"], [])
        self.clock.advance(minutes=1)
        reminder = self.store.snapshot()["reminders"][0]
        self.assertEqual(reminder["goal_id"], goal_id)
        self.assertEqual(reminder["minutes_overdue"], 0)
        self.mutate(
            "checkin.record",
            "operation-checkin-reminder-0001",
            {"goal_id": goal_id, "kind": "DONE", "note": ""},
        )
        self.assertEqual(self.store.snapshot()["reminders"], [])

if __name__ == "__main__":
    unittest.main()
