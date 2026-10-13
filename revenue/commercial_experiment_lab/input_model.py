from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from .common import (
    FAMILIES, MAX_ARMS, MAX_ASSIGNMENT_AGE_SECONDS, MAX_OPPORTUNITIES,
    UPSTREAM_READY, LabError, exact_keys, parse_time, require_id, require_int,
    require_slug, validate_source,
)

def _compile_upstream(funnel: Any, *, as_of: str) -> dict[str, Any]:
    """Compile through the landed commercial-funnel implementation.

    The import is intentionally local: this package can be inspected in isolation,
    while repository/runtime execution always binds to the real upstream compiler.
    """
    try:
        from revenue.commercial_funnel import FunnelError, compile_funnel
    except ImportError as exc:  # pragma: no cover - repository always carries it
        raise LabError("revenue.commercial_funnel is required") from exc
    try:
        return compile_funnel(funnel, as_of=as_of)
    except FunnelError as exc:
        raise LabError(f"upstream commercial funnel refused input: {exc}") from exc

def _normalize_arm(raw: Any, field: str) -> dict[str, str]:
    arm = exact_keys(
        raw,
        required=("id", "segment", "offer_id", "offer_version", "proof_package", "route_class"),
        field=field,
    )
    return {
        "id": require_id(arm["id"], f"{field}.id"),
        "segment": require_slug(arm["segment"], f"{field}.segment"),
        "offer_id": require_id(arm["offer_id"], f"{field}.offer_id"),
        "offer_version": require_id(arm["offer_version"], f"{field}.offer_version"),
        "proof_package": require_slug(arm["proof_package"], f"{field}.proof_package"),
        "route_class": require_slug(arm["route_class"], f"{field}.route_class"),
    }

def _normalize_plan(raw: Any, *, evaluated: datetime) -> dict[str, Any]:
    plan = exact_keys(
        raw,
        required=(
            "id",
            "revision",
            "family",
            "declared_at",
            "source",
            "opportunity_ids",
            "arms",
            "minimum_sample_per_arm",
            "thresholds",
        ),
        field="plan",
    )
    family = plan["family"]
    if family not in FAMILIES:
        raise LabError("plan.family invalid")
    declared_at = parse_time(plan["declared_at"], "plan.declared_at")
    if declared_at > evaluated:
        raise LabError("plan.declared_at is in the future")
    if int((evaluated - declared_at).total_seconds()) > MAX_ASSIGNMENT_AGE_SECONDS:
        raise LabError("plan.declared_at is outside the current experiment window")

    opp_raw = plan["opportunity_ids"]
    if not isinstance(opp_raw, list) or not opp_raw or len(opp_raw) > MAX_OPPORTUNITIES:
        raise LabError(f"plan.opportunity_ids must contain 1..{MAX_OPPORTUNITIES} ids")
    opportunity_ids: list[str] = []
    seen_opps: set[str] = set()
    for i, value in enumerate(opp_raw):
        opp_id = require_id(value, f"plan.opportunity_ids[{i}]")
        if opp_id in seen_opps:
            raise LabError(f"duplicate plan opportunity id: {opp_id}")
        seen_opps.add(opp_id)
        opportunity_ids.append(opp_id)
    opportunity_ids.sort()

    arms_raw = plan["arms"]
    if not isinstance(arms_raw, list) or len(arms_raw) < 2 or len(arms_raw) > MAX_ARMS:
        raise LabError(f"plan.arms must contain 2..{MAX_ARMS} arms")
    arms: list[dict[str, str]] = []
    seen_arms: set[str] = set()
    for i, raw_arm in enumerate(arms_raw):
        arm = _normalize_arm(raw_arm, f"plan.arms[{i}]")
        if arm["id"] in seen_arms:
            raise LabError(f"duplicate arm id: {arm['id']}")
        seen_arms.add(arm["id"])
        arms.append(arm)
    arms.sort(key=lambda item: item["id"])

    thresholds = exact_keys(
        plan["thresholds"],
        required=("expand_reply_bps", "expand_acceptance_bps", "pause_reply_bps"),
        field="plan.thresholds",
    )
    normalized_thresholds = {
        "expand_reply_bps": require_int(thresholds["expand_reply_bps"], "plan.thresholds.expand_reply_bps", minimum=0, maximum=10_000),
        "expand_acceptance_bps": require_int(thresholds["expand_acceptance_bps"], "plan.thresholds.expand_acceptance_bps", minimum=0, maximum=10_000),
        "pause_reply_bps": require_int(thresholds["pause_reply_bps"], "plan.thresholds.pause_reply_bps", minimum=0, maximum=10_000),
    }
    if normalized_thresholds["pause_reply_bps"] > normalized_thresholds["expand_reply_bps"]:
        raise LabError("pause_reply_bps cannot exceed expand_reply_bps")

    return {
        "id": require_id(plan["id"], "plan.id"),
        "revision": require_id(plan["revision"], "plan.revision"),
        "family": family,
        "declared_at": plan["declared_at"],
        "source": validate_source(plan["source"], "plan.source"),
        "opportunity_ids": opportunity_ids,
        "arms": arms,
        "minimum_sample_per_arm": require_int(plan["minimum_sample_per_arm"], "plan.minimum_sample_per_arm", minimum=1, maximum=MAX_OPPORTUNITIES),
        "thresholds": normalized_thresholds,
    }

