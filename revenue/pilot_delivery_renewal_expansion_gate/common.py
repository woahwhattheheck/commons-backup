"""Evidence-bound pilot-delivery -> renewal/expansion owner-review gate.

The module is intentionally provider-free.  It never contacts a buyer, performs a
Muse election, signs a contract, invoices, charges, deploys, schedules, mutates a
CRM, or recognizes revenue.  Its strongest state is READY_FOR_RENEWAL_REVIEW.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

INPUT_SCHEMA = "pilot-delivery-renewal-expansion/input/v1"
RECEIPT_SCHEMA = "pilot-delivery-renewal-expansion/receipt/v1"

READY = "READY_FOR_RENEWAL_REVIEW"
HOLD_ACCEPTANCE = "HOLD_ACCEPTANCE"
HOLD_PAYMENT = "HOLD_PAYMENT"
HOLD_WINDOW = "HOLD_WINDOW"
HOLD_EVIDENCE = "HOLD_EVIDENCE"
DNR = "DNR"
STATES = {READY, HOLD_ACCEPTANCE, HOLD_PAYMENT, HOLD_WINDOW, HOLD_EVIDENCE, DNR}

UTC_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")

SUPPORT_MAX_AGE_SECONDS = 90 * 24 * 60 * 60
PAYMENT_MAX_AGE_SECONDS = 90 * 24 * 60 * 60
ROUTE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
MILESTONE_MAX_AGE_SECONDS = 366 * 24 * 60 * 60

BASELINE_STATES = {"ACCEPTED", "PROPOSED_NOT_ACCEPTED", "SUPERSEDED"}
CHANGE_STATES = {"APPROVED", "PENDING", "REJECTED"}
MILESTONE_STATES = {"BUYER_HUMAN_ACCEPTED", "PENDING", "REJECTED", "SYSTEM_ONLY"}
PAYMENT_STATES = {"SETTLED", "PARTIAL", "PENDING", "REFUNDED", "DISPUTED"}
PAYMENT_CLASSES = {"PROVIDER_SETTLEMENT", "BANK_SETTLEMENT", "INVOICE", "PAYMENT_LINK", "ADVERTISED_AMOUNT"}
SUPPORT_SEVERITIES = {"INFO", "LOW", "MEDIUM", "HIGH", "BLOCKING"}
FINDING_STATES = {"OPEN", "RESOLVED"}
GAP_STATES = {"OPEN", "RESOLVED"}
ROUTE_STATES = {"CLEAR", "UNASSESSED", "ACTIVE_OTHER_OWNER", "DNR"}
HYPOTHESIS_BASES = {"SUPPORT_FINDING", "DELIVERY_OBSERVATION", "OWNER_HYPOTHESIS", "SECURITY_DATA_GAP"}

class GateError(ValueError):
    pass

def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise GateError(f"duplicate JSON key: {key}")
        out[key] = value
    return out

def _bad_number(value):
    raise GateError(f"non-integer/non-finite JSON number forbidden: {value}")

def load_json(raw: bytes, label: str = "input") -> dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)):
        raise GateError(f"{label}: bytes required")
    raw = bytes(raw)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise GateError(f"{label}: BOM forbidden")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_float=_bad_number,
            parse_constant=_bad_number,
        )
    except GateError:
        raise
    except Exception as exc:
        raise GateError(f"{label}: invalid JSON/UTF-8") from exc
    if not isinstance(value, dict):
        raise GateError(f"{label}: object required")
    return value

def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")

def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()

def _keys(value: Any, wanted: set[str], where: str) -> None:
    if not isinstance(value, dict) or set(value) != wanted:
        raise GateError(f"{where}: keys mismatch")

def _string(value: Any, where: str, *, token: bool = False, max_len: int = 2048) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise GateError(f"{where}: invalid string")
    if any(ord(ch) < 32 for ch in value):
        raise GateError(f"{where}: control character")
    if token and not TOKEN.fullmatch(value):
        raise GateError(f"{where}: invalid token")
    return value

def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise GateError(f"{where}: bool required")
    return value

def _int(value: Any, where: str, lo: int = 0, hi: int = 10**15) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < lo or value > hi:
        raise GateError(f"{where}: integer required")
    return value

def _enum(value: Any, choices: set[str], where: str) -> str:
    value = _string(value, where, token=True, max_len=64)
    if value not in choices:
        raise GateError(f"{where}: unsupported value")
    return value

def _sha(value: Any, where: str) -> str:
    value = _string(value, where, max_len=64)
    if not SHA256.fullmatch(value):
        raise GateError(f"{where}: sha256 required")
    return value

def _ts(value: Any, where: str) -> str:
    value = _string(value, where, max_len=20)
    if not UTC_SECOND.fullmatch(value):
        raise GateError(f"{where}: UTC-second timestamp required")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise GateError(f"{where}: invalid timestamp") from exc
    return value

def _dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

def _age(now: str, observed: str, where: str, max_age: int | None = None) -> int:
    age = int((_dt(now) - _dt(observed)).total_seconds())
    if age < 0:
        raise GateError(f"{where}: future timestamp")
    if max_age is not None and age > max_age:
        raise GateError(f"{where}: stale evidence")
    return age

def _uri(value: Any, where: str) -> str:
    value = _string(value, where)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise GateError(f"{where}: safe HTTPS source required")
    return value

def _source(value: Any, where: str, now: str, *, max_age: int | None = None) -> dict[str, Any]:
    _keys(value, {"source_id", "source_uri", "source_sha256", "observed_at"}, where)
    observed = _ts(value["observed_at"], f"{where}.observed_at")
    _age(now, observed, f"{where}.observed_at", max_age)
    return {
        "source_id": _string(value["source_id"], f"{where}.source_id", token=True),
        "source_uri": _uri(value["source_uri"], f"{where}.source_uri"),
        "source_sha256": _sha(value["source_sha256"], f"{where}.source_sha256"),
        "observed_at": observed,
    }

def authority_flags() -> dict[str, bool]:
    return {
        "external_send_authorized": False,
        "muse_election_authorized": False,
        "contract_or_signature_authorized": False,
        "buyer_acceptance_established": False,
        "buyer_renewal_interest_established": False,
        "buyer_expansion_interest_established": False,
        "renewal_or_expansion_approved": False,
        "invoice_authorized": False,
        "payment_movement_authorized": False,
        "cash_or_revenue_recognized": False,
        "deployment_authorized": False,
        "scheduling_authorized": False,
        "crm_mutation_authorized": False,
    }
