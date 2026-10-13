from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Sequence

from . import _engine as _impl

ContractError = _impl.ContractError
VERSION = _impl.VERSION
canonical_json = _impl.canonical_json
sha256_hex = _impl.sha256_hex
derive_collision_key = _impl.derive_collision_key
normalize_packet = _impl.normalize_packet
render_markdown = _impl.render_markdown


def _prepare_packet(packet: Any):
    """Validate once, canonicalize same-ID generations, and retain deterministic conflict evidence."""
    normalized = _impl.normalize_packet(packet)
    groups: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for opp in normalized["opportunities"]:
        oid = opp["opportunity_id"]
        encoded = canonical_json(opp)
        digest = sha256_hex(encoded)
        bucket = groups.setdefault(oid, {})
        entry = bucket.get(digest)
        if entry is None:
            bucket[digest] = {"opportunity": opp, "count": 1}
        else:
            entry["count"] += 1

    evaluation_opportunities = []
    replay_collapses = 0
    conflict_projection = []
    for oid in sorted(groups):
        generations = groups[oid]
        ordered = [(digest, generations[digest]) for digest in sorted(generations)]
        replay_collapses += sum(entry["count"] - 1 for _, entry in ordered)
        # Feed each distinct generation once to the original evaluator. Sorting by digest makes
        # its retained conflict representative deterministic rather than encounter-order based.
        evaluation_opportunities.extend(entry["opportunity"] for _, entry in ordered)
        if len(ordered) > 1:
            conflict_projection.append(
                {
                    "opportunity_id": oid,
                    "generations": [
                        {"sha256": digest, "occurrences": entry["count"]}
                        for digest, entry in ordered
                    ],
                }
            )

    evaluation_packet = dict(normalized)
    evaluation_packet["opportunities"] = evaluation_opportunities

    commitment = dict(normalized)
    commitment["opportunities"] = sorted(
        normalized["opportunities"],
        key=lambda opp: (opp["opportunity_id"], canonical_json(opp)),
    )
    input_sha256 = sha256_hex(canonical_json(commitment))
    return evaluation_packet, replay_collapses, conflict_projection, input_sha256


def _compile_plan_at(packet: Any, *, now: datetime) -> Dict[str, Any]:
    """Private deterministic evaluator used for historical verification and tests."""
    evaluation_packet, replay_collapses, conflicts, input_sha256 = _prepare_packet(packet)
    plan = _impl.compile_plan(evaluation_packet, now=now)
    plan["replay_collapses"] = replay_collapses
    plan["opportunity_id_conflicts"] = conflicts
    plan["input_sha256"] = input_sha256
    plan.pop("receipt_sha256", None)
    plan["receipt_sha256"] = sha256_hex(canonical_json(plan))
    return plan


def compile_plan(packet: Any) -> Dict[str, Any]:
    """Compile against process-owned current UTC. Callers cannot select the current clock."""
    return _compile_plan_at(packet, now=datetime.now(timezone.utc))


def _decision_projection(plan: Mapping[str, Any]) -> Dict[str, Any]:
    selected = sorted(item["opportunity_id"] for item in plan.get("selected", []))
    suppressed = sorted(
        (
            item["opportunity_id"],
            tuple(sorted(item.get("reasons", []))),
        )
        for item in plan.get("suppressed", [])
    )
    return {
        "stage": plan.get("stage"),
        "next_action": plan.get("next_action"),
        "portfolio_reasons": tuple(sorted(plan.get("portfolio_reasons", []))),
        "selected": tuple(selected),
        "suppressed": tuple(suppressed),
        "used_capacity_units": plan.get("used_capacity_units"),
    }


def _verify_plan_at(packet: Any, plan: Any, *, now: datetime) -> Dict[str, Any]:
    """Private deterministic verifier used by tests; production verify owns process UTC."""
    if not isinstance(plan, Mapping):
        raise ContractError("plan must be object")
    if "evaluated_at" not in plan:
        raise ContractError("plan missing evaluated_at")
    historical_at = _impl._parse_ts(plan["evaluated_at"], "plan.evaluated_at")
    expected = _compile_plan_at(packet, now=historical_at)
    historical_valid = canonical_json(expected) == canonical_json(dict(plan))
    current = _compile_plan_at(packet, now=now)
    current_semantics_match = _decision_projection(expected) == _decision_projection(current)
    current_gate_clear = bool(
        historical_valid
        and current_semantics_match
        and current["stage"] != "HOLD"
    )
    return {
        "historical_valid": historical_valid,
        "historical_receipt_sha256": expected["receipt_sha256"],
        "current_stage": current["stage"],
        "current_next_action": current["next_action"],
        "current_selected_opportunity_ids": sorted(
            item["opportunity_id"] for item in current["selected"]
        ),
        "current_receipt_sha256": current["receipt_sha256"],
        "current_semantics_match": current_semantics_match,
        "current_gate_clear": current_gate_clear,
    }


def verify_plan(packet: Any, plan: Any) -> Dict[str, Any]:
    """Verify history and current decision semantics using process-owned current UTC."""
    return _verify_plan_at(packet, plan, now=datetime.now(timezone.utc))
