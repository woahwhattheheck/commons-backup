#!/usr/bin/env python3
"""Semantic verifier for procurement remediation receipts."""
from __future__ import annotations

from typing import Any

from .core import RECEIPT_SCHEMA, RemediationError, digest, normalize_input
from .policy import compile_plan


class RemediationVerificationError(ValueError):
    """Raised when a remediation receipt is not bound to its source packet."""


def verify_plan(raw_input: Any, raw_receipt: Any) -> dict[str, Any]:
    try:
        normalized = normalize_input(raw_input)
    except RemediationError as exc:
        raise RemediationVerificationError(f"invalid remediation input: {exc}") from exc
    if type(raw_receipt) is not dict:
        raise RemediationVerificationError("receipt must be an object")

    required = {
        "schema",
        "opportunity_id",
        "compiled_at",
        "source_receipt_sha256",
        "source_outcome",
        "source_hold_reasons",
        "source_evidence",
        "status",
        "buyer_reasons",
        "internal_hypotheses",
        "remediation_gaps",
        "unattributed_source_statement_ids",
        "hold_reasons",
        "authority",
        "normalized_input_sha256",
        "receipt_sha256",
    }
    if set(raw_receipt) != required:
        raise RemediationVerificationError("receipt fields differ from fixed schema")
    if raw_receipt.get("schema") != RECEIPT_SCHEMA:
        raise RemediationVerificationError("receipt schema mismatch")
    if raw_receipt.get("normalized_input_sha256") != digest(normalized):
        raise RemediationVerificationError("normalized input digest mismatch")

    given_digest = raw_receipt.get("receipt_sha256")
    if type(given_digest) is not str or len(given_digest) != 64:
        raise RemediationVerificationError("receipt_sha256 malformed")
    unsigned = dict(raw_receipt)
    unsigned.pop("receipt_sha256")
    if digest(unsigned) != given_digest:
        raise RemediationVerificationError("receipt_sha256 mismatch")

    # Recompile from the independently revalidated source packet and require
    # exact semantic equality under the public truth-ceiling policy. This
    # catches source projections, status, attribution, basis, authority,
    # source-receipt and ordering tampering, not merely hash edits.
    expected = compile_plan(normalized)
    if raw_receipt != expected:
        raise RemediationVerificationError("semantic remediation receipt mismatch")

    return {
        "status": "VERIFIED",
        "schema": RECEIPT_SCHEMA,
        "opportunity_id": raw_receipt["opportunity_id"],
        "remediation_status": raw_receipt["status"],
        "source_receipt_sha256": raw_receipt["source_receipt_sha256"],
        "receipt_sha256": given_digest,
    }
