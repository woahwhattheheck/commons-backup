#!/usr/bin/env python3
"""Compile deterministic engine deltas into a strict TITAN W10 trace.

This module is an additive instrumentation primitive. It does not choose game
actions. A producer adapter may emit per-tick deltas and absolute inventory
gauges; the builder accumulates them, carries state to the exact horizon, and
runs the same fail-closed trace validator used by the W10 certificate.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from realized_fertilizer import (
    TRACE_SCHEMA,
    TraceValidationError,
    canonical_sha256,
    validate_trace,
)

EVENT_STREAM_SCHEMA = "titan.w10.realized-fertilizer-events/v1"
EVENT_BUILD_RECEIPT_SCHEMA = "titan.w10.realized-fertilizer-event-build/v1"

_TOP_LEVEL_KEYS = {
    "schema",
    "variant",
    "policy_sha256",
    "identity",
    "capacity",
    "initial_snapshot",
    "events",
}
_EVENT_KEYS = {"tick", "deltas", "cash_delta", "gauges"}
_GAUGE_KEYS = {"carry_units", "shed_units"}
_COUNTER_FIELDS = (
    "fertilizer_actions",
    "produced_units",
    "harvested_units",
    "deposited_units",
    "sold_units",
    "discarded_units",
    "worker_ticks_used",
    "travel_steps",
    "watering_actions",
    "harvest_actions",
    "deposit_actions",
    "sale_actions",
    "protected_obligation_misses",
    "protected_stock_shortfall_units",
)
_COUNTER_KEYS = set(_COUNTER_FIELDS)
_SNAPSHOT_FIELDS = (
    "tick",
    *_COUNTER_FIELDS,
    "cash",
    "carry_units",
    "shed_units",
)
_SNAPSHOT_KEYS = set(_SNAPSHOT_FIELDS)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_EVENTS = 100_000
_MAX_INPUT_BYTES = 8 * 1024 * 1024


class EventBuildError(ValueError):
    """Raised when an event stream cannot safely compile into a trace."""


def _mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EventBuildError(f"{where} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("extra=" + ",".join(extra))
        raise EventBuildError(f"{where} keys invalid ({'; '.join(details)})")


def _int(value: Any, where: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EventBuildError(
            f"{where} must be an integer (booleans are rejected)"
        )
    if minimum is not None and value < minimum:
        raise EventBuildError(f"{where} must be >= {minimum}")
    return value


def _sha(value: Any, where: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise EventBuildError(
            f"{where} must be a lowercase 64-character SHA-256"
        )
    return value


def _copy_json_object(value: Any, where: str) -> dict[str, Any]:
    mapping = _mapping(value, where)
    try:
        copied = json.loads(json.dumps(mapping, sort_keys=True, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise EventBuildError(f"{where} must contain JSON values: {exc}") from exc
    if not isinstance(copied, dict):
        raise EventBuildError(f"{where} must be an object")
    return copied


def _initial_snapshot(raw: Any) -> dict[str, int]:
    value = _mapping(raw, "initial_snapshot")
    _exact_keys(value, _SNAPSHOT_KEYS, "initial_snapshot")
    normalized: dict[str, int] = {}
    for field in _SNAPSHOT_FIELDS:
        minimum = None if field == "cash" else 0
        normalized[field] = _int(
            value[field], f"initial_snapshot.{field}", minimum=minimum
        )
    return normalized


def _event(raw: Any, index: int) -> dict[str, Any]:
    where = f"events[{index}]"
    value = _mapping(raw, where)
    _exact_keys(value, _EVENT_KEYS, where)
    tick = _int(value["tick"], f"{where}.tick", minimum=0)
    cash_delta = _int(value["cash_delta"], f"{where}.cash_delta")

    deltas = _mapping(value["deltas"], f"{where}.deltas")
    unknown_deltas = sorted(set(deltas) - _COUNTER_KEYS)
    if unknown_deltas:
        raise EventBuildError(
            f"{where}.deltas keys invalid (extra={','.join(unknown_deltas)})"
        )
    normalized_deltas = {
        field: _int(delta, f"{where}.deltas.{field}", minimum=0)
        for field, delta in sorted(deltas.items())
    }

    gauges = _mapping(value["gauges"], f"{where}.gauges")
    unknown_gauges = sorted(set(gauges) - _GAUGE_KEYS)
    if unknown_gauges:
        raise EventBuildError(
            f"{where}.gauges keys invalid (extra={','.join(unknown_gauges)})"
        )
    normalized_gauges = {
        field: _int(gauge, f"{where}.gauges.{field}", minimum=0)
        for field, gauge in sorted(gauges.items())
    }

    if not normalized_deltas and cash_delta == 0 and not normalized_gauges:
        raise EventBuildError(
            f"{where} must change at least one counter or gauge"
        )
    return {
        "tick": tick,
        "deltas": normalized_deltas,
        "cash_delta": cash_delta,
        "gauges": normalized_gauges,
    }


def compile_event_stream(raw: Any) -> dict[str, Any]:
    """Compile one event-stream document into a normalized trace and receipt."""

    stream = _mapping(raw, "event_stream")
    _exact_keys(stream, _TOP_LEVEL_KEYS, "event_stream")
    if stream["schema"] != EVENT_STREAM_SCHEMA:
        raise EventBuildError(
            f"event_stream.schema must equal {EVENT_STREAM_SCHEMA!r}"
        )
    variant = stream["variant"]
    if variant not in ("control", "fertilized"):
        raise EventBuildError(
            "event_stream.variant must be 'control' or 'fertilized'"
        )
    policy_sha256 = _sha(
        stream["policy_sha256"], "event_stream.policy_sha256"
    )
    identity = _copy_json_object(stream["identity"], "event_stream.identity")
    capacity = _copy_json_object(stream["capacity"], "event_stream.capacity")
    initial = _initial_snapshot(stream["initial_snapshot"])

    events_raw = stream["events"]
    if isinstance(events_raw, (str, bytes)) or not isinstance(
        events_raw, Sequence
    ):
        raise EventBuildError("event_stream.events must be an array")
    if len(events_raw) > _MAX_EVENTS:
        raise EventBuildError(f"event_stream.events exceeds {_MAX_EVENTS}")
    events = [_event(item, index) for index, item in enumerate(events_raw)]

    horizon = _int(
        identity.get("horizon_tick"),
        "event_stream.identity.horizon_tick",
        minimum=1,
    )
    if initial["tick"] > horizon:
        raise EventBuildError("initial_snapshot.tick exceeds horizon_tick")

    snapshots: list[dict[str, int]] = [dict(initial)]
    current = dict(initial)
    pending_tick: int | None = None

    def flush_pending() -> None:
        nonlocal pending_tick
        if pending_tick is None:
            return
        row = dict(current)
        row["tick"] = pending_tick
        snapshots.append(row)
        pending_tick = None

    for index, event in enumerate(events):
        tick = event["tick"]
        if tick < initial["tick"]:
            raise EventBuildError(
                f"events[{index}].tick precedes initial_snapshot.tick"
            )
        if tick > horizon:
            raise EventBuildError(
                f"events[{index}].tick exceeds horizon_tick"
            )
        if pending_tick is not None and tick < pending_tick:
            raise EventBuildError("events must be ordered by nondecreasing tick")
        if tick == initial["tick"] and pending_tick is None:
            raise EventBuildError(
                "events at initial_snapshot.tick are ambiguous; include them "
                "in the initial snapshot"
            )
        if pending_tick is not None and tick > pending_tick:
            flush_pending()
        pending_tick = tick

        for field, delta in event["deltas"].items():
            current[field] += delta
        current["cash"] += event["cash_delta"]
        for field, gauge in event["gauges"].items():
            current[field] = gauge

    flush_pending()
    if snapshots[-1]["tick"] < horizon:
        terminal = dict(current)
        terminal["tick"] = horizon
        snapshots.append(terminal)

    trace_raw = {
        "schema": TRACE_SCHEMA,
        "variant": variant,
        "policy_sha256": policy_sha256,
        "identity": identity,
        "capacity": capacity,
        "snapshots": snapshots,
    }
    try:
        trace = validate_trace(trace_raw, expected_variant=variant)
    except TraceValidationError as exc:
        raise EventBuildError(f"compiled trace rejected:{exc}") from exc

    body: dict[str, Any] = {
        "schema": EVENT_BUILD_RECEIPT_SCHEMA,
        "event_stream_sha256": canonical_sha256(
            {
                "schema": EVENT_STREAM_SCHEMA,
                "variant": variant,
                "policy_sha256": policy_sha256,
                "identity": identity,
                "capacity": capacity,
                "initial_snapshot": initial,
                "events": events,
            }
        ),
        "trace_sha256": canonical_sha256(trace),
        "event_count": len(events),
        "snapshot_count": len(trace["snapshots"]),
        "trace": trace,
    }
    body["receipt_sha256"] = canonical_sha256(body)
    return body


def _load_json(path: Path) -> Any:
    raw = path.read_bytes()
    if len(raw) > _MAX_INPUT_BYTES:
        raise EventBuildError(f"input exceeds {_MAX_INPUT_BYTES} bytes")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EventBuildError(f"invalid UTF-8 JSON:{exc}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile per-tick TITAN W10 deltas into a strict trace."
    )
    parser.add_argument("event_stream", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--trace-output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        raw = _load_json(args.event_stream)
        receipt = compile_event_stream(raw)
    except EventBuildError as exc:
        parser.error(str(exc))

    indent = 2 if args.pretty else None
    separators = None if args.pretty else (",", ":")
    rendered = (
        json.dumps(
            receipt, sort_keys=True, indent=indent, separators=separators
        )
        + "\n"
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.trace_output:
        args.trace_output.parent.mkdir(parents=True, exist_ok=True)
        args.trace_output.write_text(
            json.dumps(
                receipt["trace"],
                sort_keys=True,
                indent=indent,
                separators=separators,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
