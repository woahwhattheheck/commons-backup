#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping

POLICY_SCHEMA = "hotel-room-turn-policy/v1"
EVIDENCE_SCHEMA = "hotel-room-turn-evidence/v1"
REPORT_SCHEMA = "hotel-room-turn-report/v2"
PILOT_ID = "hotel-room-turn-evidence-pilot"
PRICE_USD = 2500
DURATION_DAYS = 7
KINDS = ("housekeeping", "maintenance", "manager_release")
STATES = ("CLEAR", "BLOCK")
MAX_INPUT_BYTES = 2 * 1024 * 1024
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MACHINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-]{0,127}$")

# Production policy identity is verifier-owned. The CLI exposes no policy path,
# root, manager, room, turn, or freshness override.
RETAINED_POLICY_PATH = Path(__file__).parent / "fixtures" / "policy.json"
RETAINED_POLICY_SHA256 = "a09f5c8ddb99a4531f1b1770c64737e8780aa1a2d491acbf206d9cd5f1d1472e"

AUTHORITY = {
    "pms_write": False,
    "guest_data_access": False,
    "dispatch_housekeeping": False,
    "dispatch_maintenance": False,
    "charge_guest": False,
    "recognize_revenue": False,
}


class ContractError(ValueError):
    """Input or authority contract violation."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(raw: bytes | str) -> Any:
    if isinstance(raw, bytes):
        if not raw or len(raw) > MAX_INPUT_BYTES:
            raise ContractError(f"input must be 1..{MAX_INPUT_BYTES} bytes")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ContractError("input must be UTF-8") from exc
    elif isinstance(raw, str):
        if not raw or len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ContractError(f"input must be 1..{MAX_INPUT_BYTES} bytes")
        text = raw
    else:
        raise ContractError("input must be bytes or text")
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ContractError(f"non-finite JSON token: {token}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {exc.msg}") from exc


def canon(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("value is not canonical JSON") from exc


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _exact_keys(obj: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(obj)
    if actual != expected:
        raise ContractError(
            f"{where} keys mismatch "
            f"missing={sorted(expected - actual)} unknown={sorted(actual - expected)}"
        )


def _obj(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError(f"{where} must be object")
    return value


def _arr(value: Any, where: str) -> list[Any]:
    if type(value) is not list:
        raise ContractError(f"{where} must be array")
    return value


def _text(value: Any, where: str, *, max_len: int = 256) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise ContractError(f"{where} must be non-empty string <= {max_len}")
    if any(ord(ch) < 0x20 or ch == "\x7f" for ch in value):
        raise ContractError(f"{where} contains control characters")
    return value


def _machine(value: Any, where: str) -> str:
    text = _text(value, where, max_len=128)
    if _MACHINE.fullmatch(text) is None:
        raise ContractError(f"{where} must be machine token")
    return text


def _int(value: Any, where: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ContractError(f"{where} must be integer in [{low},{high}]")
    return value


def _hex64(value: Any, where: str) -> str:
    text = _text(value, where, max_len=64)
    if _HEX64.fullmatch(text) is None:
        raise ContractError(f"{where} must be 64 lowercase hex")
    return text


def _time(value: Any, where: str) -> dt.datetime:
    text = _text(value, where, max_len=64)
    raw = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ContractError(f"{where} must be RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{where} must include timezone")
    return parsed.astimezone(dt.timezone.utc)


def _fmt_time(value: dt.datetime) -> str:
    return (
        value.astimezone(dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _read_regular(path: str | os.PathLike[str]) -> bytes:
    """Read one regular file through one descriptor; reject symlink final components."""
    raw_path = os.fspath(path)
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(raw_path, flags)
    except OSError as exc:
        raise ContractError(f"cannot open regular input: {raw_path}: {exc.strerror}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ContractError(f"input is not a regular file: {raw_path}")
        if before.st_size < 1 or before.st_size > MAX_INPUT_BYTES:
            raise ContractError(
                f"input size must be 1..{MAX_INPUT_BYTES} bytes: {raw_path}"
            )
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            part = os.read(fd, min(remaining, 128 * 1024))
            if not part:
                raise ContractError(f"input shortened during read: {raw_path}")
            chunks.append(part)
            remaining -= len(part)
        if os.read(fd, 1):
            raise ContractError(f"input grew during read: {raw_path}")
        after = os.fstat(fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
        ):
            raise ContractError(f"input changed during read: {raw_path}")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _write_exclusive(path: str | os.PathLike[str], data: bytes) -> None:
    if not data:
        raise ContractError("refusing empty output")
    raw_path = os.fspath(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    created = False
    try:
        fd = os.open(raw_path, flags, 0o600)
        created = True
    except OSError as exc:
        raise ContractError(f"cannot create exclusive output: {raw_path}: {exc.strerror}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ContractError(f"output is not a regular file: {raw_path}")
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise ContractError(f"short output write: {raw_path}")
            view = view[written:]
        os.fsync(fd)
    except Exception:
        os.close(fd)
        if created:
            try:
                os.unlink(raw_path)
            except OSError:
                pass
        raise
    else:
        os.close(fd)


def parse_policy(raw: Any, expected_sha256: str) -> dict[str, Any]:
    """Internal/test API. Production obtains both bytes and root from retained authority."""
    expected_sha256 = _hex64(expected_sha256, "expected_policy_sha256")
    obj = _obj(raw, "policy")
    if not hmac.compare_digest(sha256_bytes(canon(obj)), expected_sha256):
        raise ContractError("policy sha256 mismatch")
    _exact_keys(
        obj,
        {
            "schema_version",
            "pilot_id",
            "property_id",
            "price_usd",
            "duration_days",
            "max_age_minutes",
            "allowed_managers",
            "rooms",
        },
        "policy",
    )
    if obj["schema_version"] != POLICY_SCHEMA:
        raise ContractError("policy.schema_version drift")
    if obj["pilot_id"] != PILOT_ID:
        raise ContractError("policy.pilot_id drift")
    if _int(obj["price_usd"], "policy.price_usd", 0, 1_000_000) != PRICE_USD:
        raise ContractError("policy.price_usd drift")
    if _int(obj["duration_days"], "policy.duration_days", 1, 30) != DURATION_DAYS:
        raise ContractError("policy.duration_days drift")
    property_id = _machine(obj["property_id"], "policy.property_id")

    ages = _obj(obj["max_age_minutes"], "policy.max_age_minutes")
    _exact_keys(ages, set(KINDS), "policy.max_age_minutes")
    max_age_minutes = {
        kind: _int(ages[kind], f"policy.max_age_minutes.{kind}", 1, 1440)
        for kind in KINDS
    }

    managers_raw = _arr(obj["allowed_managers"], "policy.allowed_managers")
    if not managers_raw:
        raise ContractError("policy.allowed_managers must not be empty")
    managers = sorted(
        _machine(item, "policy.allowed_managers[]") for item in managers_raw
    )
    if len(managers) != len(set(managers)):
        raise ContractError("policy.allowed_managers must be unique")

    rooms_raw = _arr(obj["rooms"], "policy.rooms")
    if not rooms_raw:
        raise ContractError("policy.rooms must not be empty")
    rooms: list[dict[str, str]] = []
    seen_rooms: set[str] = set()
    seen_turns: set[str] = set()
    for idx, item in enumerate(rooms_raw):
        room = _obj(item, f"policy.rooms[{idx}]")
        _exact_keys(room, {"room_id", "turn_id"}, f"policy.rooms[{idx}]")
        room_id = _machine(room["room_id"], f"policy.rooms[{idx}].room_id")
        turn_id = _machine(room["turn_id"], f"policy.rooms[{idx}].turn_id")
        if room_id in seen_rooms:
            raise ContractError(f"duplicate room_id: {room_id}")
        if turn_id in seen_turns:
            raise ContractError(f"duplicate turn_id: {turn_id}")
        seen_rooms.add(room_id)
        seen_turns.add(turn_id)
        rooms.append({"room_id": room_id, "turn_id": turn_id})
    rooms.sort(key=lambda item: item["room_id"])

    return {
        "schema_version": POLICY_SCHEMA,
        "pilot_id": PILOT_ID,
        "property_id": property_id,
        "price_usd": PRICE_USD,
        "duration_days": DURATION_DAYS,
        "max_age_minutes": max_age_minutes,
        "allowed_managers": managers,
        "rooms": rooms,
        "policy_sha256": expected_sha256,
    }


def load_retained_policy() -> tuple[dict[str, Any], dict[str, Any]]:
    raw = loads_strict(_read_regular(RETAINED_POLICY_PATH))
    parsed = parse_policy(raw, RETAINED_POLICY_SHA256)
    return raw, parsed


def _parse_event(raw: Any, idx: int) -> dict[str, Any]:
    where = f"evidence.events[{idx}]"
    obj = _obj(raw, where)
    _exact_keys(
        obj,
        {
            "event_id",
            "room_id",
            "turn_id",
            "kind",
            "observed_at",
            "state",
            "actor_id",
            "detail_code",
            "source_ref_sha256",
        },
        where,
    )
    kind = _machine(obj["kind"], f"{where}.kind")
    if kind not in KINDS:
        raise ContractError(f"{where}.kind unknown: {kind}")
    state = _text(obj["state"], f"{where}.state", max_len=16)
    if state not in STATES:
        raise ContractError(f"{where}.state unknown: {state}")
    observed = _time(obj["observed_at"], f"{where}.observed_at")
    return {
        "event_id": _machine(obj["event_id"], f"{where}.event_id"),
        "room_id": _machine(obj["room_id"], f"{where}.room_id"),
        "turn_id": _machine(obj["turn_id"], f"{where}.turn_id"),
        "kind": kind,
        "observed_at": _fmt_time(observed),
        "state": state,
        "actor_id": _machine(obj["actor_id"], f"{where}.actor_id"),
        "detail_code": _machine(obj["detail_code"], f"{where}.detail_code"),
        "source_ref_sha256": _hex64(
            obj["source_ref_sha256"], f"{where}.source_ref_sha256"
        ),
    }


def parse_evidence(
    raw: Any, policy: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    obj = _obj(raw, "evidence")
    _exact_keys(
        obj,
        {"schema_version", "pilot_id", "property_id", "events"},
        "evidence",
    )
    if obj["schema_version"] != EVIDENCE_SCHEMA:
        raise ContractError("evidence.schema_version drift")
    if obj["pilot_id"] != PILOT_ID:
        raise ContractError("evidence.pilot_id drift")
    if obj["property_id"] != policy["property_id"]:
        raise ContractError("evidence.property_id mismatch")
    events_raw = _arr(obj["events"], "evidence.events")
    dedup: dict[str, dict[str, Any]] = {}
    for idx, item in enumerate(events_raw):
        event = _parse_event(item, idx)
        prior = dedup.get(event["event_id"])
        if prior is None:
            dedup[event["event_id"]] = event
        elif prior != event:
            raise ContractError(
                f"event_id replay content mismatch: {event['event_id']}"
            )
    events = sorted(
        dedup.values(),
        key=lambda event: (
            event["room_id"],
            event["turn_id"],
            event["kind"],
            event["observed_at"],
            event["event_id"],
        ),
    )
    normalized = {
        "schema_version": EVIDENCE_SCHEMA,
        "pilot_id": PILOT_ID,
        "property_id": policy["property_id"],
        "events": events,
    }
    return events, normalized, sha256_bytes(canon(normalized))
