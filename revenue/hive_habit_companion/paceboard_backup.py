"""Canonical backup, restore, and validation for Paceboard."""
from __future__ import annotations

import secrets
import sqlite3
from typing import Any

from paceboard_common import (
    BACKUP_FORMAT, CHECKIN_KINDS, FOCUS_STATES, GOAL_STATES, SCHEMA_VERSION,
    PaceboardError, _identifier, _integer, _iso, _parse_iso, _text,
    canonical_json, sha256_bytes,
)


class BackupMixin:
    @staticmethod
    def _rows(connection: sqlite3.Connection, table: str, order: str) -> list[dict[str, Any]]:
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY {order}")]

    def _backup_payload_from_connection(self, connection: sqlite3.Connection) -> dict[str, Any]:
        running = connection.execute("SELECT 1 FROM focus_sessions WHERE state='RUNNING' LIMIT 1").fetchone()
        if running is not None:
            raise PaceboardError("Pause the running focus session before creating a backup", 409, "FOCUS_RUNNING")
        meta = connection.execute("SELECT schema_version,revision FROM workspace_meta WHERE singleton=1").fetchone()
        return {
            "format": BACKUP_FORMAT,
            "schema_version": int(meta["schema_version"]),
            "revision": int(meta["revision"]),
            "data": {
                "goals": self._rows(connection, "goals", "goal_id"),
                "checkins": self._rows(connection, "checkins", "checkin_id"),
                "trigger_notes": self._rows(connection, "trigger_notes", "note_id"),
                "focus_sessions": self._rows(connection, "focus_sessions", "session_id"),
            },
        }

    def backup_document(self) -> dict[str, Any]:
        connection = self._connect()
        try:
            payload = self._backup_payload_from_connection(connection)
        finally:
            connection.close()
        digest = sha256_bytes(canonical_json(payload))
        return {**payload, "content_sha256": digest}

    def backup_bytes(self) -> bytes:
        return canonical_json(self.backup_document())

    @classmethod
    def _validate_backup(cls, document: Any) -> dict[str, list[dict[str, Any]]]:
        if not isinstance(document, dict):
            raise PaceboardError("backup must be an object")
        required_top = {"format", "schema_version", "revision", "data", "content_sha256"}
        if set(document) != required_top:
            raise PaceboardError("backup fields do not match Paceboard v1")
        if document["format"] != BACKUP_FORMAT or document["schema_version"] != SCHEMA_VERSION:
            raise PaceboardError("Unsupported Paceboard backup format")
        if isinstance(document["revision"], bool) or not isinstance(document["revision"], int) or document["revision"] < 0:
            raise PaceboardError("backup revision is invalid")
        claimed = document["content_sha256"]
        if not isinstance(claimed, str) or len(claimed) != 64:
            raise PaceboardError("backup content_sha256 is invalid")
        payload = {key: document[key] for key in ("format", "schema_version", "revision", "data")}
        actual = sha256_bytes(canonical_json(payload))
        if not secrets.compare_digest(actual, claimed):
            raise PaceboardError("Backup digest does not match its content", 409, "BACKUP_DIGEST_MISMATCH")
        data = document["data"]
        if not isinstance(data, dict) or set(data) != {"goals", "checkins", "trigger_notes", "focus_sessions"}:
            raise PaceboardError("backup data collections are invalid")
        for key, value in data.items():
            if not isinstance(value, list):
                raise PaceboardError(f"backup {key} must be a list")
            if len(value) > 100_000:
                raise PaceboardError(f"backup {key} is too large")

        backup_revision = int(document["revision"])
        event_sequences: set[int] = set()

        def event_sequence(value: Any) -> int:
            sequence = _integer(value, "sequence", minimum=1, maximum=max(1, backup_revision))
            if sequence > backup_revision:
                raise PaceboardError("backup event sequence exceeds its revision")
            if sequence in event_sequences:
                raise PaceboardError("backup contains duplicate event sequence")
            event_sequences.add(sequence)
            return sequence

        goals: list[dict[str, Any]] = []
        goal_ids: set[str] = set()
        for raw in data["goals"]:
            if not isinstance(raw, dict) or set(raw) != {
                "goal_id", "title", "intention", "state", "reminder_minutes", "target_focus_minutes", "created_at", "updated_at"
            }:
                raise PaceboardError("backup goal fields are invalid")
            goal_id = _identifier(raw["goal_id"], "goal_id")
            if goal_id in goal_ids:
                raise PaceboardError("backup contains duplicate goal_id")
            goal_ids.add(goal_id)
            state = raw["state"]
            if state not in GOAL_STATES:
                raise PaceboardError("backup goal state is invalid")
            created = _parse_iso(raw["created_at"], "created_at")
            updated = _parse_iso(raw["updated_at"], "updated_at")
            if updated < created:
                raise PaceboardError("backup goal updated_at precedes created_at")
            reminder = _integer(raw["reminder_minutes"], "reminder_minutes", minimum=0, maximum=10080)
            if 0 < reminder < 5:
                raise PaceboardError("backup reminder_minutes must be zero or at least 5")
            goals.append({
                "goal_id": goal_id,
                "title": _text(raw["title"], "title", minimum=1, maximum=120),
                "intention": _text(raw["intention"], "intention", maximum=500),
                "state": state,
                "reminder_minutes": reminder,
                "target_focus_minutes": _integer(raw["target_focus_minutes"], "target_focus_minutes", minimum=1, maximum=720),
                "created_at": _iso(created),
                "updated_at": _iso(updated),
            })

        checkins: list[dict[str, Any]] = []
        checkin_ids: set[str] = set()
        for raw in data["checkins"]:
            if not isinstance(raw, dict) or set(raw) != {"checkin_id", "goal_id", "kind", "note", "sequence", "created_at"}:
                raise PaceboardError("backup check-in fields are invalid")
            checkin_id = _identifier(raw["checkin_id"], "checkin_id")
            if checkin_id in checkin_ids:
                raise PaceboardError("backup contains duplicate checkin_id")
            checkin_ids.add(checkin_id)
            goal_id = _identifier(raw["goal_id"], "goal_id")
            if goal_id not in goal_ids:
                raise PaceboardError("backup check-in references an unknown goal")
            if raw["kind"] not in CHECKIN_KINDS:
                raise PaceboardError("backup check-in kind is invalid")
            checkins.append({
                "checkin_id": checkin_id,
                "goal_id": goal_id,
                "kind": raw["kind"],
                "note": _text(raw["note"], "note", maximum=1000),
                "sequence": event_sequence(raw["sequence"]),
                "created_at": _iso(_parse_iso(raw["created_at"], "created_at")),
            })

        notes: list[dict[str, Any]] = []
        note_ids: set[str] = set()
        for raw in data["trigger_notes"]:
            if not isinstance(raw, dict) or set(raw) != {"note_id", "goal_id", "body", "sequence", "created_at"}:
                raise PaceboardError("backup note fields are invalid")
            note_id = _identifier(raw["note_id"], "note_id")
            if note_id in note_ids:
                raise PaceboardError("backup contains duplicate note_id")
            note_ids.add(note_id)
            goal_id = raw["goal_id"]
            if goal_id is not None:
                goal_id = _identifier(goal_id, "goal_id")
                if goal_id not in goal_ids:
                    raise PaceboardError("backup note references an unknown goal")
            notes.append({
                "note_id": note_id,
                "goal_id": goal_id,
                "body": _text(raw["body"], "body", minimum=1, maximum=2000),
                "sequence": event_sequence(raw["sequence"]),
                "created_at": _iso(_parse_iso(raw["created_at"], "created_at")),
            })

        sessions: list[dict[str, Any]] = []
        session_ids: set[str] = set()
        running_count = 0
        for raw in data["focus_sessions"]:
            expected = {
                "session_id", "goal_id", "planned_seconds", "accumulated_seconds", "state", "sequence",
                "started_at", "segment_started_at", "finished_at", "updated_at",
            }
            if not isinstance(raw, dict) or set(raw) != expected:
                raise PaceboardError("backup focus-session fields are invalid")
            session_id = _identifier(raw["session_id"], "session_id")
            if session_id in session_ids:
                raise PaceboardError("backup contains duplicate session_id")
            session_ids.add(session_id)
            goal_id = _identifier(raw["goal_id"], "goal_id")
            if goal_id not in goal_ids:
                raise PaceboardError("backup focus session references an unknown goal")
            state = raw["state"]
            if state not in FOCUS_STATES:
                raise PaceboardError("backup focus state is invalid")
            if state == "RUNNING":
                running_count += 1
            started = _parse_iso(raw["started_at"], "started_at")
            updated = _parse_iso(raw["updated_at"], "updated_at")
            if updated < started:
                raise PaceboardError("backup focus updated_at precedes started_at")
            segment_raw = raw["segment_started_at"]
            segment = None if segment_raw is None else _parse_iso(segment_raw, "segment_started_at")
            finished_raw = raw["finished_at"]
            finished = None if finished_raw is None else _parse_iso(finished_raw, "finished_at")
            if state == "RUNNING" and segment is None:
                raise PaceboardError("running backup session is missing segment_started_at")
            if state != "RUNNING" and segment is not None:
                raise PaceboardError("non-running backup session may not have segment_started_at")
            if state == "FINISHED" and finished is None:
                raise PaceboardError("finished backup session is missing finished_at")
            if state != "FINISHED" and finished is not None:
                raise PaceboardError("unfinished backup session may not have finished_at")
            sessions.append({
                "session_id": session_id,
                "goal_id": goal_id,
                "planned_seconds": _integer(raw["planned_seconds"], "planned_seconds", minimum=60, maximum=720 * 60),
                "accumulated_seconds": _integer(raw["accumulated_seconds"], "accumulated_seconds", minimum=0, maximum=10 * 365 * 24 * 3600),
                "state": state,
                "sequence": event_sequence(raw["sequence"]),
                "started_at": _iso(started),
                "segment_started_at": None if segment is None else _iso(segment),
                "finished_at": None if finished is None else _iso(finished),
                "updated_at": _iso(updated),
            })
        if running_count > 1:
            raise PaceboardError("backup contains more than one running focus session")
        return {"goals": goals, "checkins": checkins, "trigger_notes": notes, "focus_sessions": sessions}

