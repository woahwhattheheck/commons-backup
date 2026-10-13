from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

POLICY_SCHEMA = "port-data-qc-policy/v1"
SNAPSHOT_SCHEMA = "port-data-qc-snapshot/v1"
RECEIPT_SCHEMA = "port-data-qc-receipt/v1"
REPORT_SCHEMA = "port-data-qc-report/v1"
EXCEPTIONS_SCHEMA = "port-data-qc-exceptions/v1"

MAX_SOURCES = 32
MAX_EVENTS = 10_000
MAX_FIELDS = 64
MAX_JSON_BYTES = 1_048_576
MAX_STRING_BYTES = 512
MAX_ID_BYTES = 128
MAX_SNAPSHOT_AGE_SECONDS = 30 * 24 * 3600

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_FIELD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class GateInputError(ValueError):
    """Raised when the caller supplies a malformed policy or snapshot envelope."""


@dataclass(frozen=True)
class _PolicySource:
    schema_version: str
    allowed_fields: tuple[str, ...]
    required_fields: tuple[str, ...]


@dataclass(frozen=True)
class _Event:
    source_id: str
    event_id: str
    record_id: str
    business_key: str
    schema_version: str
    previous_event_id: str | None
    effective_at: str
    observed_at: str
    values: dict[str, Any]
    digest: str


