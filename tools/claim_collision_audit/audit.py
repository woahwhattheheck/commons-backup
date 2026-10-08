#!/usr/bin/env python3
"""Audit fleet paid-issue claim collisions and exact-head publication fences.

Offline, Python stdlib only. This tool *does not* acquire distributed leases.
Each input row is independently sourced from actual Slack/GitHub receipts.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


SHA = re.compile(r"^[0-9a-fA-F]{40}$")
ISSUE = re.compile(r"^/([^/]+)/([^/]+)/issues/([1-9][0-9]*)/?$")
PR = re.compile(r"^/([^/]+)/([^/]+)/pull/([1-9][0-9]*)/?$")
BRANCH = re.compile(r"^/([^/]+)/([^/]+)/tree/(.+)$")
EVENTS = {"TAKE", "RELEASE", "HEAD_CHECK", "WRITE", "PUBLISH"}


def utc(raw: str) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("expected an ISO-8601 timestamp with a timezone")
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return value.astimezone(timezone.utc)


def canonical_issue(raw: str) -> str:
    if not isinstance(raw, str):
        raise ValueError("issue_url must be a string")
    parts = urlsplit(raw)
    match = ISSUE.fullmatch(parts.path)
    if parts.scheme != "https" or parts.netloc.lower() != "github.com" or not match:
        raise ValueError("issue_url must be https://github.com/owner/repo/issues/N")
    if parts.query or parts.fragment or parts.username or parts.password:
        raise ValueError("issue_url cannot have query, fragment, or credentials")
    return f"{match[1].lower()}/{match[2].lower()}#{int(match[3])}"


def canonical_pr(raw: str, issue_key: str, sponsor_only: bool = True) -> str:
    if not isinstance(raw, str):
        raise ValueError("pr_url must be a string")
    parts = urlsplit(raw)
    match = PR.fullmatch(parts.path)
    if (parts.scheme != "https" or parts.netloc.lower() != "github.com"
            or not match or parts.query or parts.fragment):
        raise ValueError("pr_url must be https://github.com/owner/repo/pull/N")
    repo = f"{match[1].lower()}/{match[2].lower()}"
    if sponsor_only and repo != issue_key.partition("#")[0]:
        raise ValueError("pr_url must refer to the canonical SPONSOR repository; fork-only PR is not publication")
    return f"{repo}#{int(match[3])}"



def carrier(data: dict, issue_key: str) -> str:
    """Use a sponsor/fork PR, or explicit source branch; never infer publication."""
    if data.get("pr_url"):
        return canonical_pr(data["pr_url"], issue_key, sponsor_only=False)
    raw = data.get("branch_url")
    if not isinstance(raw, str):
        raise ValueError("HEAD_CHECK/WRITE requires pr_url or branch_url")
    parts = urlsplit(raw)
    match = BRANCH.fullmatch(parts.path)
    if (parts.scheme != "https" or parts.netloc.lower() != "github.com"
            or not match or parts.query or parts.fragment):
        raise ValueError("branch_url must be https://github.com/owner/repo/tree/branch")
    return f"{match[1].lower()}/{match[2].lower()}:refs/heads/{match[3]}"


def sha(raw: object, field: str) -> str:
    if not isinstance(raw, str) or not SHA.fullmatch(raw):
        raise ValueError(f"{field} must be 40 hex characters")
    return raw.lower()


def load_events(filename: Path) -> tuple[list[dict], list[dict]]:
    rows = []
    errors = []
    seen = {}
    with filename.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("JSON row must be an object")
                kind = row.get("event")
                if kind not in EVENTS:
                    raise ValueError(f"event must be one of {sorted(EVENTS)}")
                key = canonical_issue(row.get("issue_url"))
                at = utc(row.get("at"))
                session = row.get("session")
                if not isinstance(session, str) or not session.strip() or len(session) > 150:
                    raise ValueError("session must be a nonempty string of at most 150 characters")
                operation_id = row.get("operation_id")
                if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 240:
                    raise ValueError("operation_id must be a nonempty stable string (max 240)")
                fingerprint = json.dumps(row, sort_keys=True, separators=(",", ":"))
                if operation_id in seen:
                    if seen[operation_id] != fingerprint:
                        errors.append({"line": number, "code": "OPERATION_ID_REUSED",
                                       "issue": key, "detail": operation_id})
                    continue
                seen[operation_id] = fingerprint
                rows.append({"data": row, "kind": kind, "issue": key,
                             "session": session.strip(), "at": at, "line": number})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                errors.append({"line": number, "code": "INVALID_ROW", "detail": str(exc)})
    rows.sort(key=lambda row: (row["at"], row["line"]))
    return rows, errors


def audit(rows: list[dict], errors: list[dict], now: datetime,
          ttl_seconds: int, max_head_age_seconds: int) -> dict:
    state = defaultdict(lambda: {"owner": None, "lease_until": None,
                                 "head_reads": {}, "head": None,
                                 "published_pr": None})
    stats = defaultdict(Counter)
    anomalies = list(errors)

    def warn(row: dict, code: str, detail: str) -> None:
        anomalies.append({"line": row["line"], "issue": row["issue"],
                          "code": code, "detail": detail})

    def live(entry: dict, at: datetime, row: dict | None = None) -> bool:
        if entry["owner"] is None:
            return False
        if entry["lease_until"] < at:
            if row is not None:
                warn(row, "LEASE_EXPIRED", f"Owner {entry['owner']} lease elapsed before this event")
            entry["owner"], entry["lease_until"] = None, None
            return False
        return True

    for row in rows:
        key, kind, at, session = row["issue"], row["kind"], row["at"], row["session"]
        data, entry, counters = row["data"], state[key], stats[key]
        counters["events"] += 1
        if at > now:
            warn(row, "FUTURE_EVENT", "event timestamp is later than --now")
            continue
        active = live(entry, at, row)

        if kind == "TAKE":
            counters["takes"] += 1
            lease = data.get("lease_seconds", ttl_seconds)
            if type(lease) is not int or lease < 60 or lease > 86400:
                warn(row, "INVALID_LEASE", "lease_seconds must be 60..86400")
                continue
            if active and entry["owner"] != session:
                counters["collisions"] += 1
                warn(row, "TAKE_COLLISION", f"{session} overlaps active owner {entry['owner']}")
                continue
            entry["owner"], entry["lease_until"] = session, at + timedelta(seconds=lease)

        elif kind == "RELEASE":
            if not active or entry["owner"] != session:
                warn(row, "FOREIGN_RELEASE", f"{session} has no current ownership")
            else:
                entry["owner"], entry["lease_until"] = None, None
                counters["releases"] += 1

        elif kind == "HEAD_CHECK":
            try:
                head = sha(data.get("head_sha"), "head_sha")
                pr = carrier(data, key)
            except ValueError as exc:
                warn(row, "INVALID_HEAD_CHECK", str(exc))
                continue
            # A new valid read after a write re-enables one further mutation.
            entry["head_reads"][session] = {"head": head, "pr": pr, "at": at, "used": False}
            counters["head_checks"] += 1

        elif kind == "WRITE":
            counters["writes_attempted"] += 1
            try:
                pr = carrier(data, key)
                expected = sha(data.get("expected_head_sha"), "expected_head_sha")
                new = sha(data.get("new_head_sha"), "new_head_sha")
                if expected == new:
                    raise ValueError("new_head_sha must differ from expected_head_sha")
            except ValueError as exc:
                warn(row, "INVALID_WRITE", str(exc))
                counters["blocked_writes"] += 1
                continue
            last = entry["head_reads"].get(session)
            valid = (active and entry["owner"] == session and last is not None
                     and not last["used"] and last["pr"] == pr
                     and last["head"] == expected
                     and timedelta(0) <= at - last["at"] <= timedelta(seconds=max_head_age_seconds)
                     and (entry["head"] is None or entry["head"] == expected))
            if not valid:
                counters["blocked_writes"] += 1
                warn(row, "UNFENCED_WRITE",
                     "Missing owner/lease, fresh matching unconsumed HEAD_CHECK, or expected head drift")
                continue
            last["used"] = True
            entry["head"] = new
            counters["fenced_writes"] += 1

        elif kind == "PUBLISH":
            counters["publishes_attempted"] += 1
            try:
                pr = canonical_pr(data.get("pr_url"), key)
            except ValueError as exc:
                warn(row, "INVALID_PUBLISH", str(exc))
                continue
            if not active or entry["owner"] != session:
                warn(row, "UNOWNED_PUBLISH", "publisher lacks a live owner lease")
            elif entry["published_pr"] and entry["published_pr"] != pr:
                counters["collisions"] += 1
                warn(row, "DUPLICATE_SPONSOR_PR",
                     f"existing {entry['published_pr']} vs new {pr}")
            else:
                entry["published_pr"] = pr
                counters["publishes_confirmed"] += 1

    for key, entry in state.items():
        live(entry, now)
    return {
        "as_of": now.isoformat(),
        "summary": {
            "issues": len(set(stats) | set(state)),
            "events": sum(v["events"] for v in stats.values()),
            "collisions": sum(v["collisions"] for v in stats.values()),
            "blocked_writes": sum(v["blocked_writes"] for v in stats.values()),
            "anomalies": len(anomalies),
        },
        "issues": {
            key: {"active_owner": state[key]["owner"],
                  "lease_until": state[key]["lease_until"].isoformat()
                  if state[key]["lease_until"] else None,
                  "last_verified_head": state[key]["head"],
                  "sponsor_pr": state[key]["published_pr"],
                  **dict(stats[key])}
            for key in sorted(set(stats) | set(state))
        },
        "anomalies": sorted(anomalies, key=lambda v: (v.get("line", 0), v["code"])),
    }


def slack_report(result: dict) -> str:
    s = result["summary"]
    lines = [
        f"CLAIM COLLISION AUDIT | {result['as_of']}",
        f"Issues {s['issues']} | Events {s['events']} | Collisions {s['collisions']} "
        f"| Unfenced writes {s['blocked_writes']} | Anomalies {s['anomalies']}",
    ]
    for key, info in result["issues"].items():
        if info.get("collisions", 0) or info.get("blocked_writes", 0):
            lines.append(f"- {key}: {info.get('collisions', 0)} collisions, "
                         f"{info.get('blocked_writes', 0)} blocked writes; "
                         f"owner={info['active_owner'] or 'none'}")
    for problem in result["anomalies"][:30]:
        lines.append(f"- L{problem.get('line', '?')} {problem.get('issue', '')} "
                     f"{problem['code']}: {problem.get('detail', '')}")
    if len(result["anomalies"]) > 30:
        lines.append(f"... {len(result['anomalies']) - 30} further anomalies in JSON output")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path, help="Verified JSONL TAKE/RELEASE/HEAD_CHECK/WRITE/PUBLISH events")
    parser.add_argument("--now", type=utc, default=None, help="ISO-8601 audit clock (default UTC now)")
    parser.add_argument("--lease-seconds", type=int, default=900)
    parser.add_argument("--max-head-age-seconds", type=int, default=300)
    parser.add_argument("--format", choices=("json", "slack"), default="json")
    args = parser.parse_args()
    if not 60 <= args.lease_seconds <= 86400 or not 1 <= args.max_head_age_seconds <= 3600:
        parser.error("lease must be 60..86400 and max-head-age 1..3600 seconds")
    try:
        rows, errors = load_events(args.events)
        result = audit(rows, errors, args.now or datetime.now(timezone.utc),
                       args.lease_seconds, args.max_head_age_seconds)
        print(json.dumps(result, indent=2, sort_keys=True) if args.format == "json"
              else slack_report(result))
        return 2 if result["summary"]["anomalies"] else 0
    except OSError as exc:
        print(f"INPUT_ERROR: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
