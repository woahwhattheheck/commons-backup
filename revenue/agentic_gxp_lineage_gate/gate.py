from __future__ import annotations

from typing import Any

from .case import _parse_case
from .codec import (
    AUTHORITY, BATCH_SCHEMA, CASE_SCHEMA, MANIFEST_SCHEMA, MAX_CASES, POLICY_SCHEMA, RECEIPT_SCHEMA,
    GateInputError, _HEX64, _bool, _canonical, _dict, _keys, _parse_policy,
    _utc, digest,
)
from .rules import _manifest_row

__all__ = ["AUTHORITY", "GateInputError", "digest", "evaluate", "verify"]

def evaluate(policy: Any, batch: Any, *, evaluated_at: str) -> dict[str, Any]:
    """Evaluate a complete offline evidence batch.

    READY means only that the supplied evidence is internally coherent under the supplied
    approved policy and is ready for a human QA review step. It never authorizes batch release,
    quality disposition, manufacturing action, validation/certification, or production publish.
    """
    evaluated_dt = _utc(evaluated_at, "evaluated_at")
    parsed_policy = _parse_policy(policy)
    policy_sha = digest(policy)

    obj = _dict(batch, "batch")
    _keys(obj, {"schema", "capture_complete", "captured_at", "cases"}, "batch")
    if obj["schema"] != BATCH_SCHEMA:
        raise GateInputError("unsupported batch schema")
    capture_complete = _bool(obj["capture_complete"], "batch.capture_complete")
    batch_captured = _utc(obj["captured_at"], "batch.captured_at")
    if batch_captured > evaluated_dt:
        raise GateInputError("batch captured_at cannot be after trusted evaluation time")
    raw_cases = obj["cases"]
    if type(raw_cases) is not list or not 1 <= len(raw_cases) <= MAX_CASES:
        raise GateInputError("batch.cases cardinality is out of bounds")
    batch_sha = digest(batch)

    holds: set[str] = set()
    if not capture_complete:
        holds.add("BATCH_CAPTURE_INCOMPLETE")
    if int((evaluated_dt - batch_captured).total_seconds()) > parsed_policy["age"]:
        holds.add("BATCH_CAPTURE_STALE")

    by_event: dict[str, dict[str, Any]] = {}
    by_case: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    case_conflicts: dict[str, list[str]] = {}
    parsed_cases: list[dict[str, Any]] = []

    for raw_case in raw_cases:
        case = _parse_case(raw_case, parsed_policy, evaluated_dt)
        if _utc(case["captured_at"], "case.captured_at") > batch_captured:
            raise GateInputError("case capture cannot be after batch capture")
        prior_event = by_event.get(case["event_id"])
        if prior_event is not None:
            if digest(prior_event) != digest(case):
                raise GateInputError("same event_id decoded to different canonical case")
            duplicate_count += 1
            continue
        by_event[case["event_id"]] = case
        prior_case = by_case.get(case["case_id"])
        if prior_case is not None:
            case_conflicts.setdefault(case["case_id"], [prior_case["event_id"]]).append(case["event_id"])
        else:
            by_case[case["case_id"]] = case
        parsed_cases.append(case)

    conflict_ids = set(case_conflicts)
    if conflict_ids:
        holds.add("CASE_ID_CONFLICT")

    manifest_rows: list[dict[str, Any]] = []
    for case in parsed_cases:
        if case["case_id"] in conflict_ids:
            continue
        manifest_rows.append(_manifest_row(case, parsed_policy, evaluated_dt))
    manifest_rows.sort(key=lambda row: (row["case_id"], row["event_id"]))

    conflict_rows = [
        {"case_id": case_id, "event_ids": sorted(set(event_ids)), "code": "CASE_ID_CONFLICT"}
        for case_id, event_ids in sorted(case_conflicts.items())
    ]
    case_ready_count = sum(row["status"] == AUTHORITY for row in manifest_rows)
    case_hold_count = sum(row["status"] == "HOLD" for row in manifest_rows) + len(conflict_rows)
    if case_hold_count:
        holds.add("CASES_HELD")

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "authority": AUTHORITY,
        "rows": manifest_rows,
        "conflicts": conflict_rows,
    }
    manifest_sha = digest(manifest)
    decision = AUTHORITY if not holds else "HOLD"
    core = {
        "schema": RECEIPT_SCHEMA,
        "decision": decision,
        "holds": sorted(holds),
        "authority": AUTHORITY,
        "evaluated_at": evaluated_at,
        "batch_captured_at": obj["captured_at"],
        "policy_sha256": policy_sha,
        "batch_sha256": batch_sha,
        "manifest_sha256": manifest_sha,
        "input_case_count": len(raw_cases),
        "unique_event_count": len(parsed_cases),
        "duplicate_event_count": duplicate_count,
        "conflicting_case_id_count": len(conflict_rows),
        "ready_case_count": case_ready_count,
        "held_case_count": case_hold_count,
        "source_authenticity_verified": False,
        "production_release_authorized": False,
        "qa_disposition_authorized": False,
        "regulatory_compliance_certified": False,
        "buyer_acceptance_inferred": False,
        "recognized_revenue_inferred": False,
    }
    receipt = dict(core)
    receipt["receipt_sha256"] = digest(core)
    return {"receipt": receipt, "manifest": manifest}


def verify(result: Any, *, policy: Any, batch: Any) -> bool:
    """Re-evaluate the bound evidence and reject edited or self-rehashed semantics."""
    try:
        obj = _dict(result, "result")
        _keys(obj, {"receipt", "manifest"}, "result")
        receipt = _dict(obj["receipt"], "result.receipt")
        expected_fields = {
            "schema",
            "decision",
            "holds",
            "authority",
            "evaluated_at",
            "batch_captured_at",
            "policy_sha256",
            "batch_sha256",
            "manifest_sha256",
            "input_case_count",
            "unique_event_count",
            "duplicate_event_count",
            "conflicting_case_id_count",
            "ready_case_count",
            "held_case_count",
            "source_authenticity_verified",
            "production_release_authorized",
            "qa_disposition_authorized",
            "regulatory_compliance_certified",
            "buyer_acceptance_inferred",
            "recognized_revenue_inferred",
            "receipt_sha256",
        }
        _keys(receipt, expected_fields, "result.receipt")
        if receipt["schema"] != RECEIPT_SCHEMA or receipt["authority"] != AUTHORITY:
            return False
        for field in (
            "source_authenticity_verified",
            "production_release_authorized",
            "qa_disposition_authorized",
            "regulatory_compliance_certified",
            "buyer_acceptance_inferred",
            "recognized_revenue_inferred",
        ):
            if receipt[field] is not False:
                return False
        if receipt["policy_sha256"] != digest(policy) or receipt["batch_sha256"] != digest(batch):
            return False
        if receipt["manifest_sha256"] != digest(obj["manifest"]):
            return False
        core = dict(receipt)
        supplied = core.pop("receipt_sha256")
        if type(supplied) is not str or _HEX64.fullmatch(supplied) is None or supplied != digest(core):
            return False
        expected = evaluate(policy, batch, evaluated_at=receipt["evaluated_at"])
        return _canonical(expected) == _canonical(obj)
    except (GateInputError, KeyError, TypeError, ValueError):
        return False
