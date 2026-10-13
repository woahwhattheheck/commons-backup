#!/usr/bin/env python3
"""Truth-ceiling policy for procurement loss remediation receipts.

The upstream procurement_win_loss layer proves structural integrity and packet
binding, not that caller-supplied source labels or digests came from a buyer or
provider. This module therefore preserves those retained statements as useful
diagnostic evidence while refusing to upgrade them into buyer-authenticated
facts or actionable BUYER_REASON remediation without a separate authenticated
source authority (which this product does not currently have).
"""
from __future__ import annotations

from typing import Any

from . import core

# Capture the frozen predecessor before package initialization installs this
# policy as the public compile/semantic surface.
_predecessor_derive_semantics = core.derive_semantics

CALLER_RETAINED_ATTRIBUTION = (
    "CALLER_RETAINED_STATED_SOURCE_BOUND_NOT_BUYER_AUTHENTICATED"
)


def derive_semantics(normalized: dict[str, Any]) -> dict[str, Any]:
    semantics = _predecessor_derive_semantics(normalized)
    local_holds = set(semantics["hold_reasons"])
    authentication_holds: set[str] = set()

    # The predecessor's evidence-id + digest binding remains valuable integrity
    # evidence, but it cannot establish who authored the underlying bytes.
    # Truth-narrow every mapped source statement accordingly. Merely retaining
    # a diagnostic statement is not itself a contradiction; authority is
    # blocked when a BUYER_REASON is used to justify a remediation gap.
    diagnostic_reasons: list[dict[str, Any]] = []
    for reason in semantics["buyer_reasons"]:
        narrowed = dict(reason)
        narrowed["statement_attribution"] = CALLER_RETAINED_ATTRIBUTION
        narrowed["buyer_source_authenticated"] = False
        diagnostic_reasons.append(narrowed)

    # No BUYER_REASON may authorize a gap while the product has no independent
    # buyer/provider retained-source authentication boundary. Internal
    # hypotheses remain separately labeled and can still support internal
    # experiments when their retained factual basis is otherwise valid.
    gaps: list[dict[str, Any]] = []
    for gap in semantics["remediation_gaps"]:
        narrowed = dict(gap)
        if narrowed["basis_type"] == "BUYER_REASON" and narrowed["basis_valid"]:
            narrowed["basis_valid"] = False
            authentication_holds.add(
                f"buyer_reason_not_authenticated:{narrowed['basis_id']}"
            )
            authentication_holds.add(
                f"buyer_reason_gap_not_authenticated:{narrowed['gap_id']}@{narrowed['version']}"
            )
        gaps.append(narrowed)

    local_holds.update(authentication_holds)
    source_hold = (
        semantics["source_outcome"] == "UNKNOWN"
        or bool(semantics["source_hold_reasons"])
    )
    if source_hold:
        status = "HOLD_SOURCE"
    elif authentication_holds:
        status = "HOLD_CONTRADICTION"
    else:
        # Preserve every predecessor status that does not rely on an
        # unauthenticated buyer-reason authorization: digest mismatches,
        # missing taxonomy mappings, internal hypotheses, and no-gap states.
        status = semantics["status"]

    return {
        **semantics,
        "status": status,
        "buyer_reasons": sorted(
            diagnostic_reasons, key=lambda row: row["reason_id"]
        ),
        "remediation_gaps": gaps,
        "hold_reasons": sorted(local_holds),
    }


def compile_plan(raw: Any) -> dict[str, Any]:
    normalized = core.normalize_input(raw)
    semantics = derive_semantics(normalized)
    source_receipt = normalized["outcome_receipt"]
    source_evidence = [
        {
            "evidence_id": row["evidence_id"],
            "source_kind": row["source_kind"],
            "source_digest_sha256": row["source_digest_sha256"],
            "observed_at": row["observed_at"],
            "evidence_status": row["evidence_status"],
            "decision_signal": row["decision_signal"],
            "mapped_outcome": row["mapped_outcome"],
        }
        for row in source_receipt["known_facts"]
    ]
    unsigned = {
        "schema": core.RECEIPT_SCHEMA,
        "opportunity_id": source_receipt["opportunity_id"],
        "compiled_at": source_receipt["compiled_at"],
        "source_receipt_sha256": source_receipt["receipt_sha256"],
        "source_outcome": semantics["source_outcome"],
        "source_hold_reasons": semantics["source_hold_reasons"],
        "source_evidence": source_evidence,
        "status": semantics["status"],
        "buyer_reasons": semantics["buyer_reasons"],
        "internal_hypotheses": semantics["internal_hypotheses"],
        "remediation_gaps": semantics["remediation_gaps"],
        "unattributed_source_statement_ids": semantics[
            "unattributed_source_statement_ids"
        ],
        "hold_reasons": semantics["hold_reasons"],
        "authority": {
            "buyer_contact_authorized": False,
            "debrief_request_authorized": False,
            "outbound_authorized": False,
            "provider_mutation_authorized": False,
            "contract_authorized": False,
            "payment_authorized": False,
            "cash_recognized": False,
            "revenue_recognized": False,
            "buyer_causal_inference_authorized": False,
        },
        "normalized_input_sha256": core.digest(normalized),
    }
    return {**unsigned, "receipt_sha256": core.digest(unsigned)}
