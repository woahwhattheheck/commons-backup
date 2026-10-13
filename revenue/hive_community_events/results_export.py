#!/usr/bin/env python3
"""Download finished Lantern results from the existing application and database."""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from typing import Callable

from app import Problem, Store

SCHEMA = "lantern.results.v1"
COLUMNS = ("event_id", "event_title", "room", "rank", "display_name", "points", "answered")


def results_document(store: Store, event_id: str) -> dict:
    """Use the native single-snapshot ranking, revealing only final public fields."""
    state = store.state(event_id)
    if state["phase"] != "finished":
        raise Problem(409, "Results can be exported only after the event finishes")
    # An explicit allowlist keeps reconnect references and answer keys out even
    # if the application adds more fields to its state/leaderboard in the future.
    return {
        "schema": SCHEMA,
        "event": {key: state[key] for key in
                  ("id", "title", "room", "opens", "ends", "phase", "question_count")},
        "participants": state["players"],
        "leaderboard": [{key: row[key] for key in ("rank", "name", "points", "answered")}
                        for row in state["leaderboard"]],
    }


def _csv_text(value: str) -> str:
    """Neutralize common spreadsheet formula prefixes; JSON remains lossless."""
    probe = value.lstrip("\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d"
                         "\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f ")
    if probe.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def export_bytes(store: Store, event_id: str, format: str = "json") -> bytes:
    """Return deterministic UTF-8 JSON or UTF-8-with-BOM CSV, never change state."""
    if format not in ("json", "csv"):
        raise ValueError("Export format must be json or csv")
    document = results_document(store, event_id)
    if format == "json":
        return (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    event = document["event"]
    for row in document["leaderboard"]:
        writer.writerow((_csv_text(event["id"]), _csv_text(event["title"]), _csv_text(event["room"]),
                         row["rank"], _csv_text(row["name"]), row["points"], row["answered"]))
    return buffer.getvalue().encode("utf-8-sig")


class ReadOnlyStore(Store):
    """Reuse Store.state without running Store's schema-initializing constructor.

    SQLite mode=ro sees committed WAL contents; immutable mode would not be an
    appropriate substitute for a database which the running app can still edit.
    """
    def __init__(self, database: str | Path, clock: Callable[[], float] = time.time):
        path = Path(database).resolve(strict=True)
        if not path.is_file():
            raise ValueError("Database must be an existing regular file")
        self.database, self.clock = str(path), clock
        self._uri = path.as_uri() + "?mode=ro"

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self._uri, uri=True, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA query_only=ON")
            yield db
        finally:
            db.close()


def write_new_output(output: str | Path, data: bytes) -> None:
    """Publish one complete file without replacing an existing path, even in a race.

    Staging and destination are on the same filesystem. os.link is atomic and
    refuses existing destinations (including dangling symlinks). A filesystem
    without hard-link support returns an error rather than weakening the rule.
    """
    destination = Path(output)
    fd, staged = tempfile.mkstemp(prefix=".lantern-results-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staged, destination)
    finally:
        Path(staged).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Existing Lantern SQLite database")
    parser.add_argument("--event", required=True, help="Event reference from its URL or event list")
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    parser.add_argument("--output", required=True, help="New output path; existing files are never replaced")
    args = parser.parse_args(argv)
    try:
        content = export_bytes(ReadOnlyStore(args.db), args.event, args.format)
        write_new_output(args.output, content)
    except (Problem, OSError, ValueError, sqlite3.DatabaseError) as error:
        print(f"Export failed: {error}", file=sys.stderr)
        return 2
    print(f"Exported {args.format} results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
