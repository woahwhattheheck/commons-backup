#!/usr/bin/env python3
"""Deterministic proposal compliance gate.

Keeps bid teams from treating polished prose as evidence. The gate is deliberately
buyer-neutral: requirements and evidence are supplied as JSON at runtime.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

PLACEHOLDER_RE = re.compile(
    r"(?:\bTBD\b|\bTODO\b|\[\s*(?:INSERT|TBD|TODO)[^\]]*\]|<[^>]*(?:TBD|TODO|INSERT)[^>]*>)",
    re.I,
)
VALID_EVIDENCE = {"available", "pending", "missing", "not_applicable"}
VALID_REQ_TYPES = {"mandatory", "scored", "informational"}
VALID_STAGES = ("submission", "award")
STAGE_INDEX = {stage: index for index, stage in enumerate(VALID_STAGES)}


@dataclass(frozen=True)
class GateResult:
    requirement_id: str
    section: str
    requirement_type: str
    disposition: str
    evidence_status: str
    missing_evidence: tuple[str, ...]
    owner_gate: bool
    notes: tuple[str, ...]
    requirement_stage: str = "submission"
    target_stage: str = "submission"
    controlling: bool = True


def _load(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _validate_stage(value: Any, *, label: str) -> str:
    if type(value) is not str or value not in STAGE_INDEX:
        raise ValueError(f"{label}: invalid stage {value!r}")
    return value


def _validate_payload(
    requirements: list[dict[str, Any]], evidence: list[dict[str, Any]]
) -> None:
    if not requirements:
        raise ValueError("requirements must contain at least one requirement")

    ids: set[str] = set()
    for req in requirements:
        rid = str(req.get("id", "")).strip()
        if not rid:
            raise ValueError("every requirement needs a non-empty id")
        if rid in ids:
            raise ValueError(f"duplicate requirement id: {rid}")
        ids.add(rid)
        kind = str(req.get("type", "mandatory"))
        if kind not in VALID_REQ_TYPES:
            raise ValueError(f"{rid}: invalid type {kind!r}")
        _validate_stage(req.get("stage", "submission"), label=f"{rid}.stage")
        if not isinstance(req.get("statement", ""), str):
            raise ValueError(f"{rid}: statement must be text")
        ev = req.get("evidence", [])
        if not isinstance(ev, list) or not all(
            isinstance(x, str) and x.strip() for x in ev
        ):
            raise ValueError(f"{rid}: evidence must be a list of non-empty ids")

    evid_ids: set[str] = set()
    for item in evidence:
        eid = str(item.get("id", "")).strip()
        if not eid:
            raise ValueError("every evidence item needs a non-empty id")
        if eid in evid_ids:
            raise ValueError(f"duplicate evidence id: {eid}")
        evid_ids.add(eid)
        status = str(item.get("status", "missing"))
        if status not in VALID_EVIDENCE:
            raise ValueError(f"{eid}: invalid status {status!r}")


def evaluate(
    requirements: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    *,
    stage: str = "submission",
) -> list[GateResult]:
    target_stage = _validate_stage(stage, label="target stage")
    _validate_payload(requirements, evidence)
    evid = {str(x["id"]): x for x in evidence}
    results: list[GateResult] = []

    for req in requirements:
        rid = str(req["id"])
        kind = str(req.get("type", "mandatory"))
        requirement_stage = str(req.get("stage", "submission"))
        controlling = STAGE_INDEX[requirement_stage] <= STAGE_INDEX[target_stage]
        required_evidence = [str(x) for x in req.get("evidence", [])]
        missing: list[str] = []
        pending: list[str] = []
        unavailable: list[str] = []
        available: list[str] = []
        for eid in required_evidence:
            item = evid.get(eid)
            status = "missing" if item is None else item.get("status", "missing")
            if status == "missing":
                missing.append(eid)
            elif status == "pending":
                pending.append(eid)
            elif status == "not_applicable":
                unavailable.append(eid)
            elif status == "available":
                available.append(eid)

        response = str(req.get("response", "") or "").strip()
        notes: list[str] = []
        owner_gate = bool(req.get("owner_gate", False))
        response_required = bool(req.get("response_required", True))

        if response_required and not response:
            notes.append("response missing")
        elif PLACEHOLDER_RE.search(response):
            notes.append("response contains placeholder text")

        if missing:
            notes.append("required evidence missing")
        if pending:
            notes.append("required evidence pending")
        if unavailable:
            notes.append(
                "required evidence marked not_applicable without waiver authority"
            )
        if owner_gate:
            notes.append("owner/authorized-human gate")

        if missing:
            ev_status = "missing"
        elif pending:
            ev_status = "pending"
        elif unavailable:
            ev_status = "not_applicable"
        elif required_evidence and len(available) == len(required_evidence):
            ev_status = "available"
        elif not required_evidence:
            ev_status = "not_required"
        else:  # Defensive: validation limits evidence statuses to the cases above.
            ev_status = "missing"

        response_bad = response_required and (
            not response or bool(PLACEHOLDER_RE.search(response))
        )
        evidence_gap = bool(missing or pending or unavailable)
        if not controlling:
            disposition = "DEFERRED"
            notes.append(f"deferred until {requirement_stage} stage")
        elif kind == "mandatory" and (evidence_gap or response_bad or owner_gate):
            disposition = "BLOCKED"
        elif kind == "scored" and (evidence_gap or response_bad or owner_gate):
            disposition = "AT_RISK"
        elif response_bad:
            disposition = "INCOMPLETE"
        else:
            disposition = "READY"

        results.append(
            GateResult(
                requirement_id=rid,
                section=str(req.get("section", "")),
                requirement_type=kind,
                disposition=disposition,
                evidence_status=ev_status,
                missing_evidence=tuple(missing + pending + unavailable),
                owner_gate=owner_gate,
                notes=tuple(notes),
                requirement_stage=requirement_stage,
                target_stage=target_stage,
                controlling=controlling,
            )
        )
    return results


def _target_stage(rows: list[GateResult]) -> str:
    if not rows:
        raise ValueError("cannot summarize an empty requirement universe")
    stages = {row.target_stage for row in rows}
    if len(stages) != 1:
        raise ValueError("gate results mix target stages")
    return _validate_stage(next(iter(stages)), label="result target stage")


def summarize(results: Iterable[GateResult]) -> dict[str, Any]:
    rows = list(results)
    target_stage = _target_stage(rows)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.disposition] = counts.get(row.disposition, 0) + 1

    controlling_rows = [r for r in rows if r.controlling]
    ready = [r for r in controlling_rows if r.disposition == "READY"]
    blocking = [
        r.requirement_id for r in controlling_rows if r.disposition == "BLOCKED"
    ]
    owner = [r.requirement_id for r in controlling_rows if r.owner_gate]
    deferred = [r.requirement_id for r in rows if not r.controlling]

    submission_rows = [r for r in rows if r.requirement_stage == "submission"]
    submission_blocking = [
        r.requirement_id for r in submission_rows if r.disposition == "BLOCKED"
    ]
    submission_owner = [r.requirement_id for r in submission_rows if r.owner_gate]

    score = (
        round((len(ready) / len(controlling_rows) * 100.0), 1)
        if controlling_rows
        else 100.0
    )
    stage_ready = not blocking and not owner
    submission_ready = not submission_blocking and not submission_owner
    return {
        "stage": target_stage,
        "total": len(rows),
        "controlling_total": len(controlling_rows),
        "deferred_total": len(deferred),
        "counts": dict(sorted(counts.items())),
        "readiness_percent": score,
        "stage_ready": stage_ready,
        "submission_ready": submission_ready,
        "blocking_requirements": blocking,
        "owner_gates": owner,
        "deferred_requirements": deferred,
        "submission_blocking_requirements": submission_blocking,
        "submission_owner_gates": submission_owner,
    }


def render_markdown(
    requirements: list[dict[str, Any]], results: list[GateResult]
) -> str:
    req_map = {str(r["id"]): r for r in requirements}
    summary = summarize(results)
    lines = [
        "# Proposal compliance gate",
        "",
        f"**Target stage:** {summary['stage']}  ",
        f"**Readiness:** {summary['readiness_percent']}%  ",
        f"**Stage ready:** {'YES' if summary['stage_ready'] else 'NO'}  ",
        f"**Submission ready:** {'YES' if summary['submission_ready'] else 'NO'}  ",
        f"**Blocked:** {len(summary['blocking_requirements'])}  ",
        f"**Owner gates:** {len(summary['owner_gates'])}  ",
        f"**Deferred:** {summary['deferred_total']}",
        "",
        "| ID | Section | Type | Controls at | Disposition | Evidence | Owner gate | Requirement |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in results:
        req = req_map[row.requirement_id]
        statement = (
            str(req.get("statement", ""))
            .replace("|", "\\|")
            .replace("\n", " ")
        )
        lines.append(
            f"| {row.requirement_id} | {row.section} | {row.requirement_type} | "
            f"{row.requirement_stage} | **{row.disposition}** | "
            f"{row.evidence_status} | {'YES' if row.owner_gate else 'no'} | "
            f"{statement} |"
        )
    if summary["blocking_requirements"]:
        lines += ["", f"## Blocking requirements at {summary['stage']} stage", ""]
        for rid in summary["blocking_requirements"]:
            row = next(x for x in results if x.requirement_id == rid)
            req = req_map[rid]
            detail = "; ".join(row.notes) or "blocked"
            lines.append(f"- **{rid}** — {req.get('statement', '')} ({detail})")
    if summary["owner_gates"]:
        lines += [
            "",
            f"## Authorized-human gates at {summary['stage']} stage",
            "",
        ]
        for rid in summary["owner_gates"]:
            lines.append(f"- **{rid}** — {req_map[rid].get('statement', '')}")
    if summary["deferred_requirements"]:
        lines += ["", "## Deferred requirements", ""]
        for rid in summary["deferred_requirements"]:
            req = req_map[rid]
            lines.append(
                f"- **{rid}** — controls at {req.get('stage', 'submission')} stage: "
                f"{req.get('statement', '')}"
            )
    return "\n".join(lines) + "\n"


def render_skeleton(requirements: list[dict[str, Any]]) -> str:
    sections: dict[str, list[dict[str, Any]]] = {}
    for req in requirements:
        sections.setdefault(str(req.get("section", "General")), []).append(req)
    lines = [
        "# Proposal response skeleton",
        "",
        "> Generated from the requirement register. Do not treat placeholders as evidence.",
        "",
    ]
    for section, items in sections.items():
        lines += [f"## {section}", ""]
        for req in items:
            lines += [
                f"### {req['id']}: {req['statement']}",
                "",
                "[TBD — evidence-backed response required]",
                "",
            ]
    return "\n".join(lines)


def render_draft(requirements: list[dict[str, Any]]) -> str:
    """Render current requirement responses without promoting placeholders to facts."""
    sections: dict[str, list[dict[str, Any]]] = {}
    for req in requirements:
        sections.setdefault(str(req.get("section", "General")), []).append(req)
    lines = [
        "# Evidence-backed proposal draft",
        "",
        "> Working draft only. Owner-gated facts and missing evidence remain explicitly unresolved.",
        "",
    ]
    for section, items in sections.items():
        lines += [f"## {section}", ""]
        for req in items:
            response = (
                str(req.get("response", "") or "").strip()
                or "[TBD — evidence-backed response required]"
            )
            gate = " **[OWNER GATE]**" if req.get("owner_gate") else ""
            stage = str(req.get("stage", "submission"))
            lines += [
                f"### {req['id']}{gate}",
                f"**Controls at:** {stage}",
                f"**Requirement:** {req['statement']}",
                "",
                response,
                "",
            ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("requirements", help="requirements JSON file")
    p.add_argument("evidence", help="evidence inventory JSON file")
    p.add_argument(
        "--stage",
        choices=VALID_STAGES,
        default="submission",
        help="readiness horizon to evaluate",
    )
    p.add_argument("--json-out", help="write machine-readable gate report")
    p.add_argument("--markdown-out", help="write Markdown compliance matrix")
    p.add_argument("--skeleton-out", help="write response skeleton")
    p.add_argument("--draft-out", help="write current evidence-backed response draft")
    p.add_argument(
        "--check", action="store_true", help="exit 2 unless the target stage is ready"
    )
    args = p.parse_args(argv)

    req_payload = _load(args.requirements)
    ev_payload = _load(args.evidence)
    requirements = (
        req_payload["requirements"] if isinstance(req_payload, dict) else req_payload
    )
    evidence = ev_payload["evidence"] if isinstance(ev_payload, dict) else ev_payload
    results = evaluate(requirements, evidence, stage=args.stage)
    summary = summarize(results)
    report = {
        "stage": args.stage,
        "summary": summary,
        "results": [asdict(r) for r in results],
    }

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if args.markdown_out:
        Path(args.markdown_out).write_text(
            render_markdown(requirements, results), encoding="utf-8"
        )
    if args.skeleton_out:
        Path(args.skeleton_out).write_text(
            render_skeleton(requirements), encoding="utf-8"
        )
    if args.draft_out:
        Path(args.draft_out).write_text(render_draft(requirements), encoding="utf-8")

    print(json.dumps(summary, sort_keys=True))
    if args.check and not summary["stage_ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
