"""Deterministic, bounded event ledger and volume/freshness compiler for Commons/Jev.

This module is deliberately transport-agnostic. Installed connectors remain authoritative
for provider reads and writes. The compiler accepts a minimal projection of provider
metadata (never raw private message bodies), collapses duplicate/aliased events before
counting, and makes incomplete/stale coverage explicit instead of manufacturing zeros.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

SCHEMA = "commons.jev_event_ledger/v1"
REPORT_SCHEMA = "commons.jev_event_ledger.report/v1"
MAX_BYTES = 4 * 1024 * 1024
MAX_SOURCES = 2048
MAX_EVENTS = 200000
MAX_ALIASES = 200000
MAX_SCOPE_ITEMS = 512
MAX_STRING = 2048
MAX_AGE_SECONDS = 7 * 24 * 60 * 60
CLOCK_SKEW_SECONDS = 300

PROVIDERS = {"slack", "github", "commons", "worker", "ci", "other"}
SOURCE_STATES = {"OK", "PARTIAL", "ERROR", "COOLDOWN"}
STAGES = {
    "EVENT",
    "CLAIM",
    "CONFIRMED_SESSION",
    "PROVIDER_ACCEPTED",
    "LANDED",
    "BUSINESS_OUTCOME",
}
KINDS = {
    "MESSAGE",
    "THREAD_REPLY",
    "ASK",
    "OWNER_DIRECTION",
    "HANDOFF",
    "COLLISION",
    "ISSUE",
    "PULL_REQUEST",
    "REVIEW",
    "COMMENT",
    "COMMIT",
    "CHECK",
    "COMMONS_POST",
    "PROTOCOL_EVENT",
    "WORKER_EVENT",
    "CLAIM",
    "SESSION",
    "ACCEPTED",
    "LANDED",
    "BUSINESS_OUTCOME",
}
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/#@+-]{0,191}\Z")
WINDOWS = (
    ("15m", timedelta(minutes=15)),
    ("1h", timedelta(hours=1)),
    ("24h", timedelta(hours=24)),
)


class LedgerError(ValueError):
    """Malformed, ambiguous, contradictory, or out-of-range ledger input."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise LedgerError("not canonical JSON data") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _bounded(value: Any) -> None:
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if depth > 24 or nodes > 1_000_000:
            raise LedgerError("JSON depth/node limit exceeded")
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                raise LedgerError("object keys must be strings")
            stack.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            stack.extend((v, depth + 1) for v in item)
        elif type(item) is str:
            if len(item) > MAX_STRING:
                raise LedgerError("string limit exceeded")
            try:
                item.encode("utf-8")
            except UnicodeError as exc:
                raise LedgerError("invalid Unicode") from exc
        elif item is None or type(item) is bool:
            pass
        elif type(item) is int and -(2**63) <= item < 2**63:
            pass
        else:
            raise LedgerError("only bounded integer JSON is supported")
    if len(_canonical(value)) > MAX_BYTES:
        raise LedgerError("input byte limit exceeded")


