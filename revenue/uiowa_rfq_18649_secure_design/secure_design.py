#!/usr/bin/env python3
"""Secure-design requirements evidence instrument (RFQ 18649, work order 051).

How security requirements enter design decisions, and whether they stay
traceable when the requirements change.

Reference frame
---------------
NIST Secure Software Development Framework (SSDF), SP 800-218:
https://csrc.nist.gov/Projects/ssdf

SSDF practice identifiers are used here **only to organize the instrument**, so
a reader can see which area of the framework a question relates to. Nothing in
this module asserts conformance with SSDF, and no output is a certification,
compliance verdict, attestation or assessment against the framework. The
practice descriptions carried in `SSDF_REFERENCES` are **paraphrases written for
this worksheet**, marked as such; the authoritative wording is at the URL above
and should be read there.

The rule this file exists to enforce
------------------------------------
**Documented intent, observed practice and unknown are three different states,
and none of them substitutes for another.**

* `DOCUMENTED_INTENT` -- a standard, template or policy says this should happen.
  It is evidence about an intention. It says nothing about whether any design
  decision actually did it.
* `OBSERVED_PRACTICE` -- an artifact exists for this specific requirement and
  this specific design decision.
* `UNKNOWN` -- nobody has supplied anything. Not a gap, not a pass; an open
  question, and it is never scored as either.

And the state the second half of the order implies:

* `TRACED_STALE` -- a design decision cites a **superseded version** of a
  requirement. The trace exists and points at text that has since changed. This
  is how traceability is lost silently: nothing is broken, nothing errors, the
  link still resolves, and it now resolves to the wrong thing. A stale trace is
  reported as its own state rather than collapsed into either "traced" or
  "untraced", because it is genuinely neither.

Every record here is fictional. Nothing describes the University of Iowa, and no
output is a finding.

Offline, Python 3 standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------------
# Reference frame
# --------------------------------------------------------------------------------

SSDF_URL = "https://csrc.nist.gov/Projects/ssdf"
SSDF_DOCUMENT = "NIST SP 800-218, Secure Software Development Framework (SSDF)"

#: Practice identifiers used to organize this instrument. The `paraphrase` text
#: is written for this worksheet and is NOT a quotation; read the authoritative
#: wording at SSDF_URL.
SSDF_REFERENCES: Dict[str, str] = {
    "PO.1.1": (
        "PARAPHRASE: identify and document the security requirements that apply "
        "to the organization's software development."
    ),
    "PW.1.1": (
        "PARAPHRASE: use risk modelling -- threat modelling, data-flow "
        "modelling, attack surface analysis -- to inform design."
    ),
    "PW.1.2": (
        "PARAPHRASE: track and maintain the software's security requirements, "
        "risks and design decisions."
    ),
    "PW.2.1": (
        "PARAPHRASE: have a qualified person review the design to confirm it "
        "meets the security requirements and addresses the identified risks."
    ),
}

# --------------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------------

#: What a piece of evidence is.
INTENT_KINDS: Tuple[str, ...] = (
    "written_standard",
    "design_template",
    "policy_statement",
)
PRACTICE_KINDS: Tuple[str, ...] = (
    "design_decision_record",
    "data_flow_diagram",
    "threat_model_record",
    "design_review_record",
    "requirement_change_record",
)
ALL_EVIDENCE_KINDS = INTENT_KINDS + PRACTICE_KINDS

#: The three states the order requires, plus the stale-trace state.
UNKNOWN = "UNKNOWN"
DOCUMENTED_INTENT = "DOCUMENTED_INTENT"
TRACED_STALE = "TRACED_STALE"
OBSERVED_PRACTICE = "OBSERVED_PRACTICE"

STATE_ORDER: Tuple[str, ...] = (
    UNKNOWN,
    DOCUMENTED_INTENT,
    TRACED_STALE,
    OBSERVED_PRACTICE,
)
STATE_RANK = {state: index for index, state in enumerate(STATE_ORDER)}

STATE_MEANING: Dict[str, str] = {
    UNKNOWN: (
        "Nothing has been supplied for this requirement and this design "
        "decision. An open question -- not a gap, and not a pass."
    ),
    DOCUMENTED_INTENT: (
        "A standard, template or policy says this should happen. That is "
        "evidence about an intention. It says nothing about whether this design "
        "decision did it."
    ),
    TRACED_STALE: (
        "A design artifact cites this requirement, but at a superseded version. "
        "The link still resolves, and it resolves to text that has since "
        "changed. Neither traced nor untraced."
    ),
    OBSERVED_PRACTICE: (
        "An artifact exists for this requirement at its current version. What it "
        "shows is a matter for the reviewer; that it exists is observed."
    ),
}

CONTENT_CLASS = "SYNTHETIC_NOT_A_UNIVERSITY_FINDING"


class SecureDesignError(ValueError):
    """Input the instrument refuses to interpret by guessing."""


# --------------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------------


def _record(payload: Any, label: str) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise SecureDesignError(f"{label}: expected a record object")
    return payload


def _text_field(payload: Dict[str, Any], key: str) -> str:
    """JSON null is absence, never an identifier or a statement named 'None'."""
    value = payload.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SecureDesignError(f"{key}: expected text or null")
    return value.strip()


def _string_list(payload: Dict[str, Any], key: str, *, unique: bool = True) -> List[str]:
    values = payload.get(key, [])
    if not isinstance(values, list):
        raise SecureDesignError(f"{key}: expected a list of nonblank strings")
    result = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise SecureDesignError(f"{key}[{index}]: expected nonblank text")
        result.append(value.strip())
    if unique and len(set(result)) != len(result):
        raise SecureDesignError(f"{key}: duplicate references would double-count a link")
    return result


def _boundary_label(value: Optional[bool]) -> str:
    return "UNKNOWN" if value is None else ("**yes**" if value else "no")


class Requirement:
    """One security requirement, at a version."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        _record(payload, "requirement")
        requirement_id = payload.get("requirement_id")
        if not isinstance(requirement_id, str) or not requirement_id.strip():
            raise SecureDesignError("every requirement needs a 'requirement_id'")
        self.requirement_id = requirement_id.strip()
        version = payload.get("current_version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise SecureDesignError(
                f"{self.requirement_id}: 'current_version' must be an integer >= 1. "
                f"Versions are what make a stale trace detectable, so an "
                f"unversioned requirement cannot be accepted."
            )
        self.current_version = version
        self.statement = _text_field(payload, "statement")
        if not self.statement:
            raise SecureDesignError(
                f"{self.requirement_id}: a requirement needs a statement"
            )
        self.ssdf_refs = _string_list(payload, "ssdf_references")
        for ref in self.ssdf_refs:
            if ref not in SSDF_REFERENCES:
                raise SecureDesignError(
                    f"{self.requirement_id}: SSDF reference {ref!r} is not one of "
                    f"{sorted(SSDF_REFERENCES)}. An unrecognized identifier would "
                    f"attach this worksheet to a practice nobody can look up."
                )
        self.change_history = _string_list(payload, "change_history", unique=False)
        self.applies_to_flows = _string_list(payload, "applies_to_flows")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "current_version": self.current_version,
            "statement": self.statement,
            "ssdf_references": list(self.ssdf_refs),
            "change_history": list(self.change_history),
            "applies_to_flows": list(self.applies_to_flows),
        }


