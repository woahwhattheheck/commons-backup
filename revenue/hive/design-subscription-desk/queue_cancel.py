#!/usr/bin/env python3
"""Safe operator cancellation companion for Fieldwork's one-request-at-a-time queue.

This tool is intentionally additive: it uses Fieldwork's existing SQLite schema and
a distinct terminal ``cancelled`` status. Fieldwork's shipped browser renders raw
status text, so cancellation remains distinct from delivery acceptance; its
``cancelled`` history event also records that no delivery was accepted.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

ACTIVE = {"production", "review", "revision"}
CANCELLABLE = ACTIVE | {"queued"}
TERMINAL = {"complete", "cancelled"}
REQUEST_ID = re.compile(r"[a-f0-9]{32}")
DEFAULT_DB = Path(__file__).resolve().parent / "data" / "desk.sqlite3"


class CancellationError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _reason(value: str) -> str:
    if not isinstance(value, str):
        raise CancellationError("Cancellation reason must be text")
    value = value.strip()
    if not value or len(value) > 2000:
        raise CancellationError("Cancellation reason must be 1 through 2000 characters")
    return value


def _version(value: int) -> int:
    if type(value) is not int or value < 1:
        raise CancellationError("Expected version must be a positive integer")
    return value


def _request_id(value: str) -> str:
    if not isinstance(value, str) or not REQUEST_ID.fullmatch(value):
        raise CancellationError("Request ID must be exactly 32 lowercase hexadecimal characters")
    return value


def cancel_request(database: str | Path, request_id: str, expected_version: int, reason: str) -> dict:
    """Cancel one request without losing history or violating queue ordering.

    Cancellation stores ``status='cancelled'`` so approval remains the only path
    that produces ``status='complete'``. The explicit ``cancelled`` history event
    retains the human reason and makes the boundary auditable.
    """
    database = Path(database)
    request_id = _request_id(request_id)
    expected_version = _version(expected_version)
    reason = _reason(reason)
    if not database.is_file():
        raise CancellationError(f"Fieldwork database does not exist: {database}", 404)

    db = sqlite3.connect(str(database), timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        request = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if request is None:
            raise CancellationError("Request not found", 404)
        if request["version"] != expected_version:
            raise CancellationError("Request changed; reload its current version before cancelling", 409)
        if request["status"] in TERMINAL:
            raise CancellationError("Request is already terminal; inspect its history before taking another action", 409)
        if request["status"] not in CANCELLABLE:
            raise CancellationError(f"Request status {request['status']!r} is not cancellable by this companion", 409)

        workspace_id = request["workspace_id"]
        was_active = request["status"] in ACTIVE
        changed = db.execute(
            "UPDATE requests SET status='cancelled',version=version+1 WHERE id=? AND version=?",
            (request_id, expected_version),
        )
        if changed.rowcount != 1:
            raise CancellationError("Request changed during cancellation; reload before retrying", 409)
        db.execute(
            "INSERT INTO events(request_id,kind,note,created) VALUES(?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (
                request_id,
                "cancelled",
                "Cancellation is terminal; no delivery acceptance is implied. Reason: " + reason,
            ),
        )

        advanced_request_id = None
        if was_active:
            next_request = db.execute(
                "SELECT id FROM requests WHERE workspace_id=? AND status='queued' "
                "ORDER BY priority,created,id LIMIT 1",
                (workspace_id,),
            ).fetchone()
            if next_request is not None:
                advanced_request_id = next_request["id"]
                db.execute(
                    "UPDATE requests SET status='production',version=version+1 WHERE id=?",
                    (advanced_request_id,),
                )
                db.execute(
                    "INSERT INTO events(request_id,kind,note,created) VALUES(?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                    (
                        advanced_request_id,
                        "started",
                        "Previous request was cancelled; queue advanced automatically.",
                    ),
                )
        db.execute("COMMIT")

        rows = db.execute(
            "SELECT id,status,version,priority FROM requests WHERE workspace_id=? ORDER BY priority,created,id",
            (workspace_id,),
        ).fetchall()
        return {
            "cancelled": True,
            "request_id": request_id,
            "workspace_id": workspace_id,
            "advanced_request_id": advanced_request_id,
            "requests": [dict(row) for row in rows],
        }
    except CancellationError:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    except sqlite3.Error as exc:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise CancellationError(f"Fieldwork storage error: {exc}", 503) from exc
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_id", help="32-character Fieldwork request id")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Fieldwork SQLite database")
    parser.add_argument("--expected-version", type=int, required=True, help="Current request version shown by Fieldwork")
    parser.add_argument("--reason", required=True, help="Human-readable cancellation reason kept in request history")
    parser.add_argument(
        "--confirm-request-id",
        required=True,
        help="Repeat the exact request id to prevent cancelling a mistyped target",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.confirm_request_id != args.request_id:
        print(json.dumps({"error": "Confirmation request id does not match target"}))
        return 2
    try:
        result = cancel_request(args.db, args.request_id, args.expected_version, args.reason)
    except CancellationError as exc:
        print(json.dumps({"error": str(exc), "status": exc.status}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
