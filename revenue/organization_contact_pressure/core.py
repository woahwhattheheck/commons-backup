"""Strict schemas, cryptographic primitives, and shared types."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

REQUEST_SCHEMA = "organization-contact-pressure-request/v1"
AUTHORITY_SCHEMA = "organization-contact-pressure-authority/v1"
LEDGER_SCHEMA = "organization-contact-pressure-ledger/v1"
LEDGER_HEAD_SCHEMA = "organization-contact-pressure-ledger-head/v1"
RECEIPT_SCHEMA = "organization-contact-pressure-receipt/v1"
KEY_POINTER_SCHEMA = "organization-contact-pressure-key-pointer/v1"

READY = "READY_FOR_SINGLE_WRITER_REVIEW"
HOLD_ORG_ACTIVE = "HOLD_ORG_ACTIVE"
HOLD_RECENT_CONTACT = "HOLD_RECENT_CONTACT"
HOLD_HUMAN_REPLY = "HOLD_HUMAN_REPLY"
HOLD_DNR = "HOLD_DNR"
HOLD_AUTHORITY = "HOLD_AUTHORITY"
HOLD_CONFLICT = "HOLD_CONFLICT"

DECISIONS = {
    READY,
    HOLD_ORG_ACTIVE,
    HOLD_RECENT_CONTACT,
    HOLD_HUMAN_REPLY,
    HOLD_DNR,
    HOLD_AUTHORITY,
    HOLD_CONFLICT,
}

EVENT_PROPOSED = "PROPOSED"
EVENT_SENT = "SENT"
EVENT_HUMAN_REPLY = "HUMAN_REPLY"
EVENT_AUTO_REPLY = "AUTO_REPLY"
EVENT_HARD_BOUNCE = "HARD_BOUNCE"
EVENT_UNSUBSCRIBE = "UNSUBSCRIBE"
EVENT_DNR = "DNR"
EVENT_OWNER_RELEASE = "OWNER_RELEASE"

EVENT_KINDS = {
    EVENT_PROPOSED,
    EVENT_SENT,
    EVENT_HUMAN_REPLY,
    EVENT_AUTO_REPLY,
    EVENT_HARD_BOUNCE,
    EVENT_UNSUBSCRIBE,
    EVENT_DNR,
    EVENT_OWNER_RELEASE,
}
RELEASABLE_KINDS = {
    EVENT_PROPOSED,
    EVENT_SENT,
    EVENT_HUMAN_REPLY,
    EVENT_AUTO_REPLY,
}

MAX_JSON_BYTES = 2_000_000
MAX_EVENTS = 20_000
MAX_LEDGER_HEAD_FILES = 40_000
MAX_ROUTES = 1_024
MAX_TEXT = 256
MAX_SAFE_INTEGER = (1 << 53) - 1

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class GateError(Exception):
    """Base error."""


class InputError(GateError):
    """Untrusted request or JSON is malformed."""


class AuthorityUnavailable(GateError):
    """The retained verifier boundary cannot be read safely."""


class VerificationError(GateError):
    """A receipt is malformed, forged, stale, or no longer current."""


@dataclass(frozen=True)
class ActiveKey:
    key_id: str
    verifier_id: str
    key: bytes


@dataclass(frozen=True)
class AuthorityView:
    organization_scope_sha256: str
    route_scope_sha256s: tuple[str, ...]
    policy_generation: int
    contact_cooldown_seconds: int
    request_max_age_seconds: int
    ledger_max_age_seconds: int
    ready_validity_seconds: int
    max_future_skew_seconds: int
    issued_at: datetime
    valid_until: datetime
    key_id: str
    verifier_id: str
    digest: str


@dataclass(frozen=True)
class EventView:
    event_id: str
    organization_scope_sha256: str
    route_scope_sha256: str
    kind: str
    observed_at: datetime
    source_ref_sha256: str
    provider_evidence_sha256: str
    target_event_id: Optional[str]
    canonical: bytes


@dataclass(frozen=True)
class LedgerView:
    organization_scope_sha256: str
    generation: int
    policy_generation: int
    updated_at: datetime
    events: tuple[EventView, ...]
    conflicts: tuple[str, ...]
    key_id: str
    verifier_id: str
    digest: str
    state_digest: str


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac_hex(key: bytes, value: Mapping[str, Any]) -> str:
    return hmac.new(key, _canonical_bytes(value), hashlib.sha256).hexdigest()


def _reject_duplicate_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise InputError(f"non-finite JSON number: {value}")


def strict_json_loads(data: bytes) -> Any:
    if not isinstance(data, bytes):
        raise TypeError("strict_json_loads requires bytes")
    if len(data) > MAX_JSON_BYTES:
        raise InputError("JSON exceeds size limit")
    if data.startswith(b"\xef\xbb\xbf"):
        raise InputError("UTF-8 BOM is not accepted")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputError("JSON must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except InputError:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise InputError("invalid JSON") from exc


def _expect_object(value: Any, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise InputError(f"{name} must be an object")
    return value


def _expect_exact_fields(value: Mapping[str, Any], fields: set[str], name: str) -> None:
    actual = set(value)
    if actual != fields:
        missing = sorted(fields - actual)
        extra = sorted(actual - fields)
        raise InputError(f"{name} fields mismatch; missing={missing}, extra={extra}")


def _expect_string(value: Any, name: str, *, maximum: int = MAX_TEXT) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise InputError(f"{name} must be a non-empty bounded string")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise InputError(f"{name} contains a control character")
    return value


def _expect_slug(value: Any, name: str) -> str:
    text = _expect_string(value, name, maximum=128)
    if not _SLUG_RE.fullmatch(text):
        raise InputError(f"{name} is not a canonical slug")
    return text


def _expect_key_id(value: Any, name: str = "key_id") -> str:
    text = _expect_string(value, name, maximum=64)
    if not _KEY_ID_RE.fullmatch(text):
        raise InputError(f"{name} is invalid")
    return text


def _expect_hex64(value: Any, name: str) -> str:
    if type(value) is not str or not _HEX64_RE.fullmatch(value):
        raise InputError(f"{name} must be lowercase SHA-256 hex")
    return value


def _expect_int(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or value < minimum or value > maximum:
        raise InputError(f"{name} must be an exact integer in [{minimum}, {maximum}]")
    return value


def _parse_time(value: Any, name: str) -> datetime:
    text = _expect_string(value, name, maximum=20)
    if not _RFC3339_RE.fullmatch(text):
        raise InputError(f"{name} must be strict UTC RFC3339 seconds (...Z)")
    try:
        result = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise InputError(f"{name} is not a real timestamp") from exc
    return result


def _format_time(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timezone-aware datetime required")
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
