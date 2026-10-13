"""Deterministic record analysis, not a certification or causal inference engine."""
from __future__ import annotations

from collections import Counter
from fractions import Fraction

try:
    from .contract import SCHEMA, STAGES, moment, validate
except ImportError:
    from contract import SCHEMA, STAGES, moment, validate


def effectiveness(action: dict, sources: dict) -> dict:
    measure = action.get("effectiveness")
    result = {"state": "not_measured", "rates_per_1000": None, "reasons": []}
    if measure is None:
        return result
    before, after = measure["before"], measure["after"]
    reasons = []
    if not action.get("completed_at"):
        reasons.append("implementation_time_unknown")
    elif moment(after["start"]) < moment(action["completed_at"]):
        reasons.append("followup_precedes_completion")
    if action.get("completed_at") and moment(before["end"]) > moment(action["completed_at"]):
        reasons.append("baseline_overlaps_implementation")
    if before["unit"] != after["unit"] or before["cohort"] != after["cohort"]:
        reasons.append("different_unit_or_cohort")
    for name, window in (("before", before), ("after", after)):
        if not window["complete"]:
            reasons.append(name + "_coverage_incomplete")
        if not window["evidence_ids"]:
            reasons.append(name + "_measurement_evidence_missing")
        elif any(moment(sources[s]["observed_at"]) < moment(window["end"]) for s in window["evidence_ids"]):
            reasons.append(name + "_evidence_precedes_window_end")
        if window["events"] is None or window["exposure"] is None:
            reasons.append(name + "_count_unknown")
        elif window["exposure"] == 0:
            reasons.append(name + "_zero_exposure")
    if reasons:
        result.update(state="not_comparable", reasons=reasons)
        return result
    a, b = (Fraction(w["events"], w["exposure"]) for w in (before, after))
    improved = b < a if measure["direction"] == "lower" else b > a
    result.update(state="observed_improvement" if improved else "unchanged" if a == b else "observed_deterioration",
                  rates_per_1000={"before": float(a * 1000), "after": float(b * 1000)},
                  reasons=["descriptive_comparison_not_causal_proof"])
    return result


def action_result(action: dict, data: dict, sources: dict) -> dict:
    as_of = moment(data["as_of"])
    completed = moment(action["completed_at"]) if action.get("completed_at") else None
    impl, verified = action["implementation_evidence_ids"], action["verification_evidence_ids"]
    impl_supported = bool(impl) and completed is not None and all(
        moment(sources[s]["observed_at"]) <= completed for s in impl)
    verification_supported = impl_supported and bool(verified) and all(
        moment(sources[s]["observed_at"]) >= completed for s in verified)
    state = "open_work"
    if action["status"] == "closed":
        state = "implementation_verified" if verification_supported else "closure_unverified"
    elif action["status"] == "replaced":
        decision = action.get("replacement")
        state = "replacement_documented" if decision and decision["evidence_ids"] else "replacement_unsubstantiated"
    issues = []
    if not action["owner_role"]:
        issues.append("owner_role_unknown")
    if not action.get("due_at"):
        issues.append("due_time_unknown")
    if state == "closure_unverified":
        issues.append("closed_without_complete_implementation_and_verification_evidence")
    if action["status"] not in ("closed", "replaced") and completed:
        issues.append("completion_record_conflicts_with_open_status")
    if action["status"] != "replaced" and action.get("replacement"):
        issues.append("replacement_record_conflicts_with_status")
    due = moment(action["due_at"]) if action.get("due_at") else None
    overdue = due is not None and as_of > due and state not in ("implementation_verified", "replacement_documented")
    result = {"id": action["id"], "description": action["description"], "incident_ids": action["incident_ids"],
              "condition_ids": action["condition_ids"], "owner_role": action["owner_role"],
              "reported_status": action["status"], "evidence_state": state,
              "created_at": action["created_at"], "completed_at": action.get("completed_at"),
              "measurement": action.get("effectiveness"), "due_at": action.get("due_at"),
              "overdue_unresolved": overdue,
              "days_past_due": round((as_of - due).total_seconds() / 86400, 3) if overdue else 0,
              "late_completion_days": round(max(0, (completed - due).total_seconds()) / 86400, 3)
              if due and completed else None,
              "implementation_evidence_ids": impl, "verification_evidence_ids": verified,
              "replacement": action.get("replacement"), "effectiveness": effectiveness(action, sources), "issues": issues}
    if result["effectiveness"]["state"] == "observed_improvement" and state != "implementation_verified":
        result["issues"].append("observed_improvement_not_linked_to_verified_implementation")
    return result


