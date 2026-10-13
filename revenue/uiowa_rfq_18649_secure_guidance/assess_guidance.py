#!/usr/bin/env python3
"""UIOWA-058 offline secure-development guidance usability assessor."""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOPICS = {"input_handling", "authorization_design", "error_handling"}
FORBIDDEN_KEYS = {"password", "secret", "secret_value", "credential_value", "api_key", "access_token", "private_key"}


class GuidanceError(ValueError):
    pass


def walk_keys(value: Any):
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k).lower()
            yield from walk_keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk_keys(v)


def nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return value is not None


def validate_guidance(item: dict[str, Any]) -> None:
    gid = str(item.get("guidance_id") or "<missing-guidance-id>")
    required = ["guidance_id", "title", "topic", "status", "owner_role", "audience",
                "decision_triggers", "reusable_pattern", "discoverable_locations",
                "specialist_route", "evidence_ref"]
    missing = [k for k in required if k not in item]
    if missing:
        raise GuidanceError(f"{gid}: missing fields: {', '.join(missing)}")
    bad = sorted(set(walk_keys(item)) & FORBIDDEN_KEYS)
    if bad:
        raise GuidanceError(f"{gid}: sensitive-value fields are out of scope: {', '.join(bad)}")
    if item["topic"] not in TOPICS:
        raise GuidanceError(f"{gid}: unsupported topic {item['topic']!r}")
    if item["status"] not in {"current", "superseded", "unknown"}:
        raise GuidanceError(f"{gid}: status must be current, superseded, or unknown")
    if not isinstance(item["audience"], list) or not isinstance(item["decision_triggers"], list):
        raise GuidanceError(f"{gid}: audience and decision_triggers must be arrays")
    if not isinstance(item["discoverable_locations"], list):
        raise GuidanceError(f"{gid}: discoverable_locations must be an array")
    if not isinstance(item["specialist_route"], dict):
        raise GuidanceError(f"{gid}: specialist_route must be an object")


def validate_exercise(item: dict[str, Any]) -> None:
    eid = str(item.get("exercise_id") or "<missing-exercise-id>")
    required = ["exercise_id", "topic", "scenario", "practice_goal", "guidance_refs",
                "discussion_questions", "evidence_to_request", "unsafe_shortcut",
                "reasoning_anchors", "specialist_trigger"]
    missing = [k for k in required if k not in item]
    if missing:
        raise GuidanceError(f"{eid}: missing fields: {', '.join(missing)}")
    if item["topic"] not in TOPICS:
        raise GuidanceError(f"{eid}: unsupported topic {item['topic']!r}")
    for field in ("guidance_refs", "discussion_questions", "evidence_to_request", "reasoning_anchors"):
        if not isinstance(item[field], list) or not item[field]:
            raise GuidanceError(f"{eid}: {field} must be a non-empty array")
    bad = sorted(set(walk_keys(item)) & FORBIDDEN_KEYS)
    if bad:
        raise GuidanceError(f"{eid}: sensitive-value fields are out of scope: {', '.join(bad)}")


@dataclass(frozen=True)
class GuidanceAssessment:
    guidance_id: str
    topic: str
    status: str
    ownership: str
    discoverability: str
    applicability_cues: str
    reusable_pattern: str
    specialist_route: str
    evidence_reference: str
    primary_state: str
    gaps: tuple[str, ...]

    def row(self) -> dict[str, str]:
        return {
            "guidance_id": self.guidance_id,
            "topic": self.topic,
            "status": self.status,
            "ownership": self.ownership,
            "discoverability": self.discoverability,
            "applicability_cues": self.applicability_cues,
            "reusable_pattern": self.reusable_pattern,
            "specialist_route": self.specialist_route,
            "evidence_reference": self.evidence_reference,
            "primary_state": self.primary_state,
            "gaps": " | ".join(self.gaps),
        }


def assess_guidance(item: dict[str, Any]) -> GuidanceAssessment:
    validate_guidance(item)
    gaps: list[str] = []
    owner = "EVIDENCED" if nonempty(item["owner_role"]) else "UNKNOWN"
    if owner == "UNKNOWN": gaps.append("owner role not supplied")
    discoverable = "EVIDENCED" if item["discoverable_locations"] else "MISSING"
    if discoverable == "MISSING": gaps.append("no discoverable location supplied")
    cues = "EVIDENCED" if item["decision_triggers"] else "MISSING"
    if cues == "MISSING": gaps.append("no decision/application triggers supplied")
    pattern = "EVIDENCED" if nonempty(item["reusable_pattern"]) else "MISSING"
    if pattern == "MISSING": gaps.append("no reusable pattern supplied")
    route_obj = item["specialist_route"]
    route = "EVIDENCED" if route_obj.get("available") is True and nonempty(route_obj.get("route")) and nonempty(route_obj.get("when_to_use")) else "MISSING_OR_UNKNOWN"
    if route != "EVIDENCED": gaps.append("specialist route or trigger is missing/unknown")
    evref = "EVIDENCED" if nonempty(item["evidence_ref"]) else "MISSING"
    if evref == "MISSING": gaps.append("evidence reference missing")

    if item["status"] == "superseded":
        primary = "SUPERSEDED_NOT_CURRENT_SUPPORT"
    elif item["status"] == "unknown":
        primary = "GUIDANCE_STATUS_UNKNOWN"
    elif gaps:
        primary = "PARTIAL_GUIDANCE_EVIDENCE"
    else:
        primary = "USABLE_GUIDANCE_EVIDENCED"
    return GuidanceAssessment(item["guidance_id"], item["topic"], item["status"], owner,
                              discoverable, cues, pattern, route, evref, primary, tuple(gaps))


