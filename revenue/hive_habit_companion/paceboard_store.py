"""SQLite workspace and retry-safe mutation coordinator for Paceboard."""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from paceboard_actions import ActionMixin
from paceboard_backup import BackupMixin
from paceboard_common import (
    Clock, PaceboardError, SCHEMA_VERSION, _identifier, _iso, _text,
    canonical_json, sha256_bytes, system_clock,
)
from paceboard_view import ViewMixin


class Store(ActionMixin, BackupMixin, ViewMixin):
    """Thread-safe SQLite-backed Paceboard workspace."""

    def __init__(self, path: str | Path, *, clock: Clock | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock or system_clock()
        self._schema_lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        # sqlite3.executescript() owns its transaction boundary even when a
        # caller has issued BEGIN.  Keep schema installation separate, then
        # initialize/check workspace metadata inside our explicit transaction.
        with self._schema_lock:
            connection = self._connect()
            try:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS workspace_meta (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        schema_version INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        revision INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS goals (
                        goal_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        intention TEXT NOT NULL,
                        state TEXT NOT NULL CHECK (state IN ('ACTIVE','ARCHIVED')),
                        reminder_minutes INTEGER NOT NULL,
                        target_focus_minutes INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS checkins (
                        checkin_id TEXT PRIMARY KEY,
                        goal_id TEXT NOT NULL REFERENCES goals(goal_id) ON DELETE CASCADE,
                        kind TEXT NOT NULL CHECK (kind IN ('DONE','PAUSED','RESUMED')),
                        note TEXT NOT NULL,
                        sequence INTEGER NOT NULL UNIQUE,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS checkins_goal_sequence
                        ON checkins(goal_id, sequence DESC);
                    CREATE TABLE IF NOT EXISTS trigger_notes (
                        note_id TEXT PRIMARY KEY,
                        goal_id TEXT REFERENCES goals(goal_id) ON DELETE SET NULL,
                        body TEXT NOT NULL,
                        sequence INTEGER NOT NULL UNIQUE,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS trigger_notes_sequence
                        ON trigger_notes(sequence DESC);
                    CREATE TABLE IF NOT EXISTS focus_sessions (
                        session_id TEXT PRIMARY KEY,
                        goal_id TEXT NOT NULL REFERENCES goals(goal_id) ON DELETE CASCADE,
                        planned_seconds INTEGER NOT NULL,
                        accumulated_seconds INTEGER NOT NULL,
                        state TEXT NOT NULL CHECK (state IN ('RUNNING','PAUSED','FINISHED')),
                        sequence INTEGER NOT NULL UNIQUE,
                        started_at TEXT NOT NULL,
                        segment_started_at TEXT,
                        finished_at TEXT,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS focus_goal_sequence
                        ON focus_sessions(goal_id, sequence DESC);
                    CREATE TABLE IF NOT EXISTS operations (
                        operation_id TEXT PRIMARY KEY,
                        action TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL,
                        response_json BLOB NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    """
                )
            finally:
                connection.close()

            with self._transaction() as connection:
                row = connection.execute("SELECT schema_version FROM workspace_meta WHERE singleton=1").fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO workspace_meta(singleton,schema_version,created_at,revision) VALUES(1,?,?,0)",
                        (SCHEMA_VERSION, _iso(self.clock.utc())),
                    )
                elif row["schema_version"] != SCHEMA_VERSION:
                    raise RuntimeError(f"Unsupported Paceboard schema version {row['schema_version']}")

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{secrets.token_hex(12)}"

    @staticmethod
    def _require_object(value: Any, field: str = "payload") -> dict[str, Any]:
        if not isinstance(value, dict):
            raise PaceboardError(f"{field} must be an object")
        return value

    @staticmethod
    def _goal(connection: sqlite3.Connection, goal_id: Any, *, active: bool = False) -> sqlite3.Row:
        goal_id = _identifier(goal_id, "goal_id")
        row = connection.execute("SELECT * FROM goals WHERE goal_id=?", (goal_id,)).fetchone()
        if row is None:
            raise PaceboardError("Goal not found", 404, "NOT_FOUND")
        if active and row["state"] != "ACTIVE":
            raise PaceboardError("Archived goals cannot receive new activity", 409, "GOAL_ARCHIVED")
        return row

    @staticmethod
    def _focus(connection: sqlite3.Connection, session_id: Any) -> sqlite3.Row:
        session_id = _identifier(session_id, "session_id")
        row = connection.execute("SELECT * FROM focus_sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise PaceboardError("Focus session not found", 404, "NOT_FOUND")
        return row

    @staticmethod
    def _bump_revision(connection: sqlite3.Connection) -> int:
        connection.execute("UPDATE workspace_meta SET revision=revision+1 WHERE singleton=1")
        return int(connection.execute("SELECT revision FROM workspace_meta WHERE singleton=1").fetchone()[0])

    @staticmethod
    def _next_revision(connection: sqlite3.Connection) -> int:
        """Return the revision that the current successful mutation will own."""
        return int(connection.execute(
            "SELECT revision + 1 FROM workspace_meta WHERE singleton=1"
        ).fetchone()[0])

    def mutate(self, action: Any, operation_id: Any, payload: Any) -> dict[str, Any]:
        action = _text(action, "action", minimum=3, maximum=80)
        operation_id = _identifier(operation_id, "operation_id")
        payload_obj = self._require_object(payload)
        payload_bytes = canonical_json(payload_obj)
        payload_digest = sha256_bytes(payload_bytes)
        with self._transaction() as connection:
            prior = connection.execute(
                "SELECT action,payload_sha256,response_json FROM operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if prior is not None:
                if prior["action"] != action or prior["payload_sha256"] != payload_digest:
                    raise PaceboardError(
                        "operation_id was already used for a different request",
                        409,
                        "OPERATION_CONFLICT",
                    )
                return json.loads(bytes(prior["response_json"]))

            now = self.clock.utc()
            response = self._dispatch(connection, action, payload_obj, now)
            response["operation_id"] = operation_id
            response["revision"] = self._bump_revision(connection)
            response_bytes = canonical_json(response)
            connection.execute(
                "INSERT INTO operations(operation_id,action,payload_sha256,response_json,created_at) VALUES(?,?,?,?,?)",
                (operation_id, action, payload_digest, response_bytes, _iso(now)),
            )
            return response

    def _dispatch(
        self,
        connection: sqlite3.Connection,
        action: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        handlers: Mapping[str, Callable[[sqlite3.Connection, dict[str, Any], datetime], dict[str, Any]]] = {
            "goal.create": self._goal_create,
            "goal.update": self._goal_update,
            "goal.archive": self._goal_archive,
            "checkin.record": self._checkin_record,
            "note.record": self._note_record,
            "focus.start": self._focus_start,
            "focus.pause": self._focus_pause,
            "focus.resume": self._focus_resume,
            "focus.finish": self._focus_finish,
            "item.delete": self._item_delete,
            "backup.restore": self._backup_restore,
            "all.erase": self._erase_all,
        }
        handler = handlers.get(action)
        if handler is not None:
            return handler(connection, payload, now)
        return {
            "ok": True,
            "action": action,
            "accepted": True,
            "effect": "recorded",
        }

