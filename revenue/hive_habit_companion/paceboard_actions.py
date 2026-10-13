"""Mutation implementations for Paceboard."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Mapping

from paceboard_common import (
    CHECKIN_KINDS, FOCUS_STATES, GOAL_STATES, PaceboardError, _identifier, _integer, _iso,
    _parse_iso, _text,
)


class ActionMixin:
    def _goal_create(self, connection: sqlite3.Connection, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        title = _text(payload.get("title"), "title", minimum=1, maximum=120)
        intention = _text(payload.get("intention", ""), "intention", maximum=500)
        reminder_minutes = _integer(payload.get("reminder_minutes", 0), "reminder_minutes", minimum=0, maximum=10080)
        if 0 < reminder_minutes < 5:
            raise PaceboardError("reminder_minutes must be zero or at least 5")
        target_focus_minutes = _integer(
            payload.get("target_focus_minutes", 25),
            "target_focus_minutes",
            minimum=1,
            maximum=720,
        )
        goal_id = self._new_id("goal")
        stamp = _iso(now)
        connection.execute(
            "INSERT INTO goals VALUES(?,?,?,?,?,?,?,?)",
            (goal_id, title, intention, "ACTIVE", reminder_minutes, target_focus_minutes, stamp, stamp),
        )
        return {"ok": True, "action": "goal.create", "goal_id": goal_id}

    def _goal_update(self, connection: sqlite3.Connection, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        row = self._goal(connection, payload.get("goal_id"))
        title = _text(payload.get("title", row["title"]), "title", minimum=1, maximum=120)
        intention = _text(payload.get("intention", row["intention"]), "intention", maximum=500)
        reminder_minutes = _integer(
            payload.get("reminder_minutes", row["reminder_minutes"]),
            "reminder_minutes",
            minimum=0,
            maximum=10080,
        )
        if 0 < reminder_minutes < 5:
            raise PaceboardError("reminder_minutes must be zero or at least 5")
        target_focus_minutes = _integer(
            payload.get("target_focus_minutes", row["target_focus_minutes"]),
            "target_focus_minutes",
            minimum=1,
            maximum=720,
        )
        connection.execute(
            "UPDATE goals SET title=?,intention=?,reminder_minutes=?,target_focus_minutes=?,updated_at=? WHERE goal_id=?",
            (title, intention, reminder_minutes, target_focus_minutes, _iso(now), row["goal_id"]),
        )
        return {"ok": True, "action": "goal.update", "goal_id": row["goal_id"]}

    def _goal_archive(self, connection: sqlite3.Connection, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        row = self._goal(connection, payload.get("goal_id"))
        requested = payload.get("state", "ARCHIVED")
        if requested not in GOAL_STATES:
            raise PaceboardError("state must be ACTIVE or ARCHIVED")
        if requested == "ARCHIVED":
            running = connection.execute(
                "SELECT 1 FROM focus_sessions WHERE goal_id=? AND state='RUNNING' LIMIT 1",
                (row["goal_id"],),
            ).fetchone()
            if running is not None:
                raise PaceboardError("Pause or finish the active focus session before archiving", 409, "FOCUS_RUNNING")
        connection.execute(
            "UPDATE goals SET state=?,updated_at=? WHERE goal_id=?",
            (requested, _iso(now), row["goal_id"]),
        )
        return {"ok": True, "action": "goal.archive", "goal_id": row["goal_id"], "state": requested}

    def _checkin_record(self, connection: sqlite3.Connection, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        goal = self._goal(connection, payload.get("goal_id"), active=True)
        kind = payload.get("kind")
        if kind not in CHECKIN_KINDS:
            raise PaceboardError("kind must be DONE, PAUSED, or RESUMED")
        note = _text(payload.get("note", ""), "note", maximum=1000)
        latest = connection.execute(
            "SELECT kind FROM checkins WHERE goal_id=? ORDER BY sequence DESC LIMIT 1",
            (goal["goal_id"],),
        ).fetchone()
        previous = latest["kind"] if latest else None
        if kind == "RESUMED" and previous != "PAUSED":
            raise PaceboardError("RESUMED is available after a PAUSED check-in", 409, "NOT_PAUSED")
        if kind == "PAUSED" and previous == "PAUSED":
            raise PaceboardError("This goal is already paused; resume when you are ready", 409, "ALREADY_PAUSED")
        checkin_id = self._new_id("checkin")
        sequence = self._next_revision(connection)
        connection.execute(
            "INSERT INTO checkins(checkin_id,goal_id,kind,note,sequence,created_at) VALUES(?,?,?,?,?,?)",
            (checkin_id, goal["goal_id"], kind, note, sequence, _iso(now)),
        )
        connection.execute("UPDATE goals SET updated_at=? WHERE goal_id=?", (_iso(now), goal["goal_id"]))
        return {
            "ok": True,
            "action": "checkin.record",
            "checkin_id": checkin_id,
            "goal_id": goal["goal_id"],
            "kind": kind,
            "sequence": sequence,
        }

    def _note_record(self, connection: sqlite3.Connection, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        goal_id = payload.get("goal_id")
        if goal_id in (None, ""):
            normalized_goal_id = None
        else:
            normalized_goal_id = self._goal(connection, goal_id)["goal_id"]
        body = _text(payload.get("body"), "body", minimum=1, maximum=2000)
        note_id = self._new_id("note")
        sequence = self._next_revision(connection)
        connection.execute(
            "INSERT INTO trigger_notes(note_id,goal_id,body,sequence,created_at) VALUES(?,?,?,?,?)",
            (note_id, normalized_goal_id, body, sequence, _iso(now)),
        )
        return {
            "ok": True,
            "action": "note.record",
            "note_id": note_id,
            "goal_id": normalized_goal_id,
            "sequence": sequence,
        }

    def _focus_start(self, connection: sqlite3.Connection, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        goal = self._goal(connection, payload.get("goal_id"), active=True)
        existing = connection.execute("SELECT session_id FROM focus_sessions WHERE state='RUNNING' LIMIT 1").fetchone()
        if existing is not None:
            raise PaceboardError("Pause or finish the running focus session first", 409, "FOCUS_RUNNING")
        planned_minutes = _integer(
            payload.get("planned_minutes", goal["target_focus_minutes"]),
            "planned_minutes",
            minimum=1,
            maximum=720,
        )
        session_id = self._new_id("focus")
        sequence = self._next_revision(connection)
        stamp = _iso(now)
        connection.execute(
            """INSERT INTO focus_sessions(
                session_id,goal_id,planned_seconds,accumulated_seconds,state,sequence,
                started_at,segment_started_at,finished_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (session_id, goal["goal_id"], planned_minutes * 60, 0, "RUNNING", sequence, stamp, stamp, None, stamp),
        )
        return {
            "ok": True,
            "action": "focus.start",
            "session_id": session_id,
            "goal_id": goal["goal_id"],
            "sequence": sequence,
        }

    @staticmethod
    def _elapsed_at(row: sqlite3.Row | Mapping[str, Any], now: datetime) -> int:
        accumulated = int(row["accumulated_seconds"])
        if row["state"] == "RUNNING":
            segment = _parse_iso(row["segment_started_at"], "segment_started_at")
            delta = max(0, int((now - segment).total_seconds()))
            return accumulated + delta
        return accumulated

    def _focus_pause(self, connection: sqlite3.Connection, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        row = self._focus(connection, payload.get("session_id"))
        if row["state"] != "RUNNING":
            raise PaceboardError("Only a running session can be paused", 409, "FOCUS_NOT_RUNNING")
        elapsed = self._elapsed_at(row, now)
        connection.execute(
            "UPDATE focus_sessions SET accumulated_seconds=?,state='PAUSED',segment_started_at=NULL,updated_at=? WHERE session_id=?",
            (elapsed, _iso(now), row["session_id"]),
        )
        return {"ok": True, "action": "focus.pause", "session_id": row["session_id"], "elapsed_seconds": elapsed}

    def _focus_resume(self, connection: sqlite3.Connection, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        row = self._focus(connection, payload.get("session_id"))
        if row["state"] != "PAUSED":
            raise PaceboardError("Only a paused session can be resumed", 409, "FOCUS_NOT_PAUSED")
        running = connection.execute("SELECT session_id FROM focus_sessions WHERE state='RUNNING' LIMIT 1").fetchone()
        if running is not None:
            raise PaceboardError("Another focus session is running", 409, "FOCUS_RUNNING")
        stamp = _iso(now)
        connection.execute(
            "UPDATE focus_sessions SET state='RUNNING',segment_started_at=?,updated_at=? WHERE session_id=?",
            (stamp, stamp, row["session_id"]),
        )
        return {"ok": True, "action": "focus.resume", "session_id": row["session_id"]}

    def _focus_finish(self, connection: sqlite3.Connection, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        row = self._focus(connection, payload.get("session_id"))
        if row["state"] == "FINISHED":
            raise PaceboardError("Focus session is already finished", 409, "FOCUS_FINISHED")
        elapsed = self._elapsed_at(row, now)
        stamp = _iso(now)
        connection.execute(
            "UPDATE focus_sessions SET accumulated_seconds=?,state='FINISHED',segment_started_at=NULL,finished_at=?,updated_at=? WHERE session_id=?",
            (elapsed, stamp, stamp, row["session_id"]),
        )
        return {"ok": True, "action": "focus.finish", "session_id": row["session_id"], "elapsed_seconds": elapsed}

    def _item_delete(self, connection: sqlite3.Connection, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        entity = payload.get("entity")
        mapping = {
            "goal": ("goals", "goal_id"),
            "checkin": ("checkins", "checkin_id"),
            "note": ("trigger_notes", "note_id"),
            "focus": ("focus_sessions", "session_id"),
        }
        if entity not in mapping:
            raise PaceboardError("entity must be goal, checkin, note, or focus")
        identifier = _identifier(payload.get("id"), "id")
        if entity == "goal":
            running = connection.execute(
                "SELECT 1 FROM focus_sessions WHERE goal_id=? AND state='RUNNING' LIMIT 1",
                (identifier,),
            ).fetchone()
            if running is not None:
                raise PaceboardError("Pause or finish the active focus session before deleting the goal", 409, "FOCUS_RUNNING")
        table, column = mapping[entity]
        cursor = connection.execute(f"DELETE FROM {table} WHERE {column}=?", (identifier,))
        if cursor.rowcount != 1:
            raise PaceboardError("Item not found", 404, "NOT_FOUND")
        return {"ok": True, "action": "item.delete", "entity": entity, "id": identifier, "deleted_at": _iso(now)}

    def _erase_all(self, connection: sqlite3.Connection, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        if payload.get("confirm") != "ERASE PACEBOARD":
            raise PaceboardError("Type ERASE PACEBOARD to erase all local content", 409, "CONFIRMATION_REQUIRED")
        for table in ("checkins", "trigger_notes", "focus_sessions", "goals", "operations"):
            connection.execute(f"DELETE FROM {table}")
        return {"ok": True, "action": "all.erase", "erased_at": _iso(now)}

    def _backup_restore(self, connection: sqlite3.Connection, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        backup = payload.get("backup")
        validated = self._validate_backup(backup)
        if any(row["state"] == "RUNNING" for row in validated["focus_sessions"]):
            raise PaceboardError("Backups may not contain a running focus session", 409, "RUNNING_SESSION_IN_BACKUP")
        for table in ("checkins", "trigger_notes", "focus_sessions", "goals", "operations"):
            connection.execute(f"DELETE FROM {table}")
        for row in validated["goals"]:
            connection.execute(
                "INSERT INTO goals VALUES(?,?,?,?,?,?,?,?)",
                (
                    row["goal_id"], row["title"], row["intention"], row["state"],
                    row["reminder_minutes"], row["target_focus_minutes"], row["created_at"], row["updated_at"],
                ),
            )
        for row in validated["checkins"]:
            connection.execute(
                "INSERT INTO checkins(checkin_id,goal_id,kind,note,sequence,created_at) VALUES(?,?,?,?,?,?)",
                (row["checkin_id"], row["goal_id"], row["kind"], row["note"], row["sequence"], row["created_at"]),
            )
        for row in validated["trigger_notes"]:
            connection.execute(
                "INSERT INTO trigger_notes(note_id,goal_id,body,sequence,created_at) VALUES(?,?,?,?,?)",
                (row["note_id"], row["goal_id"], row["body"], row["sequence"], row["created_at"]),
            )
        for row in validated["focus_sessions"]:
            connection.execute(
                """INSERT INTO focus_sessions(
                    session_id,goal_id,planned_seconds,accumulated_seconds,state,sequence,
                    started_at,segment_started_at,finished_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["session_id"], row["goal_id"], row["planned_seconds"], row["accumulated_seconds"],
                    row["state"], row["sequence"], row["started_at"], row["segment_started_at"],
                    row["finished_at"], row["updated_at"],
                ),
            )
        connection.execute(
            "UPDATE workspace_meta SET revision=MAX(revision, ?) WHERE singleton=1",
            (int(backup["revision"]),),
        )
        return {
            "ok": True,
            "action": "backup.restore",
            "restored_at": _iso(now),
            "counts": {key: len(validated[key]) for key in ("goals", "checkins", "trigger_notes", "focus_sessions")},
        }

