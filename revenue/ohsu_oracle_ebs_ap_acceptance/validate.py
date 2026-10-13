from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from .model import AcceptanceInputError, CaseResult, require_list, require_object, require_text


OPPORTUNITY_ID = "OHSU-RFI-2027-0824"
ORACLE_TARGET = "EBS_R12"

SCENARIOS = {
    "po_2way_match",
    "po_3way_match",
    "non_po_coding_approval",
    "duplicate_invoice",
    "posting_retry",
    "supplier_inquiry",
    "statement_reconciliation",
    "exception_routing",
    "reporting_audit",
}

POSTING_SCENARIOS = {
    "po_2way_match",
    "po_3way_match",
    "non_po_coding_approval",
    "posting_retry",
}
HOLD_SCENARIOS = {"duplicate_invoice", "exception_routing"}

EXPECTED_TERMINAL = {
    "po_2way_match": "POSTED",
    "po_3way_match": "POSTED",
    "non_po_coding_approval": "POSTED",
    "duplicate_invoice": "HOLD",
    "posting_retry": "POSTED",
    "supplier_inquiry": "INQUIRY_RESOLVED",
    "statement_reconciliation": "RECONCILED",
    "exception_routing": "HOLD",
    "reporting_audit": "REPORTED",
}

EXPECTED_EVIDENCE_KIND = {
    "po_2way_match": "oracle_posting_receipt",
    "po_3way_match": "oracle_posting_receipt",
    "non_po_coding_approval": "oracle_posting_receipt",
    "duplicate_invoice": "duplicate_detection",
    "posting_retry": "oracle_posting_receipt",
    "supplier_inquiry": "inquiry_resolution",
    "statement_reconciliation": "reconciliation",
    "exception_routing": "exception_route",
    "reporting_audit": "audit_report",
}

ALLOWED_STATES = {
    "RECEIVED",
    "VALIDATED",
    "MATCHED",
    "CODED",
    "APPROVED",
    "POST_INTENT",
    "RETRYABLE_FAILURE",
    "POSTED",
    "DUPLICATE_DETECTED",
    "EXCEPTION",
    "HOLD",
    "INQUIRY_RECEIVED",
    "INQUIRY_RESOLVED",
    "STATEMENT_RECEIVED",
    "RECONCILED",
    "AUDIT_REQUESTED",
    "REPORTED",
}

TRANSITIONS = {
    "RECEIVED": {"VALIDATED", "DUPLICATE_DETECTED", "EXCEPTION"},
    "VALIDATED": {"MATCHED", "CODED", "DUPLICATE_DETECTED", "EXCEPTION"},
    "MATCHED": {"CODED", "APPROVED", "EXCEPTION"},
    "CODED": {"APPROVED", "EXCEPTION"},
    "APPROVED": {"POST_INTENT", "EXCEPTION"},
    "POST_INTENT": {"POSTED", "RETRYABLE_FAILURE", "EXCEPTION"},
    "RETRYABLE_FAILURE": {"POST_INTENT", "EXCEPTION"},
    "DUPLICATE_DETECTED": {"HOLD"},
    "EXCEPTION": {"HOLD"},
    "INQUIRY_RECEIVED": {"INQUIRY_RESOLVED", "EXCEPTION"},
    "STATEMENT_RECEIVED": {"RECONCILED", "EXCEPTION"},
    "AUDIT_REQUESTED": {"REPORTED", "EXCEPTION"},
}

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AcceptanceInputError("value is not canonical JSON") from exc


