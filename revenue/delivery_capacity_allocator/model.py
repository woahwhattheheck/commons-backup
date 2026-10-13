from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

POLICY_SCHEMA = "tjlabs.delivery-capacity-policy/v1"
DEMAND_SCHEMA = "tjlabs.delivery-capacity-demand/v1"
RESERVATIONS_SCHEMA = "tjlabs.delivery-capacity-reservations/v1"
RECEIPT_SCHEMA = "tjlabs.delivery-capacity-allocation/v2"
MAX_INPUT_BYTES = 2_000_000
MAX_ROWS = 10_000
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class CapacityError(ValueError):
    pass


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CapacityError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(data: bytes) -> Any:
    if not isinstance(data, bytes):
        raise CapacityError("JSON input must be bytes")
    if len(data) > MAX_INPUT_BYTES:
        raise CapacityError("JSON input exceeds byte limit")
    try:
        text = data.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_dupes,
            parse_constant=lambda token: (_ for _ in ()).throw(CapacityError(f"non-finite JSON number: {token}")),
        )
    except CapacityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OverflowError) as exc:
        raise CapacityError(f"invalid JSON: {exc}") from exc


def _exact_keys(obj: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(obj)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise CapacityError(f"{label} keys mismatch missing={missing} extra={extra}")


def _require_dict(value: Any, label: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise CapacityError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise CapacityError(f"{label} must be an array")
    if len(value) > MAX_ROWS:
        raise CapacityError(f"{label} exceeds row limit")
    return value


def _require_str(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise CapacityError(f"{label} must be a non-empty string")
    return value


def _require_id(value: Any, label: str) -> str:
    value = _require_str(value, label)
    if not _ID.fullmatch(value):
        raise CapacityError(f"{label} has invalid identifier syntax")
    return value


def _require_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise CapacityError(f"{label} must be an integer >= {minimum}")
    return value


def _require_sha(value: Any, label: str) -> str:
    value = _require_str(value, label)
    if not _HEX64.fullmatch(value):
        raise CapacityError(f"{label} must be lowercase SHA-256 hex")
    return value


def _parse_utc(value: Any, label: str) -> datetime:
    text = _require_str(value, label)
    try:
        dt = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CapacityError(f"{label} must be canonical UTC seconds") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise CapacityError(f"{label} must be canonical UTC seconds")
    return dt


def _utc_text(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise CapacityError("trusted time must be timezone-aware")
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_policy(obj: Any) -> dict[str, Any]:
    obj = _require_dict(obj, "policy")
    _exact_keys(obj, {"schema", "policy_id", "generation", "snapshot_at", "max_age_seconds", "slots"}, "policy")
    if obj["schema"] != POLICY_SCHEMA:
        raise CapacityError("unsupported policy schema")
    policy_id = _require_id(obj["policy_id"], "policy.policy_id")
    generation = _require_int(obj["generation"], "policy.generation", minimum=1)
    snapshot_at = _utc_text(_parse_utc(obj["snapshot_at"], "policy.snapshot_at"))
    max_age_seconds = _require_int(obj["max_age_seconds"], "policy.max_age_seconds", minimum=1)
    slots_in = _require_list(obj["slots"], "policy.slots")
    slots: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, raw in enumerate(slots_in):
        row = _require_dict(raw, f"policy.slots[{i}]")
        _exact_keys(row, {"slot_id", "service_class", "starts_at", "ends_at", "capacity_units"}, f"policy.slots[{i}]")
        slot_id = _require_id(row["slot_id"], f"policy.slots[{i}].slot_id")
        if slot_id in seen:
            raise CapacityError(f"duplicate slot_id: {slot_id}")
        seen.add(slot_id)
        service_class = _require_id(row["service_class"], f"policy.slots[{i}].service_class")
        starts = _parse_utc(row["starts_at"], f"policy.slots[{i}].starts_at")
        ends = _parse_utc(row["ends_at"], f"policy.slots[{i}].ends_at")
        if not starts < ends:
            raise CapacityError(f"slot {slot_id} must end after it starts")
        units = _require_int(row["capacity_units"], f"policy.slots[{i}].capacity_units", minimum=1)
        slots.append({
            "slot_id": slot_id,
            "service_class": service_class,
            "starts_at": _utc_text(starts),
            "ends_at": _utc_text(ends),
            "capacity_units": units,
        })
    slots.sort(key=lambda r: r["slot_id"])
    return {
        "schema": POLICY_SCHEMA,
        "policy_id": policy_id,
        "generation": generation,
        "snapshot_at": snapshot_at,
        "max_age_seconds": max_age_seconds,
        "slots": slots,
    }


def _normalize_demands(obj: Any) -> dict[str, Any]:
    obj = _require_dict(obj, "demand")
    _exact_keys(obj, {"schema", "policy_id", "generation", "snapshot_at", "deals"}, "demand")
    if obj["schema"] != DEMAND_SCHEMA:
        raise CapacityError("unsupported demand schema")
    policy_id = _require_id(obj["policy_id"], "demand.policy_id")
    generation = _require_int(obj["generation"], "demand.generation", minimum=1)
    snapshot_at = _utc_text(_parse_utc(obj["snapshot_at"], "demand.snapshot_at"))
    rows = _require_list(obj["deals"], "demand.deals")
    deals: list[dict[str, Any]] = []
    seen: set[str] = set()
    allowed_stages = {"OFFER_READY", "BUYER_INTEREST", "BUYER_ACCEPTED", "FUNDED_TO_START", "FULFILLMENT_READY", "CLOSED_SETTLED", "DNR", "HOLD"}
    for i, raw in enumerate(rows):
        row = _require_dict(raw, f"demand.deals[{i}]")
        _exact_keys(row, {"deal_id", "buyer_id", "opportunity_id", "service_class", "requested_units", "stage", "accepted_at", "not_before", "deadline", "source_receipt_sha256"}, f"demand.deals[{i}]")
        deal_id = _require_id(row["deal_id"], f"demand.deals[{i}].deal_id")
        if deal_id in seen:
            raise CapacityError(f"duplicate deal_id: {deal_id}")
        seen.add(deal_id)
        stage = _require_str(row["stage"], f"demand.deals[{i}].stage")
        if stage not in allowed_stages:
            raise CapacityError(f"unsupported deal stage: {stage}")
        accepted_at_raw = row["accepted_at"]
        if accepted_at_raw is None:
            accepted_at = None
        else:
            accepted_at = _utc_text(_parse_utc(accepted_at_raw, f"demand.deals[{i}].accepted_at"))
        if stage in {"BUYER_ACCEPTED", "FUNDED_TO_START", "FULFILLMENT_READY", "CLOSED_SETTLED"} and accepted_at is None:
            raise CapacityError(f"deal {deal_id} stage {stage} requires accepted_at")
        not_before = _parse_utc(row["not_before"], f"demand.deals[{i}].not_before")
        deadline = _parse_utc(row["deadline"], f"demand.deals[{i}].deadline")
        if not not_before < deadline:
            raise CapacityError(f"deal {deal_id} deadline must follow not_before")
        deals.append({
            "deal_id": deal_id,
            "buyer_id": _require_id(row["buyer_id"], f"demand.deals[{i}].buyer_id"),
            "opportunity_id": _require_id(row["opportunity_id"], f"demand.deals[{i}].opportunity_id"),
            "service_class": _require_id(row["service_class"], f"demand.deals[{i}].service_class"),
            "requested_units": _require_int(row["requested_units"], f"demand.deals[{i}].requested_units", minimum=1),
            "stage": stage,
            "accepted_at": accepted_at,
            "not_before": _utc_text(not_before),
            "deadline": _utc_text(deadline),
            "source_receipt_sha256": _require_sha(row["source_receipt_sha256"], f"demand.deals[{i}].source_receipt_sha256"),
        })
    deals.sort(key=lambda r: r["deal_id"])
    return {"schema": DEMAND_SCHEMA, "policy_id": policy_id, "generation": generation, "snapshot_at": snapshot_at, "deals": deals}


def _normalize_reservations(obj: Any) -> dict[str, Any]:
    obj = _require_dict(obj, "reservations")
    _exact_keys(obj, {"schema", "policy_id", "generation", "snapshot_at", "reservations"}, "reservations")
    if obj["schema"] != RESERVATIONS_SCHEMA:
        raise CapacityError("unsupported reservations schema")
    policy_id = _require_id(obj["policy_id"], "reservations.policy_id")
    generation = _require_int(obj["generation"], "reservations.generation", minimum=1)
    snapshot_at = _utc_text(_parse_utc(obj["snapshot_at"], "reservations.snapshot_at"))
    rows = _require_list(obj["reservations"], "reservations.reservations")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, raw in enumerate(rows):
        row = _require_dict(raw, f"reservations.reservations[{i}]")
        _exact_keys(row, {"reservation_id", "deal_id", "buyer_id", "opportunity_id", "slot_id", "service_class", "units", "state", "source_receipt_sha256"}, f"reservations.reservations[{i}]")
        rid = _require_id(row["reservation_id"], f"reservations.reservations[{i}].reservation_id")
        if rid in seen:
            raise CapacityError(f"duplicate reservation_id: {rid}")
        seen.add(rid)
        state = _require_str(row["state"], f"reservations.reservations[{i}].state")
        if state not in {"ACTIVE", "RELEASED"}:
            raise CapacityError(f"unsupported reservation state: {state}")
        out.append({
            "reservation_id": rid,
            "deal_id": _require_id(row["deal_id"], f"reservations.reservations[{i}].deal_id"),
            "buyer_id": _require_id(row["buyer_id"], f"reservations.reservations[{i}].buyer_id"),
            "opportunity_id": _require_id(row["opportunity_id"], f"reservations.reservations[{i}].opportunity_id"),
            "slot_id": _require_id(row["slot_id"], f"reservations.reservations[{i}].slot_id"),
            "service_class": _require_id(row["service_class"], f"reservations.reservations[{i}].service_class"),
            "units": _require_int(row["units"], f"reservations.reservations[{i}].units", minimum=1),
            "state": state,
            "source_receipt_sha256": _require_sha(row["source_receipt_sha256"], f"reservations.reservations[{i}].source_receipt_sha256"),
        })
    out.sort(key=lambda r: r["reservation_id"])
    return {"schema": RESERVATIONS_SCHEMA, "policy_id": policy_id, "generation": generation, "snapshot_at": snapshot_at, "reservations": out}


def read_regular_file(path: str) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise CapacityError(f"cannot open input safely: {path}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not __import__("stat").S_ISREG(before.st_mode):
            raise CapacityError(f"input is not a regular file: {path}")
        if before.st_size > MAX_INPUT_BYTES:
            raise CapacityError(f"input exceeds byte limit: {path}")
        chunks: list[bytes] = []
        remaining = MAX_INPUT_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(131072, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_INPUT_BYTES:
            raise CapacityError(f"input exceeds byte limit: {path}")
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise CapacityError(f"input changed while reading: {path}")
        return data
    finally:
        os.close(fd)


def write_exclusive(path: str, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise CapacityError(f"cannot create output exclusively: {path}: {exc}") from exc
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise CapacityError("short output write")
            view = view[written:]
        os.fsync(fd)
    except Exception:
        # Preserve partial truth; do not unlink by pathname after namespace publication.
        raise
    finally:
        os.close(fd)