class DataFlow:
    """One fictional data flow the requirements attach to."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        _record(payload, "data flow")
        flow_id = payload.get("flow_id")
        if not isinstance(flow_id, str) or not flow_id.strip():
            raise SecureDesignError("every data flow needs a 'flow_id'")
        self.flow_id = flow_id.strip()
        self.description = _text_field(payload, "description")
        self.source = _text_field(payload, "source")
        self.destination = _text_field(payload, "destination")
        self.data_class = _text_field(payload, "data_class")
        boundary = payload.get("crosses_trust_boundary")
        if boundary is not None and type(boundary) is not bool:
            raise SecureDesignError(
                f"{self.flow_id}: crosses_trust_boundary must be true, false or null"
            )
        self.crosses_trust_boundary = boundary

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flow_id": self.flow_id,
            "description": self.description,
            "source": self.source,
            "destination": self.destination,
            "data_class": self.data_class,
            "crosses_trust_boundary": self.crosses_trust_boundary,
        }


class Evidence:
    """One artifact, and which requirement version it cites."""

    def __init__(self, payload: Dict[str, Any], *, index: int) -> None:
        _record(payload, f"evidence[{index}]")
        kind = payload.get("kind")
        if kind not in ALL_EVIDENCE_KINDS:
            raise SecureDesignError(
                f"evidence[{index}]: kind {kind!r} is not one of "
                f"{list(ALL_EVIDENCE_KINDS)}. An unrecognized kind cannot be "
                f"placed on the intent/practice distinction, and would be read as "
                f"establishing whatever the reader assumes."
            )
        self.kind = kind
        self.evidence_id = _text_field(payload, "evidence_id")
        if not self.evidence_id:
            raise SecureDesignError(f"evidence[{index}] needs an 'evidence_id'")
        self.requirement_id = _text_field(payload, "requirement_id")
        self.decision_id = _text_field(payload, "decision_id")
        self.flow_id = _text_field(payload, "flow_id")
        self.statement = _text_field(payload, "statement")
        if not self.statement:
            raise SecureDesignError(
                f"{self.evidence_id}: every evidence item needs a statement"
            )
        self.locator = _text_field(payload, "locator")
        cites = payload.get("cites_requirement_version")
        if cites is not None and (
            not isinstance(cites, int) or isinstance(cites, bool) or cites < 1
        ):
            raise SecureDesignError(
                f"{self.evidence_id}: 'cites_requirement_version' must be an "
                f"integer >= 1 or absent"
            )
        self.cites_requirement_version = cites
        if self.kind in PRACTICE_KINDS and self.requirement_id and cites is None:
            raise SecureDesignError(
                f"{self.evidence_id}: a {self.kind} that names a requirement must "
                f"say which version it cites. Without a version the trace cannot "
                f"be checked for staleness, and an uncheckable trace would be "
                f"reported as current."
            )

    @property
    def is_intent(self) -> bool:
        return self.kind in INTENT_KINDS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "family": "intent" if self.is_intent else "practice",
            "requirement_id": self.requirement_id or None,
            "decision_id": self.decision_id or None,
            "flow_id": self.flow_id or None,
            "statement": self.statement,
            "locator": self.locator,
            "cites_requirement_version": self.cites_requirement_version,
        }


class DesignDecision:
    """One fictional design decision that a requirement should have shaped."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        _record(payload, "design decision")
        decision_id = payload.get("decision_id")
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise SecureDesignError("every design decision needs a 'decision_id'")
        self.decision_id = decision_id.strip()
        self.summary = _text_field(payload, "summary")
        self.flow_id = _text_field(payload, "flow_id")
        self.governing_requirements = _string_list(payload, "governing_requirements")
        if not self.governing_requirements:
            raise SecureDesignError(
                f"{self.decision_id}: a design decision with no governing "
                f"requirement has nothing to be traced to"
            )
        self.decided_on = _text_field(payload, "decided_on")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "summary": self.summary,
            "flow_id": self.flow_id or None,
            "governing_requirements": list(self.governing_requirements),
            "decided_on": self.decided_on or None,
        }


