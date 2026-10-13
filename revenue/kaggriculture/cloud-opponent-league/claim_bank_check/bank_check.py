#!/usr/bin/env python3
"""Offline inclusive-bank audit. No network, allocation, or game counting."""
import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,16}\.[0-9]{6}", value):
        raise ValueError("timestamps must be Slack timestamp strings")
    return Decimal(value)


def audit(document):
    if not isinstance(document, dict):
        raise ValueError("input must be an object")
    cutoff = timestamp(document.get("snapshot_ts"))
    rows = document.get("claims")
    if not isinstance(rows, list):
        raise ValueError("claims must be a list")
    claims, copies = {}, {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each claim must be an object")
        key, bank = row.get("claim_id"), row.get("bank")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("claim_id must be a nonblank stable event/subclaim ID")
        if not isinstance(bank, list) or len(bank) != 2 or any(type(n) is not int or n < 1 for n in bank) or bank[0] > bank[1]:
            raise ValueError(f"{key}: bank must be two ordered positive integers")
        if timestamp(row.get("message_ts")) > cutoff:
            raise ValueError(f"{key}: event is after the snapshot cutoff")
        if row.get("phase", "claimed") not in ("claimed", "started", "completed"):
            raise ValueError(f"{key}: invalid phase")
        targets = row.get("supersedes", [])
        if not isinstance(targets, list) or any(not isinstance(t, str) for t in targets) or len(set(targets)) != len(targets):
            raise ValueError(f"{key}: supersedes must contain distinct IDs")
        op = row.get("operation_id")
        if op is not None and (not isinstance(op, str) or not op.strip()):
            raise ValueError(f"{key}: invalid operation_id")
        encoded = json.dumps(row, sort_keys=True, separators=(",", ":"))
        if key in copies and copies[key] != encoded:
            raise ValueError(f"{key}: inconsistent replay")
        copies[key], claims[key] = encoded, row
    retired, blocked, children = set(), [], {}
    for key, row in claims.items():
        for old in row.get("supersedes", []):
            if old not in claims:
                raise ValueError(f"{key}: missing superseded event {old}")
            if timestamp(claims[old]["message_ts"]) >= timestamp(row["message_ts"]):
                raise ValueError(f"{key}: supersession must follow its target")
            children.setdefault(old, []).append(key)
            if claims[old].get("phase", "claimed") != "claimed":
                blocked.append({"old": old, "replacement": key})
            else:
                retired.add(old)
    active = sorted((r for k, r in claims.items() if k not in retired), key=lambda r: (r["bank"], r["claim_id"]))
    conflicts = []
    for index, left in enumerate(active):
        # Starts are nondecreasing. Once a right start exceeds this left end,
        # every later interval is disjoint too. Do not slice the remaining list:
        # copying each suffix would make sparse snapshots quadratic again.
        left_end = left["bank"][1]
        for right_index in range(index + 1, len(active)):
            right = active[right_index]
            lo = right["bank"][0]
            if lo > left_end:
                break
            hi = min(left_end, right["bank"][1])
            conflicts.append({"left": left["claim_id"], "right": right["claim_id"], "bank": [lo, hi]})
    operations = {}
    for row in active:
        if row.get("operation_id"):
            operations.setdefault(row["operation_id"], []).append(row["claim_id"])
    return {
        "snapshot_ts": document["snapshot_ts"],
        "coverage": "Supplied snapshot only; not a live reservation service.",
        "coverage_note": document.get("coverage_note", ""),
        "active_claims": active,
        "superseded_claim_ids": sorted(retired),
        "conflicts": conflicts,
        "blocked_supersessions": sorted(blocked, key=lambda r: (r["old"], r["replacement"])),
        "forks": {k: sorted(v) for k, v in sorted(children.items()) if len(v) > 1},
        "reused_active_operation_ids": {k: sorted(v) for k, v in sorted(operations.items()) if len(v) > 1},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", help="JSON path, or - for stdin")
    args = parser.parse_args()
    try:
        text = sys.stdin.read() if args.snapshot == "-" else Path(args.snapshot).read_text(encoding="utf-8")
        result = audit(json.loads(text))
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(any(result[k] for k in ("conflicts", "blocked_supersessions", "forks", "reused_active_operation_ids")))


if __name__ == "__main__":
    sys.exit(main())