def load_json(data: bytes | str) -> Any:
    """Load strict bounded JSON and reject duplicate object keys."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise LedgerError("duplicate JSON key")
            result[key] = value
        return result

    try:
        if isinstance(data, bytes):
            if len(data) > MAX_BYTES:
                raise LedgerError("input byte limit exceeded")
            data = data.decode("utf-8")
        if type(data) is not str or len(data.encode("utf-8")) > MAX_BYTES:
            raise LedgerError("input byte limit exceeded")
        result = json.loads(data, object_pairs_hook=pairs)
        _bounded(result)
        return result
    except LedgerError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise LedgerError("invalid JSON") from exc


def _exact(obj: Any, fields: str, where: str) -> dict[str, Any]:
    expected = set(fields.split())
    if type(obj) is not dict or set(obj) != expected:
        raise LedgerError(f"{where}: unexpected or missing fields")
    return obj


def _token(value: Any, where: str) -> str:
    if type(value) is not str or TOKEN.fullmatch(value) is None:
        raise LedgerError(f"{where}: invalid identifier")
    return value


def _text(value: Any, where: str, maximum: int = MAX_STRING) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise LedgerError(f"{where}: invalid text")
    return value


def _int(value: Any, lo: int, hi: int, where: str) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise LedgerError(f"{where}: integer out of range")
    return value


def _time(value: Any, where: str) -> datetime:
    if type(value) is not str or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value
    ) is None:
        raise LedgerError(f"{where}: timestamp must be RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LedgerError(f"{where}: invalid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise LedgerError(f"{where}: timestamp is not UTC")
    return parsed


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _url(value: Any, where: str) -> str:
    value = _text(value, where, 1024)
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise LedgerError(f"{where}: source URL must be absolute http(s)")
    if parsed.username or parsed.password:
        raise LedgerError(f"{where}: credentials are not allowed in source URLs")
    return value


def _nullable_token(value: Any, where: str) -> str | None:
    return None if value is None else _token(value, where)


def _nullable_cursor(value: Any, where: str) -> str | None:
    # Provider cursors are opaque; preserve padding, punctuation and empty tails.
    # The packet's existing string and byte limits still apply through _bounded.
    if value is not None and type(value) is not str:
        raise LedgerError(f"{where}: cursor must be a string or null")
    return value


def _nullable_time(value: Any, where: str) -> datetime | None:
    return None if value is None else _time(value, where)


def _normalize_source(raw: Any, now: datetime, max_age_seconds: int) -> dict[str, Any]:
    row = dict(_exact(
        raw,
        "source_id connector provider scope cursor high_water_mark observed_at "
        "last_successful_read status cooldown_until coverage source_url",
        "source",
    ))
    source_id = _token(row["source_id"], "source.source_id")
    connector = _token(row["connector"], "source.connector")
    provider = row["provider"]
    if provider not in PROVIDERS:
        raise LedgerError("source.provider: unsupported provider")
    scope = row["scope"]
    if type(scope) is not list or not 1 <= len(scope) <= MAX_SCOPE_ITEMS:
        raise LedgerError("source.scope: invalid scope")
    scope = [_token(v, "source.scope") for v in scope]
    if len(set(scope)) != len(scope):
        raise LedgerError("source.scope: duplicate scope entry")
    cursor = _nullable_cursor(row["cursor"], "source.cursor")
    high_water = _nullable_token(row["high_water_mark"], "source.high_water_mark")
    observed = _time(row["observed_at"], "source.observed_at")
    last_good = _nullable_time(row["last_successful_read"], "source.last_successful_read")
    if observed > now + timedelta(seconds=CLOCK_SKEW_SECONDS):
        raise LedgerError("source.observed_at: future observation")
    if last_good is not None and last_good > observed + timedelta(seconds=CLOCK_SKEW_SECONDS):
        raise LedgerError("source.last_successful_read: after observation")
    status = row["status"]
    if status not in SOURCE_STATES:
        raise LedgerError("source.status: unsupported status")
    cooldown = _nullable_time(row["cooldown_until"], "source.cooldown_until")
    if status == "COOLDOWN" and cooldown is None:
        raise LedgerError("source.cooldown_until required during cooldown")
    if cooldown is not None and cooldown <= observed and status == "COOLDOWN":
        raise LedgerError("expired cooldown cannot be current source status")

    coverage = dict(_exact(
        row["coverage"],
        "window_start window_end complete has_more pages_read items_read",
        "source.coverage",
    ))
    start = _time(coverage["window_start"], "source.coverage.window_start")
    end = _time(coverage["window_end"], "source.coverage.window_end")
    if start > end or end > observed + timedelta(seconds=CLOCK_SKEW_SECONDS):
        raise LedgerError("source.coverage: invalid observation window")
    if type(coverage["complete"]) is not bool or type(coverage["has_more"]) is not bool:
        raise LedgerError("source.coverage: complete/has_more must be boolean")
    if coverage["complete"] and coverage["has_more"]:
        raise LedgerError("source.coverage: complete source cannot have more pages")
    pages = _int(coverage["pages_read"], 0, 100000, "source.coverage.pages_read")
    items = _int(coverage["items_read"], 0, 100000000, "source.coverage.items_read")
    if pages == 0 and items != 0:
        raise LedgerError("source.coverage: items require a read page")
    source_url = _url(row["source_url"], "source.source_url")

    if last_good is None:
        freshness = "UNAVAILABLE"
        age = None
    else:
        age = max(0, int((now - last_good).total_seconds()))
        if status == "COOLDOWN" and cooldown is not None and cooldown > now:
            freshness = "COOLDOWN"
        elif status == "ERROR":
            freshness = "STALE"
        elif status == "PARTIAL":
            freshness = "PARTIAL"
        elif age > max_age_seconds:
            freshness = "STALE"
        else:
            freshness = "FRESH"

    normalized = {
        "source_id": source_id,
        "connector": connector,
        "provider": provider,
        "scope": sorted(scope),
        "cursor": cursor,
        "high_water_mark": high_water,
        "observed_at": _stamp(observed),
        "last_successful_read": None if last_good is None else _stamp(last_good),
        "status": status,
        "freshness": freshness,
        "age_seconds": age,
        "cooldown_until": None if cooldown is None else _stamp(cooldown),
        "coverage": {
            "window_start": _stamp(start),
            "window_end": _stamp(end),
            "complete": coverage["complete"],
            "has_more": coverage["has_more"],
            "pages_read": pages,
            "items_read": items,
        },
        "source_url": source_url,
    }
    normalized["source_receipt_sha256"] = _digest(normalized)
    return normalized


def _normalize_event(raw: Any, sources: dict[str, dict[str, Any]], now: datetime) -> dict[str, Any]:
    row = dict(_exact(
        raw,
        "event_id source_id provider_event_time observed_at stage kind actor_id work_id "
        "operation_id source_url",
        "event",
    ))
    event_id = _token(row["event_id"], "event.event_id")
    source_id = _token(row["source_id"], "event.source_id")
    if source_id not in sources:
        raise LedgerError("event.source_id: unknown source")
    provider_time = _time(row["provider_event_time"], "event.provider_event_time")
    observed = _time(row["observed_at"], "event.observed_at")
    source_observed = _time(sources[source_id]["observed_at"], "source.observed_at")
    if provider_time > observed + timedelta(seconds=CLOCK_SKEW_SECONDS):
        raise LedgerError("event.provider_event_time: after event observation")
    if observed > source_observed + timedelta(seconds=CLOCK_SKEW_SECONDS):
        raise LedgerError("event.observed_at: after source observation")
    if provider_time > now + timedelta(seconds=CLOCK_SKEW_SECONDS):
        raise LedgerError("event.provider_event_time: future event")
    stage = row["stage"]
    kind = row["kind"]
    if stage not in STAGES:
        raise LedgerError("event.stage: unsupported stage")
    if kind not in KINDS:
        raise LedgerError("event.kind: unsupported kind")
    actor = _nullable_token(row["actor_id"], "event.actor_id")
    work = _nullable_token(row["work_id"], "event.work_id")
    operation = _nullable_token(row["operation_id"], "event.operation_id")
    source_url = _url(row["source_url"], "event.source_url")
    if stage in {"CLAIM", "PROVIDER_ACCEPTED", "LANDED", "BUSINESS_OUTCOME"} and work is None:
        raise LedgerError(f"event.work_id missing for stage {stage}")
    if stage in {"PROVIDER_ACCEPTED", "LANDED"} and operation is None:
        raise LedgerError(f"event.operation_id required for stage {stage}")
    return {
        "event_id": event_id,
        "source_id": source_id,
        "provider": sources[source_id]["provider"],
        "provider_event_time": _stamp(provider_time),
        "observed_at": _stamp(observed),
        "stage": stage,
        "kind": kind,
        "actor_id": actor,
        "work_id": work,
        "operation_id": operation,
        "source_url": source_url,
    }


def _event_equivalence_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """Fields that explicit aliases are allowed to say represent one provider event."""
    return (
        row["provider"],
        row["provider_event_time"],
        row["stage"],
        row["kind"],
        row["actor_id"],
        row["work_id"],
        row["operation_id"],
    )


def _dedupe_events(
    events: list[dict[str, Any]], aliases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_id[event["event_id"]].append(event)

    # Same immutable provider identity may be observed through overlapping exports.
    collapsed: dict[str, dict[str, Any]] = {}
    for event_id, rows in by_id.items():
        first = rows[0]
        key = _event_equivalence_key(first)
        if any(_event_equivalence_key(row) != key for row in rows[1:]):
            raise LedgerError("conflicting records for immutable event_id")
        observed_sources = sorted({row["source_id"] for row in rows})
        observations = sorted(row["observed_at"] for row in rows)
        urls = sorted({row["source_url"] for row in rows})
        primary = min(
            rows,
            key=lambda row: (row["observed_at"], row["source_id"], row["source_url"]),
        )
        normalized = {
            "event_id": event_id,
            "provider": first["provider"],
            "provider_event_time": first["provider_event_time"],
            "first_observed_at": observations[0],
            "last_observed_at": observations[-1],
            "stage": first["stage"],
            "kind": first["kind"],
            "actor_id": first["actor_id"],
            "work_id": first["work_id"],
            "operation_id": first["operation_id"],
            "primary_source_id": primary["source_id"],
            "observed_source_ids": observed_sources,
            "source_urls": urls,
        }
        normalized["event_receipt_sha256"] = _digest(normalized)
        collapsed[event_id] = normalized

    alias_to_canonical: dict[str, str] = {}
    for raw in aliases:
        row = _exact(raw, "alias_event_id canonical_event_id", "alias")
        alias = _token(row["alias_event_id"], "alias.alias_event_id")
        canonical = _token(row["canonical_event_id"], "alias.canonical_event_id")
        if alias == canonical:
            raise LedgerError("self alias is not allowed")
        if alias in alias_to_canonical and alias_to_canonical[alias] != canonical:
            raise LedgerError("conflicting alias mapping")
        alias_to_canonical[alias] = canonical

    def resolve(event_id: str) -> str:
        seen = set()
        current = event_id
        while current in alias_to_canonical:
            if current in seen:
                raise LedgerError("alias cycle")
            seen.add(current)
            current = alias_to_canonical[current]
        return current

    for alias, canonical in alias_to_canonical.items():
        if alias not in collapsed or canonical not in collapsed:
            raise LedgerError("alias endpoints must both exist in this snapshot")
        resolved = resolve(alias)
        if resolved not in collapsed:
            raise LedgerError("alias canonical endpoint missing")

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event_id, row in collapsed.items():
        groups[resolve(event_id)].append(row)

    result = []
    for canonical_id, rows in groups.items():
        first = rows[0]
        key = (
            first["provider"],
            first["provider_event_time"],
            first["stage"],
            first["kind"],
            first["actor_id"],
            first["work_id"],
            first["operation_id"],
        )
        for row in rows[1:]:
            row_key = (
                row["provider"],
                row["provider_event_time"],
                row["stage"],
                row["kind"],
                row["actor_id"],
                row["work_id"],
                row["operation_id"],
            )
            if row_key != key:
                raise LedgerError("explicit alias joins semantically different events")
        source_ids = sorted({sid for row in rows for sid in row["observed_source_ids"]})
        urls = sorted({url for row in rows for url in row["source_urls"]})
        first_seen = min(row["first_observed_at"] for row in rows)
        last_seen = max(row["last_observed_at"] for row in rows)
        primary = min(
            (
                (row["first_observed_at"], row["primary_source_id"])
                for row in rows
            )
        )[1]
        aliases_for_row = sorted(row["event_id"] for row in rows if row["event_id"] != canonical_id)
        normalized = {
            "event_id": canonical_id,
            "alias_event_ids": aliases_for_row,
            "provider": first["provider"],
            "provider_event_time": first["provider_event_time"],
            "first_observed_at": first_seen,
            "last_observed_at": last_seen,
            "stage": first["stage"],
            "kind": first["kind"],
            "actor_id": first["actor_id"],
            "work_id": first["work_id"],
            "operation_id": first["operation_id"],
            "primary_source_id": primary,
            "observed_source_ids": source_ids,
            "source_urls": urls,
        }
        normalized["event_receipt_sha256"] = _digest(normalized)
        result.append(normalized)

    return sorted(result, key=lambda row: (row["provider_event_time"], row["event_id"]))


def _source_covers_window(source: dict[str, Any], start: datetime, end: datetime) -> bool:
    coverage = source["coverage"]
    coverage_start = _time(coverage["window_start"], "coverage.window_start")
    coverage_end = _time(coverage["window_end"], "coverage.window_end")
    return (
        source["freshness"] == "FRESH"
        and source["status"] == "OK"
        and coverage["complete"]
        and not coverage["has_more"]
        and coverage_start <= start
        and coverage_end >= end
    )


def _aggregate(
    events: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    start: datetime,
    end: datetime,
    label: str,
) -> dict[str, Any]:
    selected = [
        row for row in events
        if start <= _time(row["provider_event_time"], "event.provider_event_time") <= end
    ]
    by_stage = Counter(row["stage"] for row in selected)
    by_provider = Counter(row["provider"] for row in selected)
    by_kind = Counter(row["kind"] for row in selected)
    by_source = Counter(row["primary_source_id"] for row in selected)
    observed_by_source = Counter()
    for row in selected:
        observed_by_source.update(row["observed_source_ids"])
    actors = {row["actor_id"] for row in selected if row["actor_id"] is not None}
    works = {row["work_id"] for row in selected if row["work_id"] is not None}
    incomplete = sorted(
        source_id
        for source_id, source in sources.items()
        if not _source_covers_window(source, start, end)
    )
    body = {
        "label": label,
        "start": _stamp(start),
        "end": _stamp(end),
        "event_count": len(selected),
        "distinct_observed_contributors": len(actors),
        "distinct_work_items": len(works),
        "by_stage": {stage: by_stage.get(stage, 0) for stage in sorted(STAGES)},
        "by_provider": dict(sorted(by_provider.items())),
        "by_kind": dict(sorted(by_kind.items())),
        "by_primary_source": dict(sorted(by_source.items())),
        "source_observation_counts": dict(sorted(observed_by_source.items())),
        "coverage": {
            "state": "COMPLETE" if not incomplete else "LOWER_BOUND",
            "lower_bound": bool(incomplete),
            "incomplete_or_stale_sources": incomplete,
        },
    }
    body["window_receipt_sha256"] = _digest(body)
    return body


def compile_ledger(packet: dict[str, Any], *, evaluated_at: str | None = None) -> dict[str, Any]:
    """Compile a deterministic machine feed with exact volume and freshness semantics.

    ``evaluated_at`` exists for offline replay/tests. Production callers should omit it and
    use process time. The resulting report declares whether it used process or supplied time.
    """
    _bounded(packet)
    root = _exact(
        packet,
        "schema snapshot_id max_source_age_seconds sources events aliases",
        "packet",
    )
    if root["schema"] != SCHEMA:
        raise LedgerError("unsupported schema")
    snapshot_id = _token(root["snapshot_id"], "packet.snapshot_id")
    max_age = _int(
        root["max_source_age_seconds"], 1, MAX_AGE_SECONDS, "packet.max_source_age_seconds"
    )
    if evaluated_at is None:
        now = datetime.now(timezone.utc)
        clock_source = "PROCESS_UTC"
    else:
        now = _time(evaluated_at, "evaluated_at")
        clock_source = "SUPPLIED_REPLAY_TIME"

    raw_sources = root["sources"]
    raw_events = root["events"]
    raw_aliases = root["aliases"]
    if type(raw_sources) is not list or not 1 <= len(raw_sources) <= MAX_SOURCES:
        raise LedgerError("packet.sources: invalid source list")
    if type(raw_events) is not list or len(raw_events) > MAX_EVENTS:
        raise LedgerError("packet.events: invalid event list")
    if type(raw_aliases) is not list or len(raw_aliases) > MAX_ALIASES:
        raise LedgerError("packet.aliases: invalid alias list")

    sources: dict[str, dict[str, Any]] = {}
    for raw in raw_sources:
        source = _normalize_source(raw, now, max_age)
        source_id = source["source_id"]
        if source_id in sources:
            raise LedgerError("duplicate source_id")
        sources[source_id] = source

    events = [_normalize_event(raw, sources, now) for raw in raw_events]
    canonical_events = _dedupe_events(events, raw_aliases)

    windows = []
    for label, delta in WINDOWS:
        windows.append(_aggregate(canonical_events, sources, now - delta, now, label))

    historical_start = min(
        _time(source["coverage"]["window_start"], "source.coverage.window_start")
        for source in sources.values()
    )
    windows.append(_aggregate(canonical_events, sources, historical_start, now, "historical"))

    freshness_counts = Counter(source["freshness"] for source in sources.values())
    stale_sources = sorted(
        source_id for source_id, source in sources.items()
        if source["freshness"] != "FRESH"
    )
    partial_sources = sorted(
        source_id for source_id, source in sources.items()
        if not source["coverage"]["complete"] or source["coverage"]["has_more"]
    )

    report = {
        "schema": REPORT_SCHEMA,
        "snapshot_id": snapshot_id,
        "evaluated_at": _stamp(now),
        "clock_source": clock_source,
        "max_source_age_seconds": max_age,
        "source_summary": {
            "source_count": len(sources),
            "freshness_counts": dict(sorted(freshness_counts.items())),
            "stale_or_degraded_sources": stale_sources,
            "partial_or_paginated_sources": partial_sources,
        },
        "sources": [sources[source_id] for source_id in sorted(sources)],
        "events": canonical_events,
        "windows": windows,
        "authority": {
            "provider_read_authority": False,
            "provider_write_authority": False,
            "claim_authority": False,
            "merge_authority": False,
            "payment_authority": False,
            "raw_private_text_included": False,
        },
    }
    report["ledger_receipt_sha256"] = _digest(report)
    return report


def verify_report(report: dict[str, Any]) -> bool:
    """Verify receipt hashes and fail closed on structural/tamper drift."""
    try:
        _bounded(report)
        if type(report) is not dict or report.get("schema") != REPORT_SCHEMA:
            return False
        expected = report.get("ledger_receipt_sha256")
        if type(expected) is not str or len(expected) != 64:
            return False
        body = dict(report)
        body.pop("ledger_receipt_sha256", None)
        if _digest(body) != expected:
            return False
        for source in report.get("sources", []):
            if type(source) is not dict:
                return False
            receipt = source.get("source_receipt_sha256")
            source_body = dict(source)
            source_body.pop("source_receipt_sha256", None)
            if type(receipt) is not str or _digest(source_body) != receipt:
                return False
        for event in report.get("events", []):
            if type(event) is not dict:
                return False
            receipt = event.get("event_receipt_sha256")
            event_body = dict(event)
            event_body.pop("event_receipt_sha256", None)
            if type(receipt) is not str or _digest(event_body) != receipt:
                return False
        for window in report.get("windows", []):
            if type(window) is not dict:
                return False
            receipt = window.get("window_receipt_sha256")
            window_body = dict(window)
            window_body.pop("window_receipt_sha256", None)
            if type(receipt) is not str or _digest(window_body) != receipt:
                return False
        authority = report.get("authority")
        if authority != {
            "provider_read_authority": False,
            "provider_write_authority": False,
            "claim_authority": False,
            "merge_authority": False,
            "payment_authority": False,
            "raw_private_text_included": False,
        }:
            return False
        return True
    except (LedgerError, TypeError, ValueError):
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", help="strict JSON event-ledger packet")
    parser.add_argument("--verify", action="store_true", help="verify a compiled report instead")
    args = parser.parse_args(argv)
    try:
        with open(args.packet, "rb") as handle:
            payload = load_json(handle.read())
        if args.verify:
            if not verify_report(payload):
                raise LedgerError("report verification failed")
            print("OK")
        else:
            print(json.dumps(compile_ledger(payload), sort_keys=True, indent=2))
        return 0
    except (OSError, LedgerError) as exc:
        print(f"jev_event_ledger: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
