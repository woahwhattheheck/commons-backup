#!/usr/bin/env python3
"""Generate the checked-in fictional review cycle and existing-workbench intake."""
from __future__ import annotations
import hashlib
import json
from copy import deepcopy
from pathlib import Path
import review_register as rr


def hashed(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def event(sequence: int, state: str, rationale: str, resulting: str | None = None) -> dict:
    return {"sequence": sequence, "at": f"2026-01-0{sequence}T12:00:00Z",
            "actor": "Fictional consolidated-review coordinator", "state": state,
            "rationale": rationale, "resulting_report_version": resulting}



def documents() -> list[tuple[str, str, str, str]]:
    return [
        ("E-POLICY-v1", "Fictional release procedure v1", "release-procedure-v1.txt",
         "SYNTHETIC REHEARSAL — not University policy\n\nSection 2: support handoff\nRecord the support role before releasing a fictional service change.\n"),
        ("E-RELEASE-v1", "Fictional release checklist v1", "release-checklist-v1.txt",
         "SYNTHETIC REHEARSAL — fictional release record v1\n\nRelease SAMPLE-001\nSupport role: fictional service desk. Acknowledgement: not recorded.\n"),
        ("E-RELEASE-v2", "Fictional release checklist v2", "release-checklist-v2.txt",
         "SYNTHETIC REHEARSAL — fictional release record v2\n\nRelease SAMPLE-001\nSupport role: fictional service desk. Acknowledgement: explicitly recorded in this revised example.\n"),
        ("E-INTERVIEW-A", "Fictional management interview", "interview-a.txt",
         "SYNTHETIC REHEARSAL — no real participant\n\nQuestion 3: emergency changes\nManagement account: emergency changes receive review. Period and service boundary not supplied.\n"),
        ("E-INTERVIEW-B", "Fictional practitioner interview", "interview-b.txt",
         "SYNTHETIC REHEARSAL — no real participant\n\nQuestion 3: emergency changes\nPractitioner account: one emergency change had no observed review. Period and service boundary not supplied.\n"),
    ]


def example() -> dict:
    evidence = [
        {"id": rid, "label": label, "source_locator": f"examples/evidence/{name}#L3-L4",
         "sha256": hashed(contents)} for rid, label, name, contents in documents()
    ]
    v1_findings = [
        {"id": "F-ESS-RELEASE", "cell": {"group": "ESS", "dimension": "deployment"},
         "statement": "The sampled release includes a named support handoff.", "evidence_refs": ["E-POLICY-v1", "E-RELEASE-v1"]},
        {"id": "F-RIS-REVIEW", "cell": {"group": "RIS", "dimension": "software_development"},
         "statement": "The two fictional accounts disagree about emergency-change review.", "evidence_refs": ["E-INTERVIEW-A", "E-INTERVIEW-B"]},
    ]
    v2_findings = deepcopy(v1_findings)
    v2_findings[0]["statement"] = "One sampled release records a named support handoff; wider consistency is unassessed."
    v3_findings = deepcopy(v2_findings)
    v3_findings[0]["statement"] = "The revised fictional checklist includes explicit support acknowledgement for one sampled release."
    v3_findings[0]["evidence_refs"] = ["E-POLICY-v1", "E-RELEASE-v2"]
    comments = [
        {"id": "C-001", "reviewer": "Fictional assessor A", "report_version": "draft-v1", "finding_id": "F-ESS-RELEASE",
         "kind": "WORDING", "comment": "Make the sample boundary explicit; one release does not establish a general practice.",
         "proposed_edit": v2_findings[0]["statement"],
         "events": [event(1, "OPEN", "Scope wording queried."), event(2, "ACCEPTED", "The sample boundary needs clarification."),
                    event(3, "RESOLVED", "Wording changed with identical evidence references.", "draft-v2")]},
        {"id": "C-002", "reviewer": "Fictional assessor B", "report_version": "draft-v2", "finding_id": "F-ESS-RELEASE",
         "kind": "EVIDENCE_CHANGE", "comment": "Replace the superseded checklist with its revised evidence version.",
         "proposed_edit": v3_findings[0]["statement"],
         "events": [event(1, "OPEN", "A revised fictional checklist was supplied."), event(2, "ACCEPTED", "Use the explicit versioned evidence record."),
                    event(3, "RESOLVED", "Checklist v2 replaces v1; this is an evidence change, not wording-only.", "draft-v3")]},
        {"id": "C-003", "reviewer": "Fictional assessor A", "report_version": "draft-v1", "finding_id": "F-RIS-REVIEW",
         "kind": "QUESTION", "comment": "The management account and practitioner account conflict. Which periods and services do they describe?",
         "proposed_edit": "Keep both accounts and request matching dated examples.",
         "events": [event(1, "OPEN", "Competing accounts retained."), event(2, "UNRESOLVED", "No dated examples yet reconcile the disagreement.")]},
        {"id": "C-004", "reviewer": "Fictional assessor B", "report_version": "draft-v1", "finding_id": "F-RIS-REVIEW",
         "kind": "QUESTION", "comment": "Can we describe the gap as University-wide?", "proposed_edit": "",
         "events": [event(1, "OPEN", "Generalization proposed."), event(2, "REJECTED", "The fictional evidence is local and conflicting; a University-wide conclusion is unsupported.")]},
    ]
    return {"schema": rr.SCHEMA, "synthetic": True, "evidence": evidence,
            "reports": [{"version": "draft-v1", "receipt_sha256": hashed("synthetic report v1; not compiler output"), "supersedes": None, "findings": v1_findings},
                        {"version": "draft-v2", "receipt_sha256": hashed("synthetic report v2; not compiler output"), "supersedes": "draft-v1", "findings": v2_findings},
                        {"version": "draft-v3", "receipt_sha256": hashed("synthetic report v3; not compiler output"), "supersedes": "draft-v2", "findings": v3_findings}],
            "comments": comments}


def handoff() -> dict:
    notes = [{"group": group, "dimension": dimension,
              "compiler_status": "HOLD_MISSING_EVIDENCE", "disposition": "UNREVIEWED", "analyst_note": ""}
             for group in sorted(rr.GROUPS) for dimension in sorted(rr.DIMENSIONS)]
    notes[0].update(disposition="NEEDS_EVIDENCE", analyst_note="Fictional note: request a dated example.")
    notes[1].update(disposition="DISCUSS_WITH_PRIME")
    return {"schema": rr.HANDOFF_SCHEMA, "status": "DRAFT_NON_AUTHORITATIVE",
            "report_receipt_sha256": "d" * 64, "report_mode": "UNTRUSTED_INSPECTION",
            "aggregate_state": "HOLD_TRUSTED_AUTHORITY_REQUIRED", "synthetic_demo": True,
            "cell_notes": notes, "authority": dict(rr.AUTHORITY)}


if __name__ == "__main__":
    dest = Path(__file__).parent / "examples"
    dest.mkdir(exist_ok=True)
    (dest / "evidence").mkdir(exist_ok=True)
    for _, _, name, contents in documents():
        (dest / "evidence" / name).write_text(contents, encoding="utf-8", newline="")
    for name, value in (("synthetic-review-cycle.json", example()), ("synthetic-workbench-handoff.json", handoff())):
        (dest / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
