# SPDX-License-Identifier: Apache-2.0
"""Create a synthetic, usable Migration Desk and exercise its recovery workflow."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
from pathlib import Path

from intake import MigrationError, digest, record_id
from migrate import apply_plan, edit_record, export_workspace, make_plan, read_state, rollback
from workspace_backup import (DATABASE, RecoveryError, backup_workspace,
                              restore_workspace, verify_archive)

HERE = Path(__file__).resolve().parent
NAMESPACE = "synthetic-recovery-drill"
INITIAL = b"SYNTHETIC original attachment, version one\x00\xff\r\n"
REPLACEMENT = b"SYNTHETIC replacement attachment, version two\x00\xfe\r\n"
INCOMPLETE = ".DRILL_INCOMPLETE"


def _write_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _source(root: Path, raw: bytes) -> None:
    root.mkdir()
    rows = {
        "customers": [
            ["id", "name", "email"],
            ["001", "SYNTHETIC Client One", "one@example.invalid"],
            ["002", "SYNTHETIC Client Two", "two@example.invalid"],
        ],
        "tasks": [
            ["id", "customer", "title"],
            ["001", "001", "SYNTHETIC confirm original file"],
            ["002", "002", "SYNTHETIC continue daily work"],
        ],
        "attachments": [
            ["id", "customer", "path", "name"],
            ["001", "001", "original.bin", "SYNTHETIC-original.bin"],
        ],
    }
    fields = {
        "customers": {"external_id": "id", "name": "name", "email": "email"},
        "tasks": {"external_id": "id", "customer_external_id": "customer", "title": "title"},
        "attachments": {"external_id": "id", "customer_external_id": "customer", "path": "path", "name": "name"},
    }
    mapping = {"namespace": NAMESPACE}
    for kind, data in rows.items():
        name = kind + ".csv"
        with (root / name).open("x", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(data)
        mapping[kind] = {"file": name, "fields": fields[kind]}
    _write_json(root / "mapping.json", mapping)
    with (root / "original.bin").open("xb") as stream:
        stream.write(raw)


def run_drill(destination: Path) -> dict:
    """Run real APIs once and retain a NEW synthetic workspace for the operator."""
    destination = Path(destination).absolute()
    if os.path.lexists(destination):
        raise RecoveryError("Choose a new drill directory; existing work is preserved")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700)
    marker = destination / INCOMPLETE
    marker.write_text("INCOMPLETE synthetic drill; no successful delivery is asserted.\n", encoding="utf-8")
    steps = []

    def require(name: str, condition: bool) -> None:
        if not condition:
            raise RecoveryError("Drill step failed: " + name)
        steps.append(name)

    first, second = destination / "source-v1", destination / "source-v2"
    _source(first, INITIAL)
    _source(second, REPLACEMENT)
    original, assets = destination / "original.sqlite3", destination / "original-assets"
    first_plan = make_plan(first, "mapping.json", original, "synthetic-import-1")
    _write_json(destination / "plan-v1.json", first_plan)
    initial = apply_plan(first_plan, first, original, assets)
    require("import five linked synthetic records", initial["changed"] == 5)
    second_plan = make_plan(second, "mapping.json", original, "synthetic-import-2")
    _write_json(destination / "plan-v2.json", second_plan)
    replaced = apply_plan(second_plan, second, original, assets)
    require("replace exactly one original attachment", replaced["changed"] == 1)
    original_state, original_digest = read_state(original), digest(original.read_bytes())
    archive, recovered = destination / "before-rollback.zip", destination / "recovered"
    backup_workspace(original, assets, archive)
    verified = verify_archive(archive)
    require("retain both attachment versions and six journal entries", verified["counts"] == {
        "records": 5, "runs": 2, "changes": 6, "attachments": 2})
    restore_workspace(archive, recovered)
    database, recovered_assets = recovered / DATABASE, recovered / "assets"
    require("restore exact current record state", read_state(database) == original_state)
    repeated = apply_plan(second_plan, second, database, recovered_assets)
    require("retry second import without duplicate operation", repeated["repeated"] is True)
    undone = rollback(database, second_plan["operation"])
    require("roll back only the replacement import", undone["restored_records"] == 1)
    attachment_id = record_id("attachments", NAMESPACE, "001")
    restored = read_state(database)[attachment_id]
    require("recover original attachment metadata and bytes", restored["data"]["sha256"] == digest(INITIAL)
            and (recovered_assets / digest(INITIAL)).read_bytes() == INITIAL)
    task_id = record_id("tasks", NAMESPACE, "002")
    task = read_state(database)[task_id]
    updated = edit_record(database, task_id, task["revision"], {"status": "done"})
    require("continue daily work on recovered desk", updated["data"]["status"] == "done")
    exported = destination / "daily-work-export"
    export_workspace(database, recovered_assets, exported)
    require("export the recovered original file", (exported / "attachments" / digest(INITIAL)).read_bytes() == INITIAL)
    require("leave original database untouched", read_state(original) == original_state
            and digest(original.read_bytes()) == original_digest)
    source_pins = {}
    for name in ("intake.py", "migrate.py", "desk.py", "workspace_backup.py", "recovery_drill.py"):
        raw = (HERE / name).read_bytes()
        source_pins[name] = {"sha256": digest(raw), "bytes": len(raw)}
    report = {
        "format": "migration-recovery-drill-v1", "synthetic_only": True,
        "completed": True, "steps": steps, "backup_counts": verified["counts"],
        "attachment_id": attachment_id, "edited_task_id": task_id,
        "initial_sha256": digest(INITIAL), "replacement_sha256": digest(REPLACEMENT),
        "paths": {"database": "recovered/" + DATABASE, "assets": "recovered/assets",
                  "archive": "before-rollback.zip", "export": "daily-work-export",
                  "original_database": "original.sqlite3"},
        "source_pins": source_pins,
        "start_argv": [sys.executable, str(HERE / "desk.py"), "--database", str(database),
                       "--assets", str(recovered_assets), "--port", "8080"],
        "http_exercised_by_this_command": False,
        "note": "This command uses real core/recovery APIs. HTTP composition is exercised by the separate test suite.",
    }
    _write_json(destination / "DRILL.json", report)
    marker.unlink()
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New directory for synthetic sources, backup and recovered desk")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run_drill(args.destination), indent=2, ensure_ascii=False))
        return 0
    except (MigrationError, OSError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"completed": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