def load_packet(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    guidance = payload.get("guidance")
    exercises = payload.get("exercises")
    if not isinstance(guidance, list) or not isinstance(exercises, list):
        raise GuidanceError("packet must contain guidance and exercises arrays")
    gids: set[str] = set()
    for item in guidance:
        validate_guidance(item)
        if item["guidance_id"] in gids:
            raise GuidanceError(f"duplicate guidance_id: {item['guidance_id']}")
        gids.add(item["guidance_id"])
    eids: set[str] = set()
    for item in exercises:
        validate_exercise(item)
        if item["exercise_id"] in eids:
            raise GuidanceError(f"duplicate exercise_id: {item['exercise_id']}")
        eids.add(item["exercise_id"])
        unknown_refs = sorted(set(item["guidance_refs"]) - gids)
        if unknown_refs:
            raise GuidanceError(f"{item['exercise_id']}: unknown guidance_refs: {', '.join(unknown_refs)}")
    missing_topics = TOPICS - {x["topic"] for x in exercises}
    if missing_topics:
        raise GuidanceError("exercise coverage missing topics: " + ", ".join(sorted(missing_topics)))
    return guidance, exercises


def render_pack(guidance: list[dict[str, Any]], exercises: list[dict[str, Any]], assessments: list[GuidanceAssessment]) -> str:
    a_by_id = {a.guidance_id: a for a in assessments}
    out = [
        "# UIOWA-058 — Secure-development guidance discussion pack",
        "",
        "> Fictional facilitation material. Assess the usability of guidance and support systems, not individual engineers.",
        "",
        "## Guidance usability snapshot",
        "",
        "| Guidance | Topic | Status | Primary evidence state |",
        "|---|---|---|---|",
    ]
    for a in assessments:
        out.append(f"| {a.guidance_id} | {a.topic} | {a.status} | {a.primary_state} |")
    out += ["", "## Discussion exercises", ""]
    for ex in exercises:
        refs = [a_by_id[r] for r in ex["guidance_refs"]]
        current_usable = [r.guidance_id for r in refs if r.primary_state == "USABLE_GUIDANCE_EVIDENCED"]
        non_current = [r.guidance_id for r in refs if r.status != "current"]
        out += [
            f"### {ex['exercise_id']} — {ex['title']}",
            "",
            f"**Topic:** {ex['topic']}",
            "",
            f"**Scenario:** {ex['scenario']}",
            "",
            f"**Practice goal:** {ex['practice_goal']}",
            "",
            f"**Unsafe shortcut to discuss:** {ex['unsafe_shortcut']}",
            "",
            "**Discussion questions**",
        ]
        out += [f"- {q}" for q in ex["discussion_questions"]]
        out += ["", "**Reasoning anchors (facilitator prompts, not employee scoring keys)**"]
        out += [f"- {q}" for q in ex["reasoning_anchors"]]
        out += ["", "**Evidence to request**"]
        out += [f"- {q}" for q in ex["evidence_to_request"]]
        out += ["", f"**When specialist help should become an option:** {ex['specialist_trigger']}"]
        out += [f"**Referenced guidance:** {', '.join(ex['guidance_refs'])}"]
        out += [f"**Current usable guidance evidenced in this synthetic packet:** {', '.join(current_usable) if current_usable else 'none'}"]
        if non_current:
            out += [f"**Non-current/unknown-status references:** {', '.join(non_current)} — do not treat these as current support."]
        gaps = []
        for r in refs:
            gaps.extend(f"{r.guidance_id}: {g}" for g in r.gaps)
        if gaps:
            out += ["**Guidance-system evidence gaps**"] + [f"- {g}" for g in gaps]
        out.append("")
    out += [
        "## Facilitation boundary",
        "",
        "Use participant reasoning to discover whether guidance is findable, applicable, reusable, owned, and backed by accessible specialist help. Do not grade individuals, demand one implementation pattern, or treat a written document as proof of routine practice. Follow up with artifacts from real work before forming a finding.",
        "",
    ]
    return "\n".join(out)


def write_csv(path: Path, assessments: list[GuidanceAssessment]) -> None:
    fields = list(assessments[0].row())
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for item in assessments:
            w.writerow(item.row())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("packet", type=Path)
    ap.add_argument("--csv-out", type=Path, required=True)
    ap.add_argument("--md-out", type=Path, required=True)
    args = ap.parse_args()
    guidance, exercises = load_packet(args.packet)
    assessments = [assess_guidance(x) for x in guidance]
    write_csv(args.csv_out, assessments)
    args.md_out.write_text(render_pack(guidance, exercises, assessments), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
