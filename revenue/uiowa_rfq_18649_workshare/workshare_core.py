#!/usr/bin/env python3
"""Strict JSON, canonical encoding, scalar validation, and verifier-owned UTC."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from typing import Any

from workshare_constants import ContractError, _CONTROL_RE, _ID_RE, _SHA_RE, _UTC_RE

def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
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


def canonical_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ContractError(f"value is not canonical JSON: {exc}") from exc
    return (encoded + "\n").encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_value(value: Any) -> str:
    return _sha256_bytes(canonical_json_bytes(value))


def _require_exact_keys(value: Any, expected: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError(f"{where} must be object")
    actual = set(value)
    if actual != expected:
        raise ContractError(
            f"{where} keys mismatch: missing={sorted(expected - actual)} "
            f"unknown={sorted(actual - expected)}"
        )
    return value


def _require_str(
    value: Any,
    where: str,
    *,
    min_len: int = 1,
    max_len: int = 1024,
    controls: bool = False,
) -> str:
    if type(value) is not str:
        raise ContractError(f"{where} must be string")
    if not (min_len <= len(value) <= max_len):
        raise ContractError(f"{where} length must be {min_len}..{max_len}")
    if not controls and _CONTROL_RE.search(value):
        raise ContractError(f"{where} contains control characters")
    return value


def _require_id(value: Any, where: str) -> str:
    text = _require_str(value, where, max_len=96)
    if _ID_RE.fullmatch(text) is None:
        raise ContractError(f"{where} must be a bounded canonical identifier")
    return text


def _require_sha(value: Any, where: str) -> str:
    text = _require_str(value, where, min_len=64, max_len=64)
    if _SHA_RE.fullmatch(text) is None:
        raise ContractError(f"{where} must be 64 lowercase hex")
    return text


def _require_int(value: Any, where: str, *, low: int, high: int) -> int:
    if type(value) is not int:
        raise ContractError(f"{where} must be integer")
    if not low <= value <= high:
        raise ContractError(f"{where} must be in {low}..{high}")
    return value


def _parse_utc(value: Any, where: str) -> _dt.datetime:
    text = _require_str(value, where, min_len=20, max_len=20)
    if _UTC_RE.fullmatch(text) is None:
        raise ContractError(f"{where} must be whole-second UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = _dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    except ValueError as exc:
        raise ContractError(f"{where} is not a real UTC instant") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise ContractError(f"{where} is not canonical UTC")
    return parsed


def _format_utc(value: _dt.datetime) -> str:
    if value.tzinfo is None:
        raise ContractError("trusted time must be timezone-aware UTC")
    normalized = value.astimezone(_dt.timezone.utc).replace(microsecond=0)
    return normalized.strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_now() -> _dt.datetime:
    """Verifier-owned process UTC, isolated only so tests can freeze it."""

    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def _coerce_now(value: _dt.datetime | str | None, where: str = "trusted_now") -> _dt.datetime:
    if value is None:
        return _utc_now()
    if isinstance(value, str):
        return _parse_utc(value, where)
    if not isinstance(value, _dt.datetime) or value.tzinfo is None:
        raise ContractError(f"{where} must be timezone-aware datetime or canonical UTC string")
    return value.astimezone(_dt.timezone.utc).replace(microsecond=0)
