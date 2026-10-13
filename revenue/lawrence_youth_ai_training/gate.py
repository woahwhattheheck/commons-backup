from __future__ import annotations

from datetime import timezone
from typing import Any

from ._common import (
    AUTHORITY,
    AUTHORITY_ENVELOPE_SCHEMA,
    AUTHORITY_KEY_SCHEMA,
    AUDIT_DOCUMENT,
    COLLABORATIVE_READY,
    EXPECTED_SOURCE_CONTRACT_SHA256,
    GOOD_STANDING_DOCUMENT,
    HOLD,
    NO_BID,
    PRIME_READY,
    RECEIPT_MAX_AGE_SECONDS,
    RECEIPT_SCHEMA,
    SNAPSHOT_SCHEMA,
    QualificationInputError,
    SemanticAuthorityUnavailable,
    _AUTHORITY_FALSE_FIELDS,
    _canonical_bytes,
    _hex64,
    _instant,
    _keys,
    _load_source_contract,
    _object,
    _utc_now,
    digest,
    strict_json_loads,
)
from ._authority import _authenticate_envelope, _load_host_authority
from ._decision import _evaluate

def evaluate_current(snapshot: Any, *, expected_rfp_sha256: str) -> dict[str, Any]:
    evaluated = _utc_now().astimezone(timezone.utc).replace(microsecond=0)
    try:
        authority = _load_host_authority()
        mode = "HOST_HMAC"
    except SemanticAuthorityUnavailable:
        authority = None
        mode = "UNAVAILABLE"
    return _evaluate(
        snapshot,
        evaluated=evaluated,
        expected_rfp_sha256=expected_rfp_sha256,
        authority=authority,
        semantic_authority_mode=mode,
        clock_authority="PROCESS_UTC",
    )


def evaluate_historical(
    snapshot: Any,
    *,
    evaluated_at: str,
    expected_rfp_sha256: str,
) -> dict[str, Any]:
    return _evaluate(
        snapshot,
        evaluated=_instant(evaluated_at, "evaluated_at"),
        expected_rfp_sha256=expected_rfp_sha256,
        authority=None,
        semantic_authority_mode="HISTORICAL_NONE",
        clock_authority="CALLER_SUPPLIED_HISTORICAL",
    )


def _verify_receipt_structure(result: Any) -> dict[str, Any]:
    obj = _object(result, "result")
    _keys(obj, {"receipt"}, "result")
    receipt = _object(obj["receipt"], "receipt")
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("authority") != AUTHORITY:
        raise QualificationInputError("receipt schema/authority mismatch")
    for field in _AUTHORITY_FALSE_FIELDS:
        if receipt.get(field) is not False:
            raise QualificationInputError("receipt action-authority ceiling changed")
    supplied_hash = _hex64(receipt.get("receipt_sha256"), "receipt.receipt_sha256")
    core = dict(receipt)
    core.pop("receipt_sha256")
    if digest(core) != supplied_hash:
        raise QualificationInputError("receipt digest mismatch")
    return receipt


def _current_projection(receipt: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "decision",
        "candidate_decision",
        "current_authority",
        "semantic_authority_mode",
        "semantic_authority_key_id",
        "semantic_authority_generation_id",
        "semantic_authority_envelope_sha256",
        "holds",
        "qualification_holds",
        "hard_constraints",
        "missing_documents",
        "missing_capabilities",
        "bidder_coverage",
        "partner_coverage",
        "document_states",
        "document_semantic_states",
    }
    return {key: receipt[key] for key in sorted(keys)}


def verify_current(
    result: Any,
    *,
    snapshot: Any,
    expected_rfp_sha256: str,
) -> bool:
    try:
        receipt = _verify_receipt_structure(result)
        if receipt.get("clock_authority") != "PROCESS_UTC":
            return False
        if receipt.get("semantic_authority_mode") != "HOST_HMAC":
            return False
        if receipt.get("current_authority") is not True:
            return False
        now = _utc_now().astimezone(timezone.utc).replace(microsecond=0)
        evaluated = _instant(receipt["evaluated_at"], "receipt.evaluated_at")
        if now < evaluated or (now - evaluated).total_seconds() > RECEIPT_MAX_AGE_SECONDS:
            return False
        authority = _load_host_authority()
        if receipt.get("semantic_authority_key_id") != authority["key_id"]:
            return False
        if receipt.get("semantic_authority_generation_id") != authority["generation_id"]:
            return False
        if receipt.get("semantic_authority_envelope_sha256") != authority["envelope_sha256"]:
            return False
        exact = _evaluate(
            snapshot,
            evaluated=evaluated,
            expected_rfp_sha256=expected_rfp_sha256,
            authority=authority,
            semantic_authority_mode="HOST_HMAC",
            clock_authority="PROCESS_UTC",
        )
        if _canonical_bytes(exact) != _canonical_bytes(result):
            return False
        current = _evaluate(
            snapshot,
            evaluated=now,
            expected_rfp_sha256=expected_rfp_sha256,
            authority=authority,
            semantic_authority_mode="HOST_HMAC",
            clock_authority="PROCESS_UTC",
        )
        return _current_projection(current["receipt"]) == _current_projection(receipt)
    except (
        QualificationInputError,
        SemanticAuthorityUnavailable,
        KeyError,
        TypeError,
        ValueError,
    ):
        return False
