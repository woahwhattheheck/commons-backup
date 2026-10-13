"""Deterministic, offline EDSS migration/interoperability acceptance evidence.

This module deliberately accepts only opaque identifiers and hashes.  It does
not consume clinical/public-health payloads and it never contacts a provider.
A clean receipt says only that the supplied synthetic/approved evidence
reconciles under the declared policy.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Iterable

PACKET_SCHEMA = "edss-migration-acceptance/v1"
POLICY_SCHEMA = "edss-migration-acceptance-policy/v1"
RECEIPT_SCHEMA = "edss-migration-acceptance-receipt/v1"

ACCEPTANCE_READY = "ACCEPTANCE_READY"
EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
EVIDENCE_STALE = "EVIDENCE_STALE"
MIGRATION_MISMATCH = "MIGRATION_MISMATCH"
INTERFACE_MISMATCH = "INTERFACE_MISMATCH"
HOLD = "HOLD"
STATES = {
    ACCEPTANCE_READY,
    EVIDENCE_INCOMPLETE,
    EVIDENCE_STALE,
    MIGRATION_MISMATCH,
    INTERFACE_MISMATCH,
    HOLD,
}

DEFAULT_POLICY = {
    "schema": POLICY_SCHEMA,
    "max_snapshot_age_seconds": 7 * 24 * 3600,
    "max_expectation_age_seconds": 7 * 24 * 3600,
    "max_event_age_seconds": 7 * 24 * 3600,
    "max_cutover_seconds": 7 * 24 * 3600,
    "max_rows": 10000,
    "max_fields_per_row": 128,
    "max_events": 10000,
    "max_acks_per_event": 4,
    "max_id_chars": 128,
}

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_OPAQUE_ID_RE = re.compile(
    r"^(?:[0-9a-f]{32}|[0-9a-f]{64}|[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$"
)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}(?!\d)")
_SECRET_RE = re.compile(r"(?i)\b(?:sk_live_|sk_test_|ghp_|github_pat_|AIza|xox[baprs]-)[A-Za-z0-9_\-]{8,}")


class EdssAcceptanceError(ValueError):
    """Raised for structurally invalid or unsafe acceptance evidence."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _no_duplicate_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EdssAcceptanceError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_strict(data: bytes | str) -> Any:
    try:
        return json.loads(data, object_pairs_hook=_no_duplicate_object, parse_constant=lambda value: (_ for _ in ()).throw(EdssAcceptanceError(f"non-finite JSON value: {value}")))
    except EdssAcceptanceError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EdssAcceptanceError(f"invalid JSON: {exc}") from exc


def _exact_object(value: Any, required: set[str], optional: set[str] | None = None, *, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise EdssAcceptanceError(f"{where} must be an object")
    optional = optional or set()
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing:
        raise EdssAcceptanceError(f"{where} missing keys: {sorted(missing)}")
    if unknown:
        raise EdssAcceptanceError(f"{where} unknown keys: {sorted(unknown)}")
    return value


def _string(value: Any, *, where: str, maximum: int = 128, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise EdssAcceptanceError(f"{where} must be a string")
    if (not allow_empty and not value) or len(value) > maximum or "\x00" in value:
        raise EdssAcceptanceError(f"{where} has invalid length/content")
    return value


def _safe_id(value: Any, *, where: str, maximum: int = 128) -> str:
    text = _string(value, where=where, maximum=maximum)
    if not _ID_RE.fullmatch(text):
        raise EdssAcceptanceError(f"{where} must be an opaque identifier")
    if not _OPAQUE_ID_RE.fullmatch(text):
        raise EdssAcceptanceError(f"{where} must be a generated opaque token (UUID or hex digest), not a semantic label")
    if _EMAIL_RE.search(text) or _PHONE_RE.search(text) or _SECRET_RE.search(text):
        raise EdssAcceptanceError(f"{where} contains direct contact/secret-shaped material")
    return text


def _sha(value: Any, *, where: str) -> str:
    text = _string(value, where=where, maximum=64)
    if not _SHA_RE.fullmatch(text):
        raise EdssAcceptanceError(f"{where} must be lowercase SHA-256")
    return text


def _integer(value: Any, *, where: str, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise EdssAcceptanceError(f"{where} must be an integer")
    if value < minimum or value > maximum:
        raise EdssAcceptanceError(f"{where} outside bounds")
    return value


def _boolean(value: Any, *, where: str) -> bool:
    if type(value) is not bool:
        raise EdssAcceptanceError(f"{where} must be boolean")
    return value


def _parse_utc(value: Any, *, where: str) -> datetime:
    text = _string(value, where=where, maximum=32)
    if not text.endswith("Z"):
        raise EdssAcceptanceError(f"{where} must be canonical UTC ending Z")
    try:
        dt = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise EdssAcceptanceError(f"{where} invalid timestamp") from exc
    if dt.tzinfo != timezone.utc or dt.microsecond:
        raise EdssAcceptanceError(f"{where} must be UTC whole seconds")
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise EdssAcceptanceError(f"{where} must be canonical UTC whole seconds")
    return dt


def _utc_text(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise EdssAcceptanceError("trusted as_of must be timezone-aware")
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_policy(raw: Any) -> dict[str, Any]:
    required = set(DEFAULT_POLICY)
    obj = _exact_object(raw, required, where="policy")
    if obj["schema"] != POLICY_SCHEMA:
        raise EdssAcceptanceError("unsupported policy schema")
    out = {"schema": POLICY_SCHEMA}
    for key in required - {"schema"}:
        if key.endswith("_seconds"):
            maximum = 365 * 24 * 3600
        elif key == "max_id_chars":
            maximum = 128
        else:
            maximum = 1_000_000
        out[key] = _integer(obj[key], where=f"policy.{key}", minimum=1, maximum=maximum)
    if out["max_id_chars"] > 128:
        raise EdssAcceptanceError("policy.max_id_chars exceeds implementation safe-id bound")
    return out

__all__ = [
    "PACKET_SCHEMA", "POLICY_SCHEMA", "RECEIPT_SCHEMA",
    "ACCEPTANCE_READY", "EVIDENCE_INCOMPLETE", "EVIDENCE_STALE", "MIGRATION_MISMATCH",
    "INTERFACE_MISMATCH", "HOLD", "STATES", "DEFAULT_POLICY",
    "EdssAcceptanceError", "canonical_json_bytes", "sha256_hex", "load_json_strict",
    "_exact_object", "_string", "_safe_id", "_sha", "_integer", "_boolean",
    "_parse_utc", "_utc_text", "_validate_policy",
]