def _exact_dict(value: Any, *, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise GateInputError(f"{name} must be an object")
    return value


def _exact_bool(value: Any, *, name: str) -> bool:
    if type(value) is not bool:
        raise GateInputError(f"{name} must be a boolean")
    return value


def _exact_int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not (minimum <= value <= maximum):
        raise GateInputError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _bounded_string(value: Any, *, name: str, max_bytes: int = MAX_STRING_BYTES) -> str:
    if type(value) is not str or not value or _utf8_len(value) > max_bytes:
        raise GateInputError(f"{name} must be a non-empty bounded string")
    return value


def _identifier(value: Any, *, name: str) -> str:
    value = _bounded_string(value, name=name, max_bytes=MAX_ID_BYTES)
    if _ID_RE.fullmatch(value) is None:
        raise GateInputError(f"{name} is not a canonical identifier")
    return value


def _field_name(value: Any, *, name: str) -> str:
    value = _bounded_string(value, name=name, max_bytes=MAX_ID_BYTES)
    if _FIELD_RE.fullmatch(value) is None:
        raise GateInputError(f"{name} is not a canonical field name")
    return value


def _exact_keys(obj: dict[str, Any], expected: set[str], *, name: str) -> None:
    keys = set(obj)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        raise GateInputError(f"{name} has wrong fields; missing={missing}, extra={extra}")


def _canonical_bytes(value: Any) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GateInputError("value is not canonical JSON") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise GateInputError("canonical JSON exceeds the 1 MiB gate limit")
    return raw


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _parse_utc(value: Any, *, name: str) -> datetime:
    value = _bounded_string(value, name=name, max_bytes=64)
    if not value.endswith("Z"):
        raise GateInputError(f"{name} must be UTC with a trailing Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise GateInputError(f"{name} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise GateInputError(f"{name} must be UTC")
    return parsed


def _validate_scalar(value: Any, *, name: str) -> Any:
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        if -(2**53) <= value <= 2**53:
            return value
        raise GateInputError(f"{name} integer is outside the exact JSON range")
    if type(value) is str:
        if _utf8_len(value) <= MAX_STRING_BYTES:
            return value
        raise GateInputError(f"{name} string exceeds the byte limit")
    raise GateInputError(f"{name} must be null, boolean, exact integer, or string")


def _parse_policy(policy: Any) -> tuple[dict[str, _PolicySource], int]:
    obj = _exact_dict(policy, name="policy")
    _exact_keys(obj, {"schema", "max_snapshot_age_seconds", "sources"}, name="policy")
    if obj["schema"] != POLICY_SCHEMA:
        raise GateInputError("unsupported policy schema")
    age = _exact_int(
        obj["max_snapshot_age_seconds"],
        name="policy.max_snapshot_age_seconds",
        minimum=0,
        maximum=MAX_SNAPSHOT_AGE_SECONDS,
    )
    sources_obj = _exact_dict(obj["sources"], name="policy.sources")
    if not (1 <= len(sources_obj) <= MAX_SOURCES):
        raise GateInputError("policy.sources cardinality is out of bounds")

    parsed: dict[str, _PolicySource] = {}
    for raw_source_id, raw_spec in sorted(sources_obj.items()):
        source_id = _identifier(raw_source_id, name="policy source id")
        spec = _exact_dict(raw_spec, name=f"policy.sources.{source_id}")
        _exact_keys(spec, {"schema_version", "allowed_fields", "required_fields"}, name=f"policy.sources.{source_id}")
        schema_version = _identifier(spec["schema_version"], name=f"policy.sources.{source_id}.schema_version")
        allowed_raw = spec["allowed_fields"]
        required_raw = spec["required_fields"]
        if type(allowed_raw) is not list or type(required_raw) is not list:
            raise GateInputError("allowed_fields and required_fields must be arrays")
        if len(allowed_raw) > MAX_FIELDS or len(required_raw) > MAX_FIELDS:
            raise GateInputError("field policy exceeds the field limit")
        allowed = tuple(_field_name(v, name="allowed field") for v in allowed_raw)
        required = tuple(_field_name(v, name="required field") for v in required_raw)
        if len(set(allowed)) != len(allowed) or len(set(required)) != len(required):
            raise GateInputError("field policy contains duplicates")
        if not set(required).issubset(set(allowed)):
            raise GateInputError("required_fields must be a subset of allowed_fields")
        parsed[source_id] = _PolicySource(schema_version, tuple(sorted(allowed)), tuple(sorted(required)))
    return parsed, age


def _parse_event(raw_event: Any, *, policy_sources: dict[str, _PolicySource], captured_at: datetime, evaluated_at: datetime) -> _Event:
    event = _exact_dict(raw_event, name="event")
    _exact_keys(
        event,
        {
            "source_id",
            "event_id",
            "record_id",
            "business_key",
            "schema_version",
            "previous_event_id",
            "effective_at",
            "observed_at",
            "values",
        },
        name="event",
    )
    source_id = _identifier(event["source_id"], name="event.source_id")
    if source_id not in policy_sources:
        raise GateInputError("event source is not present in the approved policy")
    spec = policy_sources[source_id]
    schema_version = _identifier(event["schema_version"], name="event.schema_version")
    if schema_version != spec.schema_version:
        raise GateInputError("event schema_version does not match policy")
    event_id = _identifier(event["event_id"], name="event.event_id")
    record_id = _identifier(event["record_id"], name="event.record_id")
    business_key = _identifier(event["business_key"], name="event.business_key")
    previous = event["previous_event_id"]
    if previous is not None:
        previous = _identifier(previous, name="event.previous_event_id")
        if previous == event_id:
            raise GateInputError("event cannot reference itself as predecessor")

    effective = _parse_utc(event["effective_at"], name="event.effective_at")
    observed = _parse_utc(event["observed_at"], name="event.observed_at")
    if effective > observed:
        raise GateInputError("event effective_at cannot be after observed_at")
    if observed > captured_at:
        raise GateInputError("event observed_at cannot be after snapshot captured_at")
    if observed > evaluated_at:
        raise GateInputError("event observed_at cannot be after trusted evaluation time")

    values_obj = _exact_dict(event["values"], name="event.values")
    if len(values_obj) > MAX_FIELDS:
        raise GateInputError("event.values exceeds the field limit")
    parsed_values: dict[str, Any] = {}
    for raw_name, raw_value in values_obj.items():
        field = _field_name(raw_name, name="event value field")
        if field not in spec.allowed_fields:
            raise GateInputError(f"field {field!r} is not allowed for source {source_id!r}")
        parsed_values[field] = _validate_scalar(raw_value, name=f"event.values.{field}")
    missing = sorted(set(spec.required_fields) - set(parsed_values))
    if missing:
        raise GateInputError(f"event is missing required values: {missing}")

    canonical = {
        "source_id": source_id,
        "event_id": event_id,
        "record_id": record_id,
        "business_key": business_key,
        "schema_version": schema_version,
        "previous_event_id": previous,
        "effective_at": event["effective_at"],
        "observed_at": event["observed_at"],
        "values": parsed_values,
    }
    return _Event(
        source_id=source_id,
        event_id=event_id,
        record_id=record_id,
        business_key=business_key,
        schema_version=schema_version,
        previous_event_id=previous,
        effective_at=event["effective_at"],
        observed_at=event["observed_at"],
        values=parsed_values,
        digest=_sha256(canonical),
    )


def _exception(code: str, source_id: str, record_id: str, event_ids: Iterable[str]) -> dict[str, Any]:
    return {
        "code": code,
        "source_id": source_id,
        "record_id": record_id,
        "event_ids": sorted(set(event_ids)),
    }


def _quarantine_records(events: list[_Event]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[_Event]] = {}
    for event in events:
        grouped.setdefault((event.source_id, event.record_id), []).append(event)

    report_rows: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []

    for (source_id, record_id), record_events in sorted(grouped.items()):
        by_id = {event.event_id: event for event in record_events}
        children: dict[str | None, list[_Event]] = {}
        for event in record_events:
            children.setdefault(event.previous_event_id, []).append(event)

        local_errors: list[dict[str, Any]] = []
        roots = children.get(None, [])
        if len(roots) != 1:
            local_errors.append(_exception("ROOT_CARDINALITY", source_id, record_id, [e.event_id for e in roots]))
        for event in record_events:
            if event.previous_event_id is not None and event.previous_event_id not in by_id:
                local_errors.append(_exception("MISSING_PREDECESSOR", source_id, record_id, [event.event_id, event.previous_event_id]))
        for predecessor, next_events in children.items():
            if predecessor is not None and len(next_events) > 1:
                local_errors.append(
                    _exception("BRANCH_CONFLICT", source_id, record_id, [predecessor] + [e.event_id for e in next_events])
                )
        business_keys = {event.business_key for event in record_events}
        if len(business_keys) != 1:
            local_errors.append(_exception("BUSINESS_KEY_DRIFT", source_id, record_id, [e.event_id for e in record_events]))

        if local_errors:
            exceptions.extend(local_errors)
            continue

        root = roots[0]
        lineage: list[_Event] = []
        seen: set[str] = set()
        current = root
        cycle = False
        while True:
            if current.event_id in seen:
                cycle = True
                break
            seen.add(current.event_id)
            lineage.append(current)
            nxt = children.get(current.event_id, [])
            if not nxt:
                break
            current = nxt[0]
        if cycle or len(seen) != len(record_events):
            exceptions.append(_exception("LINEAGE_NOT_SINGLE_CHAIN", source_id, record_id, [e.event_id for e in record_events]))
            continue

        # A chain is accepted irrespective of input/arrival order. The final event is report authority.
        head = lineage[-1]
        report_rows.append(
            {
                "source_id": source_id,
                "record_id": record_id,
                "business_key": head.business_key,
                "head_event_id": head.event_id,
                "effective_at": head.effective_at,
                "observed_at": head.observed_at,
                "values": head.values,
                "lineage": [event.event_id for event in lineage],
                "lineage_sha256": _sha256([{"event_id": e.event_id, "digest": e.digest} for e in lineage]),
            }
        )

    report_rows.sort(key=lambda row: (row["source_id"], row["business_key"], row["record_id"]))
    exceptions.sort(key=lambda row: (row["source_id"], row["record_id"], row["code"], row["event_ids"]))
    return report_rows, exceptions


def evaluate(policy: Any, snapshot: Any, *, evaluated_at: str) -> dict[str, Any]:
    """Evaluate one complete synthetic/offline consolidation snapshot.

    A PASS is evidence that the supplied bounded snapshot is internally coherent under the
    supplied policy. It is deliberately *not* an operational release, customer acceptance,
    payment, proposal, or production-write authorization.
    """
    evaluated_dt = _parse_utc(evaluated_at, name="evaluated_at")
    policy_sources, max_age = _parse_policy(policy)
    policy_hash = _sha256(policy)

    obj = _exact_dict(snapshot, name="snapshot")
    _exact_keys(obj, {"schema", "capture_complete", "captured_at", "events"}, name="snapshot")
    if obj["schema"] != SNAPSHOT_SCHEMA:
        raise GateInputError("unsupported snapshot schema")
    capture_complete = _exact_bool(obj["capture_complete"], name="snapshot.capture_complete")
    captured_dt = _parse_utc(obj["captured_at"], name="snapshot.captured_at")
    if captured_dt > evaluated_dt:
        raise GateInputError("snapshot captured_at cannot be after trusted evaluation time")
    age_seconds = int((evaluated_dt - captured_dt).total_seconds())

    raw_events = obj["events"]
    if type(raw_events) is not list or len(raw_events) > MAX_EVENTS:
        raise GateInputError(f"snapshot.events must be an array with at most {MAX_EVENTS} events")
    snapshot_hash = _sha256(snapshot)

    holds: set[str] = set()
    if not capture_complete:
        holds.add("SNAPSHOT_INCOMPLETE")
    if age_seconds > max_age:
        holds.add("SNAPSHOT_STALE")

    unique_by_identity: dict[tuple[str, str], _Event] = {}
    conflicting_identities: dict[tuple[str, str], set[str]] = {}
    duplicate_count = 0

    parsed_events: list[_Event] = []
    for raw_event in raw_events:
        event = _parse_event(raw_event, policy_sources=policy_sources, captured_at=captured_dt, evaluated_at=evaluated_dt)
        key = (event.source_id, event.event_id)
        prior = unique_by_identity.get(key)
        if prior is None:
            unique_by_identity[key] = event
            parsed_events.append(event)
        elif prior.digest == event.digest:
            duplicate_count += 1
        else:
            conflicting_identities.setdefault(key, {prior.digest}).add(event.digest)

    exceptions: list[dict[str, Any]] = []
    if conflicting_identities:
        holds.add("EVENT_ID_CONFLICT")
        for (source_id, event_id), digests in sorted(conflicting_identities.items()):
            exceptions.append(
                {
                    "code": "EVENT_ID_CONFLICT",
                    "source_id": source_id,
                    "record_id": "*identity-conflict*",
                    "event_ids": [event_id],
                    "digest_count": len(digests),
                }
            )

    # Conflicting identities are never allowed to contribute to the report.
    safe_events = [e for e in parsed_events if (e.source_id, e.event_id) not in conflicting_identities]
    report_rows, record_exceptions = _quarantine_records(safe_events)
    exceptions.extend(record_exceptions)
    if record_exceptions:
        holds.add("RECORDS_QUARANTINED")

    # A complete snapshot must mention every approved source. This avoids treating a silently
    # omitted source as a legitimate zero-row source.
    observed_sources = {event.source_id for event in safe_events}
    missing_sources = sorted(set(policy_sources) - observed_sources)
    if missing_sources:
        holds.add("APPROVED_SOURCE_MISSING")
        for source_id in missing_sources:
            exceptions.append(
                {
                    "code": "APPROVED_SOURCE_MISSING",
                    "source_id": source_id,
                    "record_id": "*source*",
                    "event_ids": [],
                }
            )

    exceptions.sort(key=lambda row: (row["source_id"], row["record_id"], row["code"], row.get("event_ids", [])))
    report = {"schema": REPORT_SCHEMA, "rows": report_rows}
    exception_ledger = {"schema": EXCEPTIONS_SCHEMA, "exceptions": exceptions}
    report_hash = _sha256(report)
    exception_hash = _sha256(exception_ledger)

    decision = "PASS" if not holds else "HOLD"
    receipt_core = {
        "schema": RECEIPT_SCHEMA,
        "decision": decision,
        "holds": sorted(holds),
        "evaluated_at": evaluated_at,
        "captured_at": obj["captured_at"],
        "snapshot_age_seconds": age_seconds,
        "policy_sha256": policy_hash,
        "snapshot_sha256": snapshot_hash,
        "source_count": len(observed_sources),
        "approved_source_count": len(policy_sources),
        "unique_event_count": len(safe_events),
        "duplicate_event_count": duplicate_count,
        "quarantined_record_count": len({(e["source_id"], e["record_id"]) for e in exceptions if e["record_id"] not in {"*source*", "*identity-conflict*"}}),
        "report_row_count": len(report_rows),
        "exception_count": len(exceptions),
        "report_sha256": report_hash,
        "exceptions_sha256": exception_hash,
        "authority": "EVIDENCE_ONLY_NO_OPERATIONAL_RELEASE",
    }
    receipt = dict(receipt_core)
    receipt["receipt_sha256"] = _sha256(receipt_core)
    if _HEX64_RE.fullmatch(receipt["receipt_sha256"]) is None:  # defensive invariant
        raise AssertionError("receipt digest is not canonical sha256")
    return {"receipt": receipt, "report": report, "exceptions": exception_ledger}


def verify(result: Any, *, policy: Any, snapshot: Any) -> bool:
    """Verify content binding and receipt self-hash for a previously emitted result."""
    try:
        obj = _exact_dict(result, name="result")
        _exact_keys(obj, {"receipt", "report", "exceptions"}, name="result")
        receipt = _exact_dict(obj["receipt"], name="result.receipt")
        expected_fields = {
            "schema",
            "decision",
            "holds",
            "evaluated_at",
            "captured_at",
            "snapshot_age_seconds",
            "policy_sha256",
            "snapshot_sha256",
            "source_count",
            "approved_source_count",
            "unique_event_count",
            "duplicate_event_count",
            "quarantined_record_count",
            "report_row_count",
            "exception_count",
            "report_sha256",
            "exceptions_sha256",
            "authority",
            "receipt_sha256",
        }
        _exact_keys(receipt, expected_fields, name="result.receipt")
        if receipt["schema"] != RECEIPT_SCHEMA or receipt["authority"] != "EVIDENCE_ONLY_NO_OPERATIONAL_RELEASE":
            return False
        if receipt["policy_sha256"] != _sha256(policy) or receipt["snapshot_sha256"] != _sha256(snapshot):
            return False
        if receipt["report_sha256"] != _sha256(obj["report"]) or receipt["exceptions_sha256"] != _sha256(obj["exceptions"]):
            return False
        core = dict(receipt)
        supplied = core.pop("receipt_sha256")
        if not (type(supplied) is str and _HEX64_RE.fullmatch(supplied) is not None and supplied == _sha256(core)):
            return False

        # Hashes alone are not authority: an editor could rewrite a report and recompute every
        # digest. Re-evaluate from the bound evidence and trusted evaluation time, then require
        # the complete result to match exactly. This also binds counts, HOLD reasons, lineage,
        # report rows, and exception semantics to the implementation contract.
        expected = evaluate(policy, snapshot, evaluated_at=receipt["evaluated_at"])
        return _canonical_bytes(expected) == _canonical_bytes(obj)
    except (GateInputError, KeyError, TypeError, ValueError):
        return False
