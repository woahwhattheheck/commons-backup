#!/usr/bin/env python3
"""Receipt, semantic, and current-time verification."""
from __future__ import annotations

import hmac
from typing import Any

from workshare_contract import (
    CURRENT_VERIFICATION_SCHEMA, MODE_CURRENT, MODE_HISTORICAL, MODE_UNTRUSTED,
    REPORT_SCHEMA, SCHEMA_VERSION, ContractError, _REPORT_KEYS, _external_authority,
    _format_utc, _parse_utc, _require_exact_keys, _require_int, _require_sha,
    _require_str, _sha256_value, _utc_now, canonical_json_bytes,
)
from workshare_assessment import _compile

def _verify_receipt(report: Any) -> dict[str, Any]:
    value = _require_exact_keys(report, _REPORT_KEYS, "report")
    schema = _require_str(value["schema"], "report.schema", max_len=96)
    if schema != REPORT_SCHEMA:
        raise ContractError("report.schema drift")
    if _require_int(value["schema_version"], "report.schema_version", low=SCHEMA_VERSION, high=SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ContractError("report.schema_version drift")
    receipt = _require_sha(value["receipt_sha256"], "report.receipt_sha256")
    unsigned = dict(value)
    del unsigned["receipt_sha256"]
    expected = _sha256_value(unsigned)
    if not hmac.compare_digest(receipt, expected):
        raise ContractError("report receipt mismatch")
    return value


def verify_report_integrity(
    report: Any,
    *,
    trusted_authority_sha256: str | None = None,
) -> dict[str, Any]:
    """Verify receipt plus a full semantic recompile.

    Without ``trusted_authority_sha256`` this proves only internal/historical
    integrity. It never proves current authority or external provenance.
    """

    value = _verify_receipt(report)
    mode = _require_str(value["mode"], "report.mode", max_len=64)
    evaluated_at = _parse_utc(value["evaluated_at"], "report.evaluated_at")
    embedded_root = _require_sha(value["authority_root_sha256"], "report.authority_root_sha256")
    if trusted_authority_sha256 is not None:
        trusted_root = _require_sha(trusted_authority_sha256, "trusted_authority_sha256")
        if not hmac.compare_digest(embedded_root, trusted_root):
            raise ContractError("trusted authority root mismatch")
    else:
        trusted_root = embedded_root

    if mode == MODE_CURRENT:
        expected = _compile(
            value["candidate"],
            value["evidence_authority"],
            mode=MODE_CURRENT,
            evaluated_at=evaluated_at,
            trusted_authority_sha256=trusted_root,
        )
    elif mode == MODE_HISTORICAL:
        expected = _compile(
            value["candidate"],
            value["evidence_authority"],
            mode=MODE_HISTORICAL,
            evaluated_at=evaluated_at,
            trusted_authority_sha256=trusted_root,
        )
    elif mode == MODE_UNTRUSTED:
        expected = _compile(
            value["candidate"],
            value["evidence_authority"],
            mode=MODE_UNTRUSTED,
            evaluated_at=evaluated_at,
            trusted_authority_sha256=None,
        )
    else:
        raise ContractError(f"unsupported report mode: {mode}")

    if canonical_json_bytes(expected) != canonical_json_bytes(value):
        raise ContractError("report semantic recompile mismatch")

    root_verified = trusted_authority_sha256 is not None and mode in {MODE_CURRENT, MODE_HISTORICAL}
    return {
        "integrity_valid": True,
        "semantic_recompile_valid": True,
        "trusted_authority_root_verified": root_verified,
        "current_authority_verified": bool(
            root_verified
            and mode == MODE_CURRENT
            and value["trust"]["current_evidence_review_authority"] is True
        ),
        "receipt_sha256": value["receipt_sha256"],
    }


def verify_current(
    report: Any,
    trusted_authority_sha256: str,
) -> dict[str, Any]:
    """Verify historical integrity and independently re-evaluate current state."""

    value = _verify_receipt(report)
    verify_report_integrity(value, trusted_authority_sha256=trusted_authority_sha256)
    verified_at = _utc_now()
    original_at = _parse_utc(value["evaluated_at"], "report.evaluated_at")
    if verified_at < original_at:
        raise ContractError("VERIFIER_TIME_BEFORE_REPORT_EVALUATION")
    current = _compile(
        value["candidate"],
        value["evidence_authority"],
        mode=MODE_CURRENT,
        evaluated_at=verified_at,
        trusted_authority_sha256=trusted_authority_sha256,
    )
    return {
        "schema": CURRENT_VERIFICATION_SCHEMA,
        "verified_at": _format_utc(verified_at),
        "historical_integrity_valid": True,
        "trusted_authority_root_verified": True,
        "original_mode": value["mode"],
        "original_evaluated_at": value["evaluated_at"],
        "original_receipt_sha256": value["receipt_sha256"],
        "current_report_receipt_sha256": current["receipt_sha256"],
        "current_aggregate_state": current["aggregate_state"],
        "current_status_counts": current["status_counts"],
        "current_evidence_review_authority": current["trust"]["current_evidence_review_authority"],
        "external_authority": _external_authority(),
        "current_report": current,
    }

