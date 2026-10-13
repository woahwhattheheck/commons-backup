"""Deterministic buyer-official procurement Q&A answer delta compiler.

The compiler consumes exact, already-compiled solicitation active-set/gap
artifacts plus retained buyer-official Q&A/addendum extraction facts. It never
infers buyer truth from answer prose. Structured effects are admitted facts
bound to source identity, SHA-256, generation, answer id and section.

Later official answers supersede earlier answers only through an explicit,
strictly-forward ``supersedes_answer_id`` chain. Unknown mappings, stale
sources, contradictory chronology and drift become ``SOURCE_CONFLICT`` and a
HOLD. No output authorizes buyer contact, submission, signature, pricing,
contract, award, payment, or revenue recognition.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Optional

INPUT = "procurement-qa-answer-delta/input/v1"
DELTA = "procurement-qa-answer-delta/delta/v1"
RECEIPT = "procurement-qa-answer-delta/receipt/v1"
BOUNDARY = "INTERNAL_OWNER_REVIEW_ONLY"
UP_ACTIVE = "procurement-solicitation-ingest/active-set/v1"
UP_GAPS = "procurement-solicitation-ingest/gaps/v1"
UP_RECEIPT = "procurement-solicitation-ingest/receipt/v1"
QUESTION_CLASS = {
    "MANDATORY_AMBIGUITY",
    "SCORED_AMBIGUITY",
    "COMMERCIAL_ASSUMPTION",
    "TECHNICAL_DEPENDENCY",
    "INFORMATIONAL_CURIOSITY",
}
EFFECT = {
    "CLOSE_GAP",
    "REOPEN_GAP",
    "REQUIREMENT_CHANGE",
    "DEADLINE_CHANGE",
    "INFORMATIONAL",
}
CLASSIFICATION = {
    "CLOSED_GAP",
    "REOPENED_GAP",
    "REQUIREMENT_CHANGED",
    "DEADLINE_CHANGED",
    "INFORMATIONAL_ONLY",
    "SOURCE_CONFLICT",
}
REQ_KIND = {"MANDATORY", "SCORED", "INFORMATIONAL"}
SOURCE_CLASS = {"BUYER_OFFICIAL", "SECONDARY"}
TOK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,159}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(Z|[+-]\d{2}:\d{2})$")
MAX_BYTES = 8 * 1024 * 1024


class Error(ValueError):
    pass


@dataclass(frozen=True)
class Output:
    delta: bytes
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
    if not raw or len(raw) > MAX_BYTES:
        raise Error(f"{label}: invalid byte length")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise Error(f"{label}: BOM forbidden")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_bad_number,
            parse_constant=_bad_number,
        )
    except Error:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Error(f"{label}: invalid JSON/UTF-8") from exc
    if type(value) is not dict:
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


def _keys(value: Any, wanted, where: str):
    if type(value) is not dict or set(value) != set(wanted):
        raise Error(f"{where}: keys mismatch")
    return value


def _string(value: Any, where: str, *, token=False, limit=4096, empty=False):
    if type(value) is not str or (not empty and not value) or len(value) > limit:
        raise Error(f"{where}: invalid string")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
        raise Error(f"{where}: control character forbidden")
    if token and not TOK.fullmatch(value):
        raise Error(f"{where}: invalid token")
    return value


def _nullable_token(value: Any, where: str):
    if value is None:
        return None
    return _string(value, where, token=True, limit=160)


def _integer(value: Any, where: str, lo=0, hi=10**9):
    if type(value) is not int or not lo <= value <= hi:
        raise Error(f"{where}: integer required")
    return value


def _sha(value: Any, where: str):
    value = _string(value, where, limit=64)
    if not SHA.fullmatch(value):
        raise Error(f"{where}: sha256 required")
    return value


def _timestamp(value: Any, where: str):
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
    return value, dt.astimezone(timezone.utc)


def _tokens(value: Any, where: str, maxn=64):
    if type(value) is not list or len(value) > maxn:
        raise Error(f"{where}: invalid list")
    out = [_string(item, f"{where}[{idx}]", token=True, limit=160) for idx, item in enumerate(value)]
    if len(out) != len(set(out)):
        raise Error(f"{where}: duplicate item")
    return out


def _authority():
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
            "certification_authorized",
            "price_commitment_authorized",
            "contract_acceptance_authorized",
            "award_claim_authorized",
            "payment_action_authorized",
            "revenue_recognition_authorized",
        )
    }


def _require_false_authority(value: Any, where: str):
    if type(value) is not dict or not value:
        raise Error(f"{where}: authority object required")
    if any(type(v) is not bool or v for v in value.values()):
        raise Error(f"{where}: upstream authority must remain hard-false")


def _requirement(value: Any, where: str, *, upstream=False):
    wanted = ["lineage_id", "section_id", "kind", "family", "tags", "text"]
    if upstream:
        wanted += [
            "source_id",
            "source_identity",
            "source_ref",
            "source_sha256",
            "source_captured_at",
            "sequence",
        ]
    _keys(value, wanted, where)
    kind = _string(value["kind"], where + ".kind", token=True, limit=32)
    if kind not in REQ_KIND:
        raise Error(f"{where}: unsupported requirement kind")
    out = {
        "lineage_id": _string(value["lineage_id"], where + ".lineage_id", token=True),
        "section_id": _string(value["section_id"], where + ".section_id", token=True),
        "kind": kind,
        "family": _string(value["family"], where + ".family", token=True),
        "tags": sorted(_tokens(value["tags"], where + ".tags")),
        "text": _string(value["text"], where + ".text"),
    }
    if upstream:
        _, captured = _timestamp(value["source_captured_at"], where + ".source_captured_at")
        out.update(
            {
                "source_id": _string(value["source_id"], where + ".source_id", token=True),
                "source_identity": _string(value["source_identity"], where + ".source_identity"),
                "source_ref": _string(value["source_ref"], where + ".source_ref"),
                "source_sha256": _sha(value["source_sha256"], where + ".source_sha256"),
                "source_captured_at": value["source_captured_at"],
                "source_captured_dt": captured,
                "sequence": _integer(value["sequence"], where + ".sequence", 0),
            }
        )
    return out
