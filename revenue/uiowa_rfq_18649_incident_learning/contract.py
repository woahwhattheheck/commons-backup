"""Input contract for an offline, evidence-linked incident-learning assessment."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

SCHEMA = "uiowa-incident-learning/v1"
KINDS = {"interview", "incident_record", "implementation", "verification", "measurement", "decision"}
STAGES = ("impact_start", "detected", "coordinated", "mitigated", "restored", "verified", "reviewed")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def moment(value: str) -> datetime:
    require(isinstance(value, str), "timestamp must be a string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid ISO timestamp: " + value) from error
    require(result.tzinfo is not None and result.utcoffset() is not None, "timestamp needs UTC offset")
    return result


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def index(rows: object, label: str) -> dict:
    require(isinstance(rows, list), label + " must be a list")
    result = {}
    for row in rows:
        require(isinstance(row, dict) and text(row.get("id")), label + " row needs id")
        require(row["id"] not in result, "duplicate " + label + " id: " + row["id"])
        result[row["id"]] = row
    return result


def references(values: object, pool: dict, label: str) -> list:
    require(isinstance(values, list), label + " must be a list")
    require(all(text(value) and value in pool for value in values), "unresolved " + label)
    require(len(values) == len(set(values)), "duplicate " + label)
    return values


def validate(data: dict) -> dict:
    require(isinstance(data, dict) and data.get("schema") == SCHEMA, "unsupported input schema")
    require(data.get("classification") in ("synthetic", "engagement"), "classification required")
    as_of = moment(data.get("as_of"))
    sources = index(data.get("sources"), "source")
    conditions = index(data.get("conditions"), "condition")
    incidents = index(data.get("incidents"), "incident")
    actions = index(data.get("actions"), "action")
    for source in sources.values():
        require(source.get("kind") in KINDS and text(source.get("locator"))
                and text(source.get("excerpt")), "source needs kind, locator and excerpt")
        require(moment(source.get("observed_at")) <= as_of, "source is later than as_of")
    for condition in conditions.values():
        require(text(condition.get("description")), "condition description required")
        references(condition.get("evidence_ids"), sources, "condition evidence")
    for incident in incidents.values():
        require(incident.get("group") in ("ESS", "RIS", "IAM"), "unknown group")
        require(text(incident.get("service")) and text(incident.get("impact")), "service and impact required")
        require(incident.get("coverage") in ("complete", "partial", "unknown"), "coverage required")
        references(incident.get("condition_ids"), conditions, "incident condition")
        references(incident.get("evidence_ids"), sources, "incident evidence")
        require(isinstance(incident.get("events"), list), "events must be a list")
        events = {}
        for event in incident["events"]:
            require(isinstance(event, dict), "event must be an object")
            kind = event.get("kind")
            require(kind in STAGES and kind not in events, "invalid or duplicate milestone")
            events[kind] = moment(event.get("at"))
            require(events[kind] <= as_of, "event is later than as_of")
            require(text(event.get("note")), "event note required")
            references(event.get("evidence_ids"), sources, "event evidence")
        # Coordination and mitigation can occur in either order. Detection may
        # precede impact; do not invent a universal ordering for those milestones.
        for left, right in (("detected", "restored"), ("impact_start", "restored"),
                            ("restored", "verified"), ("verified", "reviewed")):
            require(left not in events or right not in events or events[left] <= events[right],
                    "reversed timeline: " + left + " > " + right)
        review = incident.get("review")
        require(isinstance(review, dict) and text(review.get("analysis")), "review analysis required")
        for field in ("analysis_evidence_ids", "sharing_evidence_ids"):
            references(review.get(field), sources, "review " + field)
        require(isinstance(review.get("unresolved_questions"), list)
                and all(text(q) for q in review["unresolved_questions"]), "questions must be strings")
    for action in actions.values():
        require(text(action.get("description")), "action description required")
        require(action.get("status") in ("open", "in_progress", "closed", "replaced"), "invalid action status")
        require(action.get("owner_role") is None or text(action["owner_role"]), "invalid owner role")
        created = moment(action.get("created_at"))
        require(created <= as_of, "action is later than as_of")
        for field in ("due_at", "completed_at"):
            if action.get(field) is not None:
                require(moment(action[field]) >= created, field + " precedes creation")
        if action.get("completed_at") is not None:
            require(moment(action["completed_at"]) <= as_of, "completion is later than as_of")
        for field, pool in (("incident_ids", incidents), ("condition_ids", conditions),
                            ("implementation_evidence_ids", sources), ("verification_evidence_ids", sources)):
            references(action.get(field), pool, "action " + field)
        require(bool(action["incident_ids"]) and bool(action["condition_ids"]), "action needs incident and condition")
        linked = {c for i in action["incident_ids"] for c in incidents[i]["condition_ids"]}
        require(set(action["condition_ids"]) <= linked, "action condition absent from linked incidents")
        for field, kind in (("implementation_evidence_ids", "implementation"),
                            ("verification_evidence_ids", "verification")):
            require(all(sources[s]["kind"] == kind for s in action[field]), "wrong evidence kind for " + field)
        decision = action.get("replacement")
        if decision is not None:
            require(isinstance(decision, dict) and text(decision.get("reason")), "replacement needs reason")
            require(decision.get("action_id") in actions and decision["action_id"] != action["id"], "invalid replacement")
            refs = references(decision.get("evidence_ids"), sources, "replacement evidence")
            require(all(sources[s]["kind"] == "decision" for s in refs), "replacement needs decision evidence")
            replacement = actions[decision["action_id"]]
            require(set(action["condition_ids"]) <= set(replacement.get("condition_ids", [])),
                    "replacement drops original contributing conditions")
        measure = action.get("effectiveness")
        if measure is not None:
            validate_measure(measure, sources, as_of)
    for start in actions:
        seen, cursor = set(), start
        while cursor is not None:
            require(cursor not in seen, "replacement cycle")
            seen.add(cursor)
            decision = actions[cursor].get("replacement")
            cursor = decision["action_id"] if decision else None
    return data


def validate_measure(measure: dict, sources: dict, as_of: datetime) -> None:
    require(isinstance(measure, dict) and text(measure.get("metric")), "metric required")
    require(measure.get("direction") in ("lower", "higher"), "metric direction required")
    for name in ("before", "after"):
        window = measure.get(name)
        require(isinstance(window, dict), "measurement window required")
        start, end = moment(window.get("start")), moment(window.get("end"))
        require(start < end <= as_of, "invalid measurement interval")
        for field in ("events", "exposure"):
            value = window.get(field)
            require(value is None or type(value) is int and value >= 0, "counts must be nonnegative integers or null")
        require(text(window.get("unit")) and text(window.get("cohort")), "unit and cohort required")
        require(type(window.get("complete")) is bool, "measurement completeness must be boolean")
        refs = references(window.get("evidence_ids"), sources, "measurement evidence")
        require(all(sources[s]["kind"] == "measurement" for s in refs), "measurement needs measurement evidence")
    require(moment(measure["before"]["end"]) <= moment(measure["after"]["start"]), "overlapping measurement windows")


def load(path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result
    return validate(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique))