# --------------------------------------------------------------------------------
# Assessment
# --------------------------------------------------------------------------------


def assess_link(
    decision: DesignDecision,
    requirement: Requirement,
    evidence: Sequence[Evidence],
) -> Dict[str, Any]:
    """Decide what the evidence establishes about ONE requirement-to-decision link."""
    relevant = [
        e
        for e in evidence
        if (not e.requirement_id or e.requirement_id == requirement.requirement_id)
        and (not e.decision_id or e.decision_id == decision.decision_id)
    ]
    # A record that explicitly names another flow cannot support this link.
    # Preserve it as a contradiction to investigate rather than discarding it.
    flow_mismatch = [
        e for e in relevant
        if e.decision_id == decision.decision_id
        and e.flow_id and decision.flow_id and e.flow_id != decision.flow_id
    ]
    relevant = [
        e for e in relevant
        if not (e.flow_id and decision.flow_id and e.flow_id != decision.flow_id)
    ]
    # Practice evidence must name BOTH ends to count as a trace: an artifact that
    # names a requirement but no decision does not tell you this decision
    # considered it.
    practice = [
        e
        for e in relevant
        if not e.is_intent
        and e.requirement_id == requirement.requirement_id
        and e.decision_id == decision.decision_id
    ]
    intent = [e for e in relevant if e.is_intent]
    unattributed = [
        e
        for e in evidence
        if not e.is_intent
        and e.requirement_id == requirement.requirement_id
        and not e.decision_id
        and not (e.flow_id and decision.flow_id and e.flow_id != decision.flow_id)
    ]

    current = [
        e
        for e in practice
        if e.cites_requirement_version == requirement.current_version
    ]
    stale = [
        e
        for e in practice
        if e.cites_requirement_version is not None
        and e.cites_requirement_version < requirement.current_version
    ]
    ahead = [
        e
        for e in practice
        if e.cites_requirement_version is not None
        and e.cites_requirement_version > requirement.current_version
    ]

    if current:
        state = OBSERVED_PRACTICE
    elif stale:
        state = TRACED_STALE
    elif intent:
        state = DOCUMENTED_INTENT
    else:
        state = UNKNOWN

    next_step = None
    if state == UNKNOWN:
        next_step = (
            f"Ask for any artifact that shows {decision.decision_id} considered "
            f"{requirement.requirement_id}: a design decision record, a data-flow "
            f"or threat model covering the flow, or a design review note. If none "
            f"exists, that is the finding -- do not infer one from the standard."
        )
    elif state == DOCUMENTED_INTENT:
        next_step = (
            f"A standard requires this; nothing shows {decision.decision_id} "
            f"applied it. Ask for the design record or review note for this "
            f"decision specifically. A template that says a section should exist "
            f"is not that section."
        )
    elif state == TRACED_STALE:
        cited = sorted({e.cites_requirement_version for e in stale})
        next_step = (
            f"The trace points at {requirement.requirement_id} v"
            f"{', v'.join(str(v) for v in cited)}, superseded by v"
            f"{requirement.current_version}. Ask what changed between those "
            f"versions and whether {decision.decision_id} was revisited. This is "
            f"the case that looks fine in a traceability matrix."
        )

    if flow_mismatch:
        follow_up = (
            "Reconcile the explicit flow IDs in "
            + ", ".join(e.evidence_id for e in flow_mismatch)
            + f" against {decision.decision_id} ({decision.flow_id}). "
            "These artifacts are retained but do not support this link."
        )
        next_step = (next_step + " " if next_step else "") + follow_up

    return {
        "decision_id": decision.decision_id,
        "requirement_id": requirement.requirement_id,
        "requirement_current_version": requirement.current_version,
        "flow_id": decision.flow_id or None,
        "state": state,
        "state_meaning": STATE_MEANING[state],
        "ssdf_references": list(requirement.ssdf_refs),
        "evidence_observed_practice": [e.to_dict() for e in current],
        "evidence_stale_trace": [e.to_dict() for e in stale],
        "evidence_documented_intent": [e.to_dict() for e in intent],
        "evidence_citing_a_future_version": [e.to_dict() for e in ahead],
        "evidence_flow_mismatch": [e.to_dict() for e in flow_mismatch],
        "evidence_naming_requirement_but_no_decision": [
            e.to_dict() for e in unattributed
        ],
        "next_step": next_step,
    }


