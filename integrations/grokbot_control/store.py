#!/usr/bin/env python3
"""Durable run + event store for GrokBot peer control."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

STATUSES = frozenset({
    "queued",
    "running",
    "completed",
    "error",
    "cancelled",
    "interrupted",
})
TERMINAL = frozenset({"completed", "error", "cancelled", "interrupted"})

CASE_KEYS = ("offer_id", "case_ref", "client_reference_id", "sku")
_CASE_KEY_SET = frozenset(CASE_KEYS)
_MAX_CASE_LEN = 200


def normalize_case(case: Any) -> dict[str, str] | None:
    """Normalize optional paid-case metadata for durable run linkage.

    Accepts a dict with optional string keys offer_id / case_ref /
    client_reference_id / sku. Empty values and unknown keys are dropped.
    Returns None when nothing remains. Raises ValueError on bad shapes.
    """
    if case is None:
        return None
    if not isinstance(case, dict):
        raise ValueError("case must be an object")
    out: dict[str, str] = {}
    for key, raw in case.items():
        if key not in _CASE_KEY_SET:
            continue
        if raw is None:
            continue
        if not isinstance(raw, str):
            raise ValueError("case.%s must be a string" % key)
        value = raw.strip()
        if not value:
            continue
        if len(value) > _MAX_CASE_LEN:
            raise ValueError(
                "case.%s exceeds %d characters" % (key, _MAX_CASE_LEN)
            )
        out[key] = value
    return out or None


def _now() -> float:
    return time.time()


class RunStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs(
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    pool_id TEXT NOT NULL,
                    seat TEXT NOT NULL,
                    status TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    result_text TEXT,
                    error TEXT,
                    attribution_json TEXT,
                    parent_run_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    case_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id);
                CREATE TABLE IF NOT EXISTS events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    pool_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    ts REAL NOT NULL
                );
                """
            )
            cols = {
                row[1]
                for row in self._db.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "case_json" not in cols:
                self._db.execute("ALTER TABLE runs ADD COLUMN case_json TEXT")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def create_run(
        self,
        *,
        pool_id: str,
        seat: str,
        prompt: str,
        session_id: str | None = None,
        parent_run_id: str | None = None,
        case: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        sid = session_id or uuid.uuid4().hex
        now = _now()
        normalized = normalize_case(case)
        case_json = (
            json.dumps(normalized, separators=(",", ":"), ensure_ascii=False)
            if normalized is not None
            else None
        )
        with self._cond:
            with self._db:
                self._db.execute(
                    "INSERT INTO runs("
                    "run_id, session_id, pool_id, seat, status, prompt, "
                    "result_text, error, attribution_json, parent_run_id, "
                    "created_at, updated_at, case_json) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        sid,
                        pool_id,
                        seat,
                        "queued",
                        prompt,
                        None,
                        None,
                        None,
                        parent_run_id,
                        now,
                        now,
                        case_json,
                    ),
                )
            payload: dict[str, Any] = {
                "prompt_bytes": len(prompt.encode("utf-8"))
            }
            if normalized is not None:
                payload["case"] = normalized
            event = self._append_event_locked(
                run_id=run_id,
                session_id=sid,
                pool_id=pool_id,
                status="queued",
                payload=payload,
            )
            self._cond.notify_all()
            out = self.get_run(run_id)
            out["event"] = event
            return out

    def set_status(
        self,
        run_id: str,
        status: str,
        *,
        result_text: str | None = None,
        error: str | None = None,
        attribution: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in STATUSES:
            raise ValueError("invalid status %r" % status)
        with self._cond:
            row = self._db.execute(
                "SELECT * FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            now = _now()
            attr_json = (
                json.dumps(attribution, separators=(",", ":"), ensure_ascii=False)
                if attribution is not None
                else row["attribution_json"]
            )
            new_result = (
                result_text if result_text is not None else row["result_text"]
            )
            new_error = error if error is not None else row["error"]
            with self._db:
                self._db.execute(
                    "UPDATE runs SET status=?, result_text=?, error=?, "
                    "attribution_json=?, updated_at=? WHERE run_id=?",
                    (status, new_result, new_error, attr_json, now, run_id),
                )
            payload: dict[str, Any] = dict(extra or {})
            if result_text is not None:
                payload["result_text"] = result_text
            if error is not None:
                payload["error"] = error
            if attribution is not None:
                payload["attribution"] = attribution
            event = self._append_event_locked(
                run_id=run_id,
                session_id=row["session_id"],
                pool_id=row["pool_id"],
                status=status,
                payload=payload,
            )
            self._cond.notify_all()
            out = self.get_run(run_id)
            out["event"] = event
            return out

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            return self._row_to_run(row)

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM runs WHERE session_id=? ORDER BY created_at",
                (session_id,),
            ).fetchall()
            if not rows:
                raise KeyError(session_id)
            runs = [self._row_to_run(r) for r in rows]
            return {
                "session_id": session_id,
                "pool_id": runs[0]["pool_id"],
                "seat": runs[0]["seat"],
                "runs": runs,
                "latest": runs[-1],
            }

    def wait_run(self, run_id: str, wait_ms: int) -> dict[str, Any]:
        deadline = time.monotonic() + wait_ms / 1000.0
        with self._cond:
            while True:
                row = self._db.execute(
                    "SELECT * FROM runs WHERE run_id=?", (run_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(run_id)
                if row["status"] in TERMINAL or wait_ms <= 0:
                    return self._row_to_run(row)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return self._row_to_run(row)
                self._cond.wait(remaining)

    def events_after(
        self,
        cursor: int,
        *,
        pool_id: str | None = None,
        limit: int = 50,
        wait_ms: int = 0,
    ) -> list[dict[str, Any]]:
        deadline = time.monotonic() + wait_ms / 1000.0
        with self._cond:
            while True:
                found = self._query_events_locked(cursor, pool_id, limit)
                if found or wait_ms <= 0:
                    return found
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return []
                self._cond.wait(remaining)

    @property
    def cursor(self) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT COALESCE(MAX(event_id), 0) AS c FROM events"
            ).fetchone()
            return int(row["c"])

    def _append_event_locked(
        self,
        *,
        run_id: str,
        session_id: str,
        pool_id: str,
        status: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        ts = _now()
        with self._db:
            cur = self._db.execute(
                "INSERT INTO events(run_id, session_id, pool_id, status, "
                "payload_json, ts) VALUES(?,?,?,?,?,?)",
                (run_id, session_id, pool_id, status, encoded, ts),
            )
            event_id = int(cur.lastrowid)
        return {
            "event_id": event_id,
            "run_id": run_id,
            "session_id": session_id,
            "pool_id": pool_id,
            "status": status,
            "payload": payload,
            "ts": ts,
        }

    def _query_events_locked(
        self, cursor: int, pool_id: str | None, limit: int
    ) -> list[dict[str, Any]]:
        if pool_id:
            rows = self._db.execute(
                "SELECT * FROM events WHERE event_id>? AND pool_id=? "
                "ORDER BY event_id LIMIT ?",
                (cursor, pool_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM events WHERE event_id>? "
                "ORDER BY event_id LIMIT ?",
                (cursor, limit),
            ).fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "event_id": int(row["event_id"]),
                    "run_id": row["run_id"],
                    "session_id": row["session_id"],
                    "pool_id": row["pool_id"],
                    "status": row["status"],
                    "payload": json.loads(row["payload_json"]),
                    "ts": row["ts"],
                }
            )
        return out

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
        attr = None
        if row["attribution_json"]:
            attr = json.loads(row["attribution_json"])
        case = None
        case_json = None
        try:
            case_json = row["case_json"]
        except (IndexError, KeyError):
            case_json = None
        if case_json:
            case = json.loads(case_json)
        return {
            "run_id": row["run_id"],
            "session_id": row["session_id"],
            "pool_id": row["pool_id"],
            "seat": row["seat"],
            "status": row["status"],
            "prompt": row["prompt"],
            "result_text": row["result_text"],
            "error": row["error"],
            "attribution": attr,
            "case": case,
            "parent_run_id": row["parent_run_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
