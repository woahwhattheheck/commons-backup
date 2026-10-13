#!/usr/bin/env python3
"""Deterministic relationship-level outbound collision guard.

This module is diagnostic only. It never authorizes external contact. A
NO_CONFLICT_FOUND result means only that the retained packet supplied to this
compiler did not expose a relationship collision at a process-owned evaluation
time. Fresh provider census and an independent session-bound Muse consume/GO
gate remain required.
"""
from __future__ import annotations

from datetime import datetime as _PROCESS_DATETIME, timezone as _PROCESS_TIMEZONE

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "relationship-contact-guard/v3"
ARTIFACT_SCHEMA = "relationship-contact-guard-artifact/v3"
VERIFICATION_SCHEMA = "relationship-contact-guard-verification/v1"
MAX_JSON_BYTES = 1_048_576
MAX_EVENTS = 10_000
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100_000
MIN_RELATIONSHIP_COOLDOWN_SECONDS = 6 * 60 * 60
MIN_PURSUIT_COOLDOWN_SECONDS = 72 * 60 * 60
IDENT_RE = re.compile(r"^[a-z0-9][a-z0-9._@:+/\-]{0,254}$")
OPAQUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+=\-]{0,511}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
KINDS = {"PROVIDER_SENT", "PROVIDER_BOUNCE", "HUMAN_REPLY", "HUMAN_NEGATIVE", "HUMAN_REOPEN"}
SCOPES = {"ROUTE_PURPOSE", "COUNTERPARTY"}

# Compatibility/export surface only. Compile/verify semantics deliberately do
# not read this mutable module object; source-literal authority is emitted
# inside _compile_at().
AUTHORITY = {
    "send_authorized": False,
    "muse_authorized": False,
    "provider_send_proven": False,
    "buyer_acceptance_proven": False,
    "contract_proven": False,
    "payment_proven": False,
    "cash_proven": False,
    "revenue_recognized": False,
}


class GuardError(ValueError):
    pass


