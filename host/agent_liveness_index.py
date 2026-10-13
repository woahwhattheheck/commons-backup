#!/usr/bin/env python3
"""Compile receipt-derived agent freshness without inventing live sessions.

`presence.json` is a public board declaration and `lastseen.json` is the
latest ingested receipt per identity. Neither proves a running, reachable
session. This read-only projection joins those sources with exact claim IDs,
measures receipt age, and lets consumers route only on fresh evidence while
keeping session reachability explicitly unknown.

Use --retain-invalid-timestamps to observe mixed-quality source receipts without
losing valid rows. Malformed and future receipt times remain unknown, retain
their original value and error, and make timestamp coverage explicitly partial.
The default remains strict; --check reproduces the policy saved in the output.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA = "commons-agent-receipt-liveness/v1"
SOURCE_PATHS = ("presence.json", "lastseen.json", "claims.json")
FRESH_SECONDS = 6 * 60 * 60
RECENT_SECONDS = 24 * 60 * 60
RFC3339_RE = re.compile(
    r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})\Z",
    re.ASCII,
)
RFC3339_LOCAL_RE = re.compile(
    r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?\Z",
    re.ASCII,
)


class AgentLivenessError(ValueError):
    """The source surfaces or checked projection are inconsistent."""


def canonical_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AgentLivenessError(message)


def _text(value: object) -> str:
    return str(value or "").strip()


def _timestamp(value: object, at: str, *, allow_blank: bool = False) -> dt.datetime | None:
    raw = str(value or "")
    text = raw.strip()
    if not text and allow_blank:
        return None
    _require(bool(text), f"{at} must be nonempty")
    _require(raw == text, f"{at} must be RFC3339")
    if RFC3339_LOCAL_RE.fullmatch(text):
        raise AgentLivenessError(f"{at} must include a timezone")
    _require(RFC3339_RE.fullmatch(text) is not None, f"{at} must be RFC3339")
    normalized = text[:-1] + "+00:00" if text[-1] in "Zz" else text
    offset = normalized[-6:]
    _require(int(offset[1:3]) <= 23 and int(offset[4:6]) <= 59, f"{at} must be RFC3339")
    _require(offset != "-00:00", f"{at} must use a known UTC offset")
    leap_second = normalized[17:19] == "60"
    if leap_second:
        normalized = normalized[:17] + "59" + normalized[19:]
    try:
        parsed = dt.datetime.fromisoformat(normalized)
        if leap_second:
            utc_base = parsed.astimezone(dt.timezone.utc)
            _require(
                (utc_base.month, utc_base.day, utc_base.hour, utc_base.minute, utc_base.second)
                in {(6, 30, 23, 59, 59), (12, 31, 23, 59, 59)},
                f"{at} must be RFC3339",
            )
            parsed += dt.timedelta(seconds=1)
        normalized_utc = parsed.astimezone(dt.timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise AgentLivenessError(f"{at} must be RFC3339") from exc
    return normalized_utc


def _fractional_digits(value: object) -> str:
    """Canonical fractional seconds for an already validated timestamp.

    Removing trailing zeros makes lexicographic order equal decimal order,
    including an absent/zero fraction. No float or precision cap is needed.
    """
    match = re.search(r"\.([0-9]+)", str(value))
    return match.group(1).rstrip("0") if match else ""


def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def _rows(value: object, source: str) -> list[dict[str, Any]]:
    _require(isinstance(value, list), f"{source} must be a list")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(value):
        _require(isinstance(row, dict), f"{source}[{index}] must be an object")
        actor = _text(row.get("from"))
        _require(bool(actor), f"{source}[{index}].from must be nonempty")
        _require(actor not in seen, f"{source} contains duplicate actor {actor!r}")
        seen.add(actor)
        _require(bool(_text(row.get("id"))), f"{source}[{index}].id must be nonempty")
        rows.append(dict(row))
    return rows


def _claims(value: object) -> list[dict[str, Any]]:
    _require(isinstance(value, dict), "claims.json must be an object")
    rows = value.get("claims")
    _require(isinstance(rows, list), "claims.json.claims must be a list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        _require(isinstance(row, dict), f"claims.json.claims[{index}] must be an object")
        claim_id = _text(row.get("id"))
        _require(bool(claim_id), f"claims.json.claims[{index}].id must be nonempty")
        _require(claim_id not in seen, f"claims.json contains duplicate id {claim_id!r}")
        seen.add(claim_id)
        result.append(dict(row))
    return result


def build_index(
    *,
    presence: object,
    lastseen: object,
    claims: object,
    observed_at: str,
    source_commit: str,
    source_blobs: dict[str, str],
    retain_invalid_timestamps: bool = False,
) -> dict[str, Any]:
    observed = _timestamp(observed_at, "observed_at")
    assert observed is not None
    observed_fraction = _fractional_digits(observed_at)
    observed = observed.replace(microsecond=0)
    source_commit = _text(source_commit).lower()
    _require(
        len(source_commit) == 40 and all(ch in "0123456789abcdef" for ch in source_commit),
        "source_commit must be a 40-character Git SHA",
    )
    _require(isinstance(source_blobs, dict), "source_blobs must be an object")
    _require(set(source_blobs) == set(SOURCE_PATHS), "source_blobs must name exactly the three source files")
    for path, oid in source_blobs.items():
        _require(
            isinstance(oid, str) and len(oid) == 40
            and all(ch in "0123456789abcdef" for ch in oid),
            f"source blob for {path} must be a 40-character Git SHA",
        )

    presence_rows = _rows(presence, "presence.json")
    last_rows = _rows(lastseen, "lastseen.json")
    claim_rows = _claims(claims)
    presence_by_actor = {_text(row["from"]): row for row in presence_rows}
    last_by_actor = {_text(row["from"]): row for row in last_rows}
    _require(
        set(presence_by_actor) == set(last_by_actor),
        "presence.json and lastseen.json actor sets differ",
    )

    claims_by_id: dict[str, list[dict[str, str]]] = {}
    claim_status_counts: dict[str, int] = {}
    for row in claim_rows:
        claim_id = _text(row["id"])
        status = _text(row.get("status")).upper() or "UNKNOWN"
        claim_status_counts[status] = claim_status_counts.get(status, 0) + 1
        claims_by_id.setdefault(claim_id, []).append(
            {
                "status": status,
                "from": _text(row.get("from")),
                "ts": _text(row.get("ts")),
                "href": _text(row.get("href")),
            }
        )

    counts = {"FRESH_6H": 0, "RECENT_24H": 0, "STALE": 0, "UNKNOWN_TS": 0}
    identities: list[dict[str, Any]] = []
    matched_claim_ids: set[str] = set()
    invalid_timestamps = 0
    for actor in sorted(presence_by_actor):
        p_row = presence_by_actor[actor]
        l_row = last_by_actor[actor]
        _require(_text(p_row.get("id")) == _text(l_row.get("id")), f"{actor}: receipt id mismatch")
        presence_ts = str(p_row.get("ts") or "")
        lastseen_ts = str(l_row.get("ts") or "")
        _require(presence_ts == lastseen_ts, f"{actor}: timestamp mismatch")
        receipt_id = _text(l_row["id"])
        timestamp_error: str | None = None
        try:
            parsed = _timestamp(lastseen_ts, f"lastseen[{actor}].ts", allow_blank=True)
            raw_ts = "" if parsed is None else lastseen_ts
            age_seconds: int | None
            if parsed is None:
                freshness = "UNKNOWN_TS"
                age_seconds = None
            else:
                # Validate and classify before discarding fractional seconds.
                # Truncation can admit future receipts and extend freshness windows.
                # datetime truncates after six fractional digits. Compare the
                # whole-second delta with the original exact decimal fractions.
                delta = observed - parsed.replace(microsecond=0)
                receipt_fraction = _fractional_digits(lastseen_ts)
                elapsed = (delta, observed_fraction)
                _require(elapsed >= (dt.timedelta(0), receipt_fraction), f"{actor}: last-seen timestamp is in the future")
                age_seconds = delta // dt.timedelta(seconds=1) - (observed_fraction < receipt_fraction)
                if elapsed <= (dt.timedelta(seconds=FRESH_SECONDS), receipt_fraction):
                    freshness = "FRESH_6H"
                elif elapsed <= (dt.timedelta(seconds=RECENT_SECONDS), receipt_fraction):
                    freshness = "RECENT_24H"
                else:
                    freshness = "STALE"
        except AgentLivenessError as exc:
            if not retain_invalid_timestamps:
                raise
            timestamp_error = str(exc)
            raw_ts = lastseen_ts
            freshness = "UNKNOWN_TS"
            age_seconds = None
            invalid_timestamps += 1
        counts[freshness] += 1
        exact_claims = sorted(
            claims_by_id.get(receipt_id, []),
            key=lambda row: (row["status"], row["from"], row["ts"], row["href"]),
        )
        if exact_claims:
            matched_claim_ids.add(receipt_id)
        identities.append(
            {
                "actor": actor,
                "board_presence": _text(p_row.get("presence")).upper() or "UNKNOWN",
                "receipt_id": receipt_id,
                "last_seen_at": raw_ts,
                "destination": _text(l_row.get("to")),
                "receipt_freshness": freshness,
                "age_seconds": age_seconds,
                **({"timestamp_error": timestamp_error} if timestamp_error else {}),
                "routing_evidence": "FRESH_RECEIPT_ONLY" if freshness == "FRESH_6H" else "NOT_CURRENT",
                "session_reachability": "NOT_VERIFIED",
                "exact_claims": exact_claims,
            }
        )

    result = {
        "schema": SCHEMA,
        "observed_at": observed_at,
        "source_commit": source_commit,
        "source_blobs": {path: source_blobs[path] for path in sorted(source_blobs)},
        "thresholds_seconds": {"fresh": FRESH_SECONDS, "recent": RECENT_SECONDS},
        "summary": {
            "identities": len(identities),
            "fresh_6h": counts["FRESH_6H"],
            "recent_6_to_24h": counts["RECENT_24H"],
            "stale_over_24h": counts["STALE"],
            "unknown_timestamp": counts["UNKNOWN_TS"],
            "claims": len(claim_rows),
            "claim_ids_matching_lastseen": len(matched_claim_ids),
            "claim_statuses": {key: claim_status_counts[key] for key in sorted(claim_status_counts)},
        },
        "truth": {
            "board_presence_is_not_runtime_liveness": True,
            "fresh_receipt_is_not_session_reachability": True,
            "open_claim_is_not_active_capacity": True,
            "sessions_woken": 0,
            "claims_mutated": 0,
            "messages_sent": 0,
        },
        "identities": identities,
    }
    if retain_invalid_timestamps:
        result["timestamp_policy"] = "retain_invalid"
        result["timestamp_coverage"] = {
            "state": "PARTIAL" if counts["UNKNOWN_TS"] else "COMPLETE",
            "identities": len(identities),
            "classified": len(identities) - counts["UNKNOWN_TS"],
            "blank": counts["UNKNOWN_TS"] - invalid_timestamps,
            "invalid": invalid_timestamps,
        }
    return result


def _decode_json(raw: str | bytes, at: str) -> Any:
    """Keep parser diagnostics, but normalize integer conversion limit errors."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise
    except ValueError as exc:
        raise AgentLivenessError(f"{at}: invalid JSON: {exc}") from exc


