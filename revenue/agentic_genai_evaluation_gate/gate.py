"""Deterministic pre-release evidence gate for agentic GenAI evaluations.

The module is deliberately read-only. It validates already-produced synthetic or
non-production evidence; it never executes an agent, calls a tool, or grants a
release authority.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping

from ._scenario import _validate_scenario
from ._schema import (
    DECISION_HOLD,
    DECISION_RELEASE,
    RECEIPT_SCHEMA_VERSION,
    SCHEMA_VERSION,
    _ALLOWED_CATEGORIES,
    _BUILD_KEYS,
    _ESET_KEYS,
    _POLICY_KEYS,
    _RUBRIC_KEYS,
    _TOP_KEYS,
    EvidenceError,
    _canonical_bytes,
    _format_utc,
    _ordered_reasons,
    _parse_utc,
    _require_bool,
    _require_dict,
    _require_id,
    _require_int,
    _require_sha,
    sha256_object,
)


def validate_packet(
    packet: Any,
    *,
    evaluated_at: datetime,
) -> tuple[dict[str, Any], list[str]]:
    """Validate and normalize one closed-schema evaluation packet."""
    evaluated_text = _format_utc(evaluated_at)
    trusted_at = _parse_utc(evaluated_text, name="evaluated_at")

    top = _require_dict(packet, name="packet", keys=_TOP_KEYS)
    schema = _require_int(
        top["schema_version"],
        name="schema_version",
        minimum=SCHEMA_VERSION,
        maximum=SCHEMA_VERSION,
    )
    if schema != SCHEMA_VERSION:
        raise EvidenceError("unsupported schema_version")
    _require_id(top["evaluation_id"], name="evaluation_id")

    evaluation_set = _require_dict(
        top["evaluation_set"],
        name="evaluation_set",
        keys=_ESET_KEYS,
    )
    _require_id(evaluation_set["set_id"], name="evaluation_set.set_id")
    _require_int(
        evaluation_set["generation"],
        name="evaluation_set.generation",
        minimum=1,
        maximum=2**31 - 1,
    )
    _require_sha(evaluation_set["sha256"], name="evaluation_set.sha256")
    required = evaluation_set["required_scenarios"]
    if type(required) is not list or not required:
        raise EvidenceError("evaluation_set.required_scenarios: expected non-empty array")
    required_ids = [
        _require_id(item, name="required scenario id")
        for item in required
    ]
    if len(required_ids) != len(set(required_ids)):
        raise EvidenceError("evaluation_set.required_scenarios: duplicate id")

    build = _require_dict(top["agent_build"], name="agent_build", keys=_BUILD_KEYS)
    _require_id(build["agent_id"], name="agent_build.agent_id")
    _require_id(build["version"], name="agent_build.version")
    build_sha = _require_sha(build["sha256"], name="agent_build.sha256")

    rubric = _require_dict(top["rubric"], name="rubric", keys=_RUBRIC_KEYS)
    _require_id(rubric["rubric_id"], name="rubric.rubric_id")
    _require_int(
        rubric["generation"],
        name="rubric.generation",
        minimum=1,
        maximum=2**31 - 1,
    )
    rubric_sha = _require_sha(rubric["sha256"], name="rubric.sha256")
    minimum_score = _require_int(
        rubric["minimum_score_bps"],
        name="rubric.minimum_score_bps",
        minimum=0,
        maximum=10_000,
    )

    policy = _require_dict(top["policy"], name="policy", keys=_POLICY_KEYS)
    _require_int(
        policy["max_evidence_age_seconds"],
        name="policy.max_evidence_age_seconds",
        minimum=60,
        maximum=31_536_000,
    )
    _require_bool(
        policy["require_human_review"],
        name="policy.require_human_review",
    )
    _require_bool(
        policy["require_complete_observability"],
        name="policy.require_complete_observability",
    )

    if type(top["scenarios"]) is not list:
        raise EvidenceError("scenarios: expected array")

    reasons: set[str] = set()
    normalized_scenarios: list[dict[str, Any]] = []
    seen: set[str] = set()
    review_ids: set[str] = set()
    tool_call_ids: set[str] = set()
    for raw in top["scenarios"]:
        normalized = _validate_scenario(
            raw,
            build_sha=build_sha,
            rubric_sha=rubric_sha,
            minimum_score_bps=minimum_score,
            evaluated_at=trusted_at,
            policy=policy,
            reasons=reasons,
        )
        scenario_id = normalized["scenario_id"]
        if scenario_id in seen:
            reasons.add("DUPLICATE_SCENARIO_ID")
        seen.add(scenario_id)

        review = normalized["human_review"]
        if review is not None:
            review_id = review["review_id"]
            if review_id in review_ids:
                raise EvidenceError("duplicate human review id across scenarios")
            review_ids.add(review_id)

        for call in normalized["tool_calls"]:
            call_id = call["call_id"]
            if call_id in tool_call_ids:
                raise EvidenceError("duplicate tool call id across scenarios")
            tool_call_ids.add(call_id)

        normalized_scenarios.append(normalized)

    if seen != set(required_ids) or len(normalized_scenarios) != len(required_ids):
        reasons.add("SCENARIO_UNIVERSE_MISMATCH")

    normalized_packet = deepcopy(top)
    normalized_packet["evaluation_set"]["required_scenarios"] = sorted(required_ids)
    normalized_packet["scenarios"] = sorted(
        normalized_scenarios,
        key=lambda item: item["scenario_id"],
    )
    return normalized_packet, _ordered_reasons(reasons)


def compile_receipt(packet: Any, *, evaluated_at: datetime) -> dict[str, Any]:
    """Compile deterministic review evidence for one verifier-owned instant."""
    evaluated_text = _format_utc(evaluated_at)
    normalized, reasons = validate_packet(
        packet,
        evaluated_at=_parse_utc(evaluated_text, name="evaluated_at"),
    )

    categories = {name: 0 for name in sorted(_ALLOWED_CATEGORIES)}
    tool_calls = 0
    side_effect_calls = 0
    for scenario in normalized["scenarios"]:
        categories[scenario["category"]] += 1
        tool_calls += len(scenario["tool_calls"])
        side_effect_calls += sum(
            item["effect_class"] == "EXTERNAL_SIDE_EFFECT"
            for item in scenario["tool_calls"]
        )

    receipt: dict[str, Any] = {
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "evaluation_id": normalized["evaluation_id"],
        "evaluation_set": {
            "set_id": normalized["evaluation_set"]["set_id"],
            "generation": normalized["evaluation_set"]["generation"],
            "sha256": normalized["evaluation_set"]["sha256"],
        },
        "agent_build": deepcopy(normalized["agent_build"]),
        "rubric": deepcopy(normalized["rubric"]),
        "policy_sha256": sha256_object(normalized["policy"]),
        "evaluated_at": evaluated_text,
        "packet_sha256": sha256_object(normalized),
        "scenario_count": len(normalized["scenarios"]),
        "category_counts": categories,
        "tool_call_count": tool_calls,
        "external_side_effect_call_count": side_effect_calls,
        "decision": DECISION_RELEASE if not reasons else DECISION_HOLD,
        "reason_codes": reasons,
        "authority": {
            "model_deployment": False,
            "tool_execution": False,
            "provider_mutation": False,
            "customer_data_access": False,
            "compliance_certification": False,
            "payment": False,
            "external_contact": False,
            "revenue_recognition": False,
        },
    }
    receipt["receipt_sha256"] = sha256_object(receipt)
    return receipt


def verify_receipt(
    packet: Any,
    receipt: Any,
    *,
    verified_at: datetime,
) -> dict[str, Any]:
    """Verify historical integrity and separately reassess current release fitness.

    ``valid`` is current-use validity, not merely historical byte integrity.
    A receipt whose bytes still match can therefore return
    ``integrity_valid=True`` and ``valid=False`` once evidence has expired.
    """
    if type(receipt) is not dict:
        return {
            "valid": False,
            "integrity_valid": False,
            "current_valid": False,
            "reason": "RECEIPT_NOT_OBJECT",
        }

    try:
        claimed_at = _parse_utc(
            receipt.get("evaluated_at"),
            name="receipt.evaluated_at",
        )
        verifier_now = _parse_utc(
            _format_utc(verified_at),
            name="verified_at",
        )
        if claimed_at > verifier_now:
            return {
                "valid": False,
                "integrity_valid": False,
                "current_valid": False,
                "reason": "RECEIPT_FROM_FUTURE",
            }
        historical = compile_receipt(packet, evaluated_at=claimed_at)
    except EvidenceError as exc:
        return {
            "valid": False,
            "integrity_valid": False,
            "current_valid": False,
            "reason": "MALFORMED_EVIDENCE",
            "detail": str(exc),
        }

    if _canonical_bytes(receipt) != _canonical_bytes(historical):
        return {
            "valid": False,
            "integrity_valid": False,
            "current_valid": False,
            "reason": "RECEIPT_MISMATCH",
        }

    try:
        current = compile_receipt(packet, evaluated_at=verifier_now)
    except EvidenceError as exc:  # defensive: historical compile already validated
        return {
            "valid": False,
            "integrity_valid": True,
            "current_valid": False,
            "reason": "CURRENT_EVIDENCE_MALFORMED",
            "detail": str(exc),
            "receipt_sha256": historical["receipt_sha256"],
        }

    current_valid = (
        historical["decision"] == DECISION_RELEASE
        and current["decision"] == DECISION_RELEASE
    )
    if current_valid:
        reason = "VERIFIED_CURRENT"
        decision = DECISION_RELEASE
    elif historical["decision"] != DECISION_RELEASE:
        reason = "HISTORICAL_RECEIPT_HOLD"
        decision = DECISION_HOLD
    else:
        reason = "CURRENT_EVIDENCE_HOLD"
        decision = DECISION_HOLD

    return {
        "valid": current_valid,
        "integrity_valid": True,
        "current_valid": current_valid,
        "reason": reason,
        "decision": decision,
        "historical_decision": historical["decision"],
        "current_reason_codes": current["reason_codes"],
        "receipt_sha256": historical["receipt_sha256"],
        "current_receipt_sha256": current["receipt_sha256"],
        "verified_at": _format_utc(verifier_now),
    }


def render_markdown(receipt: Mapping[str, Any]) -> str:
    """Render a compact deterministic human-review projection."""
    reasons = receipt["reason_codes"] or ["NONE"]
    categories = receipt["category_counts"]
    return "\n".join(
        [
            "# Agentic GenAI Evaluation Evidence Gate",
            "",
            f"- Decision: **{receipt['decision']}**",
            f"- Evaluation: `{receipt['evaluation_id']}`",
            (
                "- Agent build: "
                f"`{receipt['agent_build']['agent_id']}@"
                f"{receipt['agent_build']['version']}`"
            ),
            f"- Agent SHA-256: `{receipt['agent_build']['sha256']}`",
            (
                "- Rubric: "
                f"`{receipt['rubric']['rubric_id']}@"
                f"{receipt['rubric']['generation']}`"
            ),
            f"- Evaluated at: `{receipt['evaluated_at']}`",
            f"- Scenarios: `{receipt['scenario_count']}`",
            (
                "- Categories: "
                f"`{json.dumps(categories, sort_keys=True, separators=(',', ':'))}`"
            ),
            (
                f"- Tool calls: `{receipt['tool_call_count']}` "
                "(external-side-effect evidence: "
                f"`{receipt['external_side_effect_call_count']}`)"
            ),
            f"- Reasons: `{','.join(reasons)}`",
            f"- Packet SHA-256: `{receipt['packet_sha256']}`",
            f"- Receipt SHA-256: `{receipt['receipt_sha256']}`",
            "",
            (
                "This receipt is review evidence only. It authorizes no deployment, "
                "tool execution, provider mutation, customer-data access, compliance "
                "conclusion, payment, contact, or revenue recognition."
            ),
            "",
        ]
    )
