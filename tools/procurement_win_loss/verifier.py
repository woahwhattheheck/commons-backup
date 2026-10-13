#!/usr/bin/env python3
"""Independent semantic verifier for procurement win/loss receipts."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .compiler import RECEIPT_SCHEMA, SIGNAL_TO_OUTCOME, OutcomeError, normalize_record


class VerificationError(ValueError):
    """Raised when a receipt is not bound to the supplied evidence."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _expected_semantics(record: dict[str, Any]) -> tuple[str, list[str], list[dict[str, Any]]]:
    evidence = record["evidence"]
    current = [row for row in evidence if row["evidence_status"] == "CURRENT"]
    terminal = [row for row in current if SIGNAL_TO_OUTCOME[row["decision_signal"]] != "UNKNOWN"]
    outcomes = {SIGNAL_TO_OUTCOME[row["decision_signal"]] for row in terminal}
    holds: set[str] = set()
    if len(outcomes) == 1:
        outcome = next(iter(outcomes))
    elif len(outcomes) > 1:
        outcome = "UNKNOWN"
        holds.add("conflicting_current_terminal_evidence")
    else:
        outcome = "UNKNOWN"

    old_terminal = [
        row for row in evidence
        if row["evidence_status"] != "CURRENT" and SIGNAL_TO_OUTCOME[row["decision_signal"]] != "UNKNOWN"
    ]
    if old_terminal and not terminal:
        holds.add("noncurrent_terminal_evidence")
    if len(outcomes) == 1:
        candidate = next(iter(outcomes))
        if any(SIGNAL_TO_OUTCOME[row["decision_signal"]] != candidate for row in old_terminal):
            outcome = "UNKNOWN"
            holds.add("conflicting_noncurrent_terminal_evidence")
    if terminal:
        newest = max(row["observed_at"] for row in terminal)
        if any(row["decision_signal"] == "PENDING" and row["observed_at"] > newest for row in current):
            outcome = "UNKNOWN"
            holds.add("later_pending_after_terminal")

    if outcome == "UNKNOWN":
        basis = terminal or current or evidence
    else:
        basis = [row for row in terminal if SIGNAL_TO_OUTCOME[row["decision_signal"]] == outcome]
    return outcome, sorted(holds), basis


def verify_record(raw_record: Any, raw_receipt: Any) -> dict[str, Any]:
    try:
        record = normalize_record(raw_record)
    except OutcomeError as exc:
        raise VerificationError(f"invalid source evidence: {exc}") from exc
    if type(raw_receipt) is not dict:
        raise VerificationError("receipt must be an object")
    receipt = raw_receipt
    required = {
        "schema", "opportunity_id", "compiled_at", "outcome", "hold_reasons",
        "known_facts", "rationale", "unknowns", "authority",
        "normalized_input_sha256", "receipt_sha256",
    }
    if set(receipt) != required:
        raise VerificationError("receipt fields differ from the fixed schema")
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise VerificationError("receipt schema mismatch")
    if receipt.get("opportunity_id") != record["opportunity_id"]:
        raise VerificationError("opportunity_id mismatch")
    if receipt.get("compiled_at") != record["compiled_at"]:
        raise VerificationError("compiled_at mismatch")
    if receipt.get("outcome") not in {"WON", "LOST", "NO_DECISION", "UNKNOWN"}:
        raise VerificationError("unsupported outcome")
    if receipt.get("normalized_input_sha256") != _digest(record):
        raise VerificationError("normalized input digest mismatch")

    given_receipt_digest = receipt.get("receipt_sha256")
    if type(given_receipt_digest) is not str or len(given_receipt_digest) != 64:
        raise VerificationError("receipt_sha256 malformed")
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256")
    if _digest(unsigned) != given_receipt_digest:
        raise VerificationError("receipt_sha256 mismatch")

    expected_outcome, expected_holds, basis = _expected_semantics(record)
    if receipt["outcome"] != expected_outcome:
        raise VerificationError("semantic outcome mismatch")
    if receipt["hold_reasons"] != expected_holds:
        raise VerificationError("hold reason mismatch")

    expected_facts = [
        {
            "evidence_id": row["evidence_id"],
            "source_kind": row["source_kind"],
            "source_digest_sha256": row["source_digest_sha256"],
            "observed_at": row["observed_at"],
            "evidence_status": row["evidence_status"],
            "decision_signal": row["decision_signal"],
            "mapped_outcome": SIGNAL_TO_OUTCOME[row["decision_signal"]],
        }
        for row in record["evidence"]
    ]
    if receipt["known_facts"] != expected_facts:
        raise VerificationError("known_facts mismatch")

    expected_statements = [
        {
            "evidence_id": row["evidence_id"],
            "source_digest_sha256": row["source_digest_sha256"],
            "text": row["rationale"]["text"],
        }
        for row in basis
        if row["rationale"]["status"] == "STATED"
    ]
    expected_unknown_ids = sorted(
        row["evidence_id"] for row in basis if row["rationale"]["status"] == "UNKNOWN"
    )
    if expected_statements and expected_unknown_ids:
        expected_rationale_status = "PARTIAL"
    elif expected_statements:
        expected_rationale_status = "STATED"
    else:
        expected_rationale_status = "UNKNOWN"
    expected_rationale = {
        "status": expected_rationale_status,
        "statements": expected_statements,
        "unknown_evidence_ids": expected_unknown_ids,
    }
    if receipt["rationale"] != expected_rationale:
        raise VerificationError("rationale mismatch")

    expected_unknowns = []
    if expected_outcome == "UNKNOWN":
        expected_unknowns.append("outcome")
    if expected_rationale_status != "STATED":
        expected_unknowns.append("rationale")
    if receipt["unknowns"] != expected_unknowns:
        raise VerificationError("unknowns mismatch")

    expected_authority = {
        "buyer_contact_authorized": False,
        "debrief_request_authorized": False,
        "outbound_authorized": False,
        "payment_authorized": False,
        "contract_authorized": False,
        "revenue_recognized": False,
        "causal_inference_authorized": False,
    }
    if receipt["authority"] != expected_authority:
        raise VerificationError("authority boundary mismatch")

    return {
        "status": "VERIFIED",
        "schema": RECEIPT_SCHEMA,
        "opportunity_id": record["opportunity_id"],
        "outcome": expected_outcome,
        "receipt_sha256": given_receipt_digest,
    }
