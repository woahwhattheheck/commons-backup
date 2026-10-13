#!/usr/bin/env python3
"""Advisory detection of concurrent work on the same paid PR from Slack exports.

Reads an already-captured snapshot. It never calls Slack, GitHub, or a payout API.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ACTION = re.compile(r"(?:^|:\s*)(TAKE|RELEASED?|SHIPPED|DONE|CANCELLED)\s*(?:[·|:/-]\s*)", re.I)
PR_URL = re.compile(r"github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)", re.I)
PR_SHORTHAND = re.compile(r"([\w.-]+/[\w.-]+)#(\d+)")
OP_ID = re.compile(r"^[A-Z][A-Z0-9-]{11,}", re.I)
BLOB_HEAD = re.compile(r"\b(?:HEAD|head|@)\s*(?:[:=]\s*)?([a-f0-9]{8,40})\b")
PATH = re.compile(r"(?<![\w/])(?:[\w.-]+/)+[\w.-]+\.(?:ts|tsx|js|jsx|py|rs|go|json|md|yml|yaml|toml|sh|css)\b")
METADATA = re.compile(
    r"\b(?:metadata.only|body.only|issue.claim.only|claim.metadata|no.source.edits|no.source.writes)\b",
    re.I,
)


@dataclass(frozen=True)
class Event:
    timestamp: float
    action: str
    operation: str
    resource: str
    actor: str
    paths: tuple[str, ...]
    head: str
    kind: str
    channel: str


def _timestamp(value: Any) -> float:
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    raise ValueError("Missing timestamp; event not used")


def _pr_resource(text: str) -> str:
    # A pull URL is an unambiguous PR identity; an issue link is not.
    match = PR_URL.search(text)
    if match:
        return f"{match.group(1).lower()}#{int(match.group(2))}"
    # Shorthand is allowed only when the author explicitly says PR.
    if re.search(r"\b(?:sponsor |original |existing |upstream )?PR\b", text, re.I):
        match = PR_SHORTHAND.search(text)
        if match:
            return f"{match.group(1).lower()}#{int(match.group(2))}"
    return ""


def parse_event(raw: dict[str, Any]) -> Event | None:
    text = str(raw.get("text") or raw.get("message") or "")
    action = ACTION.search(text)
    if not action:
        return None
    try:
        timestamp = _timestamp(raw.get("ts", raw.get("timestamp")))
    except (ValueError, TypeError):
        return None
    remainder = text[action.end():].strip()
    token = remainder.split("·", 1)[0].strip().split(" ", 1)[0]
    operation = token if OP_ID.fullmatch(token) else ""
    if not operation:
        # Missing exact operation ID: safe to report, never guess release matching.
        operation = f"anonymous:{timestamp}:{str(raw.get('user', ''))}"
    resource = _pr_resource(text)
    actor = str(raw.get("user") or raw.get("actor") or raw.get("author") or "")
    channel_value = raw.get("channel") or ""
    channel = str(channel_value.get("name", "")) if isinstance(channel_value, dict) else str(channel_value)
    paths = tuple(sorted(set(PATH.findall(text))))
    head = next(iter(BLOB_HEAD.findall(text)), "").lower()
    kind = "metadata" if METADATA.search(text) else "source"
    return Event(timestamp, action.group(1).upper(), operation, resource, actor, paths, head, kind, channel)


def load_entries(path: Path) -> list[dict[str, Any]]:
    data = path.read_text(encoding="utf-8")
    try:
        loaded = json.loads(data)
    except json.JSONDecodeError:
        loaded = [json.loads(line) for line in data.splitlines() if line.strip()]
    if isinstance(loaded, dict):
        loaded = loaded.get("messages", [])
    if not isinstance(loaded, list) or any(not isinstance(x, dict) for x in loaded):
        raise ValueError("Expected JSON list, {messages:[...]}, or JSON lines of Slack messages")
    return loaded


def audit(entries: list[dict[str, Any]], window_minutes: int = 90) -> dict[str, Any]:
    if window_minutes <= 0:
        raise ValueError("window_minutes must be positive")
    parsed = [event for item in entries if (event := parse_event(item)) is not None]
    parsed.sort(key=lambda e: (e.timestamp, e.operation))
    if not parsed:
        return {"snapshot_ts": None, "parsed_events": 0, "active_takes": 0, "alerts": []}
    active: dict[str, Event] = {}
    for event in parsed:
        # A completed operation retires only its own TAKE, never someone else's.
        if event.action == "TAKE":
            active[event.operation] = event
        else:
            active.pop(event.operation, None)
    snapshot_ts = parsed[-1].timestamp
    recent = [
        e for e in active.values()
        if e.resource and snapshot_ts - e.timestamp <= window_minutes * 60
    ]
    by_resource: dict[str, list[Event]] = defaultdict(list)
    for item in recent:
        by_resource[item.resource].append(item)
    alerts = []
    for resource, group in sorted(by_resource.items()):
        group.sort(key=lambda e: (e.timestamp, e.operation))
        if len(group) < 2:
            continue
        pairs = []
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a.operation == b.operation:
                    continue
                overlap = sorted(set(a.paths) & set(b.paths))
                if a.kind == "metadata" or b.kind == "metadata":
                    relation = "separate-metadata-scope"
                elif overlap:
                    relation = "overlapping-source-paths"
                elif not a.paths or not b.paths:
                    relation = "source-scope-unknown"
                else:
                    relation = "disjoint-source-paths"
                pairs.append({
                    "operations": [a.operation, b.operation],
                    "relation": relation,
                    "same_head": bool(a.head and a.head == b.head),
                    "overlap_paths": overlap,
                })
        if pairs:
            alerts.append({
                "pr": resource,
                "operations": [e.operation for e in group],
                "actors": [e.actor for e in group],
                "take_ts": [e.timestamp for e in group],
                "pairs": pairs,
                "advice": "Compare current-head source receipts and coordinate before writing; no exclusive owner is assigned.",
            })
    return {
        "snapshot_ts": snapshot_ts,
        "parsed_events": len(parsed),
        "active_takes": len(active),
        "alerts": alerts,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot", type=Path, help="Slack JSON export or JSONL snapshot")
    p.add_argument("--window-minutes", type=int, default=90)
    p.add_argument("--format", choices=("text", "json"), default="text")
    args = p.parse_args(argv)
    try:
        report = audit(load_entries(args.snapshot), args.window_minutes)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        p.error(str(exc))
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"{len(report['alerts'])} PR(s) with concurrent TAKEs "
              f"({report['active_takes']} active operations; snapshot {report['snapshot_ts']})")
        for alert in report["alerts"]:
            relations = ", ".join(sorted({p["relation"] for p in alert["pairs"]}))
            print(f"- {alert['pr']} | {relations} | {', '.join(alert['operations'])}")
            print(f"  {alert['advice']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
