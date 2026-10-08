#!/usr/bin/env python3
"""Advisory pre-TAKE collision check over a pre-fetched Slack snapshot; no API calls."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from audit import Event, load_entries, parse_event

PR_URL = re.compile(r"(?:https://github\.com/)?([\w.-]+/[\w.-]+)/pull/(\d+)", re.I)
PR_SHORT = re.compile(r"([\w.-]+/[\w.-]+)#(\d+)")


def canonical_pr(value: str) -> str:
    """Only accept a PR identity; never substitute an issue number."""
    match = PR_URL.fullmatch(value.strip()) or PR_SHORT.fullmatch(value.strip())
    if not match:
        raise ValueError("Expected GitHub PR URL or owner/repo#number, not an issue")
    return f"{match.group(1).lower()}#{int(match.group(2))}"


def active_takes(rows: list[dict[str, Any]], snapshot_ts: float, minutes: float) -> list[Event]:
    events = sorted(
        (event for item in rows if (event := parse_event(item)) is not None),
        key=lambda event: (event.timestamp, event.operation),
    )
    active: dict[str, Event] = {}
    for event in events:
        if event.action == "TAKE":
            active[event.operation] = event
        else:
            # A RELEASE/SHIPPED/DONE retires only its own stable operation.
            active.pop(event.operation, None)
    return [
        event for event in active.values()
        if event.resource and event.timestamp >= snapshot_ts - minutes * 60
    ]


def assess_take(
    rows: list[dict[str, Any]], *, pr: str,
    paths: Sequence[str] = (), kind: str = "source", head: str = "",
    operation_id: str = "", window_minutes: float = 90,
    max_snapshot_age_minutes: float = 15, as_of_ts: float | None = None,
) -> dict[str, Any]:
    """Explain potential conflicts; never grant exclusive ownership or permission."""
    resource = canonical_pr(pr)
    if kind not in ("source", "metadata"):
        raise ValueError("kind must be source or metadata")
    if window_minutes <= 0 or max_snapshot_age_minutes <= 0:
        raise ValueError("windows must be positive")
    now = time.time() if as_of_ts is None else as_of_ts
    known_paths = sorted({path.replace("\\", "/").lstrip("/").strip()
                          for path in paths if path.strip()})
    timestamps = []
    for row in rows:
        value = row.get("ts", row.get("timestamp"))
        try:
            timestamps.append(float(value))
        except (ValueError, TypeError):
            continue
    latest = max(timestamps) if timestamps else None
    report: dict[str, Any] = {
        "pr": resource,
        "candidate": {"operation": operation_id, "kind": kind, "paths": known_paths, "head": head},
        "snapshot_ts": latest,
        "snapshot_age_seconds": None if latest is None else round(now - latest, 2),
        "status": "REFRESH_FEED",
        "peers": [],
        "guidance": "Refresh the live Slack feed; missing or stale messages do not prove a free lane.",
    }
    if latest is None or not (-60 <= now - latest <= max_snapshot_age_minutes * 60):
        return report

    blocking = False
    for event in active_takes(rows, latest, window_minutes):
        if event.resource != resource or (operation_id and event.operation == operation_id):
            continue
        overlap = sorted(set(known_paths) & set(event.paths))
        if kind == event.kind == "metadata":
            relation = "competing-metadata"
        elif kind != event.kind:
            relation = "separate-source-and-metadata"
        elif overlap:
            relation = "overlapping-source-paths"
        elif not known_paths or not event.paths:
            relation = "unknown-source-paths"
        else:
            relation = "disjoint-source-paths"
        blocking |= relation in ("competing-metadata", "overlapping-source-paths", "unknown-source-paths")
        report["peers"].append({
            "operation": event.operation, "actor": event.actor, "channel": event.channel,
            "head": event.head, "same_head": bool(head and event.head and head.lower() == event.head),
            "kind": event.kind, "paths": list(event.paths), "overlap_paths": overlap,
            "relation": relation, "take_ts": event.timestamp,
        })
    report["peers"].sort(key=lambda peer: (peer["take_ts"], peer["operation"]))
    if blocking:
        report["status"] = "COORDINATE_SOURCE"
        report["guidance"] = (
            "A live same-PR TAKE overlaps or has unknown scope. Reconcile the "
            "existing writer and latest RELEASE/source receipt before editing."
        )
    elif report["peers"]:
        report["status"] = "PARALLEL_SCOPE_ADVISORY"
        report["guidance"] = (
            "Same-PR peers have distinct known scopes. Coordinate shared-branch "
            "changes and guard the actual GitHub update with the expected head."
        )
    else:
        report["status"] = "NO_ACTIVE_OVERLAP_OBSERVED"
        report["guidance"] = (
            "No active overlap in this snapshot; NOT a claim or lease. "
            "Refresh live Slack and source head immediately before writing."
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="Existing Slack JSON/JSONL export")
    parser.add_argument("--pr", required=True, help="Sponsor PR URL or owner/repo#number")
    parser.add_argument("--path", action="append", default=[], help="Proposed path (repeat)")
    parser.add_argument("--kind", choices=("source", "metadata"), default="source")
    parser.add_argument("--head", default="")
    parser.add_argument("--operation-id", default="")
    parser.add_argument("--window-minutes", type=float, default=90)
    parser.add_argument("--max-snapshot-age-minutes", type=float, default=15)
    parser.add_argument("--as-of-ts", type=float, help="Deterministic replay clock only")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        result = assess_take(
            load_entries(args.snapshot), pr=args.pr, paths=args.path,
            kind=args.kind, head=args.head, operation_id=args.operation_id,
            window_minutes=args.window_minutes,
            max_snapshot_age_minutes=args.max_snapshot_age_minutes,
            as_of_ts=args.as_of_ts,
        )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if args.format == "json":
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        print(f"{result['status']} {result['pr']} ({len(result['peers'])} active same-PR peers)")
        for peer in result["peers"]:
            print(f"  {peer['operation']}: {peer['relation']} (head={peer['head']})")
        print(result["guidance"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
