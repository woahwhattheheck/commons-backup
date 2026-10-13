from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

SCHEMA_VERSION = 2
BRIDGE_KIND = "commercial_offer_to_scope_bridge"
VERIFICATION_KIND = "commercial_offer_scope_acceptance_verification"
VERIFICATION_DECISION = "VERIFIED_ACCEPTANCE"
VERIFICATION_ATTESTATION = "AUTHORIZED_OPERATOR_VERIFIED_EXACT_SCOPE_TERMS_ACCEPTANCE"
SCOPE_SCHEMA = "commons-scope-agreement/v1"
SCOPE_KIND = "SCOPE_AGREEMENT"
SCOPE_ACCEPTANCE_ATTESTATION = "AUTHORIZED_OPERATOR_VERIFIED_EXACT_TERMS_ACCEPTANCE"
REFUND_CHOICE = "UNKNOWN"
MAX_TEXT = 4096
MAX_SHORT = 200
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SCOPE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,120}$")
PUBLIC_REF_RE = re.compile(r"^(https://[^\s]+|p/[A-Za-z0-9._-]+\.md|revenue/[A-Za-z0-9._/-]+)$")


class BridgeError(ValueError):
    """Raised when commercial-offer → delivery authority fails closed."""


def fail(message: str) -> None:
    raise BridgeError(message)


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BridgeError("value is not canonical JSON") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def exact(value: Any, expected: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        fail(f"{where} must be a plain object")
    got = set(value)
    if got != expected:
        fail(f"{where} keys mismatch: missing={sorted(expected-got)} extra={sorted(got-expected)}")
    return value


def text(value: Any, where: str, *, max_len: int = MAX_TEXT) -> str:
    if type(value) is not str or not value or value != value.strip():
        fail(f"{where} must be a nonempty trimmed string")
    if len(value) > max_len or "\x00" in value:
        fail(f"{where} is invalid or too long")
    return value


def identifier(value: Any, where: str) -> str:
    out = text(value, where, max_len=128)
    if not ID_RE.fullmatch(out):
        fail(f"{where} is not a canonical identifier")
    return out


def scope_identifier(value: Any, where: str) -> str:
    out = text(value, where, max_len=120)
    if not SCOPE_ID_RE.fullmatch(out):
        fail(f"{where} is not scope-compatible")
    return out


def sha(value: Any, where: str) -> str:
    if type(value) is not str or not HEX64.fullmatch(value):
        fail(f"{where} must be 64 lowercase hex")
    return value


def secret(value: Any, where: str) -> bytes:
    if type(value) is not bytes or len(value) < 32:
        fail(f"{where} must be bytes and at least 32 bytes")
    return value


def timestamp(value: Any, where: str) -> tuple[str, datetime]:
    raw = text(value, where, max_len=40)
    if not raw.endswith("Z"):
        fail(f"{where} must use canonical UTC Z time")
    try:
        dt = datetime.fromisoformat(raw[:-1] + "+00:00")
    except ValueError as exc:
        raise BridgeError(f"{where} is not a real timestamp") from exc
    canonical_time = dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt) or canonical_time != raw:
        fail(f"{where} must be whole-second canonical UTC")
    return raw, dt


def public_ref(value: Any, where: str) -> str:
    out = text(value, where, max_len=1000)
    if not PUBLIC_REF_RE.fullmatch(out):
        fail(f"{where} is not an allowed public evidence reference")
    return out


def hmac_sha256(key: bytes, domain: str, payload: Mapping[str, Any]) -> str:
    message = domain.encode("ascii") + b"\0" + canonical(dict(payload))
    return hmac.new(secret(key, "verification_secret"), message, hashlib.sha256).hexdigest()


def decimal_amount(value: Any, where: str) -> Decimal:
    if type(value) is not str or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.[0-9]{2}", value):
        fail(f"{where} must be a non-negative two-decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise BridgeError(f"{where} invalid decimal") from exc


def load_json_strict(raw: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                fail(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    try:
        parsed = json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_constant=lambda value: fail(f"nonfinite JSON number: {value}"),
            parse_float=lambda value: fail(f"floating point JSON number: {value}"),
        )
    except json.JSONDecodeError as exc:
        raise BridgeError("invalid JSON") from exc
    if type(parsed) is not dict:
        fail("JSON root must be an object")
    return parsed