def assess(
    requirements: Sequence[Requirement],
    decisions: Sequence[DesignDecision],
    flows: Sequence[DataFlow],
    evidence: Sequence[Evidence],
) -> Dict[str, Any]:
    by_requirement = {r.requirement_id: r for r in requirements}
    links: List[Dict[str, Any]] = []
    dangling: List[Dict[str, str]] = []

    for decision in decisions:
        for requirement_id in decision.governing_requirements:
            requirement = by_requirement.get(requirement_id)
            if requirement is None:
                dangling.append(
                    {
                        "decision_id": decision.decision_id,
                        "requirement_id": requirement_id,
                        "why": (
                            "the decision names a requirement that is not in the "
                            "register; the link cannot be assessed and is not "
                            "counted as either traced or untraced"
                        ),
                    }
                )
                continue
            links.append(assess_link(decision, requirement, evidence))

    by_state: Dict[str, int] = {}
    for link in links:
        by_state[link["state"]] = by_state.get(link["state"], 0) + 1

    # Requirements nothing points at. A requirement with no decision citing it is
    # not satisfied by default.
    cited_requirements = {
        r for decision in decisions for r in decision.governing_requirements
    }
    uncited = sorted(
        r.requirement_id
        for r in requirements
        if r.requirement_id not in cited_requirements
    )

    # Flows no requirement claims. A flow crossing a trust boundary with nothing
    # attached is the question worth asking in an interview.
    claimed_flows = {
        flow for r in requirements for flow in r.applies_to_flows
    }
    unclaimed_flows = [
        f.to_dict() for f in flows if f.flow_id not in claimed_flows
    ]

    changed_requirements = [
        r.to_dict() for r in requirements if r.current_version > 1
    ]

    return {
        "content_class": CONTENT_CLASS,
        "reference_frame": {
            "document": SSDF_DOCUMENT,
            "url": SSDF_URL,
            "practices_used": {
                ref: SSDF_REFERENCES[ref] for ref in sorted(SSDF_REFERENCES)
            },
            "disclaimer": (
                "SSDF practice identifiers organize this instrument only. No "
                "output here is a conformance statement, certification, "
                "attestation, compliance verdict or assessment against the "
                "framework. The descriptions above are paraphrases written for "
                "this worksheet, not quotations; the authoritative wording is at "
                f"{SSDF_URL}."
            ),
        },
        "requirements": [r.to_dict() for r in requirements],
        "data_flows": [f.to_dict() for f in flows],
        "design_decisions": [d.to_dict() for d in decisions],
        # Keep the complete source collection, including unlinked artifacts.
        # JSON output can be re-imported; derived link lists are not source data.
        "evidence": [e.to_dict() for e in evidence],
        "links": links,
        "counts": {
            "requirements": len(requirements),
            "design_decisions": len(decisions),
            "links_assessed": len(links),
            "by_state": by_state,
            "requirements_changed_since_v1": len(changed_requirements),
        },
        "gaps": {
            "dangling_requirement_references": dangling,
            "requirements_no_decision_cites": uncited,
            "flows_no_requirement_claims": unclaimed_flows,
        },
        "limits": [
            "Every requirement, decision, flow and artifact here is fictional. "
            "Nothing describes the University of Iowa and no row is a finding.",
            "OBSERVED_PRACTICE means an artifact exists and cites the current "
            "requirement version. Whether the artifact is any good is a matter "
            "for the reviewer; this instrument does not read its contents.",
            "DOCUMENTED_INTENT is never upgraded by volume. Ten standards are "
            "still zero design records.",
            "UNKNOWN is never scored as a gap or as a pass. It is an open "
            "question and is reported as one.",
            "SSDF is a reference frame here. No output is a conformance, "
            "certification or compliance claim.",
            "No individual is assessed. The subject is always an artifact's "
            "existence and what it cites.",
        ],
    }


