#!/usr/bin/env python3
"""Deterministic, side-effect-free procurement outcome compiler.

The compiler consumes redacted, source-digest-bound procurement evidence and
emits only WON, LOST, NO_DECISION, or UNKNOWN. It never contacts a buyer,
requests a debrief, sends outbound, mutates a provider, or invents causal detail.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA = "procurement-outcome-evidence/v1"
RECEIPT_SCHEMA = "procurement-win-loss-receipt/v1"
OUTCOMES = {"WON", "LOST", "NO_DECISION", "UNKNOWN"}
SOURCE_KINDS = {
    "BUYER_NOTICE",
    "PUBLIC_AWARD_NOTICE",
    "PROCUREMENT_PORTAL",
    "OWNER_LEDGER",
    "SYSTEM_RECEIPT",
    "OTHER_REDACTED_SOURCE",
}
EVIDENCE_STATES = {"CURRENT", "STALE", "WITHDRAWN"}
SIGNAL_TO_OUTCOME = {
    "SELECTED": "WON",
    "AWARDED": "WON",
    "NOT_SELECTED": "LOST",
    "NO_AWARD": "NO_DECISION",
    "CANCELLED": "NO_DECISION",
    "PENDING": "UNKNOWN",
    "UNKNOWN": "UNKNOWN",
}
MAX_EVIDENCE = 100
MAX_TEXT = 300
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_PHONEISH_RE = re.compile(r"(?<!\w)\+?\d[\d(). -]{6,}\d(?!\w)")
_URL_RE = re.compile(r"(?i)\b(?:https?|ftp)://|\bwww\.")
_EMAILISH_RE = re.compile(r"\S+@\S+")


class OutcomeError(ValueError):
    """Raised when evidence cannot be safely compiled."""


class DuplicateKeyError(OutcomeError):
    """Raised when JSON contains duplicate object keys."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON object key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                OutcomeError(f"non-finite JSON number: {value}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise OutcomeError(f"invalid JSON: {exc.msg}") from exc


