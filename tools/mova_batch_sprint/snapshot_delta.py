"""Diff successive verified MOVA planner outputs without requerying providers.

Only material transitions are emitted; a fresh checked_at alone is not a
new work order. CLI never sends Slack, registers claims or changes payout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ISSUE_KEY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*$")
DISPATCH_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,256}$")
BOUNTY_UUID = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
MATERIAL_FIELDS = (
    "operation_id", "action", "active_owner", "pr_url", "pr_author", "source_pr_url",
    "source_pr_author", "source_state", "claim_state", "competition",
    "issue_state", "eligibility", "funding", "reward_usd", "fresh",
)


def _when(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("as_of must be timezone-aware ISO 8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid as_of timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("as_of needs an explicit timezone")
    return parsed


def _listing_key(platform: str, funding_url: str | None) -> str:
    """Use first-party BountyHub UUID for identity, not a mutable page slug.

    Unknown or ambiguous URL layouts keep their literal identities. This is
    an offline reconciliation hint, never a new provider URL or claim proof.
    """
    if not funding_url or platform.casefold() != "bountyhub":
        return funding_url or ""
    parsed = urlsplit(funding_url)
    host = parsed.netloc.casefold()
    if parsed.scheme != "https" or parsed.query or parsed.fragment:
        return funding_url
    parts = parsed.path.strip("/").split("/")
    if host == "api.bountyhub.dev":
        if (len(parts) == 3 and parts[:2] == ["api", "bounties"]
                and BOUNTY_UUID.fullmatch(parts[2])):
            return "bountyhub:uuid:" + parts[2].lower()
    elif host in {"bountyhub.dev", "www.bountyhub.dev"}:
        if parts and parts[0] in {"en", "de", "fr"}:
            parts = parts[1:]
        if (len(parts) in {3, 4} and parts[:2] == ["bounty", "view"]
                and BOUNTY_UUID.fullmatch(parts[2])
                and (len(parts) == 3 or re.fullmatch(r"[A-Za-z0-9_-]+", parts[3]))):
            return "bountyhub:uuid:" + parts[2].lower()
    return funding_url


def _rows(batch: dict) -> dict[tuple[str, str, str], list[dict]]:
    if not isinstance(batch, dict) or not isinstance(batch.get("work_orders"), list):
        raise ValueError("expected MOVA planner object with work_orders list")
    if len(batch["work_orders"]) > 5000:
        raise ValueError("snapshot exceeds 5000 entries")
    found = defaultdict(list)
    for item in batch["work_orders"]:
        if not isinstance(item, dict):
            raise ValueError("each work order must be an object")
        issue, platform, funding_url = (
            item.get("issue_key"), item.get("platform"), item.get("funding_url")
        )
        if not isinstance(issue, str) or not ISSUE_KEY.fullmatch(issue):
            raise ValueError("invalid canonical issue_key")
        if not isinstance(platform, str) or not platform:
            raise ValueError("platform missing")
        if funding_url is not None and (
            not isinstance(funding_url, str) or not funding_url.startswith("https://")
        ):
            raise ValueError("funding_url must be HTTPS or null")
        if not isinstance(item.get("action"), str) or not item["action"]:
            raise ValueError("work-order action missing")
        dispatch_id = item.get("operation_id")
        if dispatch_id is not None and (
            not isinstance(dispatch_id, str) or not DISPATCH_KEY.fullmatch(dispatch_id)
        ):
            raise ValueError("invalid work-order operation_id")
        found[(issue.lower(), platform.lower(), _listing_key(platform, funding_url))].append(item)
    return found


def _event(kind: str, key: tuple[str, str, str], old: dict | None,
           new: dict | None, changes: dict | None = None) -> dict:
    issue, platform, listing = key
    delta = changes or {}
    receipt = {
        "issue_key": issue, "platform": platform, "funding_url": listing,
        "kind": kind, "changes": delta,
        "previous_action": old.get("action") if old else None,
        "action": new.get("action") if new else None,
    }
    key_bytes = json.dumps(receipt, sort_keys=True, default=str).encode("utf-8")
    op_id = "MOVA-DELTA-" + hashlib.sha256(key_bytes).hexdigest()[:16]
    item = new or old or {}
    return {
        "operation_id": op_id, "event": kind, "issue_key": issue,
        "platform": platform, "funding_url": item.get("funding_url"),
        "previous_action": old.get("action") if old else None,
        "action": new.get("action") if new else None,
        "previous_planner_operation_id": old.get("operation_id") if old else None,
        "planner_operation_id": new.get("operation_id") if new else None,
        "active_owner": item.get("active_owner"),
        "pr_url": item.get("pr_url"), "source_pr_url": item.get("source_pr_url"),
        "changed_fields": delta,
    }


def diff_snapshots(previous: dict, current: dict) -> dict:
    """Stable transition report. No interpretation as paid or awarded."""
    older, newer = _when(previous.get("as_of")), _when(current.get("as_of"))
    if newer < older:
        raise ValueError("new snapshot precedes old snapshot")
    before_actor, after_actor = previous.get("actor"), current.get("actor")
    if not isinstance(before_actor, str) or not before_actor:
        raise ValueError("previous snapshot actor missing")
    if before_actor.lower() != str(after_actor).lower():
        raise ValueError("actor mismatch; compare one original author at a time")
    before, after = _rows(previous), _rows(current)
    events = []
    unchanged = 0
    for key in sorted(set(before) | set(after)):
        a, b = before.get(key, []), after.get(key, [])
        if len(a) > 1 or len(b) > 1:
            events.append(_event(
                "CONFLICTING_LISTINGS", key, a[0] if a else None,
                b[0] if b else None,
                {"previous_rows": len(a), "current_rows": len(b)},
            ))
        elif not a:
            events.append(_event("NEW_LISTING", key, None, b[0]))
        elif not b:
            events.append(_event("MISSING_FROM_SNAPSHOT", key, a[0], None))
        else:
            changed = {
                f: {"from": a[0].get(f), "to": b[0].get(f)}
                for f in MATERIAL_FIELDS if a[0].get(f) != b[0].get(f)
            }
            if changed:
                events.append(_event("MATERIAL_CHANGE", key, a[0], b[0], changed))
            else:
                unchanged += 1
    weight = {
        "CONFLICTING_LISTINGS": 0, "MISSING_FROM_SNAPSHOT": 1,
        "MATERIAL_CHANGE": 2, "NEW_LISTING": 3,
    }
    events.sort(key=lambda x: (
        weight[x["event"]], x["issue_key"], x["platform"], x["funding_url"] or "",
    ))
    return {
        "previous_as_of": previous["as_of"], "as_of": current["as_of"],
        "actor": before_actor, "unchanged_suppressed": unchanged,
        "events_count": len(events), "events": events,
        "provider_queries_executed": 0, "earned_usd": None,
    }


def _slack_listing_url(value: object) -> str | None:
    """Render only an intact, unambiguous HTTPS link from snapshot evidence."""
    if not isinstance(value, str) or not value or len(value) > 500:
        return None
    if any(ord(ch) <= 32 or ord(ch) == 127 for ch in value):
        return None
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.fragment):
        return None
    return value


def render_slack(delta: dict, limit: int = 25) -> str:
    """Bounded human-readable report; no network/send side effects."""
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    events = delta["events"]
    lines = [
        "MOVA SNAPSHOT DELTA | %s -> %s" %
        (delta["previous_as_of"], delta["as_of"]),
        "%d material/new/missing/conflict events; %d unchanged rechecks suppressed; 0 API calls." %
        (len(events), delta["unchanged_suppressed"]),
    ]
    for event in events[:limit]:
        changes = ",".join(sorted(event["changed_fields"])) or "-"
        lines.append("%s | %s | %s | %s -> %s | %s | %s" % (
            event["event"], event["issue_key"], event["platform"],
            event["previous_action"] or "-", event["action"] or "-",
            changes, event["operation_id"],
        ))
        # Keep the independent funded listing visible: identical sponsor
        # issues can have different providers/UUIDs and acceptance terms.
        listing = event.get("funding_url")
        if listing is not None:
            safe_listing = _slack_listing_url(listing)
            lines.append("  Snapshot listing URL: %s" % (
                safe_listing or "INVALID/AMBIGUOUS; inspect source JSON",
            ))
        if event["planner_operation_id"]:
            lines.append("  Planner dispatch ID: %s" % event["planner_operation_id"])
        if "operation_id" in event["changed_fields"]:
            lines.append("  REISSUED WORK KEY: %s -> %s; recheck active owner before delivery." % (
                event["previous_planner_operation_id"] or "-",
                event["planner_operation_id"] or "-",
            ))
        if event["event"] in {"MISSING_FROM_SNAPSHOT", "CONFLICTING_LISTINGS"}:
            lines.append("  AUDIT HOLD: reconcile original records; never infer claim withdrawal or payment.")
        if event["pr_url"]:
            lines.append("  Existing sponsor PR: %s" % event["pr_url"])
        if event["source_pr_url"]:
            lines.append("  Existing fork source: %s" % event["source_pr_url"])
    if len(events) > limit:
        lines.append("%d further events in JSON; no silent discard." %
                     (len(events) - limit))
    lines.append("Offline only. Re-fence sponsor/claim facts before a provider write; preserve original claim.")
    out = "\n".join(lines)
    if len(out) > 4800:
        out = out[:4650].rsplit("\n", 1)[0] + "\nMore events in JSON; never treat truncation as released work."
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("--format", choices=("json", "slack"), default="slack")
    parser.add_argument("--max-lines", type=int, default=25)
    args = parser.parse_args(argv)
    try:
        old = json.loads(args.previous.read_text(encoding="utf-8"))
        new = json.loads(args.current.read_text(encoding="utf-8"))
        delta = diff_snapshots(old, new)
        print(json.dumps(delta, sort_keys=True, indent=2) if args.format == "json"
              else render_slack(delta, limit=args.max_lines))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        print("INPUT_HOLD: %s" % error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