# --------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------


def load_records(payload: Any):
    if not isinstance(payload, dict):
        raise SecureDesignError("expected an object with the record lists")
    for key in ("requirements", "design_decisions", "data_flows", "evidence"):
        entries = payload.get(key, [])
        if not isinstance(entries, list):
            raise SecureDesignError(f"{key}: expected a list of record objects")
        for index, entry in enumerate(entries):
            _record(entry, f"{key}[{index}]")
    requirements = [Requirement(e) for e in payload.get("requirements", [])]
    decisions = [DesignDecision(e) for e in payload.get("design_decisions", [])]
    flows = [DataFlow(e) for e in payload.get("data_flows", [])]
    evidence = [
        Evidence(e, index=i) for i, e in enumerate(payload.get("evidence", []))
    ]
    for label, items, attr in (
        ("requirement_id", requirements, "requirement_id"),
        ("decision_id", decisions, "decision_id"),
        ("flow_id", flows, "flow_id"),
        ("evidence_id", evidence, "evidence_id"),
    ):
        seen: Dict[str, int] = {}
        for item in items:
            key = getattr(item, attr)
            seen[key] = seen.get(key, 0) + 1
        duplicates = sorted(k for k, v in seen.items() if v > 1)
        if duplicates:
            raise SecureDesignError(f"duplicate {label}(s): {duplicates}")
    return requirements, decisions, flows, evidence


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        try:
            return json.load(handle)
        except json.JSONDecodeError as exc:
            raise SecureDesignError(f"{path}: not valid JSON ({exc})") from exc