def _normalize_assignments(raw: Any, *, plan: Mapping[str, Any], evaluated: datetime) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw or len(raw) > MAX_OPPORTUNITIES:
        raise LabError(f"assignments must contain 1..{MAX_OPPORTUNITIES} rows")
    target_ids = set(plan["opportunity_ids"])
    arm_ids = {arm["id"] for arm in plan["arms"]}
    declared = parse_time(plan["declared_at"], "plan.declared_at")
    assignments: list[dict[str, Any]] = []
    seen_assignment_ids: set[str] = set()
    seen_opps: set[str] = set()
    for i, raw_assignment in enumerate(raw):
        field = f"assignments[{i}]"
        assignment = exact_keys(
            raw_assignment,
            required=("id", "opportunity_id", "arm_id", "assigned_at", "evidence"),
            field=field,
        )
        assignment_id = require_id(assignment["id"], f"{field}.id")
        opportunity_id = require_id(assignment["opportunity_id"], f"{field}.opportunity_id")
        arm_id = require_id(assignment["arm_id"], f"{field}.arm_id")
        if assignment_id in seen_assignment_ids:
            raise LabError(f"duplicate assignment id: {assignment_id}")
        if opportunity_id in seen_opps:
            raise LabError(f"opportunity assigned more than once: {opportunity_id}")
        if opportunity_id not in target_ids:
            raise LabError(f"assignment references opportunity outside recorded cohort: {opportunity_id}")
        if arm_id not in arm_ids:
            raise LabError(f"assignment references unknown arm: {arm_id}")
        assigned = parse_time(assignment["assigned_at"], f"{field}.assigned_at")
        if assigned < declared:
            raise LabError(f"assignment predates experiment declaration: {opportunity_id}")
        if assigned > evaluated:
            raise LabError(f"assignment is in the future: {opportunity_id}")
        if int((evaluated - assigned).total_seconds()) > MAX_ASSIGNMENT_AGE_SECONDS:
            raise LabError(f"assignment is outside current experiment window: {opportunity_id}")
        seen_assignment_ids.add(assignment_id)
        seen_opps.add(opportunity_id)
        assignments.append(
            {
                "id": assignment_id,
                "opportunity_id": opportunity_id,
                "arm_id": arm_id,
                "assigned_at": assignment["assigned_at"],
                "evidence": validate_source(assignment["evidence"], f"{field}.evidence"),
            }
        )
    missing = target_ids - seen_opps
    if missing:
        raise LabError(f"recorded cohort missing assignments: {sorted(missing)}")
    assignments.sort(key=lambda item: (item["opportunity_id"], item["id"]))
    return assignments

def _validate_bindings(
    *,
    plan: Mapping[str, Any],
    assignments: list[dict[str, Any]],
    upstream_opportunities: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    opportunity_map: dict[str, dict[str, Any]] = {}
    for opp in upstream_opportunities:
        if not isinstance(opp, dict) or not isinstance(opp.get("id"), str):
            raise LabError("upstream funnel opportunity shape invalid")
        if opp["id"] in opportunity_map:
            raise LabError(f"upstream funnel duplicate opportunity: {opp['id']}")
        opportunity_map[opp["id"]] = opp
    missing = set(plan["opportunity_ids"]) - set(opportunity_map)
    if missing:
        raise LabError(f"recorded experiment opportunity missing from upstream funnel: {sorted(missing)}")

    arm_map = {arm["id"]: arm for arm in plan["arms"]}
    assignment_map = {assignment["opportunity_id"]: assignment for assignment in assignments}
    for opportunity_id in plan["opportunity_ids"]:
        opp = opportunity_map[opportunity_id]
        assignment = assignment_map[opportunity_id]
        arm = arm_map[assignment["arm_id"]]
        if opp.get("family") != plan["family"]:
            raise LabError(f"opportunity family does not match recorded experiment family: {opportunity_id}")
        offer = opp.get("offer")
        if not isinstance(offer, dict) or offer.get("id") != arm["offer_id"] or offer.get("version") != arm["offer_version"]:
            raise LabError(f"arm offer identity does not match upstream funnel: {opportunity_id}")
        events = opp.get("events")
        if not isinstance(events, list):
            raise LabError(f"upstream events invalid: {opportunity_id}")
        if events:
            earliest = min(parse_time(event.get("observed_at"), f"upstream.{opportunity_id}.event.observed_at") for event in events)
            assigned = parse_time(assignment["assigned_at"], f"assignment.{opportunity_id}.assigned_at")
            if assigned >= earliest:
                raise LabError(f"post-outcome assignment refused: {opportunity_id}")
    return opportunity_map, assignment_map
