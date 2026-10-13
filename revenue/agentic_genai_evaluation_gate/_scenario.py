"""Per-scenario validation for the agentic evaluation evidence gate."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping

from ._schema import (
    _ALLOWED_CATEGORIES,
    _ALLOWED_EFFECTS,
    _ALLOWED_OBSERVABILITY,
    _ALLOWED_PASSFAIL,
    _ALLOWED_SAFETY,
    _ALLOWED_TOOL_RESULT,
    _AUTOMATED_KEYS,
    _OBS_KEYS,
    _REVIEW_KEYS,
    _SAFETY_KEYS,
    _SCENARIO_KEYS,
    _TOOL_KEYS,
    EvidenceError,
    _bound_sha,
    _require_dict,
    _require_id,
    _require_int,
    _require_sha,
    _require_str,
    _validate_time,
)


def _validate_tool_calls(
    calls: Any,
    *,
    scenario_id: str,
    trace_sha: str,
    result_sha: str,
    reasons: set[str],
) -> list[dict[str, Any]]:
    if type(calls) is not list:
        raise EvidenceError(f"scenario[{scenario_id}].tool_calls: expected array")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(calls):
        name = f"scenario[{scenario_id}].tool_calls[{index}]"
        call = _require_dict(raw, name=name, keys=_TOOL_KEYS)
        call_scenario = _require_id(
            call["scenario_id"],
            name=f"{name}.scenario_id",
        )
        if call_scenario != scenario_id:
            reasons.add("SCENARIO_BINDING_MISMATCH")
        call_id = _require_id(call["call_id"], name=f"{name}.call_id")
        if call_id in seen:
            raise EvidenceError(f"scenario[{scenario_id}]: duplicate tool call id")
        seen.add(call_id)
        _require_id(call["tool"], name=f"{name}.tool")
        _require_id(call["action"], name=f"{name}.action")
        _require_str(
            call["effect_class"],
            name=f"{name}.effect_class",
            allowed=_ALLOWED_EFFECTS,
        )
        status = _require_str(
            call["result_status"],
            name=f"{name}.result_status",
            allowed=_ALLOWED_TOOL_RESULT,
        )
        _bound_sha(
            call["trace_sha256"],
            expected=trace_sha,
            name=f"{name}.trace_sha256",
            reason="TRACE_BINDING_MISMATCH",
            reasons=reasons,
        )
        _bound_sha(
            call["result_sha256"],
            expected=result_sha,
            name=f"{name}.result_sha256",
            reason="RESULT_BINDING_MISMATCH",
            reasons=reasons,
        )
        if status == "UNKNOWN":
            reasons.add("TOOL_RESULT_UNKNOWN")
        elif status == "FAILURE":
            reasons.add("TOOL_RESULT_FAILED")
        normalized.append(deepcopy(call))
    normalized.sort(key=lambda item: item["call_id"])
    return normalized


def _validate_scenario(
    raw: Any,
    *,
    build_sha: str,
    rubric_sha: str,
    minimum_score_bps: int,
    evaluated_at: datetime,
    policy: Mapping[str, Any],
    reasons: set[str],
) -> dict[str, Any]:
    scenario = _require_dict(raw, name="scenario", keys=_SCENARIO_KEYS)
    scenario_id = _require_id(scenario["scenario_id"], name="scenario_id")
    _require_str(
        scenario["category"],
        name=f"scenario[{scenario_id}].category",
        allowed=_ALLOWED_CATEGORIES,
    )

    scenario_build = _require_sha(
        scenario["agent_build_sha256"],
        name=f"scenario[{scenario_id}].agent_build_sha256",
    )
    scenario_rubric = _require_sha(
        scenario["rubric_sha256"],
        name=f"scenario[{scenario_id}].rubric_sha256",
    )
    trace_sha = _require_sha(
        scenario["trace_sha256"],
        name=f"scenario[{scenario_id}].trace_sha256",
    )
    result_sha = _require_sha(
        scenario["result_sha256"],
        name=f"scenario[{scenario_id}].result_sha256",
    )
    if scenario_build != build_sha:
        reasons.add("AGENT_BUILD_MISMATCH")
    if scenario_rubric != rubric_sha:
        reasons.add("RUBRIC_MISMATCH")

    max_age = policy["max_evidence_age_seconds"]
    _validate_time(
        scenario["evidence_at"],
        name=f"scenario[{scenario_id}].evidence_at",
        evaluated_at=evaluated_at,
        max_age_seconds=max_age,
        reasons=reasons,
    )

    automated = _require_dict(
        scenario["automated_result"],
        name=f"scenario[{scenario_id}].automated_result",
        keys=_AUTOMATED_KEYS,
    )
    automated_scenario = _require_id(
        automated["scenario_id"],
        name=f"scenario[{scenario_id}].automated_result.scenario_id",
    )
    if automated_scenario != scenario_id:
        reasons.add("SCENARIO_BINDING_MISMATCH")
    automated_status = _require_str(
        automated["status"],
        name=f"scenario[{scenario_id}].automated_result.status",
        allowed=_ALLOWED_PASSFAIL,
    )
    score = _require_int(
        automated["score_bps"],
        name=f"scenario[{scenario_id}].automated_result.score_bps",
        minimum=0,
        maximum=10_000,
    )
    _require_sha(
        automated["evaluator_sha256"],
        name=f"scenario[{scenario_id}].automated_result.evaluator_sha256",
    )
    _validate_time(
        automated["observed_at"],
        name=f"scenario[{scenario_id}].automated_result.observed_at",
        evaluated_at=evaluated_at,
        max_age_seconds=max_age,
        reasons=reasons,
    )
    _bound_sha(
        automated["agent_build_sha256"],
        expected=build_sha,
        name=f"scenario[{scenario_id}].automated_result.agent_build_sha256",
        reason="AGENT_BUILD_MISMATCH",
        reasons=reasons,
    )
    _bound_sha(
        automated["rubric_sha256"],
        expected=rubric_sha,
        name=f"scenario[{scenario_id}].automated_result.rubric_sha256",
        reason="RUBRIC_MISMATCH",
        reasons=reasons,
    )
    _bound_sha(
        automated["trace_sha256"],
        expected=trace_sha,
        name=f"scenario[{scenario_id}].automated_result.trace_sha256",
        reason="TRACE_BINDING_MISMATCH",
        reasons=reasons,
    )
    _bound_sha(
        automated["result_sha256"],
        expected=result_sha,
        name=f"scenario[{scenario_id}].automated_result.result_sha256",
        reason="RESULT_BINDING_MISMATCH",
        reasons=reasons,
    )
    if score < minimum_score_bps:
        reasons.add("AUTOMATED_SCORE_BELOW_THRESHOLD")
    if automated_status != "PASS":
        reasons.add("AUTOMATED_EVALUATION_FAILED")

    review_raw = scenario["human_review"]
    if review_raw is None:
        if policy["require_human_review"]:
            reasons.add("HUMAN_REVIEW_MISSING")
        review = None
    else:
        review = _require_dict(
            review_raw,
            name=f"scenario[{scenario_id}].human_review",
            keys=_REVIEW_KEYS,
        )
        review_scenario = _require_id(
            review["scenario_id"],
            name=f"scenario[{scenario_id}].human_review.scenario_id",
        )
        if review_scenario != scenario_id:
            reasons.add("SCENARIO_BINDING_MISMATCH")
        _require_id(review["review_id"], name=f"scenario[{scenario_id}].review_id")
        _require_id(
            review["reviewer_role"],
            name=f"scenario[{scenario_id}].reviewer_role",
        )
        decision = _require_str(
            review["decision"],
            name=f"scenario[{scenario_id}].human_review.decision",
            allowed=_ALLOWED_PASSFAIL,
        )
        _validate_time(
            review["decided_at"],
            name=f"scenario[{scenario_id}].human_review.decided_at",
            evaluated_at=evaluated_at,
            max_age_seconds=max_age,
            reasons=reasons,
        )
        _bound_sha(
            review["agent_build_sha256"],
            expected=build_sha,
            name=f"scenario[{scenario_id}].human_review.agent_build_sha256",
            reason="AGENT_BUILD_MISMATCH",
            reasons=reasons,
        )
        _bound_sha(
            review["rubric_sha256"],
            expected=rubric_sha,
            name=f"scenario[{scenario_id}].human_review.rubric_sha256",
            reason="RUBRIC_MISMATCH",
            reasons=reasons,
        )
        _bound_sha(
            review["trace_sha256"],
            expected=trace_sha,
            name=f"scenario[{scenario_id}].human_review.trace_sha256",
            reason="TRACE_BINDING_MISMATCH",
            reasons=reasons,
        )
        _bound_sha(
            review["result_sha256"],
            expected=result_sha,
            name=f"scenario[{scenario_id}].human_review.result_sha256",
            reason="RESULT_BINDING_MISMATCH",
            reasons=reasons,
        )
        if decision != "PASS":
            reasons.add("HUMAN_REVIEW_FAILED")

    safety = _require_dict(
        scenario["safety"],
        name=f"scenario[{scenario_id}].safety",
        keys=_SAFETY_KEYS,
    )
    safety_scenario = _require_id(
        safety["scenario_id"],
        name=f"scenario[{scenario_id}].safety.scenario_id",
    )
    if safety_scenario != scenario_id:
        reasons.add("SCENARIO_BINDING_MISMATCH")
    safety_status = _require_str(
        safety["status"],
        name=f"scenario[{scenario_id}].safety.status",
        allowed=_ALLOWED_SAFETY,
    )
    _require_sha(
        safety["checks_sha256"],
        name=f"scenario[{scenario_id}].safety.checks_sha256",
    )
    _validate_time(
        safety["observed_at"],
        name=f"scenario[{scenario_id}].safety.observed_at",
        evaluated_at=evaluated_at,
        max_age_seconds=max_age,
        reasons=reasons,
    )
    _bound_sha(
        safety["agent_build_sha256"],
        expected=build_sha,
        name=f"scenario[{scenario_id}].safety.agent_build_sha256",
        reason="AGENT_BUILD_MISMATCH",
        reasons=reasons,
    )
    _bound_sha(
        safety["trace_sha256"],
        expected=trace_sha,
        name=f"scenario[{scenario_id}].safety.trace_sha256",
        reason="TRACE_BINDING_MISMATCH",
        reasons=reasons,
    )
    _bound_sha(
        safety["result_sha256"],
        expected=result_sha,
        name=f"scenario[{scenario_id}].safety.result_sha256",
        reason="RESULT_BINDING_MISMATCH",
        reasons=reasons,
    )
    if safety_status == "UNKNOWN":
        reasons.add("SAFETY_UNKNOWN")
    elif safety_status == "FAIL":
        reasons.add("SAFETY_FAILED")

    observability = _require_dict(
        scenario["observability"],
        name=f"scenario[{scenario_id}].observability",
        keys=_OBS_KEYS,
    )
    observability_scenario = _require_id(
        observability["scenario_id"],
        name=f"scenario[{scenario_id}].observability.scenario_id",
    )
    if observability_scenario != scenario_id:
        reasons.add("SCENARIO_BINDING_MISMATCH")
    observability_status = _require_str(
        observability["status"],
        name=f"scenario[{scenario_id}].observability.status",
        allowed=_ALLOWED_OBSERVABILITY,
    )
    _require_sha(
        observability["pointer_sha256"],
        name=f"scenario[{scenario_id}].observability.pointer_sha256",
    )
    _validate_time(
        observability["observed_at"],
        name=f"scenario[{scenario_id}].observability.observed_at",
        evaluated_at=evaluated_at,
        max_age_seconds=max_age,
        reasons=reasons,
    )
    _bound_sha(
        observability["trace_sha256"],
        expected=trace_sha,
        name=f"scenario[{scenario_id}].observability.trace_sha256",
        reason="TRACE_BINDING_MISMATCH",
        reasons=reasons,
    )
    _bound_sha(
        observability["result_sha256"],
        expected=result_sha,
        name=f"scenario[{scenario_id}].observability.result_sha256",
        reason="RESULT_BINDING_MISMATCH",
        reasons=reasons,
    )
    if policy["require_complete_observability"] and observability_status != "COMPLETE":
        reasons.add("OBSERVABILITY_INCOMPLETE")

    normalized = deepcopy(scenario)
    normalized["tool_calls"] = _validate_tool_calls(
        scenario["tool_calls"],
        scenario_id=scenario_id,
        trace_sha=trace_sha,
        result_sha=result_sha,
        reasons=reasons,
    )
    return normalized