# --------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------

CSV_COLUMNS = [
    "decision_id",
    "requirement_id",
    "requirement_current_version",
    "flow_id",
    "state",
    "ssdf_references",
    "observed_practice_artifacts",
    "stale_trace_artifacts",
    "intent_artifacts",
    "next_step",
    "future_version_artifacts",
    "unattributed_artifacts",
    "flow_mismatch_artifacts",
]


def to_csv_rows(result: Dict[str, Any]) -> List[List[str]]:
    rows: List[List[str]] = [list(CSV_COLUMNS)]
    for link in result["links"]:
        rows.append(
            [
                link["decision_id"],
                link["requirement_id"],
                str(link["requirement_current_version"]),
                link["flow_id"] or "UNKNOWN",
                link["state"],
                "|".join(link["ssdf_references"]) or "NONE",
                "|".join(e["evidence_id"] for e in link["evidence_observed_practice"])
                or "NONE",
                "|".join(e["evidence_id"] for e in link["evidence_stale_trace"])
                or "NONE",
                "|".join(e["evidence_id"] for e in link["evidence_documented_intent"])
                or "NONE",
                link["next_step"] or "",
                "|".join(e["evidence_id"] for e in link["evidence_citing_a_future_version"])
                or "NONE",
                "|".join(e["evidence_id"] for e in link["evidence_naming_requirement_but_no_decision"])
                or "NONE",
                "|".join(e["evidence_id"] for e in link["evidence_flow_mismatch"])
                or "NONE",
            ]
        )
    return rows


