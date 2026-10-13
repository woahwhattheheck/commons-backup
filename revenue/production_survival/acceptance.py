#!/usr/bin/env python3
"""Create secret-free, replayable production-survival acceptance receipts.

The commands in this module never send mail, update a CRM, create an invoice,
or claim payment/cash.  A mailbox operator classifies private evidence and this
tool records hashes plus the minimum public facts needed for a later invoice
decision.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable


SCHEMA_VERSION = "production-survival-acceptance/v1"
KIND = "PRODUCTION_SURVIVAL_ACCEPTANCE_RECEIPT"
OFFER_ID = "same-day-agent-survival-proof"
CURRENCY = "USD"
FIXED_AMOUNT = 2500
TIMEZONE = "America/New_York"
MAX_PRIVATE_BYTES = 1_048_576
BUYER_RE = re.compile(r"^buyer_[0-9a-f]{32,64}$")
OPAQUE_REF_RE = re.compile(r"^opaque:[A-Za-z0-9._-]{8,200}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
REFUND_CHOICES = {
    "REFUND_IF_MISSED",
    "ONE_FREE_NEXT_BUSINESS_DAY_REPAIR",
}
INTENT_ATTESTATION = "AUTHORIZED_OPERATOR_VERIFIED_POSITIVE_SIGNAL"
TERMS_ATTESTATION = "AUTHORIZED_OPERATOR_VERIFIED_TERMS_SENT"
ACCEPTANCE_ATTESTATION = "AUTHORIZED_OPERATOR_VERIFIED_EXACT_TERMS_ACCEPTANCE"
NONCE_RE = re.compile(r"^nonce_[0-9a-f]{32}$")
CONTRACT_RE = re.compile(r"^contract-[0-9a-f]{24}$")
PROOF_CLAIMS = [
    "synthetic file-backed effect",
    "intentional process crash",
    "static public receipt",
]
EXCLUSIONS = [
    "authentication",
    "billing",
    "credentials",
    "ongoing hosting or SLA",
    "PII or PHI",
    "private data",
    "production migration",
    "White Box or model-file work",
]


class AcceptanceError(ValueError):
    """An evidence or state transition failed closed."""


def _fail(message: str) -> None:
    raise AcceptanceError(message)


def _pairs_no_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be a JSON object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        _fail(f"{label} keys mismatch; missing={missing}, extra={extra}")
    return value


def _string(value: Any, label: str, *, max_length: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} must be a nonempty string")
    if value != value.strip():
        _fail(f"{label} must not have leading or trailing whitespace")
    if len(value) > max_length:
        _fail(f"{label} exceeds {max_length} characters")
    if "\x00" in value or "\r" in value or "\n" in value:
        _fail(f"{label} must be a single line")
    return value


def _buyer_ref(value: Any) -> str:
    value = _string(value, "buyer_ref", max_length=70)
    if not BUYER_RE.fullmatch(value):
        _fail("buyer_ref must be an opaque buyer_<32-64 lowercase hex> token")
    return value


def _message_ref(value: Any) -> str:
    value = _string(value, "message_ref", max_length=207)
    if not OPAQUE_REF_RE.fullmatch(value):
        _fail("message_ref must be an opaque:<safe-token> reference")
    return value


def _parse_time(value: Any, label: str) -> dt.datetime:
    text = _string(value, label, max_length=40)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AcceptanceError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(f"{label} must include a UTC offset")
    return parsed


def _validate_public_safe_text(value: Any, label: str) -> str:
    text = _string(value, label, max_length=600)
    lower = text.lower()
    forbidden = ("@", "mailto:", "password", "credential", "routing number", "card number")
    if any(token in lower for token in forbidden):
        _fail(f"{label} appears to contain private or credential material")
    return text


def _relative_private_path(value: str) -> Path:
    if not isinstance(value, str) or not value:
        _fail("private evidence path must be a nonempty relative path")
    if "\\" in value:
        _fail("private evidence paths must use forward slashes")
    candidate = Path(value)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        _fail("private evidence path must be normalized and relative")
    return candidate


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _checkout_root() -> Path:
    # Deployed path: <repo>/revenue/production_survival/acceptance.py
    return Path(__file__).resolve().parents[2]


def _validated_root(root_arg: str) -> Path:
    root_raw = Path(root_arg)
    if not root_raw.is_absolute():
        _fail("evidence root must be absolute")
    root = root_raw.resolve(strict=True)
    if not root.is_dir():
        _fail("evidence root must be a directory")
    checkout = _checkout_root()
    if root == checkout or _is_relative_to(root, checkout) or _is_relative_to(checkout, root):
        _fail("private evidence root must be disjoint from the repository checkout")
    if root.is_symlink():
        _fail("evidence root must not be a symlink")
    return root


def _read_private(root: Path, relative: str) -> bytes:
    rel = _relative_private_path(relative)
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            _fail("private evidence path must not traverse symlinks")
    resolved = current.resolve(strict=True)
    if not _is_relative_to(resolved, root):
        _fail("private evidence path escaped the evidence root")
    if not resolved.is_file():
        _fail("private evidence path must name a regular file")
    size = resolved.stat().st_size
    if size <= 0:
        _fail("private evidence must not be empty")
    if size > MAX_PRIVATE_BYTES:
        _fail(f"private evidence exceeds {MAX_PRIVATE_BYTES} bytes")
    return resolved.read_bytes()


def _read_private_json(root: Path, relative: str, label: str) -> tuple[dict[str, Any], bytes]:
    raw = _read_private(root, relative)
    try:
        decoded = raw.decode("utf-8")
        value = json.loads(decoded, object_pairs_hook=_pairs_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"{label} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        _fail(f"{label} must be a JSON object")
    return value, raw


def _read_public_receipt(path_arg: str) -> tuple[dict[str, Any], bytes]:
    path = Path(path_arg)
    if not path.is_absolute():
        _fail("receipt paths must be absolute")
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or resolved.is_symlink():
        _fail("receipt must be a nonsymlink regular file")
    raw = resolved.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError("receipt must be valid UTF-8 JSON") from exc
    if canonical_bytes(value) != raw:
        _fail("receipt must use canonical JSON encoding")
    validate_receipt(value)
    return value, raw


def _base_facts(signal: str, legal_acceptance: str) -> dict[str, Any]:
    return {
        "buyer_signal": signal,
        "legal_acceptance": legal_acceptance,
        "invoice_state": "NOT_LANDED",
        "authorization_state": "NOT_LANDED",
        "settlement_state": "NOT_LANDED",
        "payout_state": "NOT_LANDED",
        "bank_available_state": "NOT_LANDED",
        "delivery_started": False,
        "clock_started": False,
        "collected_cash_usd": 0,
    }


def _receipt_digest_payload(receipt: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in receipt.items() if key not in {"receipt_id", "idempotency_key"}}


def _seal_receipt(receipt: dict[str, Any], prefix: str) -> dict[str, Any]:
    digest = sha256_bytes(canonical_bytes(_receipt_digest_payload(receipt)))
    receipt["idempotency_key"] = f"sha256:{digest}"
    receipt["receipt_id"] = f"{prefix}-{digest[:24]}"
    return receipt


def _intent_metadata(value: dict[str, Any]) -> dict[str, Any]:
    value = _exact_keys(
        value,
        {"buyer_ref", "message_ref", "received_at", "classification", "operator_attestation"},
        "intent metadata",
    )
    _buyer_ref(value["buyer_ref"])
    _message_ref(value["message_ref"])
    _parse_time(value["received_at"], "received_at")
    if value["classification"] != "POSITIVE":
        _fail("intent classification must be POSITIVE")
    if value["operator_attestation"] != INTENT_ATTESTATION:
        _fail("intent operator attestation is missing or invalid")
    return value


def _terms_metadata(value: dict[str, Any]) -> dict[str, Any]:
    value = _exact_keys(
        value,
        {"buyer_ref", "message_ref", "sent_at", "classification", "operator_attestation"},
        "terms metadata",
    )
    _buyer_ref(value["buyer_ref"])
    _message_ref(value["message_ref"])
    _parse_time(value["sent_at"], "sent_at")
    if value["classification"] != "TERMS_ISSUED":
        _fail("terms classification must be TERMS_ISSUED")
    if value["operator_attestation"] != TERMS_ATTESTATION:
        _fail("terms operator attestation is missing or invalid")
    return value


def _acceptance_metadata(value: dict[str, Any]) -> dict[str, Any]:
    value = _exact_keys(
        value,
        {
            "buyer_ref",
            "message_ref",
            "in_reply_to",
            "received_at",
            "classification",
            "operator_attestation",
        },
        "acceptance metadata",
    )
    _buyer_ref(value["buyer_ref"])
    _message_ref(value["message_ref"])
    _message_ref(value["in_reply_to"])
    _parse_time(value["received_at"], "received_at")
    if value["classification"] != "WRITTEN_ACCEPTANCE":
        _fail("acceptance classification must be WRITTEN_ACCEPTANCE")
    if value["operator_attestation"] != ACCEPTANCE_ATTESTATION:
        _fail("acceptance operator attestation is missing or invalid")
    return value


def _terms(value: dict[str, Any]) -> dict[str, Any]:
    value = _exact_keys(
        value,
        {
            "buyer_ref",
            "offer_id",
            "currency",
            "fixed_amount",
            "given",
            "when",
            "then",
            "environment",
            "terms_sent_at",
            "window_start",
            "window_end",
            "timezone",
            "refund_choice",
            "proof_claims",
            "exclusions",
            "contract_nonce",
        },
        "terms packet",
    )
    _buyer_ref(value["buyer_ref"])
    if value["offer_id"] != OFFER_ID or value["currency"] != CURRENCY:
        _fail("terms packet offer or currency does not match the fixed offer")
    if type(value["fixed_amount"]) is not int or value["fixed_amount"] != FIXED_AMOUNT:
        _fail("terms packet fixed_amount must be 2500")
    for key in ("given", "when", "then", "environment"):
        _validate_public_safe_text(value[key], key)
    terms_sent = _parse_time(value["terms_sent_at"], "terms_sent_at")
    window_start = _parse_time(value["window_start"], "window_start")
    window_end = _parse_time(value["window_end"], "window_end")
    if value["timezone"] != TIMEZONE:
        _fail("terms timezone must be America/New_York")
    for key in ("window_start", "window_end"):
        if not (value[key].endswith("-04:00") or value[key].endswith("-05:00")):
            _fail(f"{key} must carry an Eastern Time UTC offset")
    if not window_start < window_end:
        _fail("window_start must be before window_end")
    if terms_sent > window_start:
        _fail("terms must be sent no later than the delivery window start")
    if value["refund_choice"] not in REFUND_CHOICES:
        _fail("refund_choice is not an allowed binary term")
    if value["proof_claims"] != PROOF_CLAIMS:
        _fail("proof_claims must match the measured local proof exactly")
    if value["exclusions"] != EXCLUSIONS:
        _fail("exclusions must match the fixed offer exactly")
    if not isinstance(value["contract_nonce"], str) or not NONCE_RE.fullmatch(value["contract_nonce"]):
        _fail("contract_nonce must be nonce_<32 lowercase hex>")
    return value


def build_intent(reply: bytes, metadata: dict[str, Any]) -> dict[str, Any]:
    metadata = _intent_metadata(metadata)
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "receipt_id": "",
        "stage": "PURCHASE_INTENT",
        "state": "RECORDED",
        "offer_id": OFFER_ID,
        "currency": CURRENCY,
        "fixed_amount": FIXED_AMOUNT,
        "buyer_ref": metadata["buyer_ref"],
        "idempotency_key": "",
        "created_at": metadata["received_at"],
        "source": {
            "message_ref": metadata["message_ref"],
            "message_sha256": sha256_bytes(reply),
            "received_at": metadata["received_at"],
            "classification": "POSITIVE",
            "operator_attestation": INTENT_ATTESTATION,
        },
        "terms": None,
        "lineage": {
            "intent_receipt_id": None,
            "terms_receipt_id": None,
            "prior_receipt_sha256": None,
            "terms_packet_sha256": None,
            "contract_id": None,
            "contract_sha256": None,
        },
        "facts": _base_facts("PURCHASE_INTENT", "NOT_LANDED"),
        "next_stage": "ISSUE_BINARY_TERMS",
    }
    return _seal_receipt(receipt, "purchase-intent")


def _public_terms(terms: dict[str, Any]) -> dict[str, Any]:
    return {
        key: terms[key]
        for key in (
            "offer_id",
            "currency",
            "fixed_amount",
            "given",
            "when",
            "then",
            "environment",
            "terms_sent_at",
            "window_start",
            "window_end",
            "timezone",
            "refund_choice",
            "proof_claims",
            "exclusions",
            "contract_nonce",
        )
    }


def build_terms_issued(
    intent: dict[str, Any],
    intent_raw: bytes,
    terms: dict[str, Any],
    terms_raw: bytes,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    validate_receipt(intent)
    if intent["stage"] != "PURCHASE_INTENT":
        _fail("issue-terms requires a PURCHASE_INTENT receipt")
    terms = _terms(terms)
    metadata = _terms_metadata(metadata)
    if metadata["buyer_ref"] != intent["buyer_ref"] or terms["buyer_ref"] != intent["buyer_ref"]:
        _fail("buyer_ref must match across intent, terms, and terms metadata")
    intent_at = _parse_time(intent["source"]["received_at"], "intent received_at")
    terms_sent_at = _parse_time(terms["terms_sent_at"], "terms_sent_at")
    metadata_sent_at = _parse_time(metadata["sent_at"], "sent_at")
    if terms_sent_at != metadata_sent_at or intent_at > terms_sent_at:
        _fail("terms must be issued at or after intent with one exact sent_at")
    contract_sha = sha256_bytes(terms_raw)
    contract_id = f"contract-{contract_sha[:24]}"
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "receipt_id": "",
        "stage": "TERMS_ISSUED",
        "state": "RECORDED",
        "offer_id": OFFER_ID,
        "currency": CURRENCY,
        "fixed_amount": FIXED_AMOUNT,
        "buyer_ref": intent["buyer_ref"],
        "idempotency_key": "",
        "created_at": metadata["sent_at"],
        "source": {
            "message_ref": metadata["message_ref"],
            "message_sha256": contract_sha,
            "received_at": metadata["sent_at"],
            "classification": "TERMS_ISSUED",
            "operator_attestation": TERMS_ATTESTATION,
        },
        "terms": _public_terms(terms),
        "lineage": {
            "intent_receipt_id": intent["receipt_id"],
            "terms_receipt_id": None,
            "prior_receipt_sha256": sha256_bytes(intent_raw),
            "terms_packet_sha256": contract_sha,
            "contract_id": contract_id,
            "contract_sha256": contract_sha,
        },
        "facts": _base_facts("TERMS_ISSUED", "NOT_LANDED"),
        "next_stage": "EXACT_WRITTEN_ACCEPTANCE",
    }
    return _seal_receipt(receipt, "terms-issued")


def build_acceptance(
    terms_receipt: dict[str, Any],
    terms_receipt_raw: bytes,
    written_acceptance: bytes,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    validate_receipt(terms_receipt)
    if terms_receipt["stage"] != "TERMS_ISSUED":
        _fail("record-acceptance requires a TERMS_ISSUED receipt")
    metadata = _acceptance_metadata(metadata)
    if metadata["buyer_ref"] != terms_receipt["buyer_ref"]:
        _fail("buyer_ref must match the terms-issued receipt")
    if metadata["in_reply_to"] != terms_receipt["source"]["message_ref"]:
        _fail("written acceptance must reply to the exact terms message")
    if metadata["message_ref"] == terms_receipt["source"]["message_ref"]:
        _fail("written acceptance must have a distinct message_ref")
    terms_sent_at = _parse_time(terms_receipt["source"]["received_at"], "terms sent_at")
    accepted_at = _parse_time(metadata["received_at"], "acceptance received_at")
    if not terms_sent_at < accepted_at:
        _fail("written acceptance must arrive after terms were issued")
    if accepted_at > _parse_time(terms_receipt["terms"]["window_end"], "window_end"):
        _fail("written acceptance arrived after the contract window expired")
    contract_id = terms_receipt["lineage"]["contract_id"]
    contract_sha = terms_receipt["lineage"]["contract_sha256"]
    nonce = terms_receipt["terms"]["contract_nonce"]
    expected = f"ACCEPT {contract_id} {contract_sha} {nonce}\n".encode("ascii")
    if written_acceptance != expected:
        _fail("written acceptance must be the exact ASCII contract token")
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "receipt_id": "",
        "stage": "ACCEPTANCE",
        "state": "ACCEPTED",
        "offer_id": OFFER_ID,
        "currency": CURRENCY,
        "fixed_amount": FIXED_AMOUNT,
        "buyer_ref": terms_receipt["buyer_ref"],
        "idempotency_key": "",
        "created_at": metadata["received_at"],
        "source": {
            "message_ref": metadata["message_ref"],
            "message_sha256": sha256_bytes(written_acceptance),
            "received_at": metadata["received_at"],
            "classification": "WRITTEN_ACCEPTANCE",
            "operator_attestation": ACCEPTANCE_ATTESTATION,
        },
        "terms": terms_receipt["terms"],
        "lineage": {
            "intent_receipt_id": terms_receipt["lineage"]["intent_receipt_id"],
            "terms_receipt_id": terms_receipt["receipt_id"],
            "prior_receipt_sha256": sha256_bytes(terms_receipt_raw),
            "terms_packet_sha256": terms_receipt["lineage"]["terms_packet_sha256"],
            "contract_id": contract_id,
            "contract_sha256": contract_sha,
        },
        "facts": _base_facts("EXACT_WRITTEN_ACCEPTANCE", "OWNER_REPORTED"),
        "next_stage": "OWNER_HOSTED_INVOICE",
    }
    return _seal_receipt(receipt, "acceptance")


def validate_receipt(receipt: Any) -> None:
    receipt = _exact_keys(
        receipt,
        {
            "schema_version",
            "kind",
            "receipt_id",
            "stage",
            "state",
            "offer_id",
            "currency",
            "fixed_amount",
            "buyer_ref",
            "idempotency_key",
            "created_at",
            "source",
            "terms",
            "lineage",
            "facts",
            "next_stage",
        },
        "receipt",
    )
    if receipt["schema_version"] != SCHEMA_VERSION or receipt["kind"] != KIND:
        _fail("receipt schema version or kind is invalid")
    if receipt["offer_id"] != OFFER_ID or receipt["currency"] != CURRENCY:
        _fail("receipt offer or currency is invalid")
    if type(receipt["fixed_amount"]) is not int or receipt["fixed_amount"] != FIXED_AMOUNT:
        _fail("receipt fixed_amount is invalid")
    _buyer_ref(receipt["buyer_ref"])
    _parse_time(receipt["created_at"], "created_at")
    source = _exact_keys(
        receipt["source"],
        {"message_ref", "message_sha256", "received_at", "classification", "operator_attestation"},
        "source",
    )
    _message_ref(source["message_ref"])
    if not isinstance(source["message_sha256"], str) or not HEX_RE.fullmatch(source["message_sha256"]):
        _fail("source message_sha256 is invalid")
    _parse_time(source["received_at"], "source received_at")
    if receipt["created_at"] != source["received_at"]:
        _fail("created_at must equal the source event time")
    lineage = _exact_keys(
        receipt["lineage"],
        {
            "intent_receipt_id",
            "terms_receipt_id",
            "prior_receipt_sha256",
            "terms_packet_sha256",
            "contract_id",
            "contract_sha256",
        },
        "lineage",
    )
    facts = _exact_keys(
        receipt["facts"],
        {
            "buyer_signal",
            "legal_acceptance",
            "invoice_state",
            "authorization_state",
            "settlement_state",
            "payout_state",
            "bank_available_state",
            "delivery_started",
            "clock_started",
            "collected_cash_usd",
        },
        "facts",
    )
    expected_common = {
        "invoice_state": "NOT_LANDED",
        "authorization_state": "NOT_LANDED",
        "settlement_state": "NOT_LANDED",
        "payout_state": "NOT_LANDED",
        "bank_available_state": "NOT_LANDED",
        "delivery_started": False,
        "clock_started": False,
        "collected_cash_usd": 0,
    }
    for key, expected in expected_common.items():
        if facts[key] != expected or type(facts[key]) is not type(expected):
            _fail(f"receipt fact {key} must be {expected!r}")
    stage = receipt["stage"]
    if stage == "PURCHASE_INTENT":
        if receipt["state"] != "RECORDED" or receipt["terms"] is not None:
            _fail("purchase intent must be RECORDED with no terms")
        if source["classification"] != "POSITIVE" or source["operator_attestation"] != INTENT_ATTESTATION:
            _fail("purchase intent source classification or attestation is invalid")
        if any(lineage[key] is not None for key in lineage):
            _fail("purchase intent must not claim prior lineage")
        if facts["buyer_signal"] != "PURCHASE_INTENT" or facts["legal_acceptance"] != "NOT_LANDED":
            _fail("purchase intent facts are invalid")
        if receipt["next_stage"] != "ISSUE_BINARY_TERMS":
            _fail("purchase intent next_stage is invalid")
        prefix = "purchase-intent"
    elif stage == "TERMS_ISSUED":
        if receipt["state"] != "RECORDED" or not isinstance(receipt["terms"], dict):
            _fail("terms-issued receipt must be RECORDED with exact terms")
        _terms({"buyer_ref": receipt["buyer_ref"], **receipt["terms"]})
        if source["classification"] != "TERMS_ISSUED" or source["operator_attestation"] != TERMS_ATTESTATION:
            _fail("terms-issued source classification or attestation is invalid")
        if not isinstance(lineage["intent_receipt_id"], str) or not lineage["intent_receipt_id"].startswith("purchase-intent-"):
            _fail("terms-issued intent_receipt_id is invalid")
        if lineage["terms_receipt_id"] is not None:
            _fail("terms-issued receipt must not identify a later receipt")
        for key in ("prior_receipt_sha256", "terms_packet_sha256", "contract_sha256"):
            if not isinstance(lineage[key], str) or not HEX_RE.fullmatch(lineage[key]):
                _fail(f"terms-issued {key} is invalid")
        if lineage["contract_sha256"] != lineage["terms_packet_sha256"]:
            _fail("contract hash must equal the exact issued terms commitment")
        if not isinstance(lineage["contract_id"], str) or not CONTRACT_RE.fullmatch(lineage["contract_id"]):
            _fail("terms-issued contract_id is invalid")
        if lineage["contract_id"] != f"contract-{lineage['contract_sha256'][:24]}":
            _fail("contract_id does not match contract_sha256")
        if facts["buyer_signal"] != "TERMS_ISSUED" or facts["legal_acceptance"] != "NOT_LANDED":
            _fail("terms-issued facts are invalid")
        if receipt["next_stage"] != "EXACT_WRITTEN_ACCEPTANCE":
            _fail("terms-issued next_stage is invalid")
        prefix = "terms-issued"
    elif stage == "ACCEPTANCE":
        if receipt["state"] != "ACCEPTED" or not isinstance(receipt["terms"], dict):
            _fail("acceptance must be ACCEPTED with exact terms")
        terms_with_buyer = {"buyer_ref": receipt["buyer_ref"], **receipt["terms"]}
        _terms(terms_with_buyer)
        if source["classification"] != "WRITTEN_ACCEPTANCE" or source["operator_attestation"] != ACCEPTANCE_ATTESTATION:
            _fail("acceptance source classification or attestation is invalid")
        if not isinstance(lineage["intent_receipt_id"], str) or not lineage["intent_receipt_id"].startswith("purchase-intent-"):
            _fail("acceptance intent_receipt_id is invalid")
        if not isinstance(lineage["terms_receipt_id"], str) or not lineage["terms_receipt_id"].startswith("terms-issued-"):
            _fail("acceptance terms_receipt_id is invalid")
        for key in ("prior_receipt_sha256", "terms_packet_sha256", "contract_sha256"):
            if not isinstance(lineage[key], str) or not HEX_RE.fullmatch(lineage[key]):
                _fail(f"acceptance {key} is invalid")
        if not isinstance(lineage["contract_id"], str) or not CONTRACT_RE.fullmatch(lineage["contract_id"]):
            _fail("acceptance contract_id is invalid")
        if lineage["contract_sha256"] != lineage["terms_packet_sha256"]:
            _fail("acceptance contract hash must equal terms commitment")
        if lineage["contract_id"] != f"contract-{lineage['contract_sha256'][:24]}":
            _fail("acceptance contract_id does not match contract_sha256")
        if facts["buyer_signal"] != "EXACT_WRITTEN_ACCEPTANCE" or facts["legal_acceptance"] != "OWNER_REPORTED":
            _fail("acceptance facts are invalid")
        if receipt["next_stage"] != "OWNER_HOSTED_INVOICE":
            _fail("acceptance next_stage is invalid")
        prefix = "acceptance"
    else:
        _fail("receipt stage is invalid")
    digest = sha256_bytes(canonical_bytes(_receipt_digest_payload(receipt)))
    if receipt["idempotency_key"] != f"sha256:{digest}":
        _fail("receipt idempotency_key does not match its canonical facts")
    if receipt["receipt_id"] != f"{prefix}-{digest[:24]}":
        _fail("receipt_id does not match its canonical facts")


def _write_append_only(path_arg: str, payload: dict[str, Any], evidence_root: Path) -> None:
    path = Path(path_arg)
    if not path.is_absolute():
        _fail("output path must be absolute")
    target = path.resolve(strict=False)
    if _is_relative_to(target, evidence_root):
        _fail("public receipt output must not be inside the private evidence root")
    data = canonical_bytes(payload)
    if target.exists():
        if target.is_symlink() or not target.is_file():
            _fail("existing output is not a nonsymlink regular file")
        if target.read_bytes() != data:
            _fail("append-only output already exists with different bytes")
        return
    if not target.parent.exists() or not target.parent.is_dir():
        _fail("output parent directory must already exist")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def record_intent(args: argparse.Namespace) -> dict[str, Any]:
    root = _validated_root(args.evidence_root)
    reply = _read_private(root, args.reply)
    metadata, _ = _read_private_json(root, args.metadata, "intent metadata")
    receipt = build_intent(reply, metadata)
    validate_receipt(receipt)
    _write_append_only(args.out, receipt, root)
    return receipt


def issue_terms(args: argparse.Namespace) -> dict[str, Any]:
    root = _validated_root(args.evidence_root)
    intent, intent_raw = _read_public_receipt(args.intent_receipt)
    terms, terms_raw = _read_private_json(root, args.terms, "terms packet")
    metadata, _ = _read_private_json(root, args.metadata, "terms metadata")
    receipt = build_terms_issued(
        intent,
        intent_raw,
        terms,
        terms_raw,
        metadata,
    )
    validate_receipt(receipt)
    _write_append_only(args.out, receipt, root)
    return receipt


def record_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    root = _validated_root(args.evidence_root)
    terms_receipt, terms_receipt_raw = _read_public_receipt(args.terms_receipt)
    written_acceptance = _read_private(root, args.written_acceptance)
    metadata, _ = _read_private_json(root, args.metadata, "acceptance metadata")
    receipt = build_acceptance(
        terms_receipt,
        terms_receipt_raw,
        written_acceptance,
        metadata,
    )
    validate_receipt(receipt)
    _write_append_only(args.out, receipt, root)
    return receipt


def reduce_state(args: argparse.Namespace) -> dict[str, Any]:
    intent, intent_raw = _read_public_receipt(args.intent_receipt)
    terms, terms_raw = _read_public_receipt(args.terms_receipt)
    acceptance, _ = _read_public_receipt(args.acceptance_receipt)
    if intent["stage"] != "PURCHASE_INTENT" or terms["stage"] != "TERMS_ISSUED" or acceptance["stage"] != "ACCEPTANCE":
        _fail("reducer requires intent, terms-issued, then acceptance receipts")
    if len({intent["buyer_ref"], terms["buyer_ref"], acceptance["buyer_ref"]}) != 1:
        _fail("reducer buyer_ref mismatch")
    if terms["lineage"]["intent_receipt_id"] != intent["receipt_id"]:
        _fail("terms-issued receipt does not identify the supplied intent")
    if terms["lineage"]["prior_receipt_sha256"] != sha256_bytes(intent_raw):
        _fail("terms-issued prior-receipt hash mismatch")
    if acceptance["lineage"]["terms_receipt_id"] != terms["receipt_id"]:
        _fail("acceptance does not identify the supplied terms receipt")
    if acceptance["lineage"]["prior_receipt_sha256"] != sha256_bytes(terms_raw):
        _fail("acceptance prior-receipt hash mismatch")
    if acceptance["lineage"]["contract_id"] != terms["lineage"]["contract_id"]:
        _fail("acceptance contract_id mismatch")
    if acceptance["lineage"]["contract_sha256"] != terms["lineage"]["contract_sha256"]:
        _fail("acceptance contract hash mismatch")
    return {
        "schema_version": SCHEMA_VERSION,
        "buyer_ref": acceptance["buyer_ref"],
        "state": "ACCEPTED_OWNER_REPORTED",
        "intent_receipt_id": intent["receipt_id"],
        "terms_receipt_id": terms["receipt_id"],
        "acceptance_receipt_id": acceptance["receipt_id"],
        "invoice_state": "NOT_LANDED",
        "authorization_state": "NOT_LANDED",
        "settlement_state": "NOT_LANDED",
        "payout_state": "NOT_LANDED",
        "bank_available_state": "NOT_LANDED",
        "delivery_started": False,
        "clock_started": False,
        "collected_cash_usd": 0,
    }


def invoice_gate(args: argparse.Namespace) -> dict[str, Any]:
    root = _validated_root(args.evidence_root)
    state = reduce_state(args)
    intent, _ = _read_public_receipt(args.intent_receipt)
    terms, _ = _read_public_receipt(args.terms_receipt)
    acceptance, _ = _read_public_receipt(args.acceptance_receipt)
    reply = _read_private(root, args.reply)
    terms_raw = _read_private(root, args.terms)
    written_acceptance = _read_private(root, args.written_acceptance)
    if intent["source"]["message_sha256"] != sha256_bytes(reply):
        _fail("intent private evidence hash mismatch")
    if terms["lineage"]["terms_packet_sha256"] != sha256_bytes(terms_raw):
        _fail("terms private evidence hash mismatch")
    if acceptance["source"]["message_sha256"] != sha256_bytes(written_acceptance):
        _fail("written-acceptance private evidence hash mismatch")
    return {
        "status": "READY_FOR_OWNER_HOSTED_INVOICE",
        "buyer_ref": state["buyer_ref"],
        "acceptance_receipt_id": acceptance["receipt_id"],
        "invoice_state": "NOT_LANDED",
        "authorization_state": "NOT_LANDED",
        "settlement_state": "NOT_LANDED",
        "payout_state": "NOT_LANDED",
        "bank_available_state": "NOT_LANDED",
        "collected_cash_usd": 0,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    intent = subparsers.add_parser("record-intent")
    intent.add_argument("--evidence-root", required=True)
    intent.add_argument("--reply", required=True, help="relative path under evidence root")
    intent.add_argument("--metadata", required=True, help="relative path under evidence root")
    intent.add_argument("--out", required=True, help="absolute append-only public receipt path")
    intent.set_defaults(handler=record_intent)

    terms = subparsers.add_parser("issue-terms")
    terms.add_argument("--evidence-root", required=True)
    terms.add_argument("--intent-receipt", required=True, help="absolute public intent receipt path")
    terms.add_argument("--terms", required=True, help="relative path under evidence root")
    terms.add_argument("--metadata", required=True, help="relative path under evidence root")
    terms.add_argument("--out", required=True, help="absolute append-only public receipt path")
    terms.set_defaults(handler=issue_terms)

    accept = subparsers.add_parser("record-acceptance")
    accept.add_argument("--evidence-root", required=True)
    accept.add_argument("--terms-receipt", required=True, help="absolute public terms receipt path")
    accept.add_argument("--written-acceptance", required=True, help="relative path under evidence root")
    accept.add_argument("--metadata", required=True, help="relative path under evidence root")
    accept.add_argument("--out", required=True, help="absolute append-only public receipt path")
    accept.set_defaults(handler=record_acceptance)

    reducer = subparsers.add_parser("reduce")
    reducer.add_argument("--intent-receipt", required=True)
    reducer.add_argument("--terms-receipt", required=True)
    reducer.add_argument("--acceptance-receipt", required=True)
    reducer.set_defaults(handler=reduce_state)

    gate = subparsers.add_parser("invoice-gate")
    gate.add_argument("--evidence-root", required=True)
    gate.add_argument("--intent-receipt", required=True)
    gate.add_argument("--terms-receipt", required=True)
    gate.add_argument("--acceptance-receipt", required=True)
    gate.add_argument("--reply", required=True, help="relative path under evidence root")
    gate.add_argument("--terms", required=True, help="relative path under evidence root")
    gate.add_argument("--written-acceptance", required=True, help="relative path under evidence root")
    gate.set_defaults(handler=invoice_gate)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        result = args.handler(args)
        print(canonical_bytes(result).decode("utf-8"), end="")
        return 0
    except (AcceptanceError, FileNotFoundError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
