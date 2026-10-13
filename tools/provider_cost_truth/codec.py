"""Strict JSON, scalar validation, and canonical digest helpers."""

from __future__ import annotations

from datetime import datetime as _DateTime, timezone as _Timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

SNAPSHOT_SCHEMA = "provider-cost-snapshot/v1"
REQUEST_SCHEMA = "provider-cost-request/v1"
RECEIPT_SCHEMA = "provider-cost-receipt/v1"
IMPLEMENTATION_CONTRACT = "provider-cost-truth/v1"

SCOPES = ("ACCOUNT", "PRODUCT", "MODEL", "SESSION")
KINDS = ("ZERO_COST_CONFIRMED", "CHARGE_PAID", "CHARGE_FAILED", "PRICE_QUOTE")
AUTHORITIES = ("PROVIDER_AUTHENTICATED", "OWNER_ASSERTION", "MARKETING_MATERIAL")
STATES = (
    "ZERO_COST_VERIFIED",
    "BILLABLE_VERIFIED",
    "FREE_UNPROVEN_ACCOUNT_BILLING_PRESENT",
    "COST_UNKNOWN",
    "CONTRADICTORY",
)
MAX_EVIDENCE_AGE_SECONDS = 7 * 24 * 60 * 60
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class GateError(ValueError):
    """Raised when an input is malformed or violates the bounded contract."""


def _reject_constant(value: str) -> None:
    raise GateError(f"non-finite JSON number is forbidden: {value}")


def _require_unicode_scalar_text(value: str, where: str) -> None:
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise GateError(f"{where} contains invalid Unicode scalar") from exc


def _pairs_no_duplicates(
    pairs: Iterable[tuple[str, Any]],
    _scalar=_require_unicode_scalar_text,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        _scalar(key, "JSON object key")
        if key in out:
            raise GateError("duplicate JSON key")
        out[key] = value
    return out


def loads_strict_json(
    data: str | bytes,
    _loads=json.loads,
    _pairs=_pairs_no_duplicates,
    _constant=_reject_constant,
) -> Any:
    """Parse strict UTF-8 JSON, rejecting duplicate keys and non-finite numbers."""
    if isinstance(data, bytes):
        try:
            data = data.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise GateError("input is not strict UTF-8") from exc
    if not isinstance(data, str):
        raise GateError("JSON input must be str or bytes")
    try:
        return _loads(
            data,
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except GateError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise GateError(f"invalid JSON: {exc}") from exc


def _canonical_bytes(value: Any, _dumps=json.dumps) -> bytes:
    try:
        text = _dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return text.encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise GateError("value cannot be canonicalized as strict UTF-8 JSON") from exc


def _sha256_value(
    value: Any,
    _canonical=_canonical_bytes,
    _sha256=hashlib.sha256,
) -> str:
    return _sha256(_canonical(value)).hexdigest()


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise GateError(f"{where} keys mismatch: missing={missing} extra={extra}")


def _require_text(
    value: Any,
    where: str,
    *,
    nullable: bool = False,
    _scalar=_require_unicode_scalar_text,
) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value or value != value.strip():
        raise GateError(f"{where} must be a non-empty trimmed string")
    _scalar(value, where)
    if "\x00" in value:
        raise GateError(f"{where} contains NUL")
    return value


def _require_bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise GateError(f"{where} must be a JSON boolean")
    return value


def _require_minor(value: Any, where: str) -> int:
    if type(value) is not int or value < 0:
        raise GateError(f"{where} must be a non-negative integer minor-unit amount")
    return value


def _parse_ts(
    value: Any,
    where: str,
    _text=_require_text,
    _datetime=_DateTime,
    _utc=_Timezone.utc,
) -> _DateTime:
    text = _text(value, where)
    assert text is not None
    try:
        return _datetime.strptime(text, _TS_FORMAT).replace(tzinfo=_utc)
    except ValueError as exc:
        raise GateError(f"{where} must be canonical UTC YYYY-MM-DDTHH:MM:SSZ") from exc


def _format_ts(value: _DateTime, _utc=_Timezone.utc) -> str:
    if value.tzinfo is None:
        raise GateError("internal timestamp is timezone-naive")
    return value.astimezone(_utc).replace(microsecond=0).strftime(_TS_FORMAT)
