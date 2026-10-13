#!/usr/bin/env python3
"""Assessment compilation, semantic verification, and rendering."""
from __future__ import annotations

import datetime as _dt
import hmac
from typing import Any

from workshare_contract import (
    BASE_FEE_USD,
    CURRENT_VERIFICATION_SCHEMA,
    DIMENSIONS,
    GROUPS,
    MAX_EVIDENCE_AGE_SECONDS,
    MODE_CURRENT,
    MODE_HISTORICAL,
    MODE_UNTRUSTED,
    OPTIONAL_READOUT_USD,
    REPORT_SCHEMA,
    SCHEMA_VERSION,
    ContractError,
    _REPORT_KEYS,
    _coerce_now,
    _deliverables,
    _external_authority,
    _format_utc,
    _parse_utc,
    _payment_schedule,
    _prime_retains,
    _require_exact_keys,
    _require_int,
    _require_sha,
    _require_str,
    _sha256_value,
    _source_receipts,
    _utc_now,
    _validate_bindings,
    canonical_json_bytes,
    normalize_authority,
    normalize_candidate,
)
def _raw_cell(
    group: str,
    dimension: str,
    sources: list[dict[str, Any]],
    evaluated_at: _dt.datetime,
) -> dict[str, Any]:
    rows = [row for row in sources if row["group"] == group and row["dimension"] == dimension]
    rows.sort(key=lambda row: row["source_id"])
    base = {
        "group": group,
        "dimension": dimension,
        "source_ids": [row["source_id"] for row in rows],
        "source_record_sha256s": [_sha256_value(row) for row in rows],
    }
    if not rows:
        return {
            **base,
            "status": "HOLD_MISSING_EVIDENCE",
            "maturity": None,
            "confidence_bp": None,
            "reason_codes": ["NO_ROOTED_SOURCE_RECORD"],
        }

    future = [row["source_id"] for row in rows if _parse_utc(row["observed_at"], "source.observed_at") > evaluated_at]
    if future:
        raise ContractError("future source evidence: " + ",".join(future))

    stale = [
        row["source_id"]
        for row in rows
        if int((evaluated_at - _parse_utc(row["observed_at"], "source.observed_at")).total_seconds())
        > MAX_EVIDENCE_AGE_SECONDS
    ]
    maturity_values = sorted({row["maturity"] for row in rows})
    if len(maturity_values) > 1:
        return {
            **base,
            "status": "HOLD_CONFLICT",
            "maturity": None,
            "confidence_bp": None,
            "reason_codes": ["ROOTED_MATURITY_CONFLICT"],
        }
    if stale:
        return {
            **base,
            "status": "HOLD_STALE_EVIDENCE",
            "maturity": None,
            "confidence_bp": None,
            "reason_codes": ["STALE_ROOTED_SOURCE:" + ",".join(stale)],
        }
    return {
        **base,
        "status": "READY",
        "maturity": maturity_values[0],
        "confidence_bp": min(row["confidence_bp"] for row in rows),
        "reason_codes": [],
    }


def _compile(
    candidate_raw: Any,
    authority_raw: Any,
    *,
    mode: str,
    evaluated_at: _dt.datetime,
    trusted_authority_sha256: str | None,
) -> dict[str, Any]:
    candidate = normalize_candidate(candidate_raw)
    authority = normalize_authority(authority_raw)
    _validate_bindings(candidate, authority)
    root = _sha256_value(authority)

    trust_supplied = mode in {MODE_CURRENT, MODE_HISTORICAL}
    if trust_supplied:
        if trusted_authority_sha256 is None:
            raise ContractError("trusted authority root is required out of band")
        supplied = _require_sha(trusted_authority_sha256, "trusted_authority_sha256")
        if not hmac.compare_digest(root, supplied):
            raise ContractError("trusted authority root mismatch")
    elif trusted_authority_sha256 is not None:
        raise ContractError("untrusted inspection must not accept a trusted root")

    raw_matrix = [
        _raw_cell(group, dimension, authority["sources"], evaluated_at)
        for group in GROUPS
        for dimension in DIMENSIONS
    ]
    all_ready = all(row["status"] == "READY" for row in raw_matrix)

    if mode == MODE_UNTRUSTED:
        matrix: list[dict[str, Any]] = []
        for row in raw_matrix:
            if row["status"] == "READY":
                matrix.append(
                    {
                        **row,
                        "status": "UNTRUSTED_EVIDENCE_CONSISTENT",
                        "maturity": None,
                        "confidence_bp": None,
                        "reason_codes": ["TRUSTED_AUTHORITY_ROOT_REQUIRED"],
                    }
                )
            else:
                matrix.append(row)
        aggregate_state = "HOLD_TRUSTED_AUTHORITY_REQUIRED"
        current_review = False
    elif mode == MODE_HISTORICAL:
        matrix = [
            {
                **row,
                "status": "HISTORICAL_READY_NON_CURRENT" if row["status"] == "READY" else row["status"],
            }
            for row in raw_matrix
        ]
        aggregate_state = "HISTORICAL_READY_NON_CURRENT" if all_ready else "HISTORICAL_HOLD_NON_CURRENT"
        current_review = False
    elif mode == MODE_CURRENT:
        matrix = raw_matrix
        aggregate_state = (
            "READY_FOR_PRIME_TEAMING_REVIEW"
            if all_ready
            else "HOLD_FOR_PRIME_EVIDENCE_RECONCILIATION"
        )
        current_review = all_ready
    else:
        raise ContractError(f"unsupported compilation mode: {mode}")

    counts: dict[str, int] = {}
    for row in matrix:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    report_without_receipt = {
        "schema": REPORT_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "operation": "UIOWA-RFQ18649-EVIDENCE-AUTHORITY-CURRENTNESS-ZLCK8V4-20260913",
        "mode": mode,
        "evaluated_at": _format_utc(evaluated_at),
        "max_evidence_age_seconds": MAX_EVIDENCE_AGE_SECONDS,
        "candidate": candidate,
        "evidence_authority": authority,
        "authority_root_sha256": root,
        "source_receipts": _source_receipts(authority),
        "trust": {
            "authority_root_supplied_out_of_band": trust_supplied,
            "authority_root_match": trust_supplied,
            "module_authenticates_root_provenance": False,
            "current_evidence_review_authority": current_review,
        },
        "commercial_terms": {
            "base_fee_usd": BASE_FEE_USD,
            "optional_readout_support_usd": OPTIONAL_READOUT_USD,
            "total_if_option_authorized_usd": BASE_FEE_USD + OPTIONAL_READOUT_USD,
            "payment_schedule": _payment_schedule(),
            "travel": "excluded; any travel requires separate written authorization",
            "status": "PROPOSED_NOT_ACCEPTED",
        },
        "deliverables": _deliverables(),
        "prime_retains": _prime_retains(),
        "external_authority": _external_authority(),
        "assessment_matrix": matrix,
        "status_counts": dict(sorted(counts.items())),
        "aggregate_state": aggregate_state,
    }
    return {
        **report_without_receipt,
        "receipt_sha256": _sha256_value(report_without_receipt),
    }


