"""Bounded GitHub issue-update window + explicit gap-minute coverage.

This is a pure coverage adapter. It does not invent a second Jev client,
collector root, or credential road. Callers supply already-read GitHub issue
update rows (number + updated_at). The adapter:

- records an explicit missing minute as incomplete LOWER_BOUND coverage
- pages a later issue-update window without treating a cap as a census
- emits a connector-projection packet the landed ledger adapter accepts
- preserves distinct issue-update revisions under one stable work identity

The CLI keeps its summary receipt by default. Use ``--format projection`` for
connector metadata or ``--format ledger`` to feed the existing event-ledger
compiler directly. Each format retains the declared partial window and gap.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from integrations.command_center.jev_connector_projection import project, strict_loads

SCHEMA = "commons.jev_github_issue_window/v1"
PROJECTION_SCHEMA = "commons.jev_connector_projection/v1"
UTC = timezone.utc


class WindowError(ValueError):
    """Malformed issue-update window input."""


def _instant(value: Any, where: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise WindowError(f"{where}: timestamp must end in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise WindowError(f"{where}: invalid timestamp") from exc
    if parsed.tzinfo != UTC:
        raise WindowError(f"{where}: not UTC")
    return parsed


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _token(value: Any, where: str) -> str:
    if type(value) is not str or not value or len(value) > 191:
        raise WindowError(f"{where}: invalid token")
    return value


def compile_window(
    packet: dict[str, Any], *, output_format: str = "receipt"
) -> dict[str, Any]:
    """Return the coverage receipt, connector projection, or ingestible ledger.

    All formats use the same validated source records and coverage. The default
    receipt retains its existing schema and fields for current callers.
    """
    if output_format not in ("receipt", "projection", "ledger"):
        raise WindowError("output_format must be receipt, projection, or ledger")
    if type(packet) is not dict:
        raise WindowError("packet must be an object")
    if packet.get("schema") != SCHEMA:
        raise WindowError("unsupported schema")
    owner = _token(packet.get("owner"), "owner")
    repo = _token(packet.get("repo"), "repo")
    # Existing unscoped IDs belong to Commons. Other repositories need their
    # own namespace so equally numbered issues and coverage sources compose.
    repository = f"{owner}/{repo}".lower()
    namespace = "" if repository == "woahwhattheheck/commons" else f":{repository}"
    snapshot_id = _token(packet.get("snapshot_id"), "snapshot_id")
    observed_at = _instant(packet.get("observed_at"), "observed_at")
    gap_start = _instant(packet.get("gap_start"), "gap_start")
    gap_end = _instant(packet.get("gap_end"), "gap_end")
    window_start = _instant(packet.get("window_start"), "window_start")
    window_end = _instant(packet.get("window_end"), "window_end")
    if not (gap_start < gap_end <= window_start < window_end <= observed_at):
        raise WindowError("gap and update windows must be ordered and not after observation")
    page = packet.get("page")
    page_size = packet.get("page_size")
    has_more = packet.get("has_more")
    if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 100:
        raise WindowError("page/page_size out of range")
    if type(has_more) is not bool:
        raise WindowError("has_more must be boolean")
    rows = packet.get("issues")
    if type(rows) is not list:
        raise WindowError("issues must be a list")

    records = []
    seen = set()
    issue_numbers = set()
    for raw in rows:
        if type(raw) is not dict:
            raise WindowError("issue row must be an object")
        number = raw.get("number")
        if type(number) is not int or number < 1:
            raise WindowError("issue number invalid")
        updated = _instant(raw.get("updated_at"), "issue.updated_at")
        if not (window_start <= updated <= window_end):
            raise WindowError(f"issue #{number} outside declared update window")
        updated_at = _utc(updated)
        revision = (number, updated_at)
        if revision in seen:
            continue
        seen.add(revision)
        issue_numbers.add(number)
        records.append({
            "provider_event_id": f"{number}@{updated_at}",
            "provider_event_time": updated_at,
            "observed_at": _utc(observed_at),
            "resource_scope": f"{owner}/{repo}",
            "event_type": "ISSUE",
            "actor_id": None,
            "work_id": f"github-issue{namespace}-{number}",
            "operation_id": f"jev-16537-issue-window{namespace}-{number}",
            "source_url": f"https://github.com/{owner}/{repo}/issues/{number}",
        })

    source_url = f"https://github.com/{owner}/{repo}/issues?q=updated%3A%3E%3D{_utc(window_start)}"
    projection = {
        "schema": PROJECTION_SCHEMA,
        "snapshot_id": snapshot_id,
        "max_source_age_seconds": 3600,
        "sources": [
            {
                "source_id": "github-issue-update-window" + namespace,
                "connector": "github-issues-list",
                "provider": "github",
                "scope": [f"{owner}/{repo}"],
                "cursor": f"page-{page}",
                "high_water_mark": _utc(window_end),
                "observed_at": _utc(observed_at),
                "last_successful_read": _utc(observed_at),
                "status": "PARTIAL" if has_more else "OK",
                "cooldown_until": None,
                "coverage": {
                    "window_start": _utc(window_start),
                    "window_end": _utc(window_end),
                    "complete": not has_more,
                    "has_more": has_more,
                    "pages_read": page,
                    "items_read": len(records),
                },
                "source_url": source_url,
                "records": records,
            },
            {
                "source_id": "github-gap-minute-1924" + namespace,
                "connector": "github-issues-list",
                "provider": "github",
                "scope": [f"{owner}/{repo}"],
                "cursor": None,
                "high_water_mark": _utc(gap_start),
                "observed_at": _utc(observed_at),
                "last_successful_read": None,
                "status": "PARTIAL",
                "cooldown_until": None,
                "coverage": {
                    "window_start": _utc(gap_start),
                    "window_end": _utc(gap_end),
                    "complete": False,
                    "has_more": True,
                    "pages_read": 0,
                    "items_read": 0,
                },
                "source_url": f"https://github.com/{owner}/{repo}/issues",
                "records": [],
            },
        ],
    }
    ledger = project(projection)
    if output_format == "projection":
        return projection
    if output_format == "ledger":
        return ledger
    return {
        "schema": SCHEMA,
        "snapshot_id": snapshot_id,
        "owner": owner,
        "repo": repo,
        "processed_issue_count": len(issue_numbers),
        "processed_issue_numbers": sorted(issue_numbers),
        "update_window": {"start": _utc(window_start), "end": _utc(window_end), "complete": not has_more, "has_more": has_more, "page": page, "page_size": page_size},
        "gap_minute": {"start": _utc(gap_start), "end": _utc(gap_end), "complete": False, "items_read": 0, "status": "LOWER_BOUND"},
        "ledger_schema": ledger["schema"],
        "ledger_event_count": len(ledger["events"]),
        "ledger_source_ids": [source["source_id"] for source in ledger["sources"]],
    }


def _write_output(path: str, text: str) -> None:
    destination = Path(path)
    with tempfile.TemporaryDirectory(
        prefix=".jev-issue-window-", dir=destination.parent
    ) as staging:
        staged = Path(staging) / "output.json"
        with staged.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile a GitHub issue-update window packet.")
    parser.add_argument("input", nargs="?", help="JSON packet path; stdin if omitted")
    parser.add_argument("-o", "--output", help="Write the selected JSON output here")
    parser.add_argument(
        "--format", dest="output_format", choices=("receipt", "projection", "ledger"),
        default="receipt",
        help="Output a summary receipt (default), connector projection, or event-ledger packet",
    )
    args = parser.parse_args(argv)
    try:
        if args.input in (None, "-"):
            raw = sys.stdin.read()
        else:
            with open(args.input, encoding="utf-8") as handle:
                raw = handle.read()
        packet = strict_loads(raw)
        result = compile_window(packet, output_format=args.output_format)
        text = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            _write_output(args.output, text)
        else:
            sys.stdout.write(text)
        return 0
    except (OSError, ValueError) as exc:
        print(f"jev_github_issue_window: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
