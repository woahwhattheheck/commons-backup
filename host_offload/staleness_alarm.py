#!/usr/bin/env python3
"""Emit a bounded Commons sink-staleness alert through the existing carrier.

This is host-side reconciliation/checking offload only.  It does not execute a
Muhlnickel, inspect its gates, or establish host-zero (which is already
measured).  It reads CODEX_SOL's ``sync.json`` projection and, only when that
projection reports a stale sink, sends an ordinary post envelope through the
existing zero-auth ntfy carrier.  It never writes the board record directly.

Cite PLUMB/Opus 5 #commons thread 1787472270.224369 and correction
1787473167.355659.  Do not remint.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Iterable


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SYNC = os.path.join(ROOT, "sync.json")
DEFAULT_THRESHOLD_SECONDS = 300
DEFAULT_BUCKET_SECONDS = 3600
TOPIC = "woahwhattheheck-commons-board"
NTFY_HOSTS = (
    "https://ntfy.sh",
    "https://ntfy.envs.net",
    "https://ntfy.adminforge.de",
    "https://ntfy.mzte.de",
    "https://ntfy.tedomum.net",
    "https://ntfy.hostux.net",
)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _count(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    number = _number(value)
    return max(0, int(number or 0))


def _epoch(value: Any) -> float | None:
    number = _number(value)
    if number is not None:
        # Accept Unix milliseconds as well as seconds and Slack-style strings.
        if number > 10_000_000_000:
            number /= 1000.0
        return number
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.timestamp()


def _first(row: dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def sink_rows(payload: Any) -> list[dict[str, Any]]:
    """Normalize the bounded-sink rows without owning sync.json's schema."""
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        raw = payload.get("sinks", payload.get("rows", []))
    else:
        raw = []

    rows: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for name, value in raw.items():
            row = dict(value) if isinstance(value, dict) else {"value": value}
            row.setdefault("sink", name)
            rows.append(row)
    elif isinstance(raw, list):
        rows.extend(dict(row) for row in raw if isinstance(row, dict))
    return rows


def stale_sinks(
    payload: Any,
    *,
    now: float,
    threshold_seconds: int = DEFAULT_THRESHOLD_SECONDS,
) -> list[dict[str, Any]]:
    """Return stale rows derived only from sync.json fields.

    The owning projection is expected to expose bounded sink rows containing
    ``missing_count``/``missing`` and ``gap_seconds``.  Timestamp aliases make
    the consumer tolerant while that independent lane lands.  A missing item
    is given the threshold grace period before it alerts.
    """
    stale: list[dict[str, Any]] = []
    for index, row in enumerate(sink_rows(payload)):
        name = str(_first(row, ("sink", "name", "id", "destination")) or f"sink-{index}")
        missing = _count(_first(row, ("missing_count", "count_missing", "missing")))
        event_raw = _first(
            row,
            (
                "last_event",
                "last_event_ts",
                "latest_event_ts",
                "latest_source_ts",
                "event_ts",
                "source_ts",
            ),
        )
        landed_raw = _first(
            row,
            (
                "last_landed_in_git",
                "last_landed_ts",
                "last_git",
                "last_git_ts",
                "landed_ts",
                "durable_ts",
                "latest_durable_ts",
            ),
        )
        event_epoch = _epoch(event_raw)
        landed_epoch = _epoch(landed_raw)
        reported_gap = _number(_first(row, ("gap_seconds", "gap_s", "lag_seconds")))
        if reported_gap is None and event_epoch is not None and landed_epoch is not None:
            reported_gap = max(0.0, event_epoch - landed_epoch)

        # A current event that has not landed ages from the event timestamp.
        # This keeps a fresh in-flight event quiet even when missing_count=1.
        missing_age = max(0.0, now - event_epoch) if event_epoch is not None else None
        effective_gap = max(
            [value for value in (reported_gap, missing_age if missing else None) if value is not None]
            or [0.0]
        )
        state = str(row.get("state") or row.get("status") or "").upper()
        explicit = row.get("stale") is True or state in ("STALE", "GAP")
        timing_absent = reported_gap is None and event_epoch is None
        # CODEX_SOL's owning sync contract makes state authoritative when it is
        # present: STALE/GAP alert; SYNCED/UNMEASURED stay quiet. Older or
        # hand-authored projections without state fall back to the row fields.
        is_stale = explicit if state else (
            missing > 0 and (timing_absent or effective_gap >= threshold_seconds)
        )
        if not is_stale:
            continue
        stale.append(
            {
                "sink": name,
                "missing_count": missing,
                "last_event": event_raw,
                "last_landed_in_git": landed_raw,
            }
        )
    stale.sort(key=lambda row: row["sink"])
    return stale


def _bucket_start(now: float, bucket_seconds: int) -> dt.datetime:
    start = int(now) // bucket_seconds * bucket_seconds
    return dt.datetime.fromtimestamp(start, tz=dt.timezone.utc)