def analyze(data: dict) -> dict:
    validate(data)
    sources = {s["id"]: s for s in data["sources"]}
    actions = [action_result(a, data, sources) for a in sorted(data["actions"], key=lambda a: a["id"])]
    incidents = []
    for incident in sorted(data["incidents"], key=lambda i: i["id"]):
        events = {e["kind"]: e for e in incident["events"]}
        supported = [stage for stage in STAGES if stage in events and any(
            sources[s]["kind"] in ("incident_record", "verification") for s in events[stage]["evidence_ids"])]
        durations = {}
        for name, left, right in (("impact_to_restoration", "impact_start", "restored"),
                                  ("detection_to_restoration", "detected", "restored"),
                                  ("restoration_to_verification", "restored", "verified")):
            endpoints_supported = left in supported and right in supported
            durations[name] = round((moment(events[right]["at"]) - moment(events[left]["at"])).total_seconds() / 60, 3) if endpoints_supported else None
        related = [a for a in actions if incident["id"] in a["incident_ids"]]
        covered = {c for a in related for c in a["condition_ids"]}
        incidents.append({"id": incident["id"], "group": incident["group"], "service": incident["service"],
                          "impact": incident["impact"], "coverage": incident["coverage"],
                          "evidence_ids": incident["evidence_ids"], "events": incident["events"],
                          "condition_ids": incident["condition_ids"], "minutes": durations,
                          "milestones_with_evidence": supported,
                          "milestones_missing_evidence": [s for s in STAGES if s not in supported],
                          "analysis_supported": bool(incident["review"]["analysis_evidence_ids"]),
                          "sharing_supported": bool(incident["review"]["sharing_evidence_ids"]),
                          "review": incident["review"], "action_ids": [a["id"] for a in related],
                          "conditions_without_actions": sorted(set(incident["condition_ids"]) - covered),
                          "verified_action_ids": [a["id"] for a in related if a["evidence_state"] == "implementation_verified"]})
    recurring = []
    for condition in sorted(data["conditions"], key=lambda c: c["id"]):
        occurrences = [i for i in incidents if condition["id"] in i["condition_ids"]]
        related = [a for a in actions if condition["id"] in a["condition_ids"]]
        recurring.append({**condition, "incident_ids": [i["id"] for i in occurrences],
                          "groups": sorted({i["group"] for i in occurrences}),
                          "observed_incident_count": len(occurrences), "recurring_in_supplied_records": len(occurrences) > 1,
                          "action_ids": [a["id"] for a in related],
                          "unresolved_action_ids": [a["id"] for a in related if a["evidence_state"] not in ("implementation_verified", "replacement_documented")],
                          "interpretation": "Supplied records only; shared dependency is not independent group evidence or a recurrence rate."})
    return {"schema": SCHEMA, "classification": data["classification"], "as_of": data["as_of"],
            "limits": ["Record consistency and stated evidence; source authenticity and sufficiency need analyst review.",
                       "No maturity score, compliance verdict, employee rating, or causal claim.",
                       "No post-intervention incident does not establish effectiveness without exposure and coverage."],
            "summary": {"incidents": len(incidents), "actions": len(actions),
                        "states": dict(sorted(Counter(a["evidence_state"] for a in actions).items())),
                        "overdue_unresolved": sum(a["overdue_unresolved"] for a in actions)},
            "incidents": incidents, "actions": actions, "conditions": recurring,
            "sources": sorted(data["sources"], key=lambda s: s["id"])}