def write_csv(result: Dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(to_csv_rows(result))


def render_worksheet(result: Dict[str, Any]) -> str:
    """The secure-design worksheet."""
    out: List[str] = []
    out.append("# Secure-design requirements worksheet")
    out.append("")
    out.append(
        "**SYNTHETIC.** Every requirement, design decision, data flow and "
        "artifact below is fictional, written to exercise the instrument. "
        "Nothing here describes the University of Iowa, and no row is a finding."
    )
    out.append("")
    frame = result["reference_frame"]
    out.append("## Reference frame")
    out.append("")
    out.append(f"{frame['document']} — {frame['url']}")
    out.append("")
    out.append("| practice | paraphrase written for this worksheet |")
    out.append("|---|---|")
    for ref, text in frame["practices_used"].items():
        out.append(f"| `{ref}` | {text} |")
    out.append("")
    out.append(f"**{frame['disclaimer']}**")
    out.append("")

    out.append("## The three states, and the fourth")
    out.append("")
    out.append("| state | meaning |")
    out.append("|---|---|")
    for state in reversed(STATE_ORDER):
        out.append(f"| `{state}` | {STATE_MEANING[state]} |")
    out.append("")
    out.append(
        "`TRACED_STALE` is the state worth building the worksheet around. It is "
        "the case that looks correct in a traceability matrix: the link resolves, "
        "the artifact exists, and it cites a version of the requirement that has "
        "since changed. Nothing errors. Nothing is missing. The trace is simply "
        "pointing at the wrong text."
    )
    out.append("")

    counts = result["counts"]
    out.append("## Result")
    out.append("")
    out.append(
        f"{counts['requirements']} requirements, {counts['design_decisions']} "
        f"design decisions, {counts['links_assessed']} requirement-to-decision "
        f"links assessed. {counts['requirements_changed_since_v1']} requirement(s) "
        f"have changed since version 1."
    )
    out.append("")
    out.append("| state | links |")
    out.append("|---|---:|")
    for state in reversed(STATE_ORDER):
        if state in counts["by_state"]:
            out.append(f"| `{state}` | {counts['by_state'][state]} |")
    out.append("")

    out.append("## The matrix")
    out.append("")
    out.append("| decision | requirement | v | flow | state | next step |")
    out.append("|---|---|---:|---|---|---|")
    for link in result["links"]:
        out.append(
            "| `{d}` | `{r}` | {v} | {f} | **{s}** | {n} |".format(
                d=link["decision_id"],
                r=link["requirement_id"],
                v=link["requirement_current_version"],
                f=link["flow_id"] or "—",
                s=link["state"],
                n=link["next_step"] or "—",
            )
        )
    out.append("")

    gaps = result["gaps"]
    out.append("## Gaps that are not link states")
    out.append("")
    if gaps["requirements_no_decision_cites"]:
        out.append(
            "**Requirements no design decision cites** — a requirement nothing "
            "points at is not satisfied by default:"
        )
        out.append("")
        for requirement_id in gaps["requirements_no_decision_cites"]:
            out.append(f"- `{requirement_id}`")
        out.append("")
    else:
        out.append("_Every requirement is cited by at least one decision._")
        out.append("")
    if gaps["flows_no_requirement_claims"]:
        out.append(
            "**Data flows no requirement claims** — the ones crossing a trust "
            "boundary are the interview question:"
        )
        out.append("")
        out.append("| flow | description | data | crosses trust boundary |")
        out.append("|---|---|---|---|")
        for flow in gaps["flows_no_requirement_claims"]:
            out.append(
                f"| `{flow['flow_id']}` | {flow['description']} | "
                f"{flow['data_class'] or '—'} | "
                f"{_boundary_label(flow['crosses_trust_boundary'])} |"
            )
        out.append("")
    if gaps["dangling_requirement_references"]:
        out.append(
            "**Decisions naming a requirement that is not in the register** — "
            "not counted as traced or untraced, because the link cannot be "
            "assessed at all:"
        )
        out.append("")
        for item in gaps["dangling_requirement_references"]:
            out.append(
                f"- `{item['decision_id']}` → `{item['requirement_id']}` — "
                f"{item['why']}"
            )
        out.append("")

    out.append("## Interview questions")
    out.append("")
    out.append(
        "Each asks for an artifact, because a description of the process is not "
        "evidence about a decision."
    )
    out.append("")
    out.append(
        "1. Take one requirement that has changed. Which design decisions were "
        "revisited, and what record shows that?"
    )
    out.append(
        "2. When a security requirement is revised, what makes the design "
        "decisions that cited the old version visible?"
    )
    out.append(
        "3. For one data flow crossing a trust boundary, which requirements "
        "apply, and which artifact shows the design considered them?"
    )
    out.append(
        "4. Who reviews a design against its security requirements, and what do "
        "they leave behind?"
    )
    out.append(
        "5. Where a standard requires a design section, can you show that section "
        "for a recent change?"
    )
    out.append("")

    out.append("## Limits")
    out.append("")
    for limit in result["limits"]:
        out.append(f"- {limit}")
    out.append("")
    return "\n".join(out)


def render_evidence_chain(result: Dict[str, Any]) -> str:
    """The sample evidence chain for the security assessment chapter."""
    out: List[str] = []
    out.append("# Sample evidence chain — secure design")
    out.append("")
    out.append(
        "**SYNTHETIC.** A worked chain from a fictional data flow to the "
        "requirement that governs it, the design decision that should have "
        "applied it, and the artifacts that do or do not establish that. Not a "
        "finding."
    )
    out.append("")
    frame = result["reference_frame"]
    out.append(f"Reference frame: {frame['document']} — {frame['url']}. ")
    out.append(f"{frame['disclaimer']}")
    out.append("")

    flows = {f["flow_id"]: f for f in result["data_flows"]}
    requirements = {r["requirement_id"]: r for r in result["requirements"]}
    decisions = {d["decision_id"]: d for d in result["design_decisions"]}

    for link in result["links"]:
        requirement = requirements[link["requirement_id"]]
        decision = decisions[link["decision_id"]]
        out.append(
            f"## `{link['decision_id']}` ← `{link['requirement_id']}` "
            f"(v{requirement['current_version']}) — `{link['state']}`"
        )
        out.append("")
        flow = flows.get(link["flow_id"] or "")
        if flow:
            out.append(
                f"**Data flow** `{flow['flow_id']}` — {flow['description']}  \n"
                f"{flow['source']} → {flow['destination']}"
                + (f" · data: {flow['data_class']}" if flow["data_class"] else "")
                + (
                    " · **crosses a trust boundary**"
                    if flow["crosses_trust_boundary"]
                    else (
                        " · **trust boundary UNKNOWN**"
                        if flow["crosses_trust_boundary"] is None
                        else ""
                    )
                )
            )
            out.append("")
        out.append(f"**Requirement** — {requirement['statement']}")
        out.append("")
        if requirement["change_history"]:
            out.append("Change history:")
            out.append("")
            for entry in requirement["change_history"]:
                out.append(f"- {entry}")
            out.append("")
        out.append(f"**Design decision** — {decision['summary']}")
        if decision["decided_on"]:
            out.append("")
            out.append(f"*Decided:* {decision['decided_on']}")
        out.append("")
        out.append(f"**State: `{link['state']}`** — {link['state_meaning']}")
        out.append("")
        for label, key in (
            ("Observed practice", "evidence_observed_practice"),
            ("Stale trace", "evidence_stale_trace"),
            ("Documented intent", "evidence_documented_intent"),
            ("Cites a version ahead of the register", "evidence_citing_a_future_version"),
            ("Explicit flow mismatch; not supporting evidence", "evidence_flow_mismatch"),
            (
                "Names the requirement but no decision",
                "evidence_naming_requirement_but_no_decision",
            ),
        ):
            items = link[key]
            if not items:
                continue
            out.append(f"*{label}:*")
            out.append("")
            for item in items:
                version = item["cites_requirement_version"]
                out.append(
                    f"- `{item['evidence_id']}` ({item['kind']})"
                    + (f" cites v{version}" if version is not None else "")
                    + f" — {item['statement']}"
                    + (f"  \n  `{item['locator']}`" if item["locator"] else "")
                )
            out.append("")
        if link["next_step"]:
            out.append(f"**Next step:** {link['next_step']}")
            out.append("")
    out.append("---")
    out.append("")
    out.append(
        "No individual is assessed anywhere above. The subject is always an "
        "artifact's existence and which requirement version it cites."
    )
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(
        prog="secure_design.py",
        description=(
            "Assess how security requirements reach design decisions and whether "
            "the traces survive requirement changes. SSDF is a reference frame; "
            "no output is a conformance or certification claim."
        ),
    )
    parser.add_argument(
        "--records",
        default=os.path.join(here, "fixtures", "secure_design_records.json"),
    )
    parser.add_argument("--json-out")
    parser.add_argument("--csv-out")
    parser.add_argument("--worksheet-out")
    parser.add_argument("--chain-out")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        requirements, decisions, flows, evidence = load_records(
            read_json(args.records)
        )
        result = assess(requirements, decisions, flows, evidence)
    except (SecureDesignError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")
    if args.csv_out:
        write_csv(result, args.csv_out)
    if args.worksheet_out:
        with open(args.worksheet_out, "w", encoding="utf-8") as handle:
            handle.write(render_worksheet(result))
    if args.chain_out:
        with open(args.chain_out, "w", encoding="utf-8") as handle:
            handle.write(render_evidence_chain(result))
    if not (args.json_out or args.csv_out or args.worksheet_out or args.chain_out):
        print(render_worksheet(result))

    counts = result["counts"]
    print(
        f"[secure-design] {counts['links_assessed']} links; "
        + ", ".join(
            f"{state}={counts['by_state'][state]}"
            for state in reversed(STATE_ORDER)
            if state in counts["by_state"]
        )
        + f"; {counts['requirements_changed_since_v1']} requirement(s) changed; "
        f"{len(result['gaps']['flows_no_requirement_claims'])} unclaimed flow(s).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