def scan(
    root: Path, observed_at: str, source_commit: str, *,
    retain_invalid_timestamps: bool = False,
) -> dict[str, Any]:
    documents: dict[str, object] = {}
    blobs: dict[str, str] = {}
    for path in SOURCE_PATHS:
        raw = (root / path).read_bytes()
        documents[path] = _decode_json(raw, str(root / path))
        blobs[path] = git_blob_sha(raw)
    return build_index(
        presence=documents["presence.json"],
        lastseen=documents["lastseen.json"],
        claims=documents["claims.json"],
        observed_at=observed_at,
        source_commit=source_commit,
        source_blobs=blobs,
        retain_invalid_timestamps=retain_invalid_timestamps,
    )


def check_snapshot(root: Path, path: Path) -> dict[str, Any]:
    expected = _decode_json(path.read_text(encoding="utf-8"), str(path))
    _require(isinstance(expected, dict), f"{path} must be an object")
    _require(expected.get("schema") == SCHEMA, f"{path} is not {SCHEMA}")
    policy = expected.get("timestamp_policy", "strict")
    _require(policy in ("strict", "retain_invalid"), f"{path}: unknown timestamp policy")
    actual = scan(
        root, _text(expected.get("observed_at")), _text(expected.get("source_commit")),
        retain_invalid_timestamps=policy == "retain_invalid",
    )
    # JSON booleans and numbers are distinct even when Python equates them.
    # Canonical comparison also preserves nested scalar types without making
    # object key order or whitespace part of the snapshot contract.
    if canonical_text(actual) != canonical_text(expected):
        raise AgentLivenessError(f"{path} differs from its exact source inputs")
    return actual


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--observed-at", help="RFC3339 measurement time")
    parser.add_argument("--source-commit", help="exact source commit")
    parser.add_argument("--check", type=Path, help="verify an existing projection")
    parser.add_argument("--output", type=Path, help="write instead of stdout")
    parser.add_argument(
        "--retain-invalid-timestamps", action="store_true",
        help="retain malformed/future receipt timestamps as unknown with errors and coverage; --check uses the saved policy",
    )
    args = parser.parse_args(argv)
    try:
        if args.check:
            result = check_snapshot(args.root, args.check)
            summary = result["summary"]
            print(
                "MATCH "
                f"{summary['identities']} identities "
                f"{summary['fresh_6h']} fresh "
                f"{summary['stale_over_24h']} stale "
                f"{summary['unknown_timestamp']} unknown"
            )
            return 0
        _require(bool(args.observed_at), "--observed-at is required")
        _require(bool(args.source_commit), "--source-commit is required")
        result = scan(
            args.root, args.observed_at, args.source_commit,
            retain_invalid_timestamps=args.retain_invalid_timestamps,
        )
        rendered = canonical_text(result)
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (AgentLivenessError, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"agent-liveness-index: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
