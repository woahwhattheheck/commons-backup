"""Strict resident-data codecs, schema validation, and canonical hashing."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from typing import Any, Mapping

class DataError(ValueError):
    """Input is malformed or outside the administrative data contract."""


class ConflictError(DataError):
    """Migration or mutation would silently discard conflicting authority."""


class PermissionDenied(DataError):
    """Role lacks scope for the requested resident-data operation."""


class StaleWriteError(DataError):
    """Optimistic concurrency precondition does not match current state."""


class AuditError(DataError):
    """Audit chain verification failed."""


_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,31}$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

ALLOWED_FIELDS = frozenset(
    {
        "resident_id",
        "first_name",
        "last_name",
        "email",
        "program",
        "pgy_level",
        "start_date",
        "expected_end_date",
        "training_status",
        "license_status",
        "coordinator_notes",
    }
)
DIRECT_IDENTIFIERS = frozenset({"resident_id", "first_name", "last_name", "email"})

ROLE_VIEW_FIELDS = {
    "admin": ALLOWED_FIELDS,
    "coordinator": ALLOWED_FIELDS,
    "program_director": ALLOWED_FIELDS - {"coordinator_notes"},
    "resident_self": frozenset(
        {
            "resident_id",
            "first_name",
            "last_name",
            "email",
            "program",
            "pgy_level",
            "start_date",
            "expected_end_date",
            "training_status",
            "license_status",
        }
    ),
    "auditor": frozenset(
        {
            "program",
            "pgy_level",
            "start_date",
            "expected_end_date",
            "training_status",
            "license_status",
        }
    ),
}

ROLE_WRITE_FIELDS = {
    "admin": ALLOWED_FIELDS - {"resident_id"},
    "coordinator": frozenset(
        {
            "first_name",
            "last_name",
            "email",
            "program",
            "pgy_level",
            "start_date",
            "expected_end_date",
            "training_status",
            "license_status",
            "coordinator_notes",
        }
    ),
    "program_director": frozenset({"program", "pgy_level", "training_status"}),
    "resident_self": frozenset(),
    "auditor": frozenset(),
}

_REQUIRED_FIELDS = frozenset(
    {
        "resident_id",
        "first_name",
        "last_name",
        "email",
        "program",
        "pgy_level",
        "start_date",
        "expected_end_date",
        "training_status",
        "license_status",
    }
)


def _reject_constant(value: str) -> None:
    raise DataError(f"non-finite JSON number rejected: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DataError("duplicate JSON key rejected")
        out[key] = value
    return out


def _validate_unicode(value: Any, path: str = "$") -> None:
    if isinstance(value, str):
        for char in value:
            code = ord(char)
            if 0xD800 <= code <= 0xDFFF:
                raise DataError(f"non-scalar Unicode rejected at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_unicode(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_unicode(key, f"{path}.<key>")
            _validate_unicode(item, f"{path}.{key}")


def strict_json_loads(text: str) -> Any:
    if not isinstance(text, str):
        raise DataError("JSON input must be text")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except DataError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise DataError("invalid JSON") from exc
    _validate_unicode(value)
    return value


def canonical_bytes(value: Any) -> bytes:
    _validate_unicode(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DataError("value is not canonical-JSON encodable") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _require_text(name: str, value: Any, *, max_len: int) -> str:
    if not isinstance(value, str):
        raise DataError(f"{name} must be text")
    _validate_unicode(value, f"$.{name}")
    value = value.strip()
    if not value or len(value) > max_len:
        raise DataError(f"{name} length invalid")
    return value


def validate_record(record: Mapping[str, Any], *, require_all: bool = True) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise DataError("resident record must be an object")
    unknown = set(record) - ALLOWED_FIELDS
    if unknown:
        raise DataError(f"unknown resident fields: {sorted(unknown)}")
    if require_all:
        missing = _REQUIRED_FIELDS - set(record)
        if missing:
            raise DataError(f"missing required resident fields: {sorted(missing)}")

    out = dict(record)
    if "resident_id" in out:
        rid = _require_text("resident_id", out["resident_id"], max_len=32).upper()
        if not _ID_RE.fullmatch(rid):
            raise DataError("resident_id format invalid")
        out["resident_id"] = rid
    for field in ("first_name", "last_name", "program"):
        if field in out:
            out[field] = _require_text(field, out[field], max_len=120)
    if "email" in out:
        email = _require_text("email", out["email"], max_len=254).lower()
        if not _EMAIL_RE.fullmatch(email):
            raise DataError("email format invalid")
        out["email"] = email
    if "pgy_level" in out:
        level = out["pgy_level"]
        if type(level) is not int or not 1 <= level <= 12:
            raise DataError("pgy_level must be integer 1..12")
    for field in ("start_date", "expected_end_date"):
        if field in out:
            value = _require_text(field, out[field], max_len=10)
            if not _DATE_RE.fullmatch(value):
                raise DataError(f"{field} must be YYYY-MM-DD")
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise DataError(f"{field} is not a real calendar date") from exc
            out[field] = value
    if "training_status" in out:
        status = _require_text("training_status", out["training_status"], max_len=32).upper()
        if status not in {"ACTIVE", "LEAVE", "COMPLETED", "WITHDRAWN"}:
            raise DataError("training_status invalid")
        out["training_status"] = status
    if "license_status" in out:
        status = _require_text("license_status", out["license_status"], max_len=32).upper()
        if status not in {"CURRENT", "PENDING", "EXPIRED", "NOT_REQUIRED"}:
            raise DataError("license_status invalid")
        out["license_status"] = status
    if "coordinator_notes" in out:
        note = out["coordinator_notes"]
        if note is None:
            out["coordinator_notes"] = ""
        else:
            out["coordinator_notes"] = _require_text("coordinator_notes", note, max_len=2000)

    if "start_date" in out and "expected_end_date" in out:
        if out["expected_end_date"] < out["start_date"]:
            raise DataError("expected_end_date precedes start_date")
    return out