def _parse_timestamp(value: Any, path: str) -> str:
    text = require_text(value, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AcceptanceInputError(f"{path} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise AcceptanceInputError(f"{path} must include timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _validate_receipt(value: Any, path: str, *, expected_kind: str) -> dict[str, str]:
    obj = require_object(value, path)
    required = {"source_id", "sha256", "captured_at", "kind"}
    if set(obj) != required:
        missing = sorted(required - set(obj))
        extra = sorted(set(obj) - required)
        pieces = []
        if missing:
            pieces.append(f"missing={missing}")
        if extra:
            pieces.append(f"extra={extra}")
        raise AcceptanceInputError(f"{path} must contain exactly receipt fields ({'; '.join(pieces)})")
    source_id = require_text(obj["source_id"], f"{path}.source_id")
    digest = require_text(obj["sha256"], f"{path}.sha256")
    if not SHA256_RE.fullmatch(digest):
        raise AcceptanceInputError(f"{path}.sha256 must be 64 lowercase hex characters")
    kind = require_text(obj["kind"], f"{path}.kind")
    if kind != expected_kind:
        raise AcceptanceInputError(
            f"{path}.kind must be {expected_kind} for this scenario"
        )
    return {
        "source_id": source_id,
        "sha256": digest,
        "captured_at": _parse_timestamp(obj["captured_at"], f"{path}.captured_at"),
        "kind": kind,
    }


def _validate_trace(raw: Any, path: str) -> tuple[list[str], str | None]:
    items = require_list(raw, path)
    if not items:
        raise AcceptanceInputError(f"{path} must not be empty")
    trace = [require_text(item, f"{path}[]") for item in items]
    unknown = sorted(set(trace) - ALLOWED_STATES)
    if unknown:
        raise AcceptanceInputError(f"{path} contains unsupported states: {', '.join(unknown)}")
    if len(trace) != len(list(dict.fromkeys(trace))):
        seen: set[str] = set()
        for idx, state in enumerate(trace):
            if state in seen and state != "POST_INTENT":
                return trace, f"state {state} is repeated"
            if state == "POST_INTENT" and state in seen:
                if idx == 0 or trace[idx - 1] != "RETRYABLE_FAILURE":
                    return trace, "POST_INTENT may repeat only immediately after RETRYABLE_FAILURE"
            seen.add(state)
    for left, right in zip(trace, trace[1:]):
        if right not in TRANSITIONS.get(left, set()):
            return trace, f"invalid transition {left}->{right}"
    return trace, None


def _validate_attempts(raw: Any, path: str) -> list[dict[str, Any]]:
    attempts = require_list(raw, path)
    if len(attempts) > 20:
        raise AcceptanceInputError(f"{path} exceeds 20 attempts")
    seen_attempt_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for idx, value in enumerate(attempts):
        apath = f"{path}[{idx}]"
        obj = require_object(value, apath)
        required = {"attempt_id", "posting_intent_id", "outcome", "oracle_txn_id"}
        if set(obj) != required:
            raise AcceptanceInputError(f"{apath} must contain exactly attempt fields")
        attempt_id = require_text(obj["attempt_id"], f"{apath}.attempt_id")
        if attempt_id in seen_attempt_ids:
            raise AcceptanceInputError(f"{apath}.attempt_id duplicates another attempt")
        seen_attempt_ids.add(attempt_id)
        posting_intent_id = require_text(
            obj["posting_intent_id"], f"{apath}.posting_intent_id"
        )
        outcome = require_text(obj["outcome"], f"{apath}.outcome")
        if outcome not in {"failed", "posted"}:
            raise AcceptanceInputError(f"{apath}.outcome must be failed or posted")
        txn = obj["oracle_txn_id"]
        if outcome == "posted":
            txn = require_text(txn, f"{apath}.oracle_txn_id")
        elif txn is not None:
            raise AcceptanceInputError(
                f"{apath}.oracle_txn_id must be null when outcome is failed"
            )
        normalized.append(
            {
                "attempt_id": attempt_id,
                "posting_intent_id": posting_intent_id,
                "outcome": outcome,
                "oracle_txn_id": txn,
            }
        )
    return normalized


def _posting_summary(
    attempts: list[dict[str, Any]],
) -> tuple[bool, str, set[str], set[str]]:
    if not attempts:
        return False, "posting scenario has no posting attempts", set(), set()
    intent_ids = {item["posting_intent_id"] for item in attempts}
    if len(intent_ids) != 1:
        return False, "retry attempts changed logical posting_intent_id", set(), set()
    posted = [item for item in attempts if item["outcome"] == "posted"]
    if not posted:
        return False, "no successful Oracle posting evidence", intent_ids, set()
    txns = {item["oracle_txn_id"] for item in posted}
    if len(txns) != 1:
        return (
            False,
            "one logical posting intent produced multiple Oracle transaction identities",
            intent_ids,
            txns,
        )
    first_post_index = next(i for i, item in enumerate(attempts) if item["outcome"] == "posted")
    if any(item["outcome"] == "failed" for item in attempts[first_post_index + 1 :]):
        return False, "attempt evidence continues with failure after successful posting", intent_ids, txns
    return True, "exactly one logical Oracle transaction identity proven", intent_ids, txns


def evaluate_matrix(matrix: dict[str, Any], *, input_sha256: str | None = None) -> dict[str, Any]:
    if not isinstance(matrix, dict):
        raise AcceptanceInputError("matrix must be an object")
    required_top = {"opportunity_id", "oracle_target", "evaluated_at", "cases"}
    if set(matrix) != required_top:
        missing = sorted(required_top - set(matrix))
        extra = sorted(set(matrix) - required_top)
        raise AcceptanceInputError(
            f"matrix must contain exactly top-level fields; missing={missing} extra={extra}"
        )

    opportunity_id = require_text(matrix["opportunity_id"], "opportunity_id")
    if opportunity_id != OPPORTUNITY_ID:
        raise AcceptanceInputError(f"opportunity_id must be {OPPORTUNITY_ID}")
    oracle_target = require_text(matrix["oracle_target"], "oracle_target")
    if oracle_target != ORACLE_TARGET:
        raise AcceptanceInputError(f"oracle_target must be {ORACLE_TARGET}")
    evaluated_at = _parse_timestamp(matrix["evaluated_at"], "evaluated_at")

    cases_raw = require_list(matrix["cases"], "cases")
    if not cases_raw or len(cases_raw) > 1000:
        raise AcceptanceInputError("cases must be a non-empty bounded list")

    seen_case_ids: set[str] = set()
    scenario_counts = {scenario: 0 for scenario in SCENARIOS}
    case_results: list[CaseResult] = []
    global_intent_to_txn: dict[str, str] = {}
    global_txn_to_intent: dict[str, str] = {}
    receipt_digests: set[str] = set()

    for idx, value in enumerate(cases_raw):
        path = f"cases[{idx}]"
        obj = require_object(value, path)
        required_case = {
            "case_id",
            "scenario",
            "invoice_key",
            "expected_terminal",
            "state_trace",
            "attempts",
            "evidence",
        }
        if set(obj) != required_case:
            raise AcceptanceInputError(f"{path} must contain exactly case fields")

        case_id = require_text(obj["case_id"], f"{path}.case_id")
        if case_id in seen_case_ids:
            raise AcceptanceInputError(f"{path}.case_id duplicates another case")
        seen_case_ids.add(case_id)
        scenario = require_text(obj["scenario"], f"{path}.scenario")
        if scenario not in SCENARIOS:
            raise AcceptanceInputError(f"{path}.scenario unsupported: {scenario}")
        scenario_counts[scenario] += 1

        invoice_key = require_text(obj["invoice_key"], f"{path}.invoice_key")
        expected_terminal = require_text(
            obj["expected_terminal"], f"{path}.expected_terminal"
        )
        if expected_terminal != EXPECTED_TERMINAL[scenario]:
            raise AcceptanceInputError(
                f"{path}.expected_terminal must be {EXPECTED_TERMINAL[scenario]} for {scenario}"
            )
        trace, trace_error = _validate_trace(obj["state_trace"], f"{path}.state_trace")
        attempts = _validate_attempts(obj["attempts"], f"{path}.attempts")
        receipt = _validate_receipt(
            obj["evidence"],
            f"{path}.evidence",
            expected_kind=EXPECTED_EVIDENCE_KIND[scenario],
        )
        if datetime.fromisoformat(receipt["captured_at"]) > datetime.fromisoformat(evaluated_at):
            raise AcceptanceInputError(
                f"{path}.evidence.captured_at cannot be after evaluated_at"
            )
        if receipt["sha256"] in receipt_digests:
            raise AcceptanceInputError(
                f"{path}.evidence.sha256 duplicates another case receipt"
            )
        receipt_digests.add(receipt["sha256"])

        errors: list[str] = []
        if trace_error is not None:
            errors.append(trace_error)
        if trace[-1] != expected_terminal:
            errors.append(
                f"terminal state {trace[-1]} does not match expected {expected_terminal}"
            )

        if scenario in POSTING_SCENARIOS:
            posting_ok, posting_detail, intent_ids, txns = _posting_summary(attempts)
            if not posting_ok:
                errors.append(posting_detail)
            if "POST_INTENT" not in trace or "POSTED" not in trace:
                errors.append("posting scenario trace lacks POST_INTENT->POSTED evidence")
            if scenario == "posting_retry":
                if "RETRYABLE_FAILURE" not in trace:
                    errors.append("posting_retry scenario lacks RETRYABLE_FAILURE state")
                if not any(item["outcome"] == "failed" for item in attempts):
                    errors.append("posting_retry scenario lacks a failed attempt before recovery")
            elif len(attempts) != 1 or attempts[0]["outcome"] != "posted":
                errors.append(
                    "non-retry posting scenario must contain exactly one successful attempt"
                )
            for intent in intent_ids:
                for txn in txns:
                    prior_txn = global_intent_to_txn.get(intent)
                    if prior_txn is not None and prior_txn != txn:
                        errors.append(
                            "posting_intent_id maps to conflicting Oracle transaction identity across cases"
                        )
                    prior_intent = global_txn_to_intent.get(txn)
                    if prior_intent is not None and prior_intent != intent:
                        errors.append(
                            "Oracle transaction identity is reused by another logical posting intent"
                        )
                    global_intent_to_txn[intent] = txn
                    global_txn_to_intent[txn] = intent
        else:
            if attempts:
                errors.append("non-posting scenario must not contain Oracle posting attempts")
            if "POST_INTENT" in trace or "POSTED" in trace:
                errors.append("non-posting scenario contains posting states")

        if scenario == "duplicate_invoice" and "DUPLICATE_DETECTED" not in trace:
            errors.append("duplicate_invoice scenario lacks DUPLICATE_DETECTED")
        if scenario == "exception_routing" and "EXCEPTION" not in trace:
            errors.append("exception_routing scenario lacks EXCEPTION")

        case_results.append(
            CaseResult(
                case_id=case_id,
                scenario=scenario,
                status="PASS" if not errors else "HOLD",
                detail=(
                    f"{invoice_key}: acceptance evidence coherent"
                    if not errors
                    else f"{invoice_key}: " + "; ".join(errors)
                ),
            )
        )

    missing_scenarios = sorted(
        scenario for scenario, count in scenario_counts.items() if count == 0
    )
    duplicate_scenarios = sorted(
        scenario for scenario, count in scenario_counts.items() if count > 1
    )
    case_holds = [item.case_id for item in case_results if item.status != "PASS"]
    decision = (
        "ACCEPTANCE_MATRIX_READY"
        if not missing_scenarios and not duplicate_scenarios and not case_holds
        else "HOLD_ACCEPTANCE_EVIDENCE"
    )

    report_core: dict[str, Any] = {
        "schema": "ohsu-oracle-ebs-ap-acceptance/v1",
        "opportunity_id": opportunity_id,
        "oracle_target": oracle_target,
        "evaluated_at": evaluated_at,
        "decision": decision,
        "case_results": [item.to_dict() for item in case_results],
        "coverage": {
            "required_scenarios": sorted(SCENARIOS),
            "scenario_counts": {key: scenario_counts[key] for key in sorted(scenario_counts)},
            "missing_scenarios": missing_scenarios,
            "duplicate_scenarios": duplicate_scenarios,
            "held_cases": case_holds,
        },
        "evidence_receipt_count": len(receipt_digests),
        "authority": {
            "partner_inclusion_approved": False,
            "proposal_authorized": False,
            "proposal_submitted": False,
            "oracle_production_validated": False,
            "buyer_acceptance": False,
            "contract_awarded": False,
            "payment_received": False,
            "recognized_revenue": False,
        },
    }
    if input_sha256 is not None:
        if not SHA256_RE.fullmatch(input_sha256):
            raise AcceptanceInputError("input_sha256 must be 64 lowercase hex characters")
        report_core["input_sha256"] = input_sha256
    report_sha256 = hashlib.sha256(_canonical_bytes(report_core)).hexdigest()
    return {**report_core, "report_sha256": report_sha256}
