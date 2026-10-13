#!/usr/bin/env python3
"""Evidence-bound pilot delivery -> renewal/expansion review gate."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from datetime import datetime, timezone
from typing import Any

SCHEMA = "pilot-renewal-expansion/v1"
RECEIPT_SCHEMA = "pilot-renewal-expansion-receipt/v1"
TRUTH_CEILING = "PROPOSED_NOT_ACCEPTED"
TERMINAL_STATES = {"READY_FOR_RENEWAL_REVIEW", "HOLD_ACCEPTANCE", "HOLD_PAYMENT", "HOLD_WINDOW", "HOLD_EVIDENCE", "DNR"}
AUTHORITY = MappingProxyType({
    "external_send_authorized": False,
    "contract_or_signature_authorized": False,
    "buyer_acceptance_established": False,
    "renewal_or_expansion_approved": False,
    "invoice_or_payment_authorized": False,
    "cash_or_revenue_recognized": False,
    "deployment_authorized": False,
    "scheduling_authorized": False,
    "crm_mutation_authorized": False,
})
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_INPUT_BYTES = 1_000_000
MAX_JSON_INT_DIGITS = 19
ALLOWED_EVIDENCE_KINDS = {"BASELINE_ACCEPTANCE", "CHANGE_ORDER_APPROVAL", "MILESTONE_ACCEPTANCE", "PAYMENT_SETTLED", "SUPPORT_FINDING", "GAP_STATUS", "RENEWAL_WINDOW", "DNR"}
ALLOWED_EVIDENCE_STATUS = {"VERIFIED", "MISSING", "CONFLICTING", "PROVIDED_UNVERIFIED"}

class GateError(ValueError):
    pass


def _validate_scalar_text(value: str, where: str) -> None:
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise GateError(f"{where}: Unicode surrogate prohibited")


def ensure_unicode_scalars(value: Any, where: str = "root") -> None:
    if isinstance(value, str):
        _validate_scalar_text(value, where)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            ensure_unicode_scalars(item, f"{where}[{i}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise GateError(f"{where}: string object key required")
            _validate_scalar_text(key, f"{where}.<key>")
            ensure_unicode_scalars(item, f"{where}.{key}")


def canonical_json(value: Any) -> bytes:
    ensure_unicode_scalars(value)
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    except (UnicodeEncodeError, ValueError, RecursionError) as exc:
        raise GateError("value is not canonically serializable") from exc


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_constant(value: str) -> None:
    raise GateError(f"non-finite JSON number prohibited: {value}")


def _parse_int_token(token: str) -> int:
    digits = token[1:] if token.startswith("-") else token
    if len(digits) > MAX_JSON_INT_DIGITS:
        raise GateError("JSON integer exceeds digit limit")
    try:
        return int(token, 10)
    except ValueError as exc:
        raise GateError("invalid JSON integer") from exc


def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise GateError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_loads(data: bytes) -> Any:
    if type(data) is not bytes:
        raise GateError("input must be exact bytes")
    if len(data) > MAX_INPUT_BYTES:
        raise GateError("input exceeds size limit")
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise GateError("input must be UTF-8") from exc
    try:
        value = json.loads(text, object_pairs_hook=_pairs_no_dupes, parse_constant=_reject_constant, parse_int=_parse_int_token)
    except GateError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError, UnicodeError) as exc:
        raise GateError("invalid JSON") from exc
    ensure_unicode_scalars(value)
    return value


def _stat_generation(st: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (st.st_dev, st.st_ino, stat.S_IFMT(st.st_mode), st.st_nlink, st.st_size, getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)), getattr(st, "st_ctime_ns", int(st.st_ctime * 1_000_000_000)))


def _read_regular(path: Path) -> bytes:
    try:
        pre = path.lstat()
    except OSError as exc:
        raise GateError(f"{path}: unable to inspect input") from exc
    if stat.S_ISLNK(pre.st_mode) or not stat.S_ISREG(pre.st_mode) or pre.st_nlink != 1:
        raise GateError(f"{path}: single-link regular non-symlink file required")
    if pre.st_size > MAX_INPUT_BYTES:
        raise GateError(f"{path}: file too large")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise GateError(f"{path}: unable to open regular input") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or _stat_generation(pre) != _stat_generation(before):
            raise GateError(f"{path}: input generation changed before read")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, MAX_INPUT_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                raise GateError(f"{path}: file too large")
        after = os.fstat(fd)
        try:
            post = path.lstat()
        except OSError as exc:
            raise GateError(f"{path}: input pathname changed during read") from exc
        if _stat_generation(before) != _stat_generation(after) or _stat_generation(after) != _stat_generation(post):
            raise GateError(f"{path}: input generation changed during read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _dt(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise GateError(f"{field}: non-empty timestamp required")
    raw = value.strip()
    _validate_scalar_text(raw, field)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise GateError(f"{field}: invalid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise GateError(f"{field}: timezone required")
    return parsed.astimezone(timezone.utc)


def _z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _exact_keys(obj: dict[str, Any], allowed: set[str], where: str, required: set[str] | None = None) -> None:
    extra = set(obj) - allowed
    if extra:
        raise GateError(f"{where}: unknown field(s): {', '.join(sorted(extra))}")
    missing = (required or set()) - set(obj)
    if missing:
        raise GateError(f"{where}: missing field(s): {', '.join(sorted(missing))}")


def _obj(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError(f"{where}: object required")
    return value


def _list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise GateError(f"{where}: list required")
    return value


def _str(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GateError(f"{where}: non-empty string required")
    value = value.strip()
    _validate_scalar_text(value, where)
    return value


def _id(value: Any, where: str) -> str:
    value = _str(value, where)
    if not ID_RE.fullmatch(value):
        raise GateError(f"{where}: invalid identifier")
    return value


def _sha(value: Any, where: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise GateError(f"{where}: lowercase SHA-256 required")
    return value


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise GateError(f"{where}: boolean required")
    return value


def _int(value: Any, where: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise GateError(f"{where}: integer >= {minimum} required")
    return value


def _unique(values: list[str], where: str) -> None:
    if len(values) != len(set(values)):
        raise GateError(f"{where}: duplicate identifier")


def _parse_source(raw: Any, where: str) -> dict[str, Any]:
    obj = _obj(raw, where)
    allowed = {"id", "locator", "sha256", "observed_at"}
    _exact_keys(obj, allowed, where, allowed)
    source_id = _id(obj["id"], f"{where}.id")
    locator = _str(obj["locator"], f"{where}.locator")
    if not (locator.startswith("https://") or locator.startswith("repo://")):
        raise GateError(f"{where}.locator: https:// or repo:// required")
    if any(ch.isspace() for ch in locator):
        raise GateError(f"{where}.locator: whitespace prohibited")
    return {"id": source_id, "locator": locator, "sha256": _sha(obj["sha256"], f"{where}.sha256"), "observed_at": _z(_dt(obj["observed_at"], f"{where}.observed_at"))}
