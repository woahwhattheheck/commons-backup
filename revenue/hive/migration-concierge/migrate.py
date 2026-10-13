# SPDX-License-Identifier: Apache-2.0
"""Transactional CSV-to-SQLite migration, operational workspace, and rollback."""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from intake import (KINDS, MigrationError, canonical, collect, digest, read_source, read_attachment_source, validate_data)

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
 kind TEXT NOT NULL, id TEXT PRIMARY KEY, namespace TEXT NOT NULL,
 external_id TEXT NOT NULL, data TEXT NOT NULL, source TEXT NOT NULL,
 revision INTEGER NOT NULL, UNIQUE(kind, namespace, external_id));
CREATE TABLE IF NOT EXISTS runs (
 operation TEXT PRIMARY KEY, plan_id TEXT NOT NULL, status TEXT NOT NULL,
 created_at TEXT NOT NULL, plan TEXT NOT NULL, report TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS changes (
 operation TEXT NOT NULL REFERENCES runs(operation), record_id TEXT NOT NULL,
 before_state TEXT, after_state TEXT NOT NULL, PRIMARY KEY(operation, record_id));
"""


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(database, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(SCHEMA)
        return db
    except Exception:
        db.close()
        raise


def _state(db: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    result = {}
    for row in db.execute("SELECT * FROM records ORDER BY kind,id"):
        record = dict(row)
        record["data"] = json.loads(record["data"])
        record["source"] = json.loads(record["source"])
        result[record["id"]] = record
    return result


def read_state(database: Path) -> dict[str, dict[str, Any]]:
    """A trial against a missing database does not create it."""
    if not database.exists():
        return {}
    try:
        db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            return _state(db)
        finally:
            db.close()
    except sqlite3.Error as exc:
        raise MigrationError(f"Destination is not a readable migration workspace: {exc}") from exc


def validate_state(state: dict[str, dict[str, Any]], duplicate_rule: str = "keep_separate") -> list[dict]:
    emails: dict[str, list[str]] = {}
    for record in state.values():
        kind, data = record["kind"], record["data"]
        validate_data(kind, data)
        if kind in {"tasks", "attachments"}:
            parent = state.get(data["customer_id"])
            if parent is None or parent["kind"] != "customers":
                raise MigrationError(f"{kind} {record['external_id']}: customer reference is missing")
        if kind == "customers" and data.get("email", "").strip():
            emails.setdefault(data["email"].strip().casefold(), []).append(record["id"])
    duplicates = [{"email": email, "record_ids": ids} for email, ids in sorted(emails.items()) if len(ids) > 1]
    if duplicates and duplicate_rule == "error":
        raise MigrationError("Duplicate customer email: resolve the source or explicitly choose keep_separate: "
                             + ", ".join(row["email"] for row in duplicates))
    return duplicates


def _write_record(db: sqlite3.Connection, record: dict) -> None:
    db.execute("INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?)",
               (record["kind"], record["id"], record["namespace"], record["external_id"],
                canonical(record["data"]), canonical(record["source"]), record["revision"]))


def make_plan(root: Path, mapping: str, database: Path, operation: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", operation):
        raise MigrationError("Use a stable operation ID with letters, numbers, dot, dash or underscore")
    source = collect(root, mapping)
    state = read_state(database)
    projected = dict(state)
    changes = []
    for incoming in source["records"]:
        before = state.get(incoming["id"])
        after = dict(incoming, revision=(before["revision"] + 1 if before else 1))
        if before and all(before[key] == incoming[key] for key in incoming):
            after = before
        action = "create" if before is None else ("unchanged" if after == before else "update")
        changes.append({"action": action, "before": before, "after": after})
        projected[after["id"]] = after
    duplicates = validate_state(projected, source["duplicate_email"])
    plan = {"format": "migration-concierge-plan-v1", "operation": operation,
            "source": source, "changes": changes, "duplicate_decisions": duplicates,
            "counts": {kind: sum(r["kind"] == kind for r in source["records"]) for kind in KINDS},
            "cutover_steps": ["Review mapped fields, duplicate decisions, and source-linked rows.",
                              "Apply this exact plan with the same source export.",
                              "Open the workspace and inspect linked tasks and attachments.",
                              "Retain the source export and operation ID for rollback."]}
    plan["plan_id"] = digest(canonical(plan).encode())
    return plan


def _check_plan(plan: dict, root: Path) -> None:
    if not isinstance(plan, dict) or plan.get("format") != "migration-concierge-plan-v1":
        raise MigrationError("Unrecognized plan format")
    claimed = plan.get("plan_id")
    if claimed != digest(canonical({k: v for k, v in plan.items() if k != "plan_id"}).encode()):
        raise MigrationError("Plan content changed; generate a new trial plan")
    source = collect(root, plan["source"]["mapping_path"])
    if source != plan["source"]:
        raise MigrationError("Source export changed since the trial; generate a new plan")
    incoming = {r["id"]: r for r in source["records"]}
    if len(plan["changes"]) != len(incoming):
        raise MigrationError("Plan does not cover the complete source")
    seen = set()
    for change in plan["changes"]:
        after = change["after"]
        if after["id"] in seen or {k: v for k, v in after.items() if k != "revision"} != incoming.get(after["id"]):
            raise MigrationError("Plan record differs from the mapped source")
        before = change["before"]
        expected = "create" if before is None else (
            "unchanged" if all(before[k] == incoming[after["id"]][k] for k in incoming[after["id"]]) else "update")
        if change["action"] != expected:
            raise MigrationError("Plan action differs from its before-image and source record")
        if before is not None and before["id"] != after["id"]:
            raise MigrationError("Plan before-image identity differs")
        seen.add(after["id"])


def store_asset(root: Path, assets: Path, data: dict) -> None:
    raw = read_attachment_source(root, data["path"])
    if digest(raw) != data["sha256"] or len(raw) != data["bytes"]:
        raise MigrationError("Attachment changed during cutover")
    assets.mkdir(parents=True, exist_ok=True)
    target = assets / data["sha256"]
    if target.exists():
        if target.is_symlink() or digest(target.read_bytes()) != data["sha256"]:
            raise MigrationError("Destination attachment differs from its content address")
        return
    fd, name = tempfile.mkstemp(prefix=".incoming-", dir=assets)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # A concurrently created identical content address is harmless; no original is overwritten.
        try:
            os.link(name, target)
        except FileExistsError:
            if target.is_symlink() or digest(target.read_bytes()) != data["sha256"]:
                raise MigrationError("Concurrent attachment collision")
    finally:
        Path(name).unlink(missing_ok=True)


def apply_plan(plan: dict, root: Path, database: Path, assets: Path) -> dict:
    _check_plan(plan, root)
    db = connect(database)
    try:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT * FROM runs WHERE operation=?", (plan["operation"],)).fetchone()
        if previous:
            if previous["plan_id"] != plan["plan_id"]:
                raise MigrationError("Operation ID already describes a different plan")
            if previous["status"] != "applied":
                raise MigrationError("Operation was rolled back; use a new operation ID for another import")
            report = json.loads(previous["report"])
            db.rollback()
            return dict(report, repeated=True)
        state = _state(db)
        projected = dict(state)
        for change in plan["changes"]:
            after, before = change["after"], change["before"]
            if state.get(after["id"]) != before:
                raise MigrationError(f"Destination changed after trial: {after['external_id']}")
            expected_revision = before["revision"] if before and change["action"] == "unchanged" else (before["revision"] + 1 if before else 1)
            if after["revision"] != expected_revision:
                raise MigrationError("Plan revision mismatch")
            projected[after["id"]] = after
        validate_state(projected, plan["source"]["duplicate_email"])
        for record in plan["source"]["records"]:
            if record["kind"] == "attachments":
                store_asset(root, assets, record["data"])
        report = {"operation": plan["operation"], "plan_id": plan["plan_id"], "status": "applied",
                  "counts": plan["counts"], "changed": sum(c["action"] != "unchanged" for c in plan["changes"]),
                  "applied_at": utc(), "repeated": False}
        db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?)",
                   (plan["operation"], plan["plan_id"], "applied", report["applied_at"], canonical(plan), canonical(report)))
        for change in plan["changes"]:
            if change["action"] == "unchanged":
                continue
            _write_record(db, change["after"])
            db.execute("INSERT INTO changes VALUES (?,?,?,?)",
                       (plan["operation"], change["after"]["id"],
                        canonical(change["before"]) if change["before"] else None, canonical(change["after"])))
        db.commit()
        return report
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def rollback(database: Path, operation: str) -> dict:
    if not database.exists():
        raise MigrationError("Destination does not exist")
    db = connect(database)
    try:
        db.execute("BEGIN IMMEDIATE")
        run = db.execute("SELECT * FROM runs WHERE operation=?", (operation,)).fetchone()
        if run is None:
            raise MigrationError("No such operation")
        if run["status"] == "rolled_back":
            db.rollback()
            return {"operation": operation, "status": "rolled_back", "repeated": True}
        state = _state(db)
        projected = dict(state)
        changes = list(db.execute("SELECT * FROM changes WHERE operation=?", (operation,)))
        for change in changes:
            after = json.loads(change["after_state"])
            if state.get(change["record_id"]) != after:
                raise MigrationError(f"Later edit would be overwritten: {after['external_id']}; nothing rolled back")
            if change["before_state"] is None:
                projected.pop(change["record_id"])
            else:
                projected[change["record_id"]] = json.loads(change["before_state"])
        validate_state(projected)
        for change in changes:
            if change["before_state"] is None:
                db.execute("DELETE FROM records WHERE id=?", (change["record_id"],))
            else:
                _write_record(db, projected[change["record_id"]])
        db.execute("UPDATE runs SET status='rolled_back' WHERE operation=?", (operation,))
        db.commit()
        return {"operation": operation, "status": "rolled_back", "restored_records": len(changes),
                "attachments": "Source originals and content-addressed copies retained", "repeated": False}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def edit_record(database: Path, record_id: str, expected_revision: int, fields: dict[str, str]) -> dict:
    db = connect(database)
    try:
        db.execute("BEGIN IMMEDIATE")
        state = _state(db)
        record = state.get(record_id)
        if record is None or record["revision"] != expected_revision:
            raise MigrationError("Record changed; reload before saving")
        editable = {"customers": {"name", "email", "phone"}, "tasks": {"title", "status", "due_date"}}
        if not fields or set(fields) - editable.get(record["kind"], set()):
            raise MigrationError("Edit the displayed customer or task fields only")
        if not all(isinstance(value, str) for value in fields.values()):
            raise MigrationError("Fields must contain text")
        updated = dict(record, data={**record["data"], **fields}, revision=record["revision"] + 1)
        state[record_id] = updated
        validate_state(state)
        _write_record(db, updated)
        db.commit()
        return updated
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def export_workspace(database: Path, assets: Path, output: Path) -> dict:
    state = read_state(database)
    validate_state(state)
    if output.exists():
        raise MigrationError("Choose a new export directory; existing exports are preserved")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".export-", dir=output.parent))
    try:
        for kind in KINDS:
            (staging / f"{kind}.json").write_text(json.dumps([r for r in state.values() if r["kind"] == kind],
                                                         ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        copied = set()
        for record in state.values():
            if record["kind"] != "attachments":
                continue
            data = record["data"]
            raw = (assets / data["sha256"]).read_bytes()
            if digest(raw) != data["sha256"] or len(raw) != data["bytes"]:
                raise MigrationError("Attachment hash does not match during export")
            (staging / "attachments").mkdir(exist_ok=True)
            (staging / "attachments" / data["sha256"]).write_bytes(raw)
            copied.add(data["sha256"])
        manifest = {str(p.relative_to(staging)): {"sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
                    for p in sorted(staging.rglob("*")) if p.is_file()}
        (staging / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        # Rename only into a new destination; source/destination records remain untouched.
        if output.exists():
            raise MigrationError("Export destination appeared during processing")
        staging.rename(output)
        return {"records": len(state), "attachments": len(copied), "output": str(output)}
    except Exception:
        import shutil
        shutil.rmtree(staging)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("plan", help="Read-only trial against the source and destination")
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--mapping", default="mapping.json")
    p.add_argument("--database", type=Path, required=True)
    p.add_argument("--operation", required=True)
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("apply", help="Apply an exact trial plan")
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--database", type=Path, required=True)
    p.add_argument("--assets", type=Path, required=True)
    p = commands.add_parser("rollback", help="Undo one import without overwriting later edits")
    p.add_argument("--database", type=Path, required=True)
    p.add_argument("--operation", required=True)
    p = commands.add_parser("export", help="Export records, relationships, and exact attachments")
    p.add_argument("--database", type=Path, required=True)
    p.add_argument("--assets", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = make_plan(args.source, args.mapping, args.database, args.operation)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            # Plans are immutable checkpoints; a new path is required to replace one.
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        elif args.command == "apply":
            result = apply_plan(json.loads(args.plan.read_text(encoding="utf-8")), args.source, args.database, args.assets)
        elif args.command == "rollback":
            result = rollback(args.database, args.operation)
        else:
            result = export_workspace(args.database, args.assets, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (MigrationError, OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
