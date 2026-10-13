#!/usr/bin/env python3
"""Run the localized-media desk startup contract against real SQLite files."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk as deskmod
import review
from desk import InvalidState, ReleaseDesk

EXPECTED = ["approvals", "events", "requests", "titles", "variants"]


def digest(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def user_objects(path: str):
    with sqlite3.connect(path) as conn:
        return list(conn.execute(
            "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ))


def user_tables(path: str):
    return sorted(name for kind, name in user_objects(path) if kind == "table")


def expect_unchanged(path: str, label: str) -> None:
    before = digest(path)
    before_objects = user_objects(path)
    try:
        ReleaseDesk(path)
    except InvalidState:
        pass
    else:
        raise SystemExit(label + ": startup opened a foreign database")
    if digest(path) != before or user_objects(path) != before_objects:
        raise SystemExit(label + ": refusal changed the file")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        created = os.path.join(td, "new.sqlite")
        ReleaseDesk(created)
        if user_tables(created) != EXPECTED:
            raise SystemExit("missing file did not create the five desk tables")
        before = digest(created)
        ReleaseDesk(created)
        if digest(created) != before:
            raise SystemExit("compatible reopen changed file bytes")

        empty = os.path.join(td, "empty.sqlite")
        sqlite3.connect(empty).close()
        ReleaseDesk(empty)
        if user_tables(empty) != EXPECTED:
            raise SystemExit("empty database was not initialized")

        view_only = os.path.join(td, "view.sqlite")
        with sqlite3.connect(view_only) as conn:
            conn.execute("CREATE VIEW only_view AS SELECT 1 AS n")
        expect_unchanged(view_only, "view-only")
        if user_objects(view_only) != [("view", "only_view")]:
            raise SystemExit("view-only schema changed")
        review_before = digest(view_only)
        try:
            review.collect(Path(view_only))
        except ValueError as exc:
            if "not a supported release desk" not in str(exc):
                raise
        else:
            raise SystemExit("read-only review accepted a view-only database")
        if digest(view_only) != review_before:
            raise SystemExit("read-only review changed a view-only database")

        foreign = os.path.join(td, "foreign.sqlite")
        with sqlite3.connect(foreign) as conn:
            conn.execute("CREATE TABLE notes(id INTEGER PRIMARY KEY, body TEXT)")
            conn.execute("INSERT INTO notes VALUES(1, 'keep')")
        expect_unchanged(foreign, "foreign-table")
        with sqlite3.connect(foreign) as conn:
            row = list(conn.execute("SELECT id, body FROM notes"))
        if row != [(1, "keep")]:
            raise SystemExit("foreign row changed")

        desk_view = os.path.join(td, "deskview.sqlite")
        ReleaseDesk(desk_view)
        with sqlite3.connect(desk_view) as conn:
            conn.execute("CREATE VIEW extra AS SELECT title_id FROM titles")
        expect_unchanged(desk_view, "desk-plus-view")

        saved = deskmod._DESK_SCHEMA
        deskmod._DESK_SCHEMA = saved[:2] + ("CREATE TABLE nope this is bad",)
        deskmod._CANONICAL_DESK_TABLES = None
        try:
            bad = os.path.join(td, "bad.sqlite")
            sqlite3.connect(bad).close()
            before = digest(bad)
            try:
                deskmod.ReleaseDesk(bad)
            except sqlite3.OperationalError:
                pass
            else:
                raise SystemExit("broken schema initialization was committed")
            if digest(bad) != before:
                raise SystemExit("failed initialization was not rolled back")
        finally:
            deskmod._DESK_SCHEMA = saved
            deskmod._CANONICAL_DESK_TABLES = None
    print("startup_contract ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
