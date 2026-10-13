"""Source-bound RFP clarification-question packet compiler.

This module sits downstream of ``procurement_solicitation_ingest``.  It never
contacts a buyer or authorizes an outbound action.  Its strongest state is a
buyer-safe draft packet ready for owner review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

INPUT = "rfp-clarification-question-pack/input/v1"
PACKET = "rfp-clarification-question-pack/packet/v1"
RECEIPT = "rfp-clarification-question-pack/receipt/v1"
BOUNDARY = "INTERNAL_OWNER_REVIEW_ONLY"
UPSTREAM_ACTIVE = "procurement-solicitation-ingest/active-set/v1"
UPSTREAM_GAPS = "procurement-solicitation-ingest/gaps/v1"
UPSTREAM_RECEIPT = "procurement-solicitation-ingest/receipt/v1"
SOURCE_CLASS = {"BUYER_OFFICIAL", "SECONDARY"}
QUESTION_CLASS = {
    "MANDATORY_AMBIGUITY",
    "SCORED_AMBIGUITY",
    "COMMERCIAL_ASSUMPTION",
    "TECHNICAL_DEPENDENCY",
    "INFORMATIONAL_CURIOSITY",
}
STATUS = {
    "READY_FOR_OWNER_REVIEW",
    "HOLD_DEADLINE_PASSED",
    "HOLD_SOURCE_CONFLICT",
}
TOK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(Z|[+-]\d{2}:\d{2})$")
EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
URL = re.compile(r"(?i)\b(?:https?://|mailto:|tel:|www\.)\S+")
WIN_PATH = re.compile(r"(?i)(?:^|\s)[A-Z]:\\[^\s]+")
UNIX_PATH = re.compile(r"(?:^|\s)/(?:home|Users|tmp|var|etc|mnt|private)/[^\s]+")
SECRET_MARKER = re.compile(r"(?i)\b(?:INTERNAL[_ -]?ONLY|CONFIDENTIAL|API[_ -]?KEY|SECRET|TOKEN\s*=|PASSWORD\s*=|PRIVATE[_ -]?PRICING)\b")
MAX_BYTES = 4_000_000


class Error(ValueError):
    pass


@dataclass(frozen=True)
class Output:
    packet: bytes
    markdown: bytes
    receipt: bytes
    status: str


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise Error(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _bad_number(value):
    raise Error(f"non-integer JSON number forbidden: {value}")


def load(raw: bytes, label: str = "input") -> dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)):
        raise Error(f"{label}: bytes required")
    raw = bytes(raw)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise Error(f"{label}: BOM forbidden")
    if len(raw) > MAX_BYTES:
        raise Error(f"{label}: exceeds size bound")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_float=_bad_number,
            parse_constant=_bad_number,
        )
    except Error:
        raise
    except Exception as exc:
        raise Error(f"{label}: invalid JSON/UTF-8") from exc
    if not isinstance(value, dict):
        raise Error(f"{label}: object required")
    return value


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
    except (TypeError, ValueError, UnicodeError) as exc:
        raise Error("non-canonical value") from exc


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _keys(value: Any, wanted: Sequence[str], where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != set(wanted):
        raise Error(f"{where}: keys mismatch")
    return value


def _string(value: Any, where: str, *, token: bool = False, limit: int = 4096, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value) or len(value) > limit:
        raise Error(f"{where}: invalid string")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
        raise Error(f"{where}: control character forbidden")
    if token and not TOK.fullmatch(value):
        raise Error(f"{where}: invalid token")
    return value


def _integer(value: Any, where: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise Error(f"{where}: integer required")
    return value


def _boolean(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise Error(f"{where}: boolean required")
    return value


def _sha(value: Any, where: str) -> str:
    value = _string(value, where, limit=64)
    if not SHA.fullmatch(value):
        raise Error(f"{where}: sha256 required")
    return value


def _timestamp(value: Any, where: str) -> datetime:
    value = _string(value, where, limit=32)
    if not TS.fullmatch(value):
        raise Error(f"{where}: RFC3339-with-offset required")
    try:
        if value.endswith("Z"):
            dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                raise ValueError
    except ValueError as exc:
        raise Error(f"{where}: RFC3339-with-offset required") from exc
    return dt.astimezone(timezone.utc)


def _to_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _authority() -> dict[str, bool]:
    return {
        key: False
        for key in (
            "buyer_contact_authorized",
            "email_or_dm_authorized",
            "portal_or_form_action_authorized",
            "clarification_submission_authorized",
            "muse_request_authorized",
            "proposal_submission_authorized",
            "signature_authorized",
            "price_commitment_authorized",
            "contract_acceptance_authorized",
            "award_claim_authorized",
            "payment_action_authorized",
            "revenue_recognition_authorized",
        )
    }


def _buyer_safe(text: str) -> bool:
    return not any(rx.search(text) for rx in (EMAIL, URL, WIN_PATH, UNIX_PATH, SECRET_MARKER))


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def _compile_upstream(pack_bytes: bytes):
    """Return parsed upstream artifacts or one fail-closed source error string."""
    try:
        from revenue.procurement_solicitation_ingest import ingest

        result = ingest.compile_ingest(pack_bytes)
        return (
            load(result.active, "upstream active"),
            load(result.gaps, "upstream gaps"),
            load(result.receipt, "upstream receipt"),
            result.status,
            None,
        )
    except Exception as exc:  # fail-closed across upstream semantic/version errors
        return None, None, None, "HOLD", f"UPSTREAM_SOURCE_CONFLICT:{type(exc).__name__}:{exc}"


