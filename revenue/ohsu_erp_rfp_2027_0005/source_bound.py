from __future__ import annotations

import datetime as _dt
import sys
from typing import Any

from ._source_bound_constants import (
    CONTROLLING_PACK_SHA256,
    INTENT_DEADLINE,
    MAX_STDIN_BYTES,
    OPPORTUNITY_ID,
    PROFESSIONAL_SERVICES_CONTRACT_SHA256,
    PROPOSAL_DEADLINE,
    REQUIREMENT_IDS,
    RESPONDENT_REF,
    SCHEMA_FACTS,
    SCHEMA_INPUT,
    SCHEMA_PACKET,
    SCHEMA_VERIFY_INPUT,
    SUPPLIER_QA_SHA256,
    ContractError,
)
from ._source_bound_common import (
    _authority_false,
    _canonical,
    _parse_strict_json,
    _require_keys,
    _require_sha256,
    _require_utc_instant,
    _sha,
    _workshare,
)
from ._source_bound_evaluate import (
    _as_utc,
    _basis_counts,
    _gap_blockers,
    compile_at as _compile_with_trust,
    intent_receipt_is_verified as _intent_receipt_is_verified_with_trust,
)
from ._source_bound_facts import _normalize_facts, _normalize_intent_receipt
from ._source_bound_identity import (
    _normalize_commitment,
    _normalize_requirements,
    _normalize_source_binding,
)

VERIFIED_INTENT_RECEIPT_SHA256: str | None = None
VERIFIED_INTENT_RECEIPT_SUBMITTED_AT: str | None = None

def _intent_receipt_is_verified(receipt: dict[str, str] | None) -> bool:
    return _intent_receipt_is_verified_with_trust(
        receipt,
        VERIFIED_INTENT_RECEIPT_SHA256,
        VERIFIED_INTENT_RECEIPT_SUBMITTED_AT,
    )

def _compile_at(facts_obj: Any, now: _dt.datetime) -> dict[str, Any]:
    return _compile_with_trust(
        facts_obj,
        now,
        verified_intent_receipt_sha256=VERIFIED_INTENT_RECEIPT_SHA256,
        verified_intent_receipt_submitted_at=VERIFIED_INTENT_RECEIPT_SUBMITTED_AT,
    )

def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)

def compile_current(facts_obj: Any) -> dict[str, Any]:
    return _compile_at(facts_obj, _now_utc())

def _packet_evaluation_instant(packet_obj: dict[str, Any]) -> _dt.datetime:
    evaluation = _require_utc_instant(packet_obj.get("evaluation_utc"), "packet.evaluation_utc")
    return _dt.datetime.fromisoformat(evaluation.replace("Z", "+00:00"))

def _operational_projection(packet_obj: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "schema",
        "opportunity_id",
        "deadlines",
        "source_binding",
        "source_policy",
        "contract_review",
        "route",
        "status",
        "blockers",
        "next_actions",
        "requirements",
        "qualification_basis_counts",
        "teaming_commitment",
        "facts_sha256",
        "workshare",
        "authority",
        "truth_boundary",
    )
    try:
        return {key: packet_obj[key] for key in keys}
    except KeyError as exc:
        raise ContractError(f"packet missing operational field: {exc.args[0]}") from exc

def verify_current(packet_obj: Any, facts_obj: Any) -> bool:
    if not isinstance(packet_obj, dict):
        raise ContractError("packet must be object")
    bound_instant = _packet_evaluation_instant(packet_obj)
    expected_at_bound = _compile_at(facts_obj, bound_instant)
    if _canonical(packet_obj) != _canonical(expected_at_bound):
        raise ContractError("packet integrity does not match bound source compilation")
    current = compile_current(facts_obj)
    if _canonical(_operational_projection(packet_obj)) != _canonical(_operational_projection(current)):
        raise ContractError("packet operational state is stale")
    return True

def _read_stdin() -> bytes:
    raw = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
    if len(raw) > MAX_STDIN_BYTES:
        raise ContractError(f"stdin exceeds {MAX_STDIN_BYTES} bytes")
    return raw

def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in (["compile"], ["verify"]):
        print(
            "usage: python -m revenue.ohsu_erp_rfp_2027_0005.source_bound {compile|verify}",
            file=sys.stderr,
        )
        return 2
    try:
        obj = _parse_strict_json(_read_stdin(), "stdin")
        if not isinstance(obj, dict):
            raise ContractError("stdin root must be object")
        if args == ["compile"]:
            _require_keys(obj, exact={"schema", "facts"}, where="compile input")
            if obj["schema"] != SCHEMA_INPUT:
                raise ContractError("compile input schema invalid")
            out = compile_current(obj["facts"])
        else:
            _require_keys(obj, exact={"schema", "facts", "packet"}, where="verify input")
            if obj["schema"] != SCHEMA_VERIFY_INPUT:
                raise ContractError("verify input schema invalid")
            verify_current(obj["packet"], obj["facts"])
            out = {
                "schema": "ohsu-erp-source-bound-verification/v1",
                "valid": True,
                "packet_sha256": obj["packet"]["packet_sha256"],
            }
        sys.stdout.buffer.write(_canonical(out) + b"\n")
        return 0
    except (ContractError, KeyError, TypeError, ValueError) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2

__all__ = [
    "SCHEMA_FACTS", "SCHEMA_PACKET", "SCHEMA_INPUT", "SCHEMA_VERIFY_INPUT",
    "OPPORTUNITY_ID", "MAX_STDIN_BYTES", "CONTROLLING_PACK_SHA256",
    "SUPPLIER_QA_SHA256", "PROFESSIONAL_SERVICES_CONTRACT_SHA256",
    "INTENT_DEADLINE", "PROPOSAL_DEADLINE", "RESPONDENT_REF", "REQUIREMENT_IDS",
    "ContractError", "VERIFIED_INTENT_RECEIPT_SHA256",
    "VERIFIED_INTENT_RECEIPT_SUBMITTED_AT", "_canonical", "_sha", "_workshare",
    "_authority_false", "_require_keys", "_require_sha256", "_require_utc_instant",
    "_parse_strict_json", "_normalize_source_binding", "_normalize_commitment",
    "_normalize_requirements", "_normalize_intent_receipt", "_normalize_facts",
    "_intent_receipt_is_verified", "_as_utc", "_gap_blockers", "_basis_counts",
    "_compile_at", "_now_utc", "compile_current", "verify_current", "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
