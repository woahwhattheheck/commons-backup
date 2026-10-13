"""Project bounded installed-connector reads into the Commons/Jev event-ledger schema.

The adapter is intentionally pure: it performs no provider reads or writes and carries no
credentials.  Callers supply metadata returned by the installed connector, including native
cursor/pagination/error state.  Raw message bodies, titles, diffs, and other private text are
not accepted by the exact input schema.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

SCHEMA = "commons.jev_connector_projection/v1"
LEDGER_SCHEMA = "commons.jev_event_ledger/v1"
MAX_BYTES = 4 * 1024 * 1024
MAX_SOURCES = 2048
MAX_RECORDS = 200000
MAX_SCOPE = 512
MAX_STRING = 2048
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/#@+-]{0,191}\Z")
UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
HEX64_RE = re.compile(r"[0-9a-f]{64}\Z")
PROVIDERS = {"slack", "github", "commons", "worker", "ci", "other"}
SOURCE_STATES = {"OK", "PARTIAL", "ERROR", "COOLDOWN"}
EVENT_TYPES = {
    "slack": {"MESSAGE", "THREAD_REPLY"},
    "github": {"ISSUE", "PULL_REQUEST", "REVIEW", "COMMENT", "COMMIT", "CHECK"},
    "commons": {"COMMONS_POST", "PROTOCOL_EVENT"},
    "worker": {"WORKER_EVENT"},
    "ci": {"CHECK"},
    "other": {"MESSAGE", "COMMENT", "PROTOCOL_EVENT", "WORKER_EVENT"},
}


class ProjectionError(ValueError):
    """Malformed, contradictory, or privacy-unsafe connector projection."""


def _canonical(value: Any) -> bytes:
    try:
        data = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ProjectionError("not canonical JSON data") from exc
    if len(data) > MAX_BYTES:
        raise ProjectionError("input byte limit exceeded")
    return data


def _bounded(value: Any) -> None:
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if depth > 24 or nodes > 1_000_000:
            raise ProjectionError("JSON depth/node limit exceeded")
        if type(item) is dict:
            if any(type(k) is not str or len(k) > 256 for k in item):
                raise ProjectionError("invalid object key")
            stack.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            stack.extend((v, depth + 1) for v in item)
        elif type(item) is str:
            if len(item) > MAX_STRING:
                raise ProjectionError("string limit exceeded")
            try:
                item.encode("utf-8")
            except UnicodeError as exc:
                raise ProjectionError("invalid Unicode") from exc
        elif item is None or type(item) is bool:
            continue
        elif type(item) is int and -(2**63) <= item < 2**63:
            continue
        else:
            raise ProjectionError("unsupported JSON scalar")
    _canonical(value)


def strict_loads(raw: bytes | str) -> Any:
    """Parse bounded JSON while rejecting duplicate keys and non-finite numbers."""
    if isinstance(raw, bytes):
        if len(raw) > MAX_BYTES:
            raise ProjectionError("input byte limit exceeded")
        try:
            raw = raw.decode("utf-8")
        except UnicodeError as exc:
            raise ProjectionError("invalid UTF-8") from exc
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_BYTES:
        raise ProjectionError("input byte limit exceeded")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ProjectionError("duplicate JSON key")
            out[key] = value
        return out

    def bad_constant(_value):
        raise ProjectionError("non-finite JSON number")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)
    except ProjectionError:
        raise
    except (ValueError, RecursionError) as exc:
        raise ProjectionError("invalid JSON") from exc
    _bounded(value)
    return value


def _exact(obj: Any, fields: str, where: str) -> dict[str, Any]:
    expected = set(fields.split())
    if type(obj) is not dict or set(obj) != expected:
        raise ProjectionError(f"{where}: unexpected or missing fields")
    return obj


def _token(value: Any, where: str) -> str:
    if type(value) is not str or TOKEN.fullmatch(value) is None:
        raise ProjectionError(f"{where}: invalid identifier")
    return value


def _nullable_token(value: Any, where: str) -> str | None:
    return None if value is None else _token(value, where)


def _nullable_cursor(value: Any, where: str) -> str | None:
    # Provider cursors are opaque; preserve padding, punctuation and empty tails.
    # The packet's existing string and byte limits still apply through _bounded.
    if value is not None and type(value) is not str:
        raise ProjectionError(f"{where}: cursor must be a string or null")
    return value


def _instant(value: Any, where: str) -> datetime:
    if type(value) is not str or UTC_RE.fullmatch(value) is None:
        raise ProjectionError(f"{where}: timestamp must be RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProjectionError(f"{where}: invalid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ProjectionError(f"{where}: timestamp is not UTC")
    return parsed


def _utc(value: Any, where: str) -> str:
    parsed = _instant(value, where)
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _opaque(value: Any, where: str) -> str:
    if type(value) is not str or not value or len(value) > 512 or any(ord(ch) < 32 for ch in value):
        raise ProjectionError(f"{where}: invalid opaque provider identifier")
    return value


def _url(value: Any, where: str) -> str:
    if type(value) is not str or not value or len(value) > 1024:
        raise ProjectionError(f"{where}: invalid source URL")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProjectionError(f"{where}: source URL must be absolute http(s)")
    if parsed.username or parsed.password:
        raise ProjectionError(f"{where}: source URL may not contain credentials")
    return value


def _event_id(provider: str, resource_scope: str, event_type: str, provider_event_id: str) -> str:
    # Event type is part of the provider namespace: e.g. a GitHub issue number and
    # comment id may both be numeric and must never alias merely because they match.
    raw = f"{provider}\0{resource_scope}\0{event_type}\0{provider_event_id}".encode("utf-8")
    return "evt-" + hashlib.sha256(raw).hexdigest()


def _validate_coverage(raw: Any, where: str) -> dict[str, Any]:
    row = dict(_exact(raw, "window_start window_end complete has_more pages_read items_read", where))
    row["window_start"] = _utc(row["window_start"], where + ".window_start")
    row["window_end"] = _utc(row["window_end"], where + ".window_end")
    if _instant(row["window_start"], where + ".window_start") > _instant(row["window_end"], where + ".window_end"):
        raise ProjectionError(where + ": reversed window")
    if type(row["complete"]) is not bool or type(row["has_more"]) is not bool:
        raise ProjectionError(where + ": complete/has_more must be boolean")
    if row["complete"] and row["has_more"]:
        raise ProjectionError(where + ": complete source cannot have more pages")
    for key, hi in (("pages_read", 100000), ("items_read", 100000000)):
        if type(row[key]) is not int or not 0 <= row[key] <= hi:
            raise ProjectionError(where + f".{key}: integer out of range")
    if row["pages_read"] == 0 and row["items_read"] != 0:
        raise ProjectionError(where + ": items require a read page")
    return row


def _project_source(raw: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    row = dict(_exact(
        raw,
        "source_id connector provider scope cursor high_water_mark observed_at "
        "last_successful_read status cooldown_until coverage source_url records",
        "source",
    ))
    source_id = _token(row["source_id"], "source.source_id")
    connector = _token(row["connector"], "source.connector")
    provider = row["provider"]
    if provider not in PROVIDERS:
        raise ProjectionError("source.provider: unsupported provider")
    scope = row["scope"]
    if type(scope) is not list or not 1 <= len(scope) <= MAX_SCOPE:
        raise ProjectionError("source.scope: invalid scope")
    scope = [_token(item, "source.scope") for item in scope]
    if len(scope) != len(set(scope)):
        raise ProjectionError("source.scope: duplicate entry")
    cursor = _nullable_cursor(row["cursor"], "source.cursor")
    high_water = _nullable_token(row["high_water_mark"], "source.high_water_mark")
    observed_at = _utc(row["observed_at"], "source.observed_at")
    last_good = None if row["last_successful_read"] is None else _utc(
        row["last_successful_read"], "source.last_successful_read"
    )
    if last_good is not None and _instant(last_good, "source.last_successful_read") > _instant(observed_at, "source.observed_at"):
        raise ProjectionError("source.last_successful_read: after observation")
    status = row["status"]
    if status not in SOURCE_STATES:
        raise ProjectionError("source.status: unsupported status")
    cooldown = None if row["cooldown_until"] is None else _utc(
        row["cooldown_until"], "source.cooldown_until"
    )
    if status == "COOLDOWN" and cooldown is None:
        raise ProjectionError("source.cooldown_until required during cooldown")
    if status == "COOLDOWN" and _instant(cooldown, "source.cooldown_until") <= _instant(observed_at, "source.observed_at"):
        raise ProjectionError("source.cooldown_until must be after observation")
    coverage = _validate_coverage(row["coverage"], "source.coverage")
    if _instant(coverage["window_end"], "source.coverage.window_end") > _instant(observed_at, "source.observed_at"):
        raise ProjectionError("source.coverage: window ends after observation")
    source_url = _url(row["source_url"], "source.source_url")
    records = row["records"]
    if type(records) is not list or len(records) > MAX_RECORDS:
        raise ProjectionError("source.records: invalid count")
    if coverage["items_read"] != len(records):
        raise ProjectionError("source.records: items_read must equal projected records")

    ledger_source = {
        "source_id": source_id,
        "connector": connector,
        "provider": provider,
        "scope": sorted(scope),
        "cursor": cursor,
        "high_water_mark": high_water,
        "observed_at": observed_at,
        "last_successful_read": last_good,
        "status": status,
        "cooldown_until": cooldown,
        "coverage": coverage,
        "source_url": source_url,
    }

    events = []
    seen_native: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw_record in records:
        record = dict(_exact(
            raw_record,
            "provider_event_id provider_event_time observed_at resource_scope "
            "event_type actor_id work_id operation_id source_url",
            "record",
        ))
        provider_event_id = _opaque(record["provider_event_id"], "record.provider_event_id")
        provider_event_time = _utc(record["provider_event_time"], "record.provider_event_time")
        record_observed = _utc(record["observed_at"], "record.observed_at")
        if (_instant(provider_event_time, "record.provider_event_time") > _instant(record_observed, "record.observed_at") or
                _instant(record_observed, "record.observed_at") > _instant(observed_at, "source.observed_at")):
            raise ProjectionError("record: invalid event/observation chronology")
        resource_scope = _token(record["resource_scope"], "record.resource_scope")
        if resource_scope not in scope:
            raise ProjectionError("record.resource_scope outside source scope")
        event_type = record["event_type"]
        if event_type not in EVENT_TYPES[provider]:
            raise ProjectionError("record.event_type invalid for provider")
        actor_id = _nullable_token(record["actor_id"], "record.actor_id")
        work_id = _nullable_token(record["work_id"], "record.work_id")
        operation_id = _nullable_token(record["operation_id"], "record.operation_id")
        event_url = _url(record["source_url"], "record.source_url")
        identity = (resource_scope, event_type, provider_event_id)
        # A later read is another observation of the same immutable event. Keep
        # its receipt time on the emitted row so the ledger can combine it.
        semantic = {
            "provider_event_time": provider_event_time,
            "event_type": event_type,
            "actor_id": actor_id,
            "work_id": work_id,
            "operation_id": operation_id,
            "source_url": event_url,
        }
        if identity in seen_native and seen_native[identity] != semantic:
            raise ProjectionError("record: provider event identity has contradictory metadata")
        seen_native[identity] = semantic
        events.append({
            "event_id": _event_id(provider, resource_scope, event_type, provider_event_id),
            "source_id": source_id,
            "provider_event_time": provider_event_time,
            "observed_at": record_observed,
            "stage": "EVENT",
            "kind": event_type,
            "actor_id": actor_id,
            "work_id": work_id,
            "operation_id": operation_id,
            "source_url": event_url,
        })
    events.sort(key=lambda event: (event["provider_event_time"], event["event_id"], event["source_id"]))
    return ledger_source, events


def project(packet: dict[str, Any]) -> dict[str, Any]:
    """Return an exact ``commons.jev_event_ledger/v1`` packet from connector metadata."""
    _bounded(packet)
    root = _exact(packet, "schema snapshot_id max_source_age_seconds sources", "packet")
    if root["schema"] != SCHEMA:
        raise ProjectionError("packet: unsupported schema")
    snapshot_id = _token(root["snapshot_id"], "packet.snapshot_id")
    max_age = root["max_source_age_seconds"]
    if type(max_age) is not int or not 1 <= max_age <= 7 * 24 * 60 * 60:
        raise ProjectionError("packet.max_source_age_seconds: integer out of range")
    raw_sources = root["sources"]
    if type(raw_sources) is not list or not 1 <= len(raw_sources) <= MAX_SOURCES:
        raise ProjectionError("packet.sources: invalid count")

    sources = []
    events = []
    source_ids = set()
    for raw_source in raw_sources:
        source, projected = _project_source(raw_source)
        if source["source_id"] in source_ids:
            raise ProjectionError("packet.sources: duplicate source_id")
        source_ids.add(source["source_id"])
        sources.append(source)
        events.extend(projected)

    sources.sort(key=lambda source: source["source_id"])
    events.sort(key=lambda event: (event["event_id"], event["source_id"]))
    return {
        "schema": LEDGER_SCHEMA,
        "snapshot_id": snapshot_id,
        "max_source_age_seconds": max_age,
        "sources": sources,
        "events": events,
        "aliases": [],
    }


def projection_digest(packet: dict[str, Any]) -> str:
    """Return a deterministic integrity digest of the projected ledger packet."""
    projected = project(packet)
    digest = hashlib.sha256(_canonical(projected)).hexdigest()
    if HEX64_RE.fullmatch(digest) is None:  # defensive, keeps receipt shape explicit
        raise ProjectionError("projection digest failed")
    return digest
