from __future__ import annotations

from collections import defaultdict
from typing import Any

from .analytics import _arm_metrics, _comparisons, _csv_bytes, _markdown_bytes, _strategy_status
from .common import (
    INPUT_SCHEMA, PACKET_SCHEMA, READY, RECEIPT_SCHEMA, UPSTREAM_READY, LabError,
    authority_ceiling, canonical_json, exact_keys, parse_time, sha256, validate_json_scalars,
)
from .input_model import _compile_upstream, _normalize_assignments, _normalize_plan, _validate_bindings

def compile_experiment(value: Any, *, as_of: str) -> dict[str, Any]:
    validate_json_scalars(value)
    root = exact_keys(value, required=("schema", "plan", "assignments", "funnel"), field="$")
    if root["schema"] != INPUT_SCHEMA:
        raise LabError("unsupported input schema")
    evaluated = parse_time(as_of, "as_of")
    plan = _normalize_plan(root["plan"], evaluated=evaluated)
    assignments = _normalize_assignments(root["assignments"], plan=plan, evaluated=evaluated)
    upstream = _compile_upstream(root["funnel"], as_of=as_of)
    if not isinstance(upstream, dict) or not isinstance(upstream.get("packet"), dict) or not isinstance(upstream.get("receipt"), dict):
        raise LabError("upstream commercial funnel compiler returned invalid shape")
    upstream_packet = upstream["packet"]
    upstream_receipt = upstream["receipt"]
    upstream_opportunities = upstream_packet.get("opportunities")
    if not isinstance(upstream_opportunities, list):
        raise LabError("upstream funnel packet missing opportunities")
    opportunity_map, assignment_map = _validate_bindings(
        plan=plan,
        assignments=assignments,
        upstream_opportunities=upstream_opportunities,
    )

    assignments_by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assignment in assignments:
        assignments_by_arm[assignment["arm_id"]].append(assignment)
    arm_results: list[dict[str, Any]] = []
    for arm in plan["arms"]:
        metrics = _arm_metrics(arm, assignments_by_arm.get(arm["id"], []), opportunity_map)
        metrics["strategy_status"] = _strategy_status(
            metrics,
            minimum_sample=plan["minimum_sample_per_arm"],
        )
        arm_results.append(metrics)
    arm_results.sort(key=lambda item: item["arm"]["id"])

    exclusions = []
    for opp_id in plan["opportunity_ids"]:
        opp = opportunity_map[opp_id]
        if opp.get("state") != UPSTREAM_READY:
            exclusions.append(
                {
                    "opportunity_id": opp_id,
                    "arm_id": assignment_map[opp_id]["arm_id"],
                    "reason": "UPSTREAM_FUNNEL_HOLD",
                    "upstream_hold_reasons": sorted(opp.get("hold_reasons", [])),
                }
            )

    upstream_input_digest = upstream_receipt.get("input_sha256")
    upstream_packet_digest = upstream_receipt.get("packet_sha256")
    if not isinstance(upstream_input_digest, str) or not isinstance(upstream_packet_digest, str):
        raise LabError("upstream receipt missing digests")
    semantic_identity = {
        "schema": INPUT_SCHEMA,
        "plan": plan,
        "assignments": assignments,
        "upstream_funnel_input_sha256": upstream_input_digest,
    }
    input_digest = sha256(canonical_json(semantic_identity))
    authority = authority_ceiling()
    packet_base = {
        "schema": PACKET_SCHEMA,
        "state": READY,
        "evaluated_at": as_of,
        "input_sha256": input_digest,
        "experiment": plan,
        "assignments": assignments,
        "chronology": {
            "state": "SELF_ASSERTED_UNVERIFIED",
            "plan_predeclaration_authenticated": False,
            "assignment_chronology_authenticated": False,
            "declared_thresholds_authenticated": False,
            "strategy_recommendations_authorized": False,
        },
        "upstream_funnel": {
            "state": upstream_packet.get("state"),
            "input_sha256": upstream_input_digest,
            "packet_sha256": upstream_packet_digest,
            "source_authenticity_asserted_by_lab": False,
        },
        "arms": arm_results,
        "comparisons": _comparisons(arm_results, plan["minimum_sample_per_arm"]),
        "excluded_opportunities": exclusions,
        "authority": authority,
    }
    report_json = canonical_json(packet_base)
    report_csv = _csv_bytes(arm_results)
    report_markdown = _markdown_bytes(packet_base)
    outputs = {
        "report_json_sha256": sha256(report_json),
        "report_csv_sha256": sha256(report_csv),
        "report_markdown_sha256": sha256(report_markdown),
    }
    packet = dict(packet_base)
    packet["outputs"] = outputs
    packet_sha = sha256(canonical_json(packet))
    receipt_base = {
        "schema": RECEIPT_SCHEMA,
        "state": READY,
        "evaluated_at": as_of,
        "input_sha256": input_digest,
        "upstream_funnel_input_sha256": upstream_input_digest,
        "upstream_funnel_packet_sha256": upstream_packet_digest,
        "chronology_state": "SELF_ASSERTED_UNVERIFIED",
        "strategy_recommendations_authorized": False,
        "packet_sha256": packet_sha,
        "outputs": outputs,
        "authority": authority,
    }
    receipt = dict(receipt_base)
    receipt["receipt_sha256"] = sha256(canonical_json(receipt_base))
    return {
        "packet": packet,
        "receipt": receipt,
        "json": report_json,
        "csv": report_csv,
        "markdown": report_markdown,
    }

def verify_compilation(value: Any, *, as_of: str, packet: Any, receipt: Any) -> bool:
    try:
        expected = compile_experiment(value, as_of=as_of)
        if not isinstance(packet, dict) or not isinstance(receipt, dict):
            return False
        if canonical_json(packet) != canonical_json(expected["packet"]):
            return False
        if canonical_json(receipt) != canonical_json(expected["receipt"]):
            return False
        without_digest = {key: val for key, val in receipt.items() if key != "receipt_sha256"}
        return receipt.get("receipt_sha256") == sha256(canonical_json(without_digest))
    except (LabError, TypeError, ValueError, OverflowError):
        return False

def verify_artifacts(
    value: Any,
    *,
    as_of: str,
    packet: Any,
    receipt: Any,
    report_json: bytes,
    report_csv: bytes,
    report_markdown: bytes,
) -> bool:
    try:
        expected = compile_experiment(value, as_of=as_of)
        return (
            verify_compilation(value, as_of=as_of, packet=packet, receipt=receipt)
            and report_json == expected["json"]
            and report_csv == expected["csv"]
            and report_markdown == expected["markdown"]
            and receipt.get("outputs", {}).get("report_json_sha256") == sha256(report_json)
            and receipt.get("outputs", {}).get("report_csv_sha256") == sha256(report_csv)
            and receipt.get("outputs", {}).get("report_markdown_sha256") == sha256(report_markdown)
        )
    except (LabError, TypeError, ValueError, OverflowError):
        return False
