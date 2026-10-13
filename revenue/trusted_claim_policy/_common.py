from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from revenue.trusted_evidence_authority.strict_json import (
    StrictJsonError,
    validate_json_value,
)

UTC = timezone.utc
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
MAX_POLICY_BYTES = 1_048_576
MAX_STATEMENT_CHARS = 8_192

POLICY_SCHEMA = "trusted-claim-policy/v1"
PACKET_SCHEMA = "trusted-claim-policy-packet/v1"
RECEIPT_SCHEMA = "trusted-claim-policy-receipt/v1"
CURRENT_LEVEL = "CURRENT_CLAIM_AUTHORITY"
HISTORICAL_LEVEL = "HISTORICAL_INTEGRITY"
HOLD_LEVEL = "HOLD"
AUTHORITY_CEILING = (
    "claim/source/time evidence only; no buyer or provider action, submission, "
    "signature, legal/compliance conclusion, payment, accounting treatment, "
    "award, cash, or revenue recognition"
)

class ClaimPolicyError(ValueError):
    pass

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))

def _json_guard(value: Any, *, path: str = "$") -> None:
    try:
        validate_json_value(value, path=path)
    except StrictJsonError as exc:
        raise ClaimPolicyError(str(exc)) from exc

def _exact_keys(value: dict[str, Any], required: set[str]) -> None:
    actual = set(value)
    if missing := required - actual:
        raise ClaimPolicyError("missing keys: " + ",".join(sorted(missing)))
    if extra := actual - required:
        raise ClaimPolicyError("unknown keys: " + ",".join(sorted(extra)))

def _require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ClaimPolicyError(f"invalid {field}")
    return value

def _require_hex64(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise ClaimPolicyError(f"invalid {field}")
    return value

def _require_nonnegative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ClaimPolicyError(f"{field} must be a non-negative integer")
    return value

def _require_positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ClaimPolicyError(f"{field} must be a positive integer")
    return value

def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ClaimPolicyError(f"{field} must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ClaimPolicyError(f"invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ClaimPolicyError(f"{field} must be UTC")
    return parsed.astimezone(UTC)

def _optional_utc(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    return _parse_utc(value, field)

def _aware_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ClaimPolicyError(f"{field} must be an aware datetime")
    return value.astimezone(UTC)

def _utc_z(value: datetime) -> str:
    value = _aware_utc(value, "timestamp")
    if value.microsecond:
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")

def _statement(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_STATEMENT_CHARS or "\x00" in value:
        raise ClaimPolicyError(f"invalid {field}")
    return value

def _normalized_id_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ClaimPolicyError(f"{field} must be a non-empty list")
    out = [_require_id(item, field) for item in value]
    if len(set(out)) != len(out):
        raise ClaimPolicyError(f"duplicate value in {field}")
    return sorted(out)
