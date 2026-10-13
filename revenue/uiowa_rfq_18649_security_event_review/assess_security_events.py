#!/usr/bin/env python3
"""Offline security-event review evidence assessor for UIOWA-060.

The tool evaluates supplied records only. It never connects to live systems, reads
credentials, or turns missing evidence into a security/compliance verdict.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REQUIRED = (
    "event_id",
    "service",
    "event_category",
    "security_relevant",
    "occurred_at",
    "collected_at",
    "retained_context",
    "review_owner",
    "reviewed_at",
    "decision",
    "escalation",
    "action",
    "monitoring_only",
)
FORBIDDEN_KEYS = {
    "password",
    "passwd",
    "credential",
    "credentials",
    "secret",
    "secret_value",
    "access_token",
    "api_key",
    "private_key",
}
CONTEXT_KEYS = ("actor", "target", "action", "source", "correlation_id")


class EvidenceError(ValueError):
    pass


def parse_ts(value: Any, field: str, event_id: str) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise EvidenceError(f"{event_id}: {field} must be an ISO-8601 string or null")
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise EvidenceError(f"{event_id}: invalid {field}: {value}") from exc
    if dt.tzinfo is None:
        raise EvidenceError(f"{event_id}: {field} must include a timezone")
    return dt.astimezone(timezone.utc)


def walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key).lower()
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def validate_record(record: dict[str, Any]) -> None:
    event_id = str(record.get("event_id") or "<missing-event-id>")
    missing = [name for name in REQUIRED if name not in record]
    if missing:
        raise EvidenceError(f"{event_id}: missing fields: {', '.join(missing)}")
    forbidden = sorted(set(walk_keys(record)) & FORBIDDEN_KEYS)
    if forbidden:
        raise EvidenceError(
            f"{event_id}: credential/secret material is out of scope; forbidden keys: {', '.join(forbidden)}"
        )
    if record["security_relevant"] not in (True, False, None):
        raise EvidenceError(f"{event_id}: security_relevant must be true, false, or null")
    if not isinstance(record["monitoring_only"], bool):
        raise EvidenceError(f"{event_id}: monitoring_only must be boolean")
    for obj_name in ("retained_context", "escalation", "action"):
        if not isinstance(record[obj_name], dict):
            raise EvidenceError(f"{event_id}: {obj_name} must be an object")
    if record["monitoring_only"] and record["security_relevant"] is True:
        raise EvidenceError(
            f"{event_id}: monitoring_only=true contradicts security_relevant=true; separate the records or clarify relevance"
        )

    occurred = parse_ts(record["occurred_at"], "occurred_at", event_id)
    collected = parse_ts(record["collected_at"], "collected_at", event_id)
    reviewed = parse_ts(record["reviewed_at"], "reviewed_at", event_id)
    escalated = parse_ts(record["escalation"].get("escalated_at"), "escalation.escalated_at", event_id)
    completed = parse_ts(record["action"].get("completed_at"), "action.completed_at", event_id)
    ordered = [("occurred_at", occurred), ("collected_at", collected), ("reviewed_at", reviewed),
               ("escalated_at", escalated), ("completed_at", completed)]
    prior_name, prior = None, None
    for name, ts in ordered:
        if ts is None:
            continue
        if prior is not None and ts < prior:
            raise EvidenceError(f"{event_id}: {name} precedes {prior_name}; timeline is inconsistent")
        prior_name, prior = name, ts


@dataclass(frozen=True)
class Assessment:
    event_id: str
    service: str
    event_category: str
    security_relevant: str
    monitoring_only: bool
    review_state: str
    action_state: str
    escalation_state: str
    context_completeness: str
    primary_status: str
    evidence_gaps: tuple[str, ...]
    evidence_strengths: tuple[str, ...]

    def as_row(self) -> dict[str, str]:
        return {
            "event_id": self.event_id,
            "service": self.service,
            "event_category": self.event_category,
            "security_relevant": self.security_relevant,
            "monitoring_only": str(self.monitoring_only).lower(),
            "review_state": self.review_state,
            "action_state": self.action_state,
            "escalation_state": self.escalation_state,
            "context_completeness": self.context_completeness,
            "primary_status": self.primary_status,
            "evidence_gaps": " | ".join(self.evidence_gaps),
            "evidence_strengths": " | ".join(self.evidence_strengths),
        }


def assess(record: dict[str, Any]) -> Assessment:
    validate_record(record)
    event_id = record["event_id"]
    relevant = record["security_relevant"]
    monitoring = record["monitoring_only"]
    context = record["retained_context"]
    gaps: list[str] = []
    strengths: list[str] = []

    missing_context = [key for key in CONTEXT_KEYS if context.get(key) in (None, "")]
    if missing_context:
        context_state = "PARTIAL"
        gaps.append("retained context missing: " + ", ".join(missing_context))
    else:
        context_state = "COMPLETE"
        strengths.append("retained context links actor/target/action/source/correlation")

    if relevant is None:
        review_state = "RELEVANCE_UNKNOWN"
        action_state = "NOT_EVALUATED"
        escalation_state = "NOT_EVALUATED"
        gaps.append("security relevance is not established")
        primary = "UNKNOWN_SECURITY_RELEVANCE"
    elif relevant is False:
        if monitoring:
            review_state = "MONITORING_PATH"
            action_state = "NOT_REQUIRED_BY_RECORD"
            escalation_state = "NOT_REQUIRED_BY_RECORD"
            primary = "MONITORING_SIGNAL_NOT_SECURITY_REVIEW"
            strengths.append("record explicitly separates general monitoring from security review")
        else:
            review_state = "NOT_SECURITY_RELEVANT"
            action_state = "NOT_REQUIRED_BY_RECORD"
            escalation_state = "NOT_REQUIRED_BY_RECORD"
            primary = "NON_SECURITY_EVENT"
    else:
        owner = record.get("review_owner")
        reviewed_at = record.get("reviewed_at")
        decision = record.get("decision")
        if owner and reviewed_at and decision:
            review_state = "REVIEW_EVIDENCED"
            strengths.append("review owner, time, and decision are recorded")
        else:
            review_state = "REVIEW_EVIDENCE_MISSING"
            if not owner:
                gaps.append("review owner missing")
            if not reviewed_at:
                gaps.append("review timestamp missing")
            if not decision:
                gaps.append("review decision missing")

        escalation = record["escalation"]
        if escalation.get("required") is True:
            if escalation.get("status") == "escalated" and escalation.get("escalated_at") and escalation.get("evidence_ref"):
                escalation_state = "ESCALATION_EVIDENCED"
                strengths.append("required escalation has timestamp and evidence reference")
            else:
                escalation_state = "ESCALATION_EVIDENCE_MISSING"
                gaps.append("required escalation lacks complete status/time/evidence")
        elif escalation.get("required") is False:
            escalation_state = "NOT_REQUIRED_BY_RECORD"
        else:
            escalation_state = "ESCALATION_REQUIREMENT_UNKNOWN"
            gaps.append("escalation requirement is not established")

        action = record["action"]
        needs_action = decision in {"action_required", "escalate", "contain", "remediate"}
        if needs_action:
            if action.get("status") == "completed" and action.get("completed_at") and action.get("evidence_ref"):
                action_state = "ACTION_EVIDENCED"
                strengths.append("completed action has time and evidence reference")
            elif action.get("status") in {"pending", "in_progress"}:
                action_state = "ACTION_OPEN"
                gaps.append("follow-up action remains open")
            else:
                action_state = "ACTION_EVIDENCE_MISSING"
                gaps.append("review requires action but completion evidence is absent")
        elif decision in {"no_action", "informational", "false_positive"}:
            action_state = "NO_ACTION_DECISION_RECORDED"
        else:
            action_state = "ACTION_REQUIREMENT_UNKNOWN"
            gaps.append("action requirement cannot be determined from review decision")

        if review_state != "REVIEW_EVIDENCED":
            primary = "SECURITY_REVIEW_EVIDENCE_MISSING"
        elif escalation_state == "ESCALATION_EVIDENCE_MISSING":
            primary = "ESCALATION_EVIDENCE_MISSING"
        elif action_state == "ACTION_EVIDENCE_MISSING":
            primary = "ACTION_EVIDENCE_MISSING"
        elif action_state == "ACTION_OPEN":
            primary = "ACTION_OPEN"
        elif action_state == "ACTION_EVIDENCED":
            primary = "REVIEW_TO_ACTION_EVIDENCED"
        elif action_state == "NO_ACTION_DECISION_RECORDED":
            primary = "REVIEWED_NO_ACTION_REQUIRED_BY_RECORD"
        else:
            primary = "REVIEWED_WITH_UNRESOLVED_EVIDENCE"

    return Assessment(
        event_id=event_id,
        service=record["service"],
        event_category=record["event_category"],
        security_relevant="unknown" if relevant is None else str(relevant).lower(),
        monitoring_only=monitoring,
        review_state=review_state,
        action_state=action_state,
        escalation_state=escalation_state,
        context_completeness=context_state,
        primary_status=primary,
        evidence_gaps=tuple(gaps),
        evidence_strengths=tuple(strengths),
    )


def load_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise EvidenceError("input must be an object containing an events array")
    records = payload["events"]
    seen: set[str] = set()
    for item in records:
        if not isinstance(item, dict):
            raise EvidenceError("every event must be an object")
        validate_record(item)
        eid = item["event_id"]
        if eid in seen:
            raise EvidenceError(f"duplicate event_id: {eid}")
        seen.add(eid)
    return records


def summary(assessments: list[Assessment]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    for item in assessments:
        statuses[item.primary_status] = statuses.get(item.primary_status, 0) + 1
    return {
        "event_count": len(assessments),
        "security_relevant_count": sum(a.security_relevant == "true" for a in assessments),
        "monitoring_only_count": sum(a.monitoring_only for a in assessments),
        "unknown_relevance_count": sum(a.security_relevant == "unknown" for a in assessments),
        "review_to_action_evidenced_count": sum(a.primary_status == "REVIEW_TO_ACTION_EVIDENCED" for a in assessments),
        "status_counts": dict(sorted(statuses.items())),
        "interpretation": "Counts describe supplied evidence only; they are not maturity scores or incident-rate benchmarks.",
    }


def render_markdown(records: list[dict[str, Any]], assessments: list[Assessment]) -> str:
    by_id = {r["event_id"]: r for r in records}
    s = summary(assessments)
    out = [
        "# UIOWA-060 synthetic security-event review assessment",
        "",
        "> Fictional assessment rehearsal only. Collection does not equal review; missing evidence remains missing evidence.",
        "",
        "## Evidence summary",
        "",
        f"- Supplied events: **{s['event_count']}**",
        f"- Records marked security-relevant: **{s['security_relevant_count']}**",
        f"- General monitoring-only records: **{s['monitoring_only_count']}**",
        f"- Records with unknown security relevance: **{s['unknown_relevance_count']}**",
        f"- Security reviews with evidenced completed action: **{s['review_to_action_evidenced_count']}**",
        "- These are counts over the fictional supplied packet, **not** a maturity score or a performance benchmark.",
        "",
        "## Event matrix",
        "",
        "| Event | Service | Relevance | Review | Escalation | Action | Primary status |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in assessments:
        out.append(f"| {a.event_id} | {a.service} | {a.security_relevant} | {a.review_state} | {a.escalation_state} | {a.action_state} | {a.primary_status} |")

    out += ["", "## Fictional event-to-resolution timelines", ""]
    for a in assessments:
        r = by_id[a.event_id]
        out += [f"### {a.event_id} — {a.service}", ""]
        stages = [
            ("Occurred", r.get("occurred_at")),
            ("Collected", r.get("collected_at")),
            ("Reviewed", r.get("reviewed_at")),
            ("Escalated", r.get("escalation", {}).get("escalated_at")),
            ("Action completed", r.get("action", {}).get("completed_at")),
        ]
        for label, value in stages:
            out.append(f"- **{label}:** {value if value else 'UNKNOWN / no supplied evidence'}")
        out.append(f"- **Decision:** {r.get('decision') or 'UNKNOWN / no supplied evidence'}")
        out.append(f"- **Status:** {a.primary_status}")
        if a.evidence_gaps:
            out.append("- **Evidence gaps:** " + "; ".join(a.evidence_gaps))
        if a.evidence_strengths:
            out.append("- **Evidence present:** " + "; ".join(a.evidence_strengths))
        out.append("")

    out += [
        "## Interview prompts generated by the evidence model",
        "",
        "1. Which event classes are intentionally selected for security review, and who owns that selection?",
        "2. Which retained fields let a reviewer reconstruct actor, target, action, source, and correlation without retaining unnecessary sensitive content?",
        "3. Which roles can access the needed logs, and how is that access maintained when responsibilities change?",
        "4. What creates a review obligation versus a general monitoring response?",
        "5. What decision states are recorded, and what evidence shows that required escalation occurred?",
        "6. When action is required, where is completion evidence linked back to the originating event?",
        "7. Which events remain unreviewed because ownership, access, context, or escalation routing is unclear?",
        "8. How are repeated events aggregated without hiding distinct affected services or users?",
        "",
        "## Interpretation boundary",
        "",
        "This tool does not determine compromise, legal/compliance status, control effectiveness, or individual performance. It tests whether a supplied evidence packet can establish the operational chain from event selection through review, escalation, and action. General service telemetry remains a separate path unless the supplied record establishes security relevance.",
        "",
    ]
    return "\n".join(out)


def write_csv(path: Path, assessments: list[Assessment]) -> None:
    fields = list(assessments[0].as_row()) if assessments else [
        "event_id", "service", "event_category", "security_relevant", "monitoring_only",
        "review_state", "action_state", "escalation_state", "context_completeness",
        "primary_status", "evidence_gaps", "evidence_strengths",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for item in assessments:
            writer.writerow(item.as_row())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON event packet")
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--csv-out", type=Path, required=True)
    parser.add_argument("--md-out", type=Path, required=True)
    args = parser.parse_args()

    records = load_records(args.input)
    assessments = [assess(r) for r in records]
    args.json_out.write_text(json.dumps({
        "schema_version": "uiowa-060-v1",
        "scope": "supplied offline evidence only",
        "summary": summary(assessments),
        "events": [{**a.as_row(), "evidence_gaps": list(a.evidence_gaps), "evidence_strengths": list(a.evidence_strengths)} for a in assessments],
    }, indent=2) + "\n", encoding="utf-8")
    write_csv(args.csv_out, assessments)
    args.md_out.write_text(render_markdown(records, assessments), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