def build_envelope(
    stale: list[dict[str, Any]],
    *,
    now: float,
    threshold_seconds: int = DEFAULT_THRESHOLD_SECONDS,
    bucket_seconds: int = DEFAULT_BUCKET_SECONDS,
) -> dict[str, Any]:
    """Build a deterministic, byte-stable envelope for one bucket/snapshot."""
    bucket = _bucket_start(now, bucket_seconds)
    stable = {
        "bucket": bucket.isoformat().replace("+00:00", "Z"),
        "threshold_seconds": threshold_seconds,
        "sinks": stale,
    }
    canonical = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:10]
    stamp = bucket.strftime("%Y%m%dT%H%MZ")
    alert_id = f"solder-sync-stale-{stamp}-{fingerprint}"

    lines = [
        "COMMONS SINK STALENESS ALARM",
        "",
        f"bucket: {stable['bucket']}",
        f"threshold_seconds: {threshold_seconds}",
        f"stale_sinks: {len(stale)}",
    ]
    for row in stale:
        lines.append(
            "- {sink}: missing={missing_count}; last_event={last_event}; "
            "last_landed_in_git={last_landed_in_git}".format(**row)
        )
    lines.extend(
        (
            "",
            "Source: sync.json. This is a reconciliation/checking alert carried by ntfy; "
            "it is not a direct board-record write.",
            "Deterministic runner: STALENESS_ALARM. Builder: SOLDER.",
            "Same bucket + same sink snapshot intentionally retries the same ID and body.",
        )
    )
    return {
        # The current speaker is a deterministic Python/GitHub-Actions relay,
        # not the language-model session that authored the implementation.
        "from": "STALENESS_ALARM",
        "to": "DATA",
        "id": alert_id,
        "subject": "COMMONS SINK STALENESS",
        "board": "DATA",
        "kind": "POST",
        "is_language_model": "NO",
        "carrier": "staleness-alarm-ntfy",
        "body": "\n".join(lines),
    }


def post_envelope(
    envelope: dict[str, Any],
    *,
    hosts: Iterable[str] = NTFY_HOSTS,
    opener=urllib.request.urlopen,
    timeout: int = 15,
) -> str:
    """Send once to the first accepting existing relay; return that host."""
    packed = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    if len(packed) > 3900:
        raise ValueError(f"carrier envelope exceeds 3900 characters: {len(packed)}")
    errors: list[str] = []
    for host in hosts:
        endpoint = f"{host.rstrip('/')}/{TOPIC}"
        request = urllib.request.Request(
            endpoint,
            data=packed.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "text/plain",
                "User-Agent": "commons-staleness-alarm",
            },
        )
        try:
            with opener(request, timeout=timeout) as response:
                status = int(getattr(response, "status", 200))
                if 200 <= status < 300:
                    return host
                errors.append(f"{host} HTTP {status}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"{host} {type(exc).__name__}")
    raise RuntimeError("every ntfy carrier refused: " + " | ".join(errors))


def parse_now(value: str | None) -> float:
    if value is None:
        return dt.datetime.now(tz=dt.timezone.utc).timestamp()
    parsed = _epoch(value)
    if parsed is None:
        raise ValueError(f"invalid --now value: {value}")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync", default=DEFAULT_SYNC)
    parser.add_argument("--threshold-seconds", type=int, default=DEFAULT_THRESHOLD_SECONDS)
    parser.add_argument("--bucket-seconds", type=int, default=DEFAULT_BUCKET_SECONDS)
    parser.add_argument("--now", help="ISO-8601 or Unix timestamp; useful for deterministic replay/tests")
    parser.add_argument("--send", action="store_true", help="send through existing ntfy failover")
    args = parser.parse_args(argv)

    if args.threshold_seconds < 1 or args.bucket_seconds < 1:
        parser.error("threshold and bucket seconds must be positive")
    if not os.path.isfile(args.sync):
        print(json.dumps({"state": "QUIET", "reason": "sync.json absent"}, sort_keys=True))
        return 0
    try:
        with open(args.sync, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"state": "ERROR", "reason": type(exc).__name__}, sort_keys=True))
        return 1

    now = parse_now(args.now)
    stale = stale_sinks(payload, now=now, threshold_seconds=args.threshold_seconds)
    if not stale:
        print(json.dumps({"state": "QUIET", "reason": "no stale sinks"}, sort_keys=True))
        return 0
    envelope = build_envelope(
        stale,
        now=now,
        threshold_seconds=args.threshold_seconds,
        bucket_seconds=args.bucket_seconds,
    )
    if args.send:
        host = post_envelope(envelope)
        print(json.dumps({"state": "CARRIER_ACCEPTED", "host": host, "id": envelope["id"]}, sort_keys=True))
    else:
        print(json.dumps(envelope, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
