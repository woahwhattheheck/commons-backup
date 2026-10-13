#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import recruiting_coordination as rc  # noqa: E402


def fixture() -> dict:
    return {
        "schema": "recruiting-coordination-v1",
        "people": [
            {"id": "cand-ada", "kind": "candidate", "name": "Ada Chen", "contact": "ada@example.test", "availability": [
                {"start": "2026-09-14T13:00:00Z", "end": "2026-09-14T15:00:00Z"},
                {"start": "2026-09-15T16:00:00Z", "end": "2026-09-15T18:00:00Z"}
            ]},
            {"id": "cand-linus", "kind": "candidate", "name": "Linus Ray", "contact": "linus@example.test", "availability": [
                {"start": "2026-09-14T14:00:00Z", "end": "2026-09-14T16:00:00Z"}
            ]},
            {"id": "iv-1", "kind": "interviewer", "name": "Inez Patel", "contact": "inez@example.test", "availability": [
                {"start": "2026-09-14T13:30:00Z", "end": "2026-09-14T15:30:00Z"},
                {"start": "2026-09-15T16:00:00Z", "end": "2026-09-15T17:30:00Z"}
            ]},
            {"id": "iv-2", "kind": "interviewer", "name": "Mateo Green", "contact": "mateo@example.test", "availability": [
                {"start": "2026-09-14T13:45:00Z", "end": "2026-09-14T15:00:00Z"},
                {"start": "2026-09-15T16:30:00Z", "end": "2026-09-15T18:00:00Z"}
            ]},
            {"id": "iv-3", "kind": "interviewer", "name": "Priya Shah", "contact": "priya@example.test", "availability": [
                {"start": "2026-09-14T14:00:00Z", "end": "2026-09-14T16:00:00Z"}
            ]},
            {"id": "rec-1", "kind": "recruiter", "name": "Rae Morgan", "contact": "rae@example.test", "availability": []}
        ],
        "candidates": [
            {"id": "app-001", "person_id": "cand-ada", "role": "Support Engineer", "interviewer_ids": ["iv-1", "iv-2"], "recruiter_id": "rec-1"},
            {"id": "app-002", "person_id": "cand-linus", "role": "Implementation Specialist", "interviewer_ids": ["iv-1", "iv-3"], "recruiter_id": "rec-1"}
        ],
        "interviews": []
    }


class RecruitingCoordinationTests(unittest.TestCase):
    def test_common_slots_require_candidate_and_both_interviewers(self) -> None:
        ws = fixture()
        slots = rc.available_slots(ws, "app-001", duration_minutes=45, step_minutes=15)
        self.assertEqual(slots[:3], [
            {"start": "2026-09-14T13:45:00Z", "end": "2026-09-14T14:30:00Z"},
            {"start": "2026-09-14T14:00:00Z", "end": "2026-09-14T14:45:00Z"},
            {"start": "2026-09-14T14:15:00Z", "end": "2026-09-14T15:00:00Z"},
        ])
        self.assertIn({"start": "2026-09-15T16:30:00Z", "end": "2026-09-15T17:15:00Z"}, slots)

    def test_schedule_packet_is_scoped_and_never_sends_or_decides(self) -> None:
        ws = fixture()
        interview = rc.schedule_interview(ws, "app-001", "2026-09-14T14:00:00Z")
        packet = rc.coordination_packet(ws, interview["id"])
        dumped = json.dumps(packet)
        self.assertEqual(packet["automatic_sends"], 0)
        self.assertFalse(packet["hiring_decisions"])
        self.assertFalse(packet["ranking"])
        self.assertFalse(packet["rejection"])
        self.assertEqual(len(packet["drafts"]), 3)
        self.assertTrue(all(row["send"] is False for row in packet["drafts"]))
        self.assertIn("Ada Chen", dumped)
        self.assertIn("Inez Patel", dumped)
        self.assertIn("Mateo Green", dumped)
        self.assertNotIn("Linus Ray", dumped)
        self.assertNotIn("linus@example.test", dumped)
        self.assertNotIn("app-002", dumped)

    def test_reschedule_keeps_history_and_refreshes_drafts(self) -> None:
        ws = fixture()
        interview = rc.schedule_interview(ws, "app-001", "2026-09-14T14:00:00Z")
        moved = rc.reschedule_interview(ws, interview["id"], "2026-09-15T16:30:00Z")
        self.assertEqual(moved["status"], "rescheduled")
        self.assertEqual(moved["version"], 2)
        self.assertEqual(moved["previous_slots"], [
            {"start": "2026-09-14T14:00:00Z", "end": "2026-09-14T14:45:00Z"}
        ])
        packet = rc.coordination_packet(ws, interview["id"])
        self.assertTrue(all("updated" in row["subject"].lower() for row in packet["drafts"]))
        self.assertEqual(packet["handoff"]["previous_slots"], moved["previous_slots"])

    def test_shared_interviewer_conflict_is_rejected(self) -> None:
        ws = fixture()
        rc.schedule_interview(ws, "app-002", "2026-09-14T14:00:00Z")
        with self.assertRaisesRegex(rc.CoordinationError, "not available"):
            rc.schedule_interview(ws, "app-001", "2026-09-14T14:00:00Z")

    def test_unavailable_reschedule_is_atomic(self) -> None:
        ws = fixture()
        interview = rc.schedule_interview(ws, "app-001", "2026-09-14T14:00:00Z")
        before = copy.deepcopy(ws)
        with self.assertRaisesRegex(rc.CoordinationError, "not available"):
            rc.reschedule_interview(ws, interview["id"], "2026-09-14T18:00:00Z")
        self.assertEqual(ws, before)

    def test_workspace_rejects_hiring_decision_fields(self) -> None:
        ws = fixture()
        ws["candidates"][0]["score"] = 99
        with self.assertRaisesRegex(rc.CoordinationError, "hiring-decision field"):
            rc.validate_workspace(ws)

    def test_cli_schedule_persists_atomically_and_packet_is_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workspace.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(HERE / "recruiting_coordination.py"), str(path), "schedule", "app-001", "2026-09-14T14:00:00Z"],
                check=True, capture_output=True, text=True,
            )
            scheduled = json.loads(proc.stdout)
            self.assertEqual(scheduled["status"], "scheduled")
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["interviews"]), 1)
            packet_proc = subprocess.run(
                [sys.executable, str(HERE / "recruiting_coordination.py"), str(path), "packet", scheduled["id"]],
                check=True, capture_output=True, text=True,
            )
            packet = json.loads(packet_proc.stdout)
            self.assertEqual(packet["automatic_sends"], 0)
            self.assertEqual(packet["candidate_id"], "app-001")
            self.assertFalse(any(row["send"] for row in packet["drafts"]))

    def test_reminder_drafts_stay_unsent(self) -> None:
        ws = fixture()
        interview = rc.schedule_interview(ws, "app-001", "2026-09-14T14:00:00Z")
        packet = rc.reminder_packet(ws, interview["id"])
        self.assertEqual(packet["kind"], "reminder")
        self.assertTrue(all(row["subject"].startswith("Reminder:") for row in packet["drafts"]))
        self.assertTrue(all(row["send"] is False for row in packet["drafts"]))


if __name__ == "__main__":
    unittest.main()
