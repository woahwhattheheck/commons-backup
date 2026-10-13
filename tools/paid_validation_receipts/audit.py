"""Offline, source-head-fenced reuse of focused bounty validation evidence.

This tool does not run tests, call GitHub, verify external evidence,
make claims, or infer payment. Input is a previously verified local snapshot.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_CHECK = re.compile(r"[A-Za-z0-9_./:-]{1,96}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_OUTCOMES = frozenset({"passed", "failed", "blocked", "not_run"})


class InputError(ValueError):
    """Invalid or misleading saved validation snapshot."""


def _must_object(value: object, name: str) -> dict:
    if type(value) is not dict:
        raise InputError(f"{name} must be an object")
    return value


def _keys(obj: dict, required: set[str], optional: set[str], name: str) -> None:
    missing = required - obj.keys()
    unknown = obj.keys() - required - optional
    if missing or unknown:
        raise InputError(f"{name}: missing={sorted(missing)} unknown={sorted(unknown)}")


def _head(value: object, name: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise InputError(f"{name} must be a full lowercase 40-character source SHA")
    return value


def _check_id(value: object) -> str:
    if not isinstance(value, str) or not _CHECK.fullmatch(value):
        raise InputError("check_id must be a compact stable identifier")
    return value


def _time(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise InputError(f"{name} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError(f"{name} is not ISO time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InputError(f"{name} requires a timezone")
    return parsed.astimezone(timezone.utc)


def _safe_evidence_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
        raise InputError("executed check needs a safe HTTPS evidence URL")
    p = urlsplit(value)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise InputError("evidence URL must be HTTPS, without credentials, query or fragment")
    return value


def _strict_pairs(pairs: list[tuple[str, object]]) -> dict:
    output = {}
    for key, value in pairs:
        if key in output:
            raise InputError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def load(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise InputError("snapshot missing or larger than 2 MB")
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(InputError(f"invalid constant: {value}")),
        )
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise InputError("invalid UTF-8 JSON snapshot") from exc


def evaluate(snapshot: dict, *, now: datetime | None = None, max_age_hours: int = 168) -> dict:
    """Return offline advice, never a claim of provider-authenticated tests."""
    data = _must_object(snapshot, "snapshot")
    _keys(data, {"repository", "pull_request", "current_head", "checks", "receipts"}, set(), "snapshot")
    if not isinstance(data["repository"], str) or not _REPO.fullmatch(data["repository"]):
        raise InputError("repository must be owner/name")
    if type(data["pull_request"]) is not int or data["pull_request"] <= 0:
        raise InputError("pull_request must be a positive integer")
    head = _head(data["current_head"], "current_head")
    if not isinstance(data["checks"], list) or not 1 <= len(data["checks"]) <= 200:
        raise InputError("checks must have 1–200 entries")
    if not isinstance(data["receipts"], list) or len(data["receipts"]) > 1000:
        raise InputError("receipts must have up to 1000 entries")
    if type(max_age_hours) is not int or not 1 <= max_age_hours <= 720:
        raise InputError("max_age_hours must be 1–720")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise InputError("now must have a timezone")
    expected = []
    for item in data["checks"]:
        c = _must_object(item, "check")
        _keys(c, {"id"}, set(), "check")
        identifier = _check_id(c["id"])
        if identifier in expected:
            raise InputError("duplicate check id")
        expected.append(identifier)

    indexed: dict[str, list[dict]] = {item: [] for item in expected}
    for item in data["receipts"]:
        r = _must_object(item, "receipt")
        _keys(r, {"check_id", "head", "outcome", "checked_at"}, {"evidence_url"}, "receipt")
        identifier = _check_id(r["check_id"])
        if identifier not in indexed:
            raise InputError("receipt refers to an unrequested check")
        source_head = _head(r["head"], "receipt head")
        outcome = r["outcome"]
        if not isinstance(outcome, str) or outcome not in _OUTCOMES:
            raise InputError("receipt outcome must be passed/failed/blocked/not_run")
        checked = _time(r["checked_at"], "checked_at")
        if checked > now + timedelta(minutes=2):
            raise InputError("future-dated receipt")
        evidence_url = r.get("evidence_url")
        if outcome in {"passed", "failed"}:
            evidence_url = _safe_evidence_url(evidence_url)
        elif evidence_url is not None:
            raise InputError("not_run/blocked cannot carry an executed evidence URL")
        indexed[identifier].append({
            "head": source_head, "outcome": outcome, "checked_at": checked,
            "evidence_url": evidence_url,
        })

    advice = []
    for identifier in expected:
        records = indexed[identifier]
        same_head = [r for r in records if r["head"] == head]
        executions = [r for r in same_head if r["outcome"] in {"passed", "failed"}]
        outcome = "PERFORM_FOCUSED"
        reason = "No executed receipt for this exact source head"
        evidence = None
        if executions:
            executions.sort(key=lambda r: r["checked_at"], reverse=True)
            latest = executions[0]
            if any(r["outcome"] != latest["outcome"] and r["checked_at"] == latest["checked_at"] for r in executions):
                outcome, reason = "RECONCILE_RECEIPTS", "Conflicting executed outcomes at the same instant"
            elif latest["outcome"] == "failed":
                outcome, reason = "FOCUSED_FIX_REQUIRED", "Latest executed check failed at the exact head"
                evidence = latest["evidence_url"]
            elif now - latest["checked_at"] > timedelta(hours=max_age_hours):
                outcome, reason = "REVIEW_OLD_RECEIPT", "Same-head passing evidence exceeded configured age"
                evidence = latest["evidence_url"]
            else:
                outcome, reason = "REUSE_REPORTED_PASS", "Same exact head, executed passing evidence within configured age"
                evidence = latest["evidence_url"]
        elif any(r["head"] != head and r["outcome"] == "passed" for r in records):
            outcome, reason = "SOURCE_HEAD_CHANGED", "Passing history exists only for older or different source"
        elif same_head:
            reason = "Only blocked/not-run reports exist; a test file is not an execution"
        advice.append({"check_id": identifier, "decision": outcome, "reason": reason, "evidence_url": evidence})
    return {
        "repository": data["repository"], "pull_request": data["pull_request"],
        "current_head": head, "advice": advice,
        "limits": {"max_age_hours": max_age_hours, "external_evidence_authenticated": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--format", choices=("json", "slack"), default="json")
    parser.add_argument("--max-age-hours", type=int, default=168)
    args = parser.parse_args()
    try:
        result = evaluate(load(args.snapshot), max_age_hours=args.max_age_hours)
    except (InputError, OSError) as exc:
        print(f"INPUT_HOLD: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"FOCUSED VALIDATION · {result['repository']}#{result['pull_request']} @ {result['current_head']}")
        for row in result["advice"]:
            print(f"{row['check_id']}: {row['decision']} — {row['reason']}")
            if row["evidence_url"]:
                print(f"  recorded_evidence: {row['evidence_url']}")
        print("Offline, reporter-supplied evidence only; no test, claim, award, payment or provider verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
