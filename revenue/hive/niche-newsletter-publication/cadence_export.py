#!/usr/bin/env python3
"""Build deterministic UNSENT newsletter handoff ZIPs by subscriber cadence."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sqlite3
import sys
import zipfile
from pathlib import Path
from typing import Any

CADENCES = {"weekly", "monthly"}
STATUSES = {"active", "unsubscribed"}
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


class ExportError(ValueError):
    """Raised when stored publication data cannot be exported safely."""


def _as_json_list(raw: str, label: str) -> list[str]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ExportError(f"{label} must contain a JSON array") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ExportError(f"{label} must contain a JSON array of strings")
    return value


def _zip_text(archive: zipfile.ZipFile, name: str, value: str | bytes) -> None:
    payload = value if isinstance(value, bytes) else value.encode("utf-8")
    info = zipfile.ZipInfo(name, ZIP_EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o600 << 16
    archive.writestr(info, payload)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _open_read_only(database: str | Path) -> sqlite3.Connection:
    path = Path(database).resolve()
    if not path.is_file():
        raise ExportError(f"Database does not exist: {path}")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def build_cadence_export(database: str | Path, issue_id: str, cadence: str) -> bytes:
    """Return one deterministic provider-agnostic ZIP for the requested cadence.

    The database is opened read-only. Only active subscribers whose stored cadence
    matches *cadence* and whose topic preferences include the issue topic (or are
    empty) receive an UNSENT recipient packet.
    """
    if cadence not in CADENCES:
        raise ExportError("Cadence must be weekly or monthly")
    issue_id = issue_id.strip() if isinstance(issue_id, str) else ""
    if not issue_id:
        raise ExportError("Issue id is required")

    try:
        with _open_read_only(database) as db:
            db.execute("BEGIN")
            issue = db.execute(
                "SELECT id,slug,title,subject,body,topic,scheduled_at,state,revision "
                "FROM issues WHERE id=?",
                (issue_id,),
            ).fetchone()
            if issue is None:
                raise ExportError("Issue not found")
            if issue["state"] != "published":
                raise ExportError("Only published issues can be exported")

            sources = [
                dict(row)
                for row in db.execute(
                    "SELECT s.id,s.title,s.url,s.observed_at,s.synthetic "
                    "FROM sources s JOIN issue_sources x ON x.source_id=s.id "
                    "WHERE x.issue_id=? ORDER BY s.id",
                    (issue_id,),
                ).fetchall()
            ]
            if not sources:
                raise ExportError("Published issue has no source links")

            subscribers = db.execute(
                "SELECT id,email,topics,frequency,status FROM subscribers ORDER BY email,id"
            ).fetchall()
            eligible: list[sqlite3.Row] = []
            for row in subscribers:
                if row["frequency"] not in CADENCES:
                    raise ExportError(f"Subscriber {row['id']} has invalid frequency")
                if row["status"] not in STATUSES:
                    raise ExportError(f"Subscriber {row['id']} has invalid status")
                topics = _as_json_list(row["topics"], f"Subscriber {row['id']} topics")
                if row["status"] != "active" or row["frequency"] != cadence:
                    continue
                if topics and issue["topic"] not in topics:
                    continue
                eligible.append(row)

            manifest = {
                "schema": "northstar.cadence-export.v1",
                "delivery_state": "UNSENT",
                "cadence": cadence,
                "issue": {
                    key: issue[key]
                    for key in ("id", "slug", "title", "subject", "topic", "scheduled_at", "revision")
                },
                "sources": sources,
                "recipient_count": len(eligible),
                "recipients": [row["email"] for row in eligible],
            }

            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                _zip_text(archive, "manifest.json", _json_bytes(manifest))
                _zip_text(archive, "issue.txt", issue["body"] + "\n")
                _zip_text(archive, "sources.json", _json_bytes(sources))
                for index, row in enumerate(eligible, start=1):
                    safe_id = hashlib.sha256(row["id"].encode("utf-8")).hexdigest()[:12]
                    packet = {
                        "delivery_state": "UNSENT",
                        "cadence": cadence,
                        "subscriber_id": row["id"],
                        "email": row["email"],
                        "subject": issue["subject"],
                        "scheduled_at": issue["scheduled_at"],
                        "issue_id": issue["id"],
                        "revision": issue["revision"],
                        "source_ids": [source["id"] for source in sources],
                    }
                    _zip_text(
                        archive,
                        f"recipients/{index:04d}-{safe_id}.json",
                        _json_bytes(packet),
                    )
            return buffer.getvalue()
    except sqlite3.Error as exc:
        raise ExportError(f"Newsletter database is incompatible: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Existing Northstar SQLite database")
    parser.add_argument("--issue", required=True, help="Published issue id")
    parser.add_argument("--cadence", required=True, choices=sorted(CADENCES))
    parser.add_argument("--output", required=True, help="New ZIP path; existing files are never replaced")
    args = parser.parse_args(argv)

    try:
        payload = build_cadence_export(args.db, args.issue, args.cadence)
        output = Path(args.output)
        with output.open("xb") as handle:
            handle.write(payload)
    except (ExportError, OSError) as exc:
        print(f"cadence export failed: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "cadence": args.cadence,
                "delivery_state": "UNSENT",
                "issue_id": args.issue,
                "output": str(output),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
