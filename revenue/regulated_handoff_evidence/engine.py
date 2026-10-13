from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = 1
RECEIPT_KIND = "regulated-handoff-evidence-receipt/v1"
MAX_EVENTS = 100_000
MAX_INPUT_BYTES = 32 * 1024 * 1024
EVENT_TYPES = {"ORIGIN_ACCEPT", "HANDOFF", "TEMP_OBSERVATION", "EXCEPTION_OPEN", "EXCEPTION_RESOLVE", "DELIVERY_ACCEPT"}
EVENT_FIELDS = {
    "schema_version", "shipment_id", "shipment_fingerprint_sha256", "event_id", "event_type",
    "event_time_utc", "source_system_id", "source_event_id", "actor_id", "location_id",
    "from_custodian", "to_custodian", "temperature_c", "exception_id", "exception_note",
}
POLICY_FIELDS = {
    "schema_version", "require_temperature_on", "temperature_min_c", "temperature_max_c",
    "max_temperature_age_seconds", "allowed_source_system_ids", "allowed_location_ids",
}

class ContractError(ValueError):
    pass


def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    def bad_constant(value: str) -> None:
        raise ContractError(f"non-finite JSON number: {value}")
    return json.loads(text, object_pairs_hook=_pairs_no_dupes, parse_constant=bad_constant)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _expect_obj(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{where} must be an object")
    return value


def _expect_str(value: Any, where: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{where} must be a string")
    if not allow_empty and not value.strip():
        raise ContractError(f"{where} must be non-empty")
    if len(value) > 512:
        raise ContractError(f"{where} too long")
    return value


def _expect_sha(value: Any, where: str) -> str:
    text = _expect_str(value, where)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ContractError(f"{where} must be lowercase SHA-256 hex")
    return text


def _parse_utc(value: Any, where: str) -> datetime:
    text = _expect_str(value, where)
    if not text.endswith("Z"):
        raise ContractError(f"{where} must use canonical UTC Z form")
    try:
        dt = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{where} invalid timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise ContractError(f"{where} must be UTC")
    if dt.microsecond or dt.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise ContractError(f"{where} must use canonical UTC-second form")
    return dt


def _num(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{where} must be numeric")
    f = float(value)
    if not math.isfinite(f):
        raise ContractError(f"{where} must be finite")
    return f


def normalize_policy(raw: Mapping[str, Any]) -> dict[str, Any]:
    policy = dict(_expect_obj(raw, "policy"))
    extra = set(policy) - POLICY_FIELDS
    if extra:
        raise ContractError(f"policy unknown fields: {sorted(extra)}")
    if policy.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("policy schema_version must be 1")
    required = policy.get("require_temperature_on", ["HANDOFF", "DELIVERY_ACCEPT"])
    if not isinstance(required, list) or any(x not in EVENT_TYPES for x in required):
        raise ContractError("policy require_temperature_on must be event-type list")
    min_c = _num(policy.get("temperature_min_c", 2.0), "policy.temperature_min_c")
    max_c = _num(policy.get("temperature_max_c", 8.0), "policy.temperature_max_c")
    if min_c > max_c:
        raise ContractError("policy temperature range inverted")
    max_age = policy.get("max_temperature_age_seconds", 900)
    if isinstance(max_age, bool) or not isinstance(max_age, int) or not (0 <= max_age <= 86400 * 30):
        raise ContractError("policy max_temperature_age_seconds invalid")
    sources = policy.get("allowed_source_system_ids", [])
    locations = policy.get("allowed_location_ids", [])
    if not isinstance(sources, list) or not isinstance(locations, list):
        raise ContractError("policy allowlists must be lists")
    sources_n = sorted({_expect_str(x, "policy.allowed_source_system_ids[]") for x in sources})
    locations_n = sorted({_expect_str(x, "policy.allowed_location_ids[]") for x in locations})
    return {
        "schema_version": 1,
        "require_temperature_on": sorted(set(required)),
        "temperature_min_c": min_c,
        "temperature_max_c": max_c,
        "max_temperature_age_seconds": max_age,
        "allowed_source_system_ids": sources_n,
        "allowed_location_ids": locations_n,
    }


def normalize_event(raw: Mapping[str, Any]) -> dict[str, Any]:
    event = dict(_expect_obj(raw, "event"))
    extra = set(event) - EVENT_FIELDS
    if extra:
        raise ContractError(f"event unknown fields: {sorted(extra)}")
    if event.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("event schema_version must be 1")
    et = _expect_str(event.get("event_type"), "event.event_type")
    if et not in EVENT_TYPES:
        raise ContractError(f"event unknown event_type: {et}")
    out: dict[str, Any] = {
        "schema_version": 1,
        "shipment_id": _expect_str(event.get("shipment_id"), "event.shipment_id"),
        "shipment_fingerprint_sha256": _expect_sha(event.get("shipment_fingerprint_sha256"), "event.shipment_fingerprint_sha256"),
        "event_id": _expect_str(event.get("event_id"), "event.event_id"),
        "event_type": et,
        "event_time_utc": _expect_str(event.get("event_time_utc"), "event.event_time_utc"),
        "source_system_id": _expect_str(event.get("source_system_id", ""), "event.source_system_id", allow_empty=True),
        "source_event_id": _expect_str(event.get("source_event_id", ""), "event.source_event_id", allow_empty=True),
        "actor_id": _expect_str(event.get("actor_id", ""), "event.actor_id", allow_empty=True),
        "location_id": _expect_str(event.get("location_id", ""), "event.location_id", allow_empty=True),
    }
    _parse_utc(out["event_time_utc"], "event.event_time_utc")
    for key in ("from_custodian", "to_custodian", "exception_id", "exception_note"):
        if key in event and event[key] is not None:
            out[key] = _expect_str(event[key], f"event.{key}", allow_empty=(key == "exception_note"))
    if "temperature_c" in event and event["temperature_c"] is not None:
        out["temperature_c"] = _num(event["temperature_c"], "event.temperature_c")
    return out


def _reason(code: str, event_id: str | None = None, detail: str | None = None) -> dict[str, str]:
    r = {"code": code}
    if event_id is not None:
        r["event_id"] = event_id
    if detail is not None:
        r["detail"] = detail
    return r


def compile_receipt(events: Iterable[Mapping[str, Any]], policy: Mapping[str, Any]) -> dict[str, Any]:
    normalized_policy = normalize_policy(policy)
    raw_events = list(events)
    if len(raw_events) > MAX_EVENTS:
        raise ContractError("too many events")
    normalized = [normalize_event(e) for e in raw_events]
    # Group by logical event ID, then by exact canonical payload. A conflict is
    # represented deterministically independent of arrival order. Exact replays
    # remain in the embedded event evidence so verification can reproduce counts.
    groups: dict[str, dict[bytes, tuple[dict[str, Any], int]]] = {}
    for event in normalized:
        encoded = canonical_json_bytes(event)
        variants = groups.setdefault(event["event_id"], {})
        prior = variants.get(encoded)
        variants[encoded] = (event, 1 if prior is None else prior[1] + 1)
    replay_count = 0
    conflicts: set[str] = set()
    unique: list[dict[str, Any]] = []
    for event_id in sorted(groups):
        variants = groups[event_id]
        if len(variants) > 1:
            conflicts.add(event_id)
        ordered_variants = sorted(variants.items(), key=lambda item: item[0])
        # Deterministic representative for downstream diagnostic reconstruction;
        # a changed-payload ID always forces HOLD regardless of representative.
        unique.append(ordered_variants[0][1][0])
        replay_count += sum(count - 1 for _, (_, count) in ordered_variants)
    unique.sort(key=lambda e: (e["event_time_utc"], e["event_id"], canonical_json_bytes(e)))
    normalized.sort(key=lambda e: (e["event_time_utc"], e["event_id"], canonical_json_bytes(e)))

    reasons: list[dict[str, str]] = []
    for event_id in sorted(conflicts):
        reasons.append(_reason("EVENT_ID_CHANGED_PAYLOAD", event_id))

    shipment_ids = sorted({e["shipment_id"] for e in unique})
    fingerprints = sorted({e["shipment_fingerprint_sha256"] for e in unique})
    if len(shipment_ids) != 1:
        reasons.append(_reason("SHIPMENT_ID_AMBIGUOUS", detail=str(shipment_ids)))
    if len(fingerprints) != 1:
        reasons.append(_reason("SHIPMENT_FINGERPRINT_AMBIGUOUS", detail=str(fingerprints)))

    current: str | None = None
    current_location: str | None = None
    open_exceptions: set[str] = set()
    last_temp: tuple[datetime, float, str] | None = None
    transition_count = 0
    allowed_sources = set(normalized_policy["allowed_source_system_ids"])
    allowed_locations = set(normalized_policy["allowed_location_ids"])
    temp_required = set(normalized_policy["require_temperature_on"])
    min_c = normalized_policy["temperature_min_c"]
    max_c = normalized_policy["temperature_max_c"]
    max_age = normalized_policy["max_temperature_age_seconds"]

    for event in unique:
        eid = event["event_id"]
        et = event["event_type"]
        when = _parse_utc(event["event_time_utc"], "event.event_time_utc")
        if not event["source_system_id"] or not event["source_event_id"]:
            reasons.append(_reason("MISSING_SOURCE_LINEAGE", eid))
        if allowed_sources and event["source_system_id"] not in allowed_sources:
            reasons.append(_reason("SOURCE_SYSTEM_NOT_ALLOWED", eid, event["source_system_id"]))
        if not event["actor_id"] or not event["location_id"]:
            reasons.append(_reason("MISSING_ACTOR_OR_LOCATION", eid))
        if allowed_locations and event["location_id"] not in allowed_locations:
            reasons.append(_reason("LOCATION_NOT_ALLOWED", eid, event["location_id"]))

        if "temperature_c" in event:
            temp = event["temperature_c"]
            last_temp = (when, temp, eid)
            if not (min_c <= temp <= max_c):
                reasons.append(_reason("TEMPERATURE_OUT_OF_RANGE", eid, f"{temp:g}"))

        if et in temp_required:
            if "temperature_c" in event:
                evidence_when, evidence_temp, evidence_id = when, event["temperature_c"], eid
            elif last_temp is not None:
                evidence_when, evidence_temp, evidence_id = last_temp
            else:
                evidence_when = evidence_temp = evidence_id = None
            if evidence_when is None:
                reasons.append(_reason("MISSING_TEMPERATURE_EVIDENCE", eid))
            else:
                age = int((when - evidence_when).total_seconds())
                if age < 0 or age > max_age:
                    reasons.append(_reason("STALE_TEMPERATURE_EVIDENCE", eid, str(age)))
                if not (min_c <= float(evidence_temp) <= max_c):
                    # The evidence event itself already carries a range reason; bind the handoff too.
                    reasons.append(_reason("HANDOFF_TEMPERATURE_NOT_ACCEPTABLE", eid, str(evidence_id)))

        if et == "ORIGIN_ACCEPT":
            to_c = event.get("to_custodian")
            if current is not None or not to_c or event.get("from_custodian"):
                reasons.append(_reason("INVALID_ORIGIN_TRANSITION", eid))
            else:
                current = to_c
                transition_count += 1
        elif et == "HANDOFF":
            from_c = event.get("from_custodian")
            to_c = event.get("to_custodian")
            if current is None or not from_c or not to_c or from_c != current or from_c == to_c:
                reasons.append(_reason("CUSTODY_TRANSITION_MISMATCH", eid, f"expected_from={current}"))
            else:
                current = to_c
                transition_count += 1
        elif et == "DELIVERY_ACCEPT":
            from_c = event.get("from_custodian")
            to_c = event.get("to_custodian")
            if current is None or not from_c or not to_c or from_c != current:
                reasons.append(_reason("DELIVERY_TRANSITION_MISMATCH", eid, f"expected_from={current}"))
            else:
                current = to_c
                transition_count += 1
        elif et == "EXCEPTION_OPEN":
            ex = event.get("exception_id")
            if not ex or ex in open_exceptions:
                reasons.append(_reason("INVALID_EXCEPTION_OPEN", eid))
            else:
                open_exceptions.add(ex)
        elif et == "EXCEPTION_RESOLVE":
            ex = event.get("exception_id")
            if not ex or ex not in open_exceptions:
                reasons.append(_reason("INVALID_EXCEPTION_RESOLUTION", eid))
            else:
                open_exceptions.remove(ex)

        if event["location_id"]:
            current_location = event["location_id"]

    for ex in sorted(open_exceptions):
        reasons.append(_reason("UNRESOLVED_EXCEPTION", detail=ex))
    if not unique:
        reasons.append(_reason("NO_EVENTS"))
    elif transition_count == 0:
        reasons.append(_reason("NO_CUSTODY_TRANSITION"))

    # Canonical dedupe of identical reasons keeps replay behavior byte-stable.
    reason_map = {canonical_json_bytes(r): r for r in reasons}
    reasons = [reason_map[k] for k in sorted(reason_map)]
    state = "PASS_EVIDENCE" if not reasons else "HOLD"
    shipment_id = shipment_ids[0] if len(shipment_ids) == 1 else None
    shipment_fp = fingerprints[0] if len(fingerprints) == 1 else None
    evidence_commitment = sha256_hex(canonical_json_bytes({
        "policy": normalized_policy,
        "events": normalized,
        "state": state,
        "reasons": reasons,
        "current_custodian": current,
        "current_location": current_location,
        "open_exceptions": sorted(open_exceptions),
    }))
    body = {
        "kind": RECEIPT_KIND,
        "schema_version": 1,
        "authority": "EVIDENCE_COMPLETENESS_ONLY_NOT_RELEASE_COMPLIANCE_ROUTING_OR_BUYER_ACCEPTANCE",
        "shipment_id": shipment_id,
        "shipment_fingerprint_sha256": shipment_fp,
        "state": state,
        "reasons": reasons,
        "current_custodian": current,
        "current_location": current_location,
        "open_exceptions": sorted(open_exceptions),
        "unique_event_count": len(groups),
        "exact_replay_count": replay_count,
        "conflicting_event_ids": sorted(conflicts),
        "policy": normalized_policy,
        "events": normalized,
        "evidence_sha256": evidence_commitment,
    }
    return {"body": body, "receipt_sha256": sha256_hex(canonical_json_bytes(body))}


def verify_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    obj = dict(_expect_obj(receipt, "receipt"))
    if set(obj) != {"body", "receipt_sha256"}:
        raise ContractError("receipt top-level fields invalid")
    digest = _expect_sha(obj["receipt_sha256"], "receipt.receipt_sha256")
    body = _expect_obj(obj["body"], "receipt.body")
    if body.get("kind") != RECEIPT_KIND:
        raise ContractError("receipt kind invalid")
    if sha256_hex(canonical_json_bytes(body)) != digest:
        raise ContractError("receipt SHA-256 mismatch")
    if not isinstance(body.get("events"), list) or not isinstance(body.get("policy"), dict):
        raise ContractError("receipt embedded evidence invalid")
    rebuilt = compile_receipt(body["events"], body["policy"])
    # Recompile the embedded canonical event evidence; replay and conflict metadata must reproduce exactly.
    rebuilt_body = rebuilt["body"]
    if set(body) != set(rebuilt_body):
        raise ContractError("receipt body fields invalid")
    for field in (
        "kind", "schema_version", "authority", "shipment_id", "shipment_fingerprint_sha256",
        "state", "reasons", "current_custodian", "current_location", "open_exceptions",
        "unique_event_count", "exact_replay_count", "conflicting_event_ids", "policy", "events", "evidence_sha256",
    ):
        if rebuilt_body.get(field) != body.get(field):
            raise ContractError(f"receipt semantic verification failed: {field}")
    return obj


def read_json_regular(path: str | os.PathLike[str]) -> Any:
    p = Path(path)
    st = os.lstat(p)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise ContractError("input must be a regular non-symlink file")
    if st.st_size > MAX_INPUT_BYTES:
        raise ContractError("input exceeds size limit")
    return loads_strict(p.read_text(encoding="utf-8"))


def write_json_exclusive(path: str | os.PathLike[str], value: Any) -> None:
    p = Path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(p, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as fh:
            fh.write(canonical_json_bytes(value))
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        os.close(fd)
