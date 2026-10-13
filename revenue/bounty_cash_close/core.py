from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

INPUT_SCHEMA = "bounty-cash-close-input/v1"
OUTPUT_SCHEMA = "bounty-cash-close-board/v1"
RECEIPT_SCHEMA = "bounty-cash-close-receipt/v1"
ZERO_SHA256 = "0" * 64
MAX_SAFE_INT = 9_007_199_254_740_991
MAX_BOUNTIES = 1000
MAX_RECEIPTS = 256
MAX_TEXT = 160
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,159}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

KINDS = {
    "CLAIMED",
    "BUILD_COMPLETE",
    "SUBMISSION_ATTEMPT_FAILED",
    "SUBMISSION_DELIVERED",
    "GATE_BLOCKED",
    "GATE_FOLLOWUP_SENT",
    "GATE_CLEARED",
    "TECHNICAL_ACCEPTED",
    "COMPENSATION_ASK_SENT",
    "COMPENSATION_FOLLOWUP_SENT",
    "PAYOUT_ACKNOWLEDGED",
    "PAYMENT_LINK_CREATED",
    "SETTLEMENT_OBSERVED",
    "TERMINAL_NONPAY",
}
PROVIDER_CLASSES = {
    "LOCAL",
    "GITHUB",
    "EMAIL",
    "FORM",
    "SPONSOR",
    "PROCESSOR",
    "WALLET",
    "BANK",
    "LEDGER",
    "OTHER",
}
RAIL_CLASSES = {"PROCESSOR", "WALLET", "BANK", "LEDGER"}
ACTIONS = {
    "SUBMIT",
    "UNBLOCK_EXTERNAL_GATE",
    "ASK_COMPENSATION",
    "FOLLOW_UP_COMPENSATION",
    "RECONCILE_SETTLEMENT",
    "WAIT_DNR",
    "CLOSE_SETTLED",
}



class CloseBoardError(ValueError):
    pass

def _keys(obj: Any, expected: set[str], label: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise CloseBoardError(f"{label} must be an object")
    got = set(obj)
    if got != expected:
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        raise CloseBoardError(f"{label} keys mismatch missing={missing} extra={extra}")
    return obj

def _text(value: Any, label: str, *, pattern: re.Pattern[str] | None = REF_RE) -> str:
    if type(value) is not str or not value or len(value) > MAX_TEXT:
        raise CloseBoardError(f"{label} must be a bounded non-empty string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CloseBoardError(f"{label} contains control characters")
    if pattern is not None and not pattern.fullmatch(value):
        raise CloseBoardError(f"{label} has unsafe format")
    lowered = value.lower()
    if any(token in lowered for token in ("password=", "secret=", "token=", "apikey=", "api_key=")):
        raise CloseBoardError(f"{label} looks secret-shaped")
    return value

def _sha(value: Any, label: str) -> str:
    if type(value) is not str or not SHA_RE.fullmatch(value):
        raise CloseBoardError(f"{label} must be lowercase SHA-256 hex")
    return value

def _int(value: Any, label: str, *, lo: int = 0, hi: int = MAX_SAFE_INT) -> int:
    if type(value) is not int or value < lo or value > hi:
        raise CloseBoardError(f"{label} must be integer in [{lo}, {hi}]")
    return value

def parse_utc(value: Any, label: str) -> int:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise CloseBoardError(f"{label} must be canonical whole-second UTC")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CloseBoardError(f"{label} is invalid UTC") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise CloseBoardError(f"{label} is not canonical UTC")
    return int(dt.timestamp())

def format_utc(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

def sha256_obj(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

def _event_core(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key != "receipt_sha256"}

def mint_receipt(event_core: dict[str, Any]) -> dict[str, Any]:
    event = dict(event_core)
    if "receipt_sha256" in event:
        raise CloseBoardError("mint_receipt core must omit receipt_sha256")
    event["receipt_sha256"] = sha256_obj(event)
    return event

def canonical_bounty_key(bounty: dict[str, Any]) -> str:
    identity = {
        "sponsor_ref": bounty["sponsor_ref"],
        "program_ref": bounty["program_ref"],
        "bounty_ref": bounty["bounty_ref"],
        "claimant_ref": bounty["claimant_ref"],
        "source_revision": bounty["source_revision"],
        "work_fingerprint_sha256": bounty["work_fingerprint_sha256"],
    }
    return sha256_obj(identity)

def _validate_value(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CloseBoardError(f"{label} must be object")
    state = value.get("state")
    if state == "FIXED":
        obj = _keys(value, {"state", "amount_minor", "currency", "source_ref", "evidence_sha256"}, label)
        amount = _int(obj["amount_minor"], f"{label}.amount_minor", lo=1)
        currency = obj["currency"]
        if type(currency) is not str or not CURRENCY_RE.fullmatch(currency):
            raise CloseBoardError(f"{label}.currency must be uppercase ISO-like 3 letters")
        return {
            "state": "FIXED",
            "amount_minor": amount,
            "currency": currency,
            "source_ref": _text(obj["source_ref"], f"{label}.source_ref"),
            "evidence_sha256": _sha(obj["evidence_sha256"], f"{label}.evidence_sha256"),
        }
    if state == "UNPRICED":
        obj = _keys(value, {"state", "source_ref", "evidence_sha256"}, label)
        return {
            "state": "UNPRICED",
            "source_ref": _text(obj["source_ref"], f"{label}.source_ref"),
            "evidence_sha256": _sha(obj["evidence_sha256"], f"{label}.evidence_sha256"),
        }
    raise CloseBoardError(f"{label}.state must be FIXED or UNPRICED")