def _pairs(
    pairs: Sequence[tuple[str, Any]],
    _guard_error=GuardError,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _guard_error(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _bad_constant(value: str, _guard_error=GuardError) -> None:
    raise _guard_error(f"non-finite JSON constant forbidden: {value}")


def _make_json_text_encoder(
    _guard_error,
    _isfinite,
    _repr,
    _sorted,
):
    escapes = {
        '"': '\\"',
        "\\": "\\\\",
        "\b": "\\b",
        "\f": "\\f",
        "\n": "\\n",
        "\r": "\\r",
        "\t": "\\t",
    }

    def quote(value: str) -> str:
        parts = ['"']
        for char in value:
            replacement = escapes.get(char)
            if replacement is not None:
                parts.append(replacement)
                continue
            code = ord(char)
            if 0x20 <= code < 0x7F:
                parts.append(char)
            elif code <= 0xFFFF:
                parts.append(f"\\u{code:04x}")
            else:
                scalar = code - 0x10000
                high = 0xD800 + (scalar >> 10)
                low = 0xDC00 + (scalar & 0x3FF)
                parts.append(f"\\u{high:04x}\\u{low:04x}")
        parts.append('"')
        return "".join(parts)

    def encode(value: Any, *, pretty: bool = False) -> str:
        def walk(item: Any, depth: int) -> str:
            if item is None:
                return "null"
            if type(item) is bool:
                return "true" if item else "false"
            if type(item) is int:
                return _repr(item)
            if type(item) is float:
                if not _isfinite(item):
                    raise _guard_error("canonical JSON serialization forbids non-finite float")
                return _repr(item)
            if type(item) is str:
                return quote(item)
            if type(item) is list:
                if not item:
                    return "[]"
                values = [walk(child, depth + 1) for child in item]
                if not pretty:
                    return "[" + ",".join(values) + "]"
                child_pad = " " * (2 * (depth + 1))
                pad = " " * (2 * depth)
                return "[\n" + child_pad + (",\n" + child_pad).join(values) + "\n" + pad + "]"
            if type(item) is dict:
                if not item:
                    return "{}"
                entries: list[str] = []
                for key in _sorted(item):
                    if type(key) is not str:
                        raise _guard_error("canonical JSON object key must be string")
                    separator = ": " if pretty else ":"
                    entries.append(quote(key) + separator + walk(item[key], depth + 1))
                if not pretty:
                    return "{" + ",".join(entries) + "}"
                child_pad = " " * (2 * (depth + 1))
                pad = " " * (2 * depth)
                return "{\n" + child_pad + (",\n" + child_pad).join(entries) + "\n" + pad + "}"
            raise _guard_error("canonical JSON serialization requires exact plain JSON types")

        return walk(value, 0)

    return encode


_json_text = _make_json_text_encoder(
    GuardError,
    math.isfinite,
    repr,
    sorted,
)


def _make_strict_json_decoder(
    _decoder_cls,
    _pairs_hook,
    _bad_constant_hook,
    _decode_error,
    _guard_error,
):
    # Build one private decoder generation now. Its bound raw_decode and
    # scan_once retain the parser/hook generation even if public json module
    # encoder/decoder/scanner attributes are rebound later.
    decoder = _decoder_cls(
        object_pairs_hook=_pairs_hook,
        parse_constant=_bad_constant_hook,
    )
    raw_decode = decoder.raw_decode

    def decode(raw: bytes, label: str) -> Any:
        try:
            text = raw.decode("utf-8")
            start = 0
            while start < len(text) and text[start] in " \t\n\r":
                start += 1
            value, end = raw_decode(text, start)
            while end < len(text) and text[end] in " \t\n\r":
                end += 1
            if end != len(text):
                raise _guard_error(f"{label}: trailing JSON data")
            return value
        except _guard_error:
            raise
        except (UnicodeDecodeError, _decode_error, ValueError, RecursionError) as exc:
            raise _guard_error(f"{label}: invalid strict JSON") from exc

    return decode


_strict_json_decode = _make_strict_json_decoder(
    json.JSONDecoder,
    _pairs,
    _bad_constant,
    json.JSONDecodeError,
    GuardError,
)


def _json_string_size(value: str, path: str, remaining: int) -> int:
    """Return exact ensure_ascii canonical JSON string bytes without allocating it."""
    total = 2  # surrounding quotes
    if total > remaining:
        raise GuardError(f"{path}: canonical bytes limit exceeded")
    for char in value:
        code = ord(char)
        if char in ('"', "\\") or char in ("\b", "\f", "\n", "\r", "\t"):
            step = 2
        elif code < 0x20:
            step = 6
        elif code < 0x7F:
            step = 1
        elif code <= 0xFFFF:
            step = 6
        else:
            step = 12
        total += step
        if total > remaining:
            raise GuardError(f"{path}: canonical bytes limit exceeded")
    return total


def _freeze_plain_json(
    value: Any,
    path: str,
    *,
    _max_json_bytes: int = MAX_JSON_BYTES,
    _max_safe_integer: int = MAX_SAFE_INTEGER,
    _max_json_depth: int = MAX_JSON_DEPTH,
    _max_json_nodes: int = MAX_JSON_NODES,
    _json_string_size_fn=_json_string_size,
    _isfinite=math.isfinite,
    _float_text=repr,
) -> Any:
    """Detach one bounded exact-JSON generation before canonical serialization.

    Container cardinality is checked against the remaining node budget before
    child iteration/copy. String/key canonical bytes are charged incrementally,
    so over-budget direct objects fail before the full value reaches the canonical encoder.
    """
    state = {"nodes": 0, "bytes": 0}

    def charge_bytes(amount: int, item_path: str) -> None:
        if amount < 0 or state["bytes"] + amount > _max_json_bytes:
            raise GuardError(f"{item_path}: canonical bytes limit exceeded")
        state["bytes"] += amount

    def take_node(item_path: str) -> None:
        if state["nodes"] >= _max_json_nodes:
            raise GuardError(f"{item_path}: JSON node limit exceeded")
        state["nodes"] += 1

    def visit(item: Any, item_path: str, depth: int) -> Any:
        if depth > _max_json_depth:
            raise GuardError(f"{item_path}: JSON depth limit exceeded")
        take_node(item_path)

        if item is None:
            charge_bytes(4, item_path)
            return None
        if type(item) is bool:
            charge_bytes(4 if item else 5, item_path)
            return item
        if type(item) is int:
            if item < -_max_safe_integer or item > _max_safe_integer:
                raise GuardError(f"{item_path}: integer outside supported exact JSON range")
            charge_bytes(len(str(item)), item_path)
            return item
        if type(item) is float:
            if not _isfinite(item):
                raise GuardError(f"{item_path}: non-finite number")
            # Python's finite-float repr is the scalar spelling used by the
            # canonical encoder. Capture it as a first-load dependency.
            scalar = _float_text(item)
            charge_bytes(len(scalar.encode("ascii")), item_path)
            return item
        if type(item) is str:
            remaining = _max_json_bytes - state["bytes"]
            charge_bytes(_json_string_size_fn(item, item_path, remaining), item_path)
            return item

        if type(item) is list:
            count = len(item)
            if state["nodes"] + count > _max_json_nodes:
                raise GuardError(f"{item_path}: JSON node limit exceeded before child traversal")
            charge_bytes(2 + max(0, count - 1), item_path)  # [] plus commas
            out: list[Any] = []
            try:
                for index in range(count):
                    out.append(visit(item[index], f"{item_path}[{index}]", depth + 1))
            except IndexError as exc:
                raise GuardError(f"{item_path}: list changed during bounded snapshot") from exc
            if len(item) != count:
                raise GuardError(f"{item_path}: list changed during bounded snapshot")
            return out

        if type(item) is dict:
            count = len(item)
            # Each pair costs one string-key work node and one value work node.
            if state["nodes"] + (2 * count) > _max_json_nodes:
                raise GuardError(f"{item_path}: JSON node limit exceeded before child traversal")
            charge_bytes(2 + max(0, count - 1) + count, item_path)  # {}, commas, colons
            out: dict[str, Any] = {}
            seen = 0
            try:
                for key, child in item.items():
                    seen += 1
                    if seen > count:
                        raise GuardError(f"{item_path}: object changed during bounded snapshot")
                    if type(key) is not str:
                        raise GuardError(f"{item_path}: non-string JSON key")
                    take_node(f"{item_path}.<key>")
                    remaining = _max_json_bytes - state["bytes"]
                    charge_bytes(_json_string_size_fn(key, f"{item_path}.<key>", remaining), f"{item_path}.<key>")
                    out[key] = visit(child, f"{item_path}.{key}", depth + 1)
            except RuntimeError as exc:
                raise GuardError(f"{item_path}: object changed during bounded snapshot") from exc
            if seen != count or len(item) != count:
                raise GuardError(f"{item_path}: object changed during bounded snapshot")
            return out

        raise GuardError(f"{item_path}: exact plain JSON types required")

    return visit(value, path, 0)


def canonical_bytes(
    value: Any,
    *,
    _json_text_fn=_json_text,
    _guard_error=GuardError,
) -> bytes:
    try:
        return _json_text_fn(value, pretty=False).encode("ascii")
    except _guard_error:
        raise
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise _guard_error("canonical JSON serialization failed") from exc


def digest(value: Any, *, _sha256=hashlib.sha256, _canonical_bytes=canonical_bytes) -> str:
    return _sha256(_canonical_bytes(value)).hexdigest()


def _decode_json_bytes(
    raw: bytes,
    label: str,
    *,
    _strict_decode_fn=_strict_json_decode,
) -> Any:
    return _strict_decode_fn(raw, label)

def _freeze(
    value: Any,
    label: str,
    *,
    _freeze_plain_json_fn=_freeze_plain_json,
    _canonical_bytes_fn=canonical_bytes,
    _decode_json_bytes_fn=_decode_json_bytes,
    _max_json_bytes: int = MAX_JSON_BYTES,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise GuardError(f"{label}: top level must be a plain object")
    frozen_plain = _freeze_plain_json_fn(value, label)
    if type(frozen_plain) is not dict:
        raise GuardError(f"{label}: top level must be a plain object")
    raw = _canonical_bytes_fn(frozen_plain)
    if len(raw) > _max_json_bytes:
        # Defensive consistency check: bounded preflight should have rejected
        # before serializer entry if its byte accounting ever drifts.
        raise GuardError(f"{label}: exceeds {_max_json_bytes} canonical bytes")
    frozen = _decode_json_bytes_fn(raw, label)
    if type(frozen) is not dict:
        raise GuardError(f"{label}: top level must be a plain object")
    return frozen


def _bounded_file_prefix(
    path: Path,
    limit: int,
    *,
    _path_open=Path.open,
) -> bytes:
    if type(limit) is not int or limit < 0:
        raise GuardError("file byte limit must be a nonnegative integer")
    with _path_open(path, "rb") as handle:
        raw = handle.read(limit + 1)
    if type(raw) is not bytes:
        raise GuardError(f"{path}: binary file read required")
    return raw


def _make_load_json(
    _max_json_bytes: int,
    _bounded_file_prefix_fn,
    _decode_json_bytes_fn,
    _freeze_fn,
):
    def load_json(path: Path) -> dict[str, Any]:
        raw = _bounded_file_prefix_fn(path, _max_json_bytes)
        if len(raw) > _max_json_bytes:
            raise GuardError(f"{path}: exceeds {_max_json_bytes} bytes")
        value = _decode_json_bytes_fn(raw, str(path))
        return _freeze_fn(value, str(path))

    return load_json


load_json = _make_load_json(
    MAX_JSON_BYTES,
    _bounded_file_prefix,
    _decode_json_bytes,
    _freeze,
)

def _keys(obj: Mapping[str, Any], required: set[str], allowed: set[str], label: str) -> None:
    keys = set(obj)
    missing = sorted(required - keys)
    unknown = sorted(keys - allowed)
    if missing:
        raise GuardError(f"{label}: missing keys: {', '.join(missing)}")
    if unknown:
        raise GuardError(f"{label}: unknown keys: {', '.join(unknown)}")


def _ident(value: Any, label: str, *, _fullmatch=IDENT_RE.fullmatch) -> str:
    if type(value) is not str or not _fullmatch(value):
        raise GuardError(f"{label}: canonical lowercase ASCII identifier required")
    return value


def _opaque(value: Any, label: str, *, _fullmatch=OPAQUE_RE.fullmatch) -> str:
    if type(value) is not str or not _fullmatch(value):
        raise GuardError(f"{label}: bounded ASCII identifier required")
    return value


def _make_time(_fromisoformat, _utc):
    def _time(value: Any, label: str):
        if type(value) is not str or not value.endswith("Z"):
            raise GuardError(f"{label}: canonical UTC Z timestamp required")
        try:
            dt = _fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise GuardError(f"{label}: invalid timestamp") from exc
        if dt.tzinfo != _utc or value != dt.isoformat(timespec="seconds").replace("+00:00", "Z"):
            raise GuardError(f"{label}: whole-second canonical UTC timestamp required")
        return dt

    return _time


_time = _make_time(_PROCESS_DATETIME.fromisoformat, _PROCESS_TIMEZONE.utc)


def _format_time(dt) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _cooldown(value: Any, minimum: int, label: str) -> int:
    if type(value) is not int or value < minimum:
        raise GuardError(f"{label}: integer must be >= {minimum}")
    return value


def _candidate(
    raw: Mapping[str, Any],
    *,
    _relationship_floor: int = MIN_RELATIONSHIP_COOLDOWN_SECONDS,
    _pursuit_floor: int = MIN_PURSUIT_COOLDOWN_SECONDS,
    _keys_fn=_keys,
    _ident_fn=_ident,
    _cooldown_fn=_cooldown,
) -> dict[str, Any]:
    required = {"counterparty_id", "opportunity_id", "route", "purpose"}
    allowed = required | {"relationship_cooldown_seconds", "pursuit_cooldown_seconds"}
    _keys_fn(raw, required, allowed, "candidate")
    return {
        "counterparty_id": _ident_fn(raw["counterparty_id"], "candidate.counterparty_id"),
        "opportunity_id": _ident_fn(raw["opportunity_id"], "candidate.opportunity_id"),
        "route": _ident_fn(raw["route"], "candidate.route"),
        "purpose": _ident_fn(raw["purpose"], "candidate.purpose"),
        "relationship_cooldown_seconds": _cooldown_fn(
            raw.get("relationship_cooldown_seconds", _relationship_floor),
            _relationship_floor,
            "candidate.relationship_cooldown_seconds",
        ),
        "pursuit_cooldown_seconds": _cooldown_fn(
            raw.get("pursuit_cooldown_seconds", _pursuit_floor),
            _pursuit_floor,
            "candidate.pursuit_cooldown_seconds",
        ),
    }


def _event(
    raw: Mapping[str, Any],
    index: int,
    counterparty: str,
    *,
    _kinds=frozenset(KINDS),
    _scopes=frozenset(SCOPES),
    _keys_fn=_keys,
    _opaque_fn=_opaque,
    _ident_fn=_ident,
    _time_fn=_time,
) -> dict[str, Any]:
    label = f"events[{index}]"
    required = {"event_id", "kind", "occurred_at", "counterparty_id", "opportunity_id", "route", "purpose"}
    allowed = required | {
        "provider_message_id",
        "provider_thread_id",
        "scope",
        "in_reply_to_message_id",
        "reopens_event_id",
    }
    _keys_fn(raw, required, allowed, label)
    kind = raw["kind"]
    if type(kind) is not str or kind not in _kinds:
        raise GuardError(f"{label}.kind: unsupported event kind")
    out = {
        "event_id": _opaque_fn(raw["event_id"], f"{label}.event_id"),
        "kind": kind,
        "occurred_at": raw["occurred_at"],
        "counterparty_id": _ident_fn(raw["counterparty_id"], f"{label}.counterparty_id"),
        "opportunity_id": _ident_fn(raw["opportunity_id"], f"{label}.opportunity_id"),
        "route": _ident_fn(raw["route"], f"{label}.route"),
        "purpose": _ident_fn(raw["purpose"], f"{label}.purpose"),
    }
    _time_fn(out["occurred_at"], f"{label}.occurred_at")
    if out["counterparty_id"] != counterparty:
        raise GuardError(f"{label}: cross-counterparty event transplant")
    for field in ("provider_message_id", "provider_thread_id", "in_reply_to_message_id", "reopens_event_id"):
        if field in raw:
            out[field] = _opaque_fn(raw[field], f"{label}.{field}")

    if kind == "PROVIDER_SENT":
        if "provider_message_id" not in out:
            raise GuardError(f"{label}: PROVIDER_SENT requires provider_message_id")
        if "in_reply_to_message_id" in out or "reopens_event_id" in out or "scope" in raw:
            raise GuardError(f"{label}: PROVIDER_SENT has incompatible response fields")
    elif kind == "PROVIDER_BOUNCE":
        if "in_reply_to_message_id" not in out:
            raise GuardError(f"{label}: PROVIDER_BOUNCE requires in_reply_to_message_id")
        if "scope" in raw or "reopens_event_id" in out:
            raise GuardError(f"{label}: PROVIDER_BOUNCE has incompatible fields")
    elif kind == "HUMAN_REPLY":
        if "in_reply_to_message_id" not in out:
            raise GuardError(f"{label}: HUMAN_REPLY requires in_reply_to_message_id")
        if "scope" in raw or "reopens_event_id" in out:
            raise GuardError(f"{label}: HUMAN_REPLY has incompatible fields")
    elif kind == "HUMAN_NEGATIVE":
        if "in_reply_to_message_id" not in out:
            raise GuardError(f"{label}: HUMAN_NEGATIVE requires in_reply_to_message_id")
        scope = raw.get("scope")
        if type(scope) is not str or scope not in _scopes:
            raise GuardError(f"{label}: HUMAN_NEGATIVE requires valid scope")
        out["scope"] = scope
        if "reopens_event_id" in out:
            raise GuardError(f"{label}: HUMAN_NEGATIVE cannot reopen another event")
    elif kind == "HUMAN_REOPEN":
        if "in_reply_to_message_id" not in out or "reopens_event_id" not in out:
            raise GuardError(f"{label}: HUMAN_REOPEN requires in_reply_to_message_id and reopens_event_id")
        scope = raw.get("scope")
        if type(scope) is not str or scope not in _scopes:
            raise GuardError(f"{label}: HUMAN_REOPEN requires valid scope")
        out["scope"] = scope

    return out


def _bind_response(event: Mapping[str, Any], send: Mapping[str, Any], label: str) -> None:
    for field in ("counterparty_id", "opportunity_id", "route", "purpose"):
        if event[field] != send[field]:
            raise GuardError(f"{label}: response/bounce transplant changes referenced send {field}")
    # Thread identity is optional, but when present it is exact-generation
    # evidence: a response cannot add, omit, or swap the referenced send thread.
    if event.get("provider_thread_id") != send.get("provider_thread_id"):
        raise GuardError(f"{label}: response/bounce thread does not match referenced send")


def _semantic_event_key(event: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    # event_id and provider_message_id are source identities, not semantic
    # evidence identity. Reminting either must not turn one retained fact into
    # two facts. provider_thread_id and all lineage/scope fields remain bound.
    excluded = {"event_id", "provider_message_id"}
    return tuple((key, event[key]) for key in sorted(event) if key not in excluded)


def _validate(
    packet: Mapping[str, Any],
    now,
    *,
    _max_events: int = MAX_EVENTS,
    _keys_fn=_keys,
    _candidate_fn=_candidate,
    _event_fn=_event,
    _time_fn=_time,
    _semantic_event_key_fn=_semantic_event_key,
    _bind_response_fn=_bind_response,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _keys_fn(packet, {"candidate", "events"}, {"candidate", "events"}, "packet")
    if type(packet["candidate"]) is not dict or type(packet["events"]) is not list:
        raise GuardError("packet candidate/events types invalid")
    candidate = _candidate_fn(packet["candidate"])
    if len(packet["events"]) > _max_events:
        raise GuardError("too many events")
    events = [_event_fn(raw, i, candidate["counterparty_id"]) for i, raw in enumerate(packet["events"])]

    seen_event: set[str] = set()
    seen_provider: set[str] = set()
    seen_semantic: set[tuple[tuple[str, Any], ...]] = set()
    send_by_message: dict[str, dict[str, Any]] = {}
    event_by_id: dict[str, dict[str, Any]] = {}
    last = None

    for i, event in enumerate(events):
        label = f"events[{i}]"
        dt = _time_fn(event["occurred_at"], f"{label}.occurred_at")
        if dt > now:
            raise GuardError(f"{label}: future-dated event")
        if last is not None and dt < last:
            raise GuardError("events: chronology must be nondecreasing")
        last = dt

        if event["event_id"] in seen_event:
            raise GuardError("duplicate event_id")
        seen_event.add(event["event_id"])

        semantic_key = _semantic_event_key_fn(event)
        if semantic_key in seen_semantic:
            raise GuardError("duplicate semantic event")
        seen_semantic.add(semantic_key)

        mid = event.get("provider_message_id")
        if mid is not None:
            if mid in seen_provider:
                raise GuardError("duplicate provider_message_id")
            seen_provider.add(mid)

        if event["kind"] == "PROVIDER_SENT":
            send_by_message[event["provider_message_id"]] = event
        ref = event.get("in_reply_to_message_id")
        if ref is not None:
            send = send_by_message.get(ref)
            if send is None:
                raise GuardError(f"{label}: orphan response/bounce reference")
            _bind_response_fn(event, send, label)

        if event["kind"] == "HUMAN_REOPEN":
            blocker = event_by_id.get(event["reopens_event_id"])
            if blocker is None or blocker["kind"] != "HUMAN_NEGATIVE":
                raise GuardError(f"{label}: reopen must reference an earlier HUMAN_NEGATIVE")
            if event["scope"] != blocker["scope"]:
                raise GuardError(f"{label}: reopen scope does not match referenced negative")
            for field in ("counterparty_id", "opportunity_id", "route", "purpose", "in_reply_to_message_id"):
                if event[field] != blocker[field]:
                    raise GuardError(f"{label}: reopen does not exactly bind referenced negative {field}")

        event_by_id[event["event_id"]] = event

    return candidate, events


def _send_state(send: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> str:
    mid = send["provider_message_id"]
    later = [e for e in events if e.get("in_reply_to_message_id") == mid]
    # A retained hard bounce is transport evidence and remains route-dead even
    # if later contradictory human-shaped evidence is present.
    if any(event["kind"] == "PROVIDER_BOUNCE" for event in later):
        return "BOUNCED"
    if any(event["kind"] in {"HUMAN_REPLY", "HUMAN_NEGATIVE", "HUMAN_REOPEN"} for event in later):
        return "HUMAN_EVENT"
    return "DELIVERED_UNANSWERED"


def _reopened_after(
    events: Sequence[Mapping[str, Any]],
    blocker: Mapping[str, Any],
    *,
    _time_fn=_time,
) -> bool:
    blocker_time = _time_fn(blocker["occurred_at"], "blocker.occurred_at")
    for event in events:
        if event["kind"] != "HUMAN_REOPEN":
            continue
        if event.get("reopens_event_id") != blocker["event_id"]:
            continue
        if _time_fn(event["occurred_at"], "reopen.occurred_at") > blocker_time:
            return True
    return False


def _active_scoped_negative(
    events: Sequence[Mapping[str, Any]],
    scope: str,
    candidate: Mapping[str, Any],
    *,
    _reopened_after_fn=_reopened_after,
):
    active = []
    for event in events:
        if event["kind"] != "HUMAN_NEGATIVE" or event.get("scope") != scope:
            continue
        if scope == "ROUTE_PURPOSE" and (
            event["route"] != candidate["route"] or event["purpose"] != candidate["purpose"]
        ):
            continue
        if not _reopened_after_fn(events, event):
            active.append(event)
    return active[-1] if active else None


def _compile_at(
    frozen: Mapping[str, Any],
    now,
    evaluation_mode: str,
    *,
    _schema: str = SCHEMA,
    _artifact_schema: str = ARTIFACT_SCHEMA,
    _validate_fn=_validate,
    _active_scoped_negative_fn=_active_scoped_negative,
    _send_state_fn=_send_state,
    _time_fn=_time,
    _format_time_fn=_format_time,
    _digest_fn=digest,
) -> dict[str, Any]:
    candidate, events = _validate_fn(frozen, now)
    status = "NO_CONFLICT_FOUND"
    reasons: list[str] = []
    blockers: list[str] = []

    org_negative = _active_scoped_negative_fn(events, "COUNTERPARTY", candidate)
    route_negative = _active_scoped_negative_fn(events, "ROUTE_PURPOSE", candidate)
    if org_negative is not None:
        status = "HOLD_COUNTERPARTY_OPT_OUT"
        reasons.append("retained human negative event applies to the whole counterparty")
        blockers.append(org_negative["event_id"])
    elif route_negative is not None:
        status = "HOLD_ROUTE_PURPOSE_OPT_OUT"
        reasons.append("retained human negative event applies to this route/purpose")
        blockers.append(route_negative["event_id"])

    sends = [(e, _send_state_fn(e, events)) for e in events if e["kind"] == "PROVIDER_SENT"]
    if status == "NO_CONFLICT_FOUND":
        bounced = [e for e, state in sends if state == "BOUNCED" and e["route"] == candidate["route"]]
        if bounced:
            status = "HOLD_DEAD_ROUTE"
            reasons.append("current route has a retained hard-bounce event; bounce is route-scoped, not counterparty rejection")
            blockers.append(bounced[-1]["event_id"])
    if status == "NO_CONFLICT_FOUND":
        exact = [
            e
            for e, state in sends
            if state == "DELIVERED_UNANSWERED"
            and e["route"] == candidate["route"]
            and e["purpose"] == candidate["purpose"]
        ]
        if exact:
            status = "HOLD_EXACT_DNR"
            reasons.append("same route/purpose has provider-SENT with no later human/provider resolution")
            blockers.append(exact[-1]["event_id"])
    if status == "NO_CONFLICT_FOUND":
        recent = []
        for send, state in sends:
            if state == "BOUNCED":
                continue
            age = int((now - _time_fn(send["occurred_at"], "send.occurred_at")).total_seconds())
            if age < candidate["relationship_cooldown_seconds"]:
                recent.append((send, age))
        if recent:
            send, age = recent[-1]
            status = "HOLD_RECENT_COUNTERPARTY_CONTACT"
            reasons.append(
                f"same counterparty has recent non-bounced provider send "
                f"({age}s < {candidate['relationship_cooldown_seconds']}s)"
            )
            blockers.append(send["event_id"])
    if status == "NO_CONFLICT_FOUND":
        recent = []
        for send, state in sends:
            if (
                state == "BOUNCED"
                or send["opportunity_id"] != candidate["opportunity_id"]
                or send["purpose"] != candidate["purpose"]
            ):
                continue
            age = int((now - _time_fn(send["occurred_at"], "send.occurred_at")).total_seconds())
            if age < candidate["pursuit_cooldown_seconds"]:
                recent.append((send, age))
        if recent:
            send, age = recent[-1]
            status = "HOLD_RECENT_PURSUIT_CONTACT"
            reasons.append(
                f"same opportunity/purpose has recent non-bounced provider send "
                f"({age}s < {candidate['pursuit_cooldown_seconds']}s)"
            )
            blockers.append(send["event_id"])

    # HUMAN_REPLY is relationship-level inbound custody. Every admitted event
    # is already exact-counterparty-bound in _event/_validate, so a genuine
    # reply on opportunity A must not age into fresh outbound permission for
    # opportunity B at the same counterparty merely because cooldown windows
    # elapsed. Response lineage remains exact to the original send.
    replies = [e for e in events if e["kind"] == "HUMAN_REPLY"]
    if status == "NO_CONFLICT_FOUND" and replies:
        status = "HOLD_INBOUND_REVIEW"
        reasons.append(
            "retained human reply exists for this counterparty relationship; "
            "relationship should be handled as inbound context"
        )
        blockers.append(replies[-1]["event_id"])
    if not reasons:
        reasons.append(
            "no relationship conflict found in supplied retained packet; "
            "packet completeness and provider authentication are not established"
        )

    # Source-literal authority ceiling. Do not replace this with AUTHORITY.copy():
    # that exported compatibility object is intentionally non-semantic.
    authority = {
        "send_authorized": False,
        "muse_authorized": False,
        "provider_send_proven": False,
        "buyer_acceptance_proven": False,
        "contract_proven": False,
        "payment_proven": False,
        "cash_proven": False,
        "revenue_recognized": False,
    }
    decision = {
        "schema": _schema,
        "evaluation_mode": evaluation_mode,
        "evaluated_at": _format_time_fn(now),
        "status": status,
        "candidate": candidate,
        "blocker_event_ids": blockers,
        "reasons": reasons,
        "retained_event_count": len(events),
        "input_sha256": _digest_fn(frozen),
        "authority": authority,
        "next_gate": (
            "HOLD_AND_RECONCILE"
            if status != "NO_CONFLICT_FOUND"
            else "FRESH_SLACK_GMAIL_RECENSUS_THEN_SESSION_BOUND_MUSE_CONSUME_GO"
        ),
        "truth": {
            "retained_packet_complete": False,
            "provider_authentication_established_here": False,
            "no_conflict_is_send_permission": False,
            "evaluation_time_claim": evaluation_mode,
            "evaluation_time_process_origin_authenticated": False,
            "retained_replay_establishes_currentness": False,
        },
    }
    core = {"artifact_schema": _artifact_schema, "decision": decision}
    return {**core, "receipt_sha256": _digest_fn(core)}


def _make_compile_guard(_freeze_fn, _compile_at_fn, _datetime_cls, _utc):
    def compile_guard(packet: Mapping[str, Any]) -> dict[str, Any]:
        frozen = _freeze_fn(packet, "packet")
        now = _datetime_cls.now(_utc).replace(microsecond=0)
        return _compile_at_fn(frozen, now, "PROCESS_UTC_SNAPSHOT")

    return compile_guard


compile_guard = _make_compile_guard(
    _freeze,
    _compile_at,
    _PROCESS_DATETIME,
    _PROCESS_TIMEZONE.utc,
)


def _make_verify_guard(
    _verification_schema: str,
    _hex64_fullmatch,
    _freeze_fn,
    _time_fn,
    _compile_at_fn,
    _canonical_bytes_fn,
    _digest_fn,
    _datetime_cls,
    _utc,
):
    def verify_guard(packet: Mapping[str, Any], artifact: Mapping[str, Any]) -> dict[str, Any]:
        """Verify retained artifact integrity, then freshly re-evaluate current semantics.

        A semantic receipt is not a signature. The retained artifact cannot prove
        that its own evaluated_at was originally sampled from process UTC, so this
        verifier never upgrades that retained clock claim. Current diagnostic
        status comes only from a fresh process-time evaluation performed here.
        """
        frozen_artifact = _freeze_fn(artifact, "artifact")
        decision = frozen_artifact.get("decision")
        if type(decision) is not dict:
            raise GuardError("artifact decision missing")
        if decision.get("evaluation_mode") != "PROCESS_UTC_SNAPSHOT":
            raise GuardError("artifact evaluation_mode must be PROCESS_UTC_SNAPSHOT")
        evaluated_at = _time_fn(decision.get("evaluated_at"), "artifact.decision.evaluated_at")

        verify_now = _datetime_cls.now(_utc).replace(microsecond=0)
        if evaluated_at > verify_now:
            raise GuardError("artifact evaluated_at is in the future")

        frozen_packet = _freeze_fn(packet, "packet")
        expected = _compile_at_fn(frozen_packet, evaluated_at, "PROCESS_UTC_SNAPSHOT")
        if _canonical_bytes_fn(frozen_artifact) != _canonical_bytes_fn(expected):
            raise GuardError("artifact does not exactly match deterministic retained-time recompile")
        receipt = frozen_artifact.get("receipt_sha256")
        if type(receipt) is not str or not _hex64_fullmatch(receipt):
            raise GuardError("artifact receipt_sha256 malformed")
        core = {"artifact_schema": frozen_artifact["artifact_schema"], "decision": frozen_artifact["decision"]}
        if _digest_fn(core) != receipt:
            raise GuardError("artifact receipt mismatch")
        if any(frozen_artifact["decision"]["authority"].values()):
            raise GuardError("artifact authority ceiling widened")

        fresh = _compile_at_fn(frozen_packet, verify_now, "PROCESS_UTC_VERIFY_FRESH")
        if any(fresh["decision"]["authority"].values()):
            raise GuardError("fresh verification authority ceiling widened")

        return {
            "verification_schema": _verification_schema,
            "retained_integrity_verified": True,
            "retained_time_process_origin_verified": False,
            "retained_status_is_current": False,
            "artifact_evaluated_at": frozen_artifact["decision"]["evaluated_at"],
            "artifact_status": frozen_artifact["decision"]["status"],
            "verification_evaluated_at": fresh["decision"]["evaluated_at"],
            "fresh_status": fresh["decision"]["status"],
            "fresh_decision": fresh["decision"],
            "fresh_receipt_sha256": fresh["receipt_sha256"],
            "authority": {
                "send_authorized": False,
                "muse_authorized": False,
                "provider_send_proven": False,
                "buyer_acceptance_proven": False,
                "contract_proven": False,
                "payment_proven": False,
                "cash_proven": False,
                "revenue_recognized": False,
            },
        }

    return verify_guard


verify_guard = _make_verify_guard(
    VERIFICATION_SCHEMA,
    HEX64_RE.fullmatch,
    _freeze,
    _time,
    _compile_at,
    canonical_bytes,
    digest,
    _PROCESS_DATETIME,
    _PROCESS_TIMEZONE.utc,
)

def _make_write(_json_text_fn, _write_text):
    def _write(path: Path, value: Any) -> None:
        text = _json_text_fn(value, pretty=True) + "\n"
        _write_text(path, text, encoding="utf-8")

    return _write


_write = _make_write(_json_text, Path.write_text)


def _make_main(
    _compile_guard_fn,
    _verify_guard_fn,
    _load_json_fn,
    _write_fn,
    _argument_parser_cls,
    _path_cls,
    _description,
):
    def main(argv: Sequence[str] | None = None) -> int:
        parser = _argument_parser_cls(description=_description)
        sub = parser.add_subparsers(dest="command", required=True)
        cp = sub.add_parser("compile")
        cp.add_argument("packet", type=_path_cls)
        cp.add_argument("output", type=_path_cls)
        vp = sub.add_parser("verify")
        vp.add_argument("packet", type=_path_cls)
        vp.add_argument("artifact", type=_path_cls)
        args = parser.parse_args(argv)
        if args.command == "compile":
            artifact = _compile_guard_fn(_load_json_fn(args.packet))
            _write_fn(args.output, artifact)
            print(artifact["receipt_sha256"])
            return 0
        _verify_guard_fn(_load_json_fn(args.packet), _load_json_fn(args.artifact))
        print("OK")
        return 0

    return main


main = _make_main(
    compile_guard,
    verify_guard,
    load_json,
    _write,
    argparse.ArgumentParser,
    Path,
    __doc__,
)


if __name__ == "__main__":
    raise SystemExit(main())
