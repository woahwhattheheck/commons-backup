"""Shared APProof types and strict canonical JSON helpers."""
from __future__ import annotations
from datetime import date
import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA = "approof/v1"
PROJECTION_SCHEMA = "approof/projection/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

SOURCE_HASH_AUTHORITY = "CALLER_DECLARED_FORMAT_VALIDATED_ONLY"

AUTHORITY = {
    "oracle_ebs_write_authorized": False,
    "invoice_approval_authorized": False,
    "payment_authorized": False,
    "supplier_contact_authorized": False,
    "buyer_submission_authorized": False,
    "contract_award_claimed": False,
    "revenue_claimed": False,
}

class APProofError(ValueError):
    """Raised for malformed or authority-unsafe APProof input."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise APProofError(f"not canonical-json encodable: {exc}") from exc


def load_json_strict(text: str) -> Any:
    """Parse JSON while rejecting duplicate keys and non-finite constants."""
    def pairs_hook(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise APProofError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def bad_constant(value):
        raise APProofError(f"non-finite JSON number: {value}")

    try:
        return json.loads(text, object_pairs_hook=pairs_hook, parse_constant=bad_constant)
    except APProofError:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        raise APProofError(f"invalid JSON: {exc}") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def obj(value: Any, name: str, required: set[str], optional: set[str] = frozenset()) -> dict[str, Any]:
    if type(value) is not dict:
        raise APProofError(f"{name} must be an object")
    keys = set(value)
    missing = required - keys
    extra = keys - required - optional
    if missing:
        raise APProofError(f"{name} missing keys: {sorted(missing)}")
    if extra:
        raise APProofError(f"{name} unknown keys: {sorted(extra)}")
    return value


def list_(value: Any, name: str) -> list[Any]:
    if type(value) is not list:
        raise APProofError(f"{name} must be a list")
    return value


def string(value: Any, name: str) -> str:
    if type(value) is not str or not value:
        raise APProofError(f"{name} must be a nonempty string")
    if len(value) > 512:
        raise APProofError(f"{name} too long")
    if any(ord(ch) < 0x20 and ch not in "\t\n\r" for ch in value):
        raise APProofError(f"{name} contains control characters")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise APProofError(f"{name} contains non-scalar Unicode") from exc
    return value


def ident(value: Any, name: str) -> str:
    text = string(value, name)
    if not _ID_RE.fullmatch(text):
        raise APProofError(f"{name} has invalid identifier syntax")
    return text


def sha256(value: Any, name: str) -> str:
    text = string(value, name)
    if not _SHA256_RE.fullmatch(text):
        raise APProofError(f"{name} must be lowercase sha256")
    return text


def integer(value: Any, name: str, *, lo: int = 0, hi: int = 10**15) -> int:
    if type(value) is not int:
        raise APProofError(f"{name} must be an integer")
    if value < lo or value > hi:
        raise APProofError(f"{name} outside [{lo},{hi}]")
    return value


def iso_date(value: Any, name: str) -> str:
    text = string(value, name)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise APProofError(f"{name} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != text:
        raise APProofError(f"{name} must be canonical YYYY-MM-DD")
    return text


def currency(value: Any, name: str) -> str:
    text = string(value, name)
    if not _CURRENCY_RE.fullmatch(text):
        raise APProofError(f"{name} must be 3 uppercase letters")
    return text


def source(obj_: Mapping[str, Any], name: str) -> None:
    sha256(obj_["source_sha256"], f"{name}.source_sha256")