def load_json_file(path: str | Path) -> Any:
    raw = Path(path).read_bytes()
    if len(raw) > 256 * 1024:
        raise OutcomeError("input exceeds 256 KiB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OutcomeError("input must be UTF-8") from exc
    return loads_strict(text)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise OutcomeError(f"{label} must be an object")
    return value


def _list(value: Any, label: str, maximum: int) -> list[Any]:
    if type(value) is not list:
        raise OutcomeError(f"{label} must be a list")
    if len(value) > maximum:
        raise OutcomeError(f"{label} exceeds {maximum} entries")
    return value


def _exact(obj: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = sorted(set(obj) - allowed)
    missing = sorted(allowed - set(obj))
    if extra:
        raise OutcomeError(f"{label} contains unknown fields: {', '.join(extra)}")
    if missing:
        raise OutcomeError(f"{label} is missing fields: {', '.join(missing)}")


def _text(value: Any, label: str, max_len: int = 128) -> str:
    if type(value) is not str:
        raise OutcomeError(f"{label} must be a string")
    text = value.strip()
    if not text:
        raise OutcomeError(f"{label} must not be empty")
    if len(text) > max_len:
        raise OutcomeError(f"{label} exceeds {max_len} characters")
    if any(
        ord(ch) < 32
        or ord(ch) == 127
        or unicodedata.category(ch).startswith("C")
        or unicodedata.category(ch) in {"Zl", "Zp"}
        for ch in text
    ):
        raise OutcomeError(f"{label} contains control characters")
    return text


def _enum(value: Any, allowed: set[str], label: str) -> str:
    text = _text(value, label, 64)
    if text not in allowed:
        raise OutcomeError(f"{label} is unsupported")
    return text


def _sha(value: Any, label: str) -> str:
    text = _text(value, label, 64)
    if not _HEX64_RE.fullmatch(text):
        raise OutcomeError(f"{label} must be lowercase SHA-256 hex")
    return text


def _time(value: Any, label: str) -> datetime:
    text = _text(value, label, 64)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise OutcomeError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OutcomeError(f"{label} must include a timezone")
    parsed_utc = parsed.astimezone(timezone.utc)
    if parsed_utc.microsecond != 0:
        raise OutcomeError(f"{label} must be second-aligned")
    return parsed_utc


def _ftime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_rationale_text(value: Any, label: str) -> str:
    text = _text(value, label, MAX_TEXT)
    screened = unicodedata.normalize("NFKC", text)
    if _EMAILISH_RE.search(screened):
        raise OutcomeError(f"{label} must not contain an email address")
    if _URL_RE.search(screened):
        raise OutcomeError(f"{label} must not contain a URL")
    if _PHONEISH_RE.search(screened):
        raise OutcomeError(f"{label} must not contain phone-like data")
    return text


def _normalize_rationale(raw: Any, label: str) -> dict[str, Any]:
    obj = _dict(raw, label)
    status = _enum(obj.get("status"), {"UNKNOWN", "STATED"}, f"{label}.status")
    if status == "UNKNOWN":
        _exact(obj, {"status"}, label)
        return {"status": "UNKNOWN"}
    _exact(obj, {"status", "text"}, label)
    return {"status": "STATED", "text": _safe_rationale_text(obj.get("text"), f"{label}.text")}


def normalize_record(raw: Any) -> dict[str, Any]:
    obj = _dict(raw, "record")
    _exact(obj, {"schema", "opportunity_id", "compiled_at", "evidence"}, "record")
    if obj.get("schema") != INPUT_SCHEMA:
        raise OutcomeError(f"record.schema must be {INPUT_SCHEMA}")

    opportunity_id = _text(obj.get("opportunity_id"), "record.opportunity_id", 160)
    compiled_at = _time(obj.get("compiled_at"), "record.compiled_at")
    evidence_raw = _list(obj.get("evidence"), "record.evidence", MAX_EVIDENCE)
    if not evidence_raw:
        raise OutcomeError("record.evidence must not be empty")

    seen_ids: set[str] = set()
    seen_digests: set[str] = set()
    normalized: list[dict[str, Any]] = []
    required = {
        "evidence_id",
        "bound_opportunity_id",
        "source_kind",
        "source_digest_sha256",
        "observed_at",
        "captured_at",
        "evidence_status",
        "redacted",
        "decision_signal",
        "rationale",
    }
    for index, raw_item in enumerate(evidence_raw):
        label = f"record.evidence[{index}]"
        item = _dict(raw_item, label)
        _exact(item, required, label)
        evidence_id = _text(item.get("evidence_id"), f"{label}.evidence_id", 160)
        if evidence_id in seen_ids:
            raise OutcomeError("record.evidence contains duplicate evidence_id")
        seen_ids.add(evidence_id)

        bound = _text(item.get("bound_opportunity_id"), f"{label}.bound_opportunity_id", 160)
        if bound != opportunity_id:
            raise OutcomeError(f"{label}.bound_opportunity_id does not match record.opportunity_id")

        source_digest = _sha(item.get("source_digest_sha256"), f"{label}.source_digest_sha256")
        if source_digest in seen_digests:
            raise OutcomeError("record.evidence contains replayed source_digest_sha256")
        seen_digests.add(source_digest)

        if item.get("redacted") is not True:
            raise OutcomeError(f"{label}.redacted must be true")
        observed_at = _time(item.get("observed_at"), f"{label}.observed_at")
        captured_at = _time(item.get("captured_at"), f"{label}.captured_at")
        if captured_at < observed_at:
            raise OutcomeError(f"{label}.captured_at precedes observed_at")
        if captured_at > compiled_at:
            raise OutcomeError(f"{label}.captured_at is later than compiled_at")

        source_kind = _enum(item.get("source_kind"), SOURCE_KINDS, f"{label}.source_kind")
        evidence_status = _enum(item.get("evidence_status"), EVIDENCE_STATES, f"{label}.evidence_status")
        signal = _enum(item.get("decision_signal"), set(SIGNAL_TO_OUTCOME), f"{label}.decision_signal")
        rationale = _normalize_rationale(item.get("rationale"), f"{label}.rationale")
        normalized.append(
            {
                "evidence_id": evidence_id,
                "bound_opportunity_id": bound,
                "source_kind": source_kind,
                "source_digest_sha256": source_digest,
                "observed_at": _ftime(observed_at),
                "captured_at": _ftime(captured_at),
                "evidence_status": evidence_status,
                "redacted": True,
                "decision_signal": signal,
                "rationale": rationale,
            }
        )

    normalized.sort(key=lambda item: (item["observed_at"], item["evidence_id"]))
    return {
        "schema": INPUT_SCHEMA,
        "opportunity_id": opportunity_id,
        "compiled_at": _ftime(compiled_at),
        "evidence": normalized,
    }


def _derive_outcome(evidence: list[dict[str, Any]]) -> tuple[str, list[str], list[dict[str, Any]]]:
    current = [item for item in evidence if item["evidence_status"] == "CURRENT"]
    current_terminal = [item for item in current if SIGNAL_TO_OUTCOME[item["decision_signal"]] != "UNKNOWN"]
    current_outcomes = {SIGNAL_TO_OUTCOME[item["decision_signal"]] for item in current_terminal}
    hold_reasons: set[str] = set()

    if len(current_outcomes) == 1:
        outcome = next(iter(current_outcomes))
    elif len(current_outcomes) > 1:
        outcome = "UNKNOWN"
        hold_reasons.add("conflicting_current_terminal_evidence")
    else:
        outcome = "UNKNOWN"

    noncurrent_terminal = [
        item
        for item in evidence
        if item["evidence_status"] != "CURRENT" and SIGNAL_TO_OUTCOME[item["decision_signal"]] != "UNKNOWN"
    ]
    if noncurrent_terminal and not current_terminal:
        hold_reasons.add("noncurrent_terminal_evidence")
    if len(current_outcomes) == 1:
        candidate = next(iter(current_outcomes))
        if any(SIGNAL_TO_OUTCOME[item["decision_signal"]] != candidate for item in noncurrent_terminal):
            outcome = "UNKNOWN"
            hold_reasons.add("conflicting_noncurrent_terminal_evidence")

    if current_terminal:
        newest_terminal_at = max(item["observed_at"] for item in current_terminal)
        if any(
            item["decision_signal"] == "PENDING" and item["observed_at"] > newest_terminal_at
            for item in current
        ):
            outcome = "UNKNOWN"
            hold_reasons.add("later_pending_after_terminal")

    if outcome == "UNKNOWN":
        basis = current_terminal or current or evidence
    else:
        basis = [
            item
            for item in current_terminal
            if SIGNAL_TO_OUTCOME[item["decision_signal"]] == outcome
        ]
    return outcome, sorted(hold_reasons), basis


def compile_record(raw: Any) -> dict[str, Any]:
    record = normalize_record(raw)
    outcome, hold_reasons, basis = _derive_outcome(record["evidence"])

    known_facts = [
        {
            "evidence_id": item["evidence_id"],
            "source_kind": item["source_kind"],
            "source_digest_sha256": item["source_digest_sha256"],
            "observed_at": item["observed_at"],
            "evidence_status": item["evidence_status"],
            "decision_signal": item["decision_signal"],
            "mapped_outcome": SIGNAL_TO_OUTCOME[item["decision_signal"]],
        }
        for item in record["evidence"]
    ]

    statements = [
        {
            "evidence_id": item["evidence_id"],
            "source_digest_sha256": item["source_digest_sha256"],
            "text": item["rationale"]["text"],
        }
        for item in basis
        if item["rationale"]["status"] == "STATED"
    ]
    unknown_ids = sorted(
        item["evidence_id"] for item in basis if item["rationale"]["status"] == "UNKNOWN"
    )
    if statements and unknown_ids:
        rationale_status = "PARTIAL"
    elif statements:
        rationale_status = "STATED"
    else:
        rationale_status = "UNKNOWN"

    unknowns: list[str] = []
    if outcome == "UNKNOWN":
        unknowns.append("outcome")
    if rationale_status != "STATED":
        unknowns.append("rationale")

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "opportunity_id": record["opportunity_id"],
        "compiled_at": record["compiled_at"],
        "outcome": outcome,
        "hold_reasons": hold_reasons,
        "known_facts": known_facts,
        "rationale": {
            "status": rationale_status,
            "statements": statements,
            "unknown_evidence_ids": unknown_ids,
        },
        "unknowns": unknowns,
        "authority": {
            "buyer_contact_authorized": False,
            "debrief_request_authorized": False,
            "outbound_authorized": False,
            "payment_authorized": False,
            "contract_authorized": False,
            "revenue_recognized": False,
            "causal_inference_authorized": False,
        },
        "normalized_input_sha256": digest(record),
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


def render_receipt(receipt: dict[str, Any]) -> bytes:
    return canonical_bytes(receipt) + b"\n"
