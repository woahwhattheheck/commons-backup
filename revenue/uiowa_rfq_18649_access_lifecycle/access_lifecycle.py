#!/usr/bin/env python3
"""Human-access lifecycle evidence review (RFQ 18649, work order 053).

Joiner, mover and leaver access across development and deployment environments:
approvals, entitlement reviews, emergency access, and whether an access change
actually reached the systems it was supposed to reach.

The rule this file exists to enforce
------------------------------------
**A written policy is never proof about a case, and a closed ticket is not a
system state.**

Implemented as evidence stages that cannot substitute for one another:

    written_policy -> ticket_request -> approval_record -> execution_record
                                                      -> system_state_observation

Each stage proves only what it is. A policy proves an intent exists and supports
**no conclusion about any individual case**. A closed ticket proves somebody
closed a ticket. Only a `system_state_observation` dated after the change proves
the change reached that system.

Two further rules follow from the order's wording:

*   **Status is per system, never rolled up.** "Evidence that access changes
    reached the relevant systems" is plural. A single aggregate verdict is
    exactly what hides a deployment pipeline that still carries the account, so
    the reviewer gets one status per system and the case status is the weakest
    of them.

*   **An observation before the change proves nothing about the change.** A
    directory export taken the day before someone left says nothing about
    whether their account was removed. Dates are checked, not assumed.

Everything here is synthetic. No real person, account, system or access record is
described, and no output is a University of Iowa finding.

Offline, Python 3 standard library only.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
from contextlib import ExitStack
from datetime import date
from pathlib import Path
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------------

JOINER = "joiner"
MOVER = "mover"
LEAVER = "leaver"
EMERGENCY = "emergency_access"
LIFECYCLE_EVENTS: Tuple[str, ...] = (JOINER, MOVER, LEAVER, EMERGENCY)

GRANT = "grant"
REVOKE = "revoke"
CHANGE_INTENTS: Tuple[str, ...] = (GRANT, REVOKE)

#: Evidence kinds in increasing order of what they establish. The ORDER is the
#: policy: a kind never establishes anything a later kind establishes.
EVIDENCE_STAGES: Tuple[str, ...] = (
    "written_policy",
    "ticket_request",
    "approval_record",
    "execution_record",
    "system_state_observation",
)
STAGE_INDEX = {kind: index for index, kind in enumerate(EVIDENCE_STAGES)}

#: An entitlement review is a distinct artifact: it says somebody looked at
#: standing access on a date. It is not a change record and cannot establish
#: that any particular change happened.
ENTITLEMENT_REVIEW = "entitlement_review_record"

ALL_EVIDENCE_KINDS = EVIDENCE_STAGES + (ENTITLEMENT_REVIEW,)

#: Per-system conclusions, weakest first.
NO_EVIDENCE = "NO_EVIDENCE"
POLICY_ONLY = "POLICY_ONLY"
REQUESTED_ONLY = "REQUESTED_ONLY"
APPROVED_ONLY = "APPROVED_ONLY"
ACTION_RECORDED = "ACTION_RECORDED"
CONFIRMED_IN_SYSTEM = "CONFIRMED_IN_SYSTEM"
CONTRADICTED_IN_SYSTEM = "CONTRADICTED_IN_SYSTEM"

STATUS_ORDER: Tuple[str, ...] = (
    CONTRADICTED_IN_SYSTEM,
    NO_EVIDENCE,
    POLICY_ONLY,
    REQUESTED_ONLY,
    APPROVED_ONLY,
    ACTION_RECORDED,
    CONFIRMED_IN_SYSTEM,
)
STATUS_RANK = {status: index for index, status in enumerate(STATUS_ORDER)}

STATUS_MEANING: Dict[str, str] = {
    NO_EVIDENCE: (
        "Nothing is recorded for this system. Not a failure and not a pass -- "
        "an open question."
    ),
    POLICY_ONLY: (
        "Only a written policy applies. A policy states an intent; it is not "
        "evidence about this case, and no conclusion about this case rests on it."
    ),
    REQUESTED_ONLY: (
        "A request exists. Nobody has evidenced that it was approved, performed, "
        "or reached the system."
    ),
    APPROVED_ONLY: (
        "An approval is recorded. Nobody has evidenced that the change was "
        "performed or reached the system."
    ),
    ACTION_RECORDED: (
        "Somebody recorded performing the change. The system's own state has not "
        "been observed since, so whether it took effect is unverified."
    ),
    CONFIRMED_IN_SYSTEM: (
        "The system's own state was observed after the change and matches the "
        "intent."
    ),
    CONTRADICTED_IN_SYSTEM: (
        "The system's own state was observed after the change and does NOT match "
        "the intent. This outranks every paper record."
    ),
}

CONTENT_CLASS = "SYNTHETIC_NOT_A_UNIVERSITY_FINDING"


class AccessReviewError(ValueError):
    """Input the review refuses to interpret by guessing."""


# --------------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------------


def _object(value: Any, where: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise AccessReviewError(f"{where}: expected an object")
    return value


def _list(value: Any, where: str) -> List[Any]:
    if not isinstance(value, list):
        raise AccessReviewError(f"{where}: expected a list")
    return value


def _text(value: Any, where: str, *, optional: bool = True) -> str:
    if value is None and optional:
        return ""
    if not isinstance(value, str):
        raise AccessReviewError(f"{where}: expected text, not {type(value).__name__}")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise AccessReviewError(f"{where}: invalid Unicode") from exc
    return value.strip()


def _date(value: Any, *, case_id: str, field: str) -> Optional[str]:
    """Calendar-valid, zero-padded date, or an explicit unknown marker."""
    if value is None:
        return None
    text = _text(value, f"{case_id}: {field}")
    if text in ("", "UNKNOWN"):
        return None
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text) is None:
            raise ValueError("expected canonical date")
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise AccessReviewError(
            f"{case_id}: {field} is {value!r}; expected a calendar-valid "
            "YYYY-MM-DD or an unknown marker"
        ) from exc


class Evidence:
    """One piece of evidence about one system."""

    def __init__(self, payload: Dict[str, Any], *, case_id: str) -> None:
        _object(payload, f"{case_id}: evidence")
        allowed = {"kind", "system", "statement", "observed_on", "locator",
                   "matches_intent", "intent", "entitlement", "environment", "effective_on"}
        unknown = set(payload) - allowed
        if unknown:
            raise AccessReviewError(f"{case_id}: unknown evidence fields {sorted(unknown)}")
        kind = payload.get("kind")
        if kind not in ALL_EVIDENCE_KINDS:
            raise AccessReviewError(
                f"{case_id}: evidence kind {kind!r} is not one of "
                f"{list(ALL_EVIDENCE_KINDS)}. An unrecognized kind has no place in "
                f"the stage order and could be read as establishing anything."
            )
        self.kind = kind
        self.system = _text(payload.get("system", ""), f"{case_id}: system")
        if not self.system and kind != "written_policy":
            raise AccessReviewError(
                f"{case_id}: evidence of kind {kind!r} must name the system it "
                f"concerns. Evidence that names no system cannot show a change "
                f"reached any particular one."
            )
        self.statement = _text(payload.get("statement", ""), f"{case_id}: statement")
        if not self.statement:
            raise AccessReviewError(f"{case_id}: every evidence item needs a statement")
        #: Which change this evidence concerns, when a system carries more than
        #: one. An emergency elevation and its later removal are two changes on
        #: one system, and the elevation's record says nothing about the removal.
        intent = payload.get("intent")
        if intent is not None and intent not in CHANGE_INTENTS:
            raise AccessReviewError(
                f"{case_id}: evidence 'intent' must be one of "
                f"{list(CHANGE_INTENTS)} or absent, got {intent!r}"
            )
        self.intent = intent
        self.observed_on = _date(
            payload.get("observed_on"), case_id=case_id, field="observed_on"
        )
        self.locator = _text(payload.get("locator", ""), f"{case_id}: locator")
        # Optional exact qualifiers; no fuzzy matching or evidence borrowing.
        self.qualifiers: Dict[str, str] = {}
        for name in ("entitlement", "environment", "effective_on"):
            if name not in payload:
                continue
            value = (_date(payload[name], case_id=case_id, field=name)
                     if name == "effective_on" else _text(payload[name], f"{case_id}: {name}"))
            if not value:
                raise AccessReviewError(f"{case_id}: supplied evidence qualifier {name} must be known")
            self.qualifiers[name] = value
        #: For a system_state_observation only: does the observed state match the
        #: intent? Absent means the observation exists but its result was not
        #: recorded, which is itself a gap rather than a pass.
        self.matches_intent = payload.get("matches_intent")
        if self.kind == "system_state_observation":
            if self.matches_intent is not None and type(self.matches_intent) is not bool:
                raise AccessReviewError(
                    f"{case_id}: a system_state_observation's 'matches_intent' "
                    f"must be true, false, or absent"
                )
            if self.observed_on is None:
                raise AccessReviewError(
                    f"{case_id}: a system_state_observation must carry "
                    f"'observed_on'. An observation with no date cannot be shown "
                    f"to post-date the change, and an undated observation is "
                    f"exactly how a stale export gets read as confirmation."
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "system": self.system or None,
            "statement": self.statement,
            "observed_on": self.observed_on,
            "locator": self.locator,
            "matches_intent": self.matches_intent,
            "intent": self.intent,
            **self.qualifiers,
        }


class AccessChange:
    """One intended access change, on one system, within a case."""

    def __init__(self, payload: Dict[str, Any], *, case_id: str) -> None:
        _object(payload, f"{case_id}: access change")
        unknown = set(payload) - {"system", "environment", "intent", "entitlement", "effective_on"}
        if unknown:
            raise AccessReviewError(f"{case_id}: unknown access-change fields {sorted(unknown)}")
        self.system = _text(payload.get("system", ""), f"{case_id}: system")
        if not self.system:
            raise AccessReviewError(f"{case_id}: every access change names a system")
        self.environment = _text(payload.get("environment", ""), f"{case_id}: environment")
        intent = payload.get("intent")
        if intent not in CHANGE_INTENTS:
            raise AccessReviewError(
                f"{case_id}/{self.system}: intent must be one of "
                f"{list(CHANGE_INTENTS)}"
            )
        self.intent = intent
        self.entitlement = _text(payload.get("entitlement", ""), f"{case_id}: entitlement")
        self.effective_on = _date(
            payload.get("effective_on"), case_id=case_id, field="effective_on"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system": self.system,
            "environment": self.environment,
            "intent": self.intent,
            "entitlement": self.entitlement,
            "effective_on": self.effective_on,
        }


class Case:
    """One fictional joiner, mover, leaver or emergency-access episode."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        _object(payload, "case")
        case_id = payload.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise AccessReviewError("every case needs a 'case_id'")
        self.case_id = _text(case_id, "case_id", optional=False)
        event = payload.get("lifecycle_event")
        if event not in LIFECYCLE_EVENTS:
            raise AccessReviewError(
                f"{self.case_id}: lifecycle_event must be one of "
                f"{list(LIFECYCLE_EVENTS)}"
            )
        self.lifecycle_event = event
        self.summary = _text(payload.get("summary", ""), f"{self.case_id}: summary")
        self.person_role = _text(payload.get("person_role", ""), f"{self.case_id}: person_role")
        self.worker_type = _text(payload.get("worker_type", ""), f"{self.case_id}: worker_type")
        self.event_on = _date(
            payload.get("event_on"), case_id=self.case_id, field="event_on"
        )
        self.changes = [
            AccessChange(entry, case_id=self.case_id)
            for entry in _list(payload.get("access_changes", []), f"{self.case_id}: access_changes")
        ]
        if not self.changes:
            raise AccessReviewError(
                f"{self.case_id}: a case with no access changes has nothing to "
                f"review"
            )
        identities = [tuple(change.to_dict().values()) for change in self.changes]
        if len(identities) != len(set(identities)):
            raise AccessReviewError(f"{self.case_id}: duplicate access change")
        self.evidence = [
            Evidence(entry, case_id=self.case_id)
            for entry in _list(payload.get("evidence", []), f"{self.case_id}: evidence")
        ]
        self.interview_prompts = [
            _text(p, f"{self.case_id}: interview prompt", optional=False)
            for p in _list(payload.get("interview_prompts", []), f"{self.case_id}: interview_prompts")
        ]
        self.notes = _text(payload.get("notes", ""), f"{self.case_id}: notes")


# --------------------------------------------------------------------------------
# Review
# --------------------------------------------------------------------------------


def _relevant(
    evidence: Evidence, change: AccessChange, *, system_has_multiple_changes: bool,
    case_changes: Optional[Sequence[AccessChange]] = None,
) -> Tuple[bool, Optional[str]]:
    """Attribute a record to exactly one declared change, never by proximity."""
    if evidence.kind == "written_policy":
        return True, None

    def matches(candidate: AccessChange) -> bool:
        return (evidence.system == candidate.system
                and (evidence.intent is None or evidence.intent == candidate.intent)
                and all(getattr(candidate, key) == value
                        for key, value in evidence.qualifiers.items()))

    if not matches(change):
        return False, None
    if case_changes is not None:
        ambiguous = sum(matches(candidate) for candidate in case_changes) != 1
    else:
        ambiguous = system_has_multiple_changes and evidence.intent is None
    if ambiguous:
        return False, (
            "this record does not uniquely identify a declared change on this system; "
            "supply the intent and, where needed, entitlement, environment or effective_on. "
            "Attributing it to this change would be a guess."
        )
    return True, None


def review_change(
    case: Case, change: AccessChange, *, system_has_multiple_changes: bool = False
) -> Dict[str, Any]:
    """Conclude what the evidence establishes about ONE system.

    The conclusion is the highest stage the relevant evidence actually reaches,
    with two overrides: a system observation that contradicts the intent beats
    every paper record, and an observation that pre-dates the change establishes
    nothing about it.
    """
    relevant: List[Evidence] = []
    ambiguous: List[Dict[str, Any]] = []
    for item in case.evidence:
        ok, why_not = _relevant(
            item, change, system_has_multiple_changes=system_has_multiple_changes,
            case_changes=case.changes,
        )
        if ok:
            relevant.append(item)
        elif why_not:
            ambiguous.append(
                {
                    "kind": item.kind,
                    "statement": item.statement,
                    "locator": item.locator,
                    "why_excluded": why_not,
                }
            )
    declared_reference_date = change.effective_on or case.event_on
    reference_date = declared_reference_date
    executions = [item for item in relevant if item.kind == "execution_record"]
    dated_checkpoints = [value for value in
                        [reference_date, *(item.observed_on for item in executions)] if value]
    reference_date = max(dated_checkpoints) if dated_checkpoints else None
    undated_execution = any(item.observed_on is None for item in executions)

    stale: List[Dict[str, Any]] = []
    usable: List[Evidence] = []
    for item in relevant:
        if item.kind == "system_state_observation":
            if reference_date is None or undated_execution or item.observed_on < reference_date:
                # A directory export from before the change says nothing about
                # whether the change happened. Demote it, loudly.
                stale.append(
                    {
                        "statement": item.statement,
                        "observed_on": item.observed_on,
                        "reference_date": reference_date,
                        "why_excluded": (
                            "change/execution checkpoint is unknown, so this observation "
                            "cannot show the change reached the system"
                            if reference_date is None or undated_execution else
                            "observed before a later execution record, so it "
                            "cannot show the change reached the system"
                            if declared_reference_date is None or reference_date > declared_reference_date else
                            "observed before the change took effect, so it "
                            "cannot show the change reached the system"
                        ),
                    }
                )
                continue
        usable.append(item)

    reviews = [e for e in usable if e.kind == ENTITLEMENT_REVIEW]
    staged = [e for e in usable if e.kind in STAGE_INDEX]

    contradicting = [
        e
        for e in staged
        if e.kind == "system_state_observation" and e.matches_intent is False
    ]
    confirming = [
        e
        for e in staged
        if e.kind == "system_state_observation" and e.matches_intent is True
    ]
    unrecorded_observation = [
        e
        for e in staged
        if e.kind == "system_state_observation" and e.matches_intent is None
    ]

    if contradicting:
        status = CONTRADICTED_IN_SYSTEM
    elif confirming:
        status = CONFIRMED_IN_SYSTEM
    elif not staged:
        status = NO_EVIDENCE
    else:
        best = max(STAGE_INDEX[e.kind] for e in staged)
        # An observation whose result was never recorded cannot confirm; it is
        # treated as no better than the paper trail beneath it.
        if EVIDENCE_STAGES[best] == "system_state_observation":
            paper = [
                STAGE_INDEX[e.kind]
                for e in staged
                if e.kind != "system_state_observation"
            ]
            best = max(paper) if paper else -1
        status = {
            "written_policy": POLICY_ONLY,
            "ticket_request": REQUESTED_ONLY,
            "approval_record": APPROVED_ONLY,
            "execution_record": ACTION_RECORDED,
        }[EVIDENCE_STAGES[best]] if best >= 0 else NO_EVIDENCE

    gap = None
    if status in (POLICY_ONLY, NO_EVIDENCE):
        gap = (
            "No case-specific evidence establishes anything about this system. "
            "A written policy is an intent, not a record of what happened here."
        )
    elif status in (REQUESTED_ONLY, APPROVED_ONLY, ACTION_RECORDED):
        gap = (
            f"Request this system's own state as at a date after "
            f"{reference_date or 'the change'}: an export or account listing "
            f"showing whether the {change.intent} took effect."
        )
    elif status == CONTRADICTED_IN_SYSTEM:
        gap = (
            "The system's state does not match the intent. Establish whether the "
            "change was reversed, never applied, or applied to a different "
            "account."
        )

    return {
        "case_id": case.case_id,
        "system": change.system,
        "environment": change.environment,
        "intent": change.intent,
        "entitlement": change.entitlement,
        "effective_on": change.effective_on,
        "status": status,
        "status_meaning": STATUS_MEANING[status],
        "evidence_used": [e.to_dict() for e in usable],
        "evidence_excluded_as_stale": stale,
        "evidence_excluded_as_ambiguous": ambiguous,
        "entitlement_reviews": [e.to_dict() for e in reviews],
        "observation_result_not_recorded": [
            e.to_dict() for e in unrecorded_observation
        ],
        "what_would_settle_it": gap,
        "conclusion_rests_on_policy_alone": status == POLICY_ONLY,
    }


def review_case(case: Case) -> Dict[str, Any]:
    """Review every system in a case. The case status is the weakest system."""
    counts: Dict[str, int] = {}
    for change in case.changes:
        counts[change.system] = counts.get(change.system, 0) + 1
    per_system = [
        review_change(
            case, change, system_has_multiple_changes=counts[change.system] > 1
        )
        for change in case.changes
    ]
    weakest = min(per_system, key=lambda r: STATUS_RANK[r["status"]])
    unverified = [
        r["system"]
        for r in per_system
        if STATUS_RANK[r["status"]] < STATUS_RANK[CONFIRMED_IN_SYSTEM]
    ]
    return {
        "case_id": case.case_id,
        "lifecycle_event": case.lifecycle_event,
        "worker_type": case.worker_type,
        "person_role": case.person_role,
        "event_on": case.event_on,
        "summary": case.summary,
        "per_system": per_system,
        "case_status": weakest["status"],
        "case_status_basis": (
            f"the weakest system is {weakest['system']} at "
            f"{weakest['status']}. The case status is the weakest system, not an "
            f"average: an access change that reached three systems and missed a "
            f"fourth has not been made."
        ),
        "systems_not_confirmed": unverified,
        "systems_reviewed": [r["system"] for r in per_system],
        "interview_prompts": list(case.interview_prompts),
        "notes": case.notes,
        "content_class": CONTENT_CLASS,
    }


def review_all(cases: Sequence[Case]) -> Dict[str, Any]:
    results = [review_case(case) for case in cases]
    by_status: Dict[str, int] = {}
    for record in results:
        by_status[record["case_status"]] = by_status.get(record["case_status"], 0) + 1

    system_rows = [r for record in results for r in record["per_system"]]
    system_status_counts: Dict[str, int] = {}
    for row in system_rows:
        system_status_counts[row["status"]] = (
            system_status_counts.get(row["status"], 0) + 1
        )

    events_covered = sorted({r["lifecycle_event"] for r in results})
    return {
        "content_class": CONTENT_CLASS,
        "cases": results,
        "counts": {
            "cases": len(results),
            "systems_reviewed": len(system_rows),
            "case_status": by_status,
            "system_status": system_status_counts,
            "cases_resting_on_policy_alone": sum(
                1
                for record in results
                if any(r["conclusion_rests_on_policy_alone"] for r in record["per_system"])
            ),
        },
        "coverage": {
            "lifecycle_events": list(LIFECYCLE_EVENTS),
            "lifecycle_events_covered": events_covered,
            "lifecycle_events_missing": [
                e for e in LIFECYCLE_EVENTS if e not in events_covered
            ],
            "contractor_departure_present": any(
                r["lifecycle_event"] == LEAVER
                and "contractor" in r["worker_type"].lower()
                for r in results
            ),
            "changed_responsibilities_present": any(
                r["lifecycle_event"] == MOVER for r in results
            ),
        },
        "evidence_stage_order": list(EVIDENCE_STAGES),
        "limits": [
            "Every case, system, role and record here is fictional. Nothing "
            "describes the University of Iowa, and no output is a finding.",
            "A CONFIRMED_IN_SYSTEM status means one observation of one system "
            "matched the intent on one date. It is not a statement that access "
            "management works.",
            "A written policy establishes nothing about any individual case, and "
            "no status in this output is derived from one.",
            "No person is assessed. The subject of every conclusion is a system's "
            "recorded state, never an individual's performance.",
        ],
    }


# --------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------


def load_cases(payload: Any) -> List[Case]:
    if isinstance(payload, dict):
        payload = payload.get("cases")
    if not isinstance(payload, list):
        raise AccessReviewError("expected an object with a 'cases' list")
    cases = [Case(entry) for entry in payload]
    seen: Dict[str, int] = {}
    for case in cases:
        seen[case.case_id] = seen.get(case.case_id, 0) + 1
    duplicates = sorted(k for k, v in seen.items() if v > 1)
    if duplicates:
        raise AccessReviewError(f"duplicate case_id(s): {duplicates}")
    return cases


def read_json(path: str) -> Any:
    def pairs(items):
        record = {}
        for key, value in items:
            if key in record:
                raise AccessReviewError(f"{path}: duplicate JSON key {key!r}")
            record[key] = value
        return record

    def constant(value):
        raise AccessReviewError(f"{path}: non-JSON constant {value}")

    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=pairs, parse_constant=constant)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise AccessReviewError(f"{path}: cannot read valid UTF-8 JSON ({exc})") from exc


# --------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------

CSV_COLUMNS = [
    "case_id",
    "lifecycle_event",
    "worker_type",
    "system",
    "environment",
    "intent",
    "entitlement",
    "effective_on",
    "status",
    "rests_on_policy_alone",
    "stale_evidence_excluded",
    "what_would_settle_it",
]


def to_csv_rows(result: Dict[str, Any]) -> List[List[str]]:
    rows: List[List[str]] = [list(CSV_COLUMNS)]
    for record in result["cases"]:
        for row in record["per_system"]:
            rows.append(
                [
                    record["case_id"],
                    record["lifecycle_event"],
                    record["worker_type"] or "UNKNOWN",
                    row["system"],
                    row["environment"] or "UNKNOWN",
                    row["intent"],
                    row["entitlement"] or "UNKNOWN",
                    # A word, never a blank: a blank date reads as no date needed.
                    row["effective_on"] or "UNKNOWN",
                    row["status"],
                    "YES" if row["conclusion_rests_on_policy_alone"] else "NO",
                    str(len(row["evidence_excluded_as_stale"])),
                    row["what_would_settle_it"] or "",
                ]
            )
    return rows


def _csv_literal(value: str) -> str:
    """Literalize formula-like cells; no spreadsheet program is invoked."""
    return "'" + value if value and (value[0] in "'=+-@" or value[0].isspace()) else value


def csv_text(result: Dict[str, Any]) -> str:
    stream = io.StringIO(newline="")
    csv.writer(stream).writerows([[_csv_literal(cell) for cell in row]
                                  for row in to_csv_rows(result)])
    return stream.getvalue()


def _write_new_outputs(outputs: Sequence[Tuple[str, str]]) -> None:
    """Preflight all destinations and reserve exclusively before writing.

    Never overwrites or deletes an existing path. A later filesystem failure may
    leave new empty/partial files; this is not an atomic filesystem transaction.
    """
    resolved = [Path(path).resolve() for path, _ in outputs]
    if len(resolved) != len(set(resolved)):
        raise AccessReviewError("output paths must identify distinct files")
    for path, _ in outputs:
        if os.path.lexists(path):
            raise AccessReviewError(f"output already exists; choose a new path: {path}")
        if not Path(path).parent.is_dir():
            raise AccessReviewError(f"output parent directory does not exist: {path}")
    with ExitStack() as stack:
        handles = [stack.enter_context(open(path, "x", encoding="utf-8", newline=""))
                   for path, _ in outputs]
        for handle, (_, content) in zip(handles, outputs):
            handle.write(content)


def write_csv(result: Dict[str, Any], path: str) -> None:
    _write_new_outputs([(path, csv_text(result))])


def _markdown_values(value: Any) -> Any:
    """Render record text literally without changing the review JSON itself."""
    if isinstance(value, str):
        for original, escaped in (("\\", "\\\\"), ("`", "\\`"), ("[", "\\["),
                                  ("]", "\\]"), ("|", "\\|"), ("<", "&lt;"), (">", "&gt;")):
            value = value.replace(original, escaped)
        return value.replace("\r", " ").replace("\n", "<br>")
    if isinstance(value, list):
        return [_markdown_values(item) for item in value]
    if isinstance(value, dict):
        return {key: _markdown_values(item) for key, item in value.items()}
    return value


def _readable_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Disambiguate colliding displayed targets on a rendering-only copy.

    Both readable exports show system and intent. Where those repeat, use the
    complete declared identity, never a row number that changes on reordering.
    JSON and CSV evidence remain untouched. Original unambiguous examples keep
    their exact output bytes.
    """
    rendered = _markdown_values(result)
    for original, record in zip(result["cases"], rendered["cases"]):
        counts: Dict[Tuple[str, str], int] = {}
        for row in original["per_system"]:
            key = (row["system"], row["intent"])
            counts[key] = counts.get(key, 0) + 1
        changed = False
        for raw, row in zip(original["per_system"], record["per_system"]):
            if counts[(raw["system"], raw["intent"])] < 2:
                continue
            fields = "; ".join(
                name + "=" + (json.dumps(raw[name], ensure_ascii=False)
                              if raw[name] else "UNKNOWN")
                for name in ("entitlement", "environment", "effective_on")
            )
            row["system"] = _markdown_values(raw["system"] + " [" + fields + "]")
            changed = True
        if changed:
            record["systems_not_confirmed"] = [
                row["system"] for row in record["per_system"]
                if STATUS_RANK[row["status"]] < STATUS_RANK[CONFIRMED_IN_SYSTEM]
            ]
            weakest = min(record["per_system"], key=lambda row: STATUS_RANK[row["status"]])
            record["case_status_basis"] = (
                f"the weakest system is {weakest['system']} at {weakest['status']}. "
                "The case status is the weakest system, not an average: an access "
                "change that reached three systems and missed a fourth has not been made."
            )
    return rendered


def render_matrix(result: Dict[str, Any]) -> str:
    """The access-lifecycle evidence matrix."""
    result = _readable_result(result)
    out: List[str] = []
    out.append("# Access-lifecycle evidence matrix")
    out.append("")
    out.append(
        "**SYNTHETIC.** Every case, person, system and record below is fictional, "
        "written to exercise the review method. Nothing here describes the "
        "University of Iowa, and no row is a finding."
    )
    out.append("")
    out.append("## What each evidence kind establishes")
    out.append("")
    out.append("| evidence | establishes |")
    out.append("|---|---|")
    out.append(
        "| `written_policy` | That an intent exists. **Nothing about any "
        "individual case.** |"
    )
    out.append("| `ticket_request` | That a request was raised. |")
    out.append("| `approval_record` | That an approval was recorded. |")
    out.append(
        "| `execution_record` | That somebody recorded performing the change. "
        "Not that the system changed. |"
    )
    out.append(
        "| `system_state_observation` | That the system's own state was observed "
        "on a date, and what it showed. |"
    )
    out.append(
        "| `entitlement_review_record` | That standing access was reviewed on a "
        "date. Not that any particular change happened. |"
    )
    out.append("")
    out.append(
        "A stage never establishes what a later stage establishes. The order is "
        "the method: `"
        + "` → `".join(result["evidence_stage_order"])
        + "`."
    )
    out.append("")
    out.append("## Status vocabulary")
    out.append("")
    out.append("| status | meaning |")
    out.append("|---|---|")
    for status in reversed(STATUS_ORDER):
        out.append(f"| `{status}` | {STATUS_MEANING[status]} |")
    out.append("")

    counts = result["counts"]
    out.append("## The matrix")
    out.append("")
    out.append(
        f"{counts['cases']} cases, {counts['systems_reviewed']} system rows. "
        f"**Status is per system.** A case's status is its weakest system, never "
        f"an average — an access change that reached three systems and missed a "
        f"fourth has not been made."
    )
    out.append("")
    out.append(
        "| case | event | system | env | intent | status | what would settle it |"
    )
    out.append("|---|---|---|---|---|---|---|")
    for record in result["cases"]:
        for row in record["per_system"]:
            out.append(
                "| `{case}` | {event} | {system} | {env} | {intent} | "
                "**{status}** | {gap} |".format(
                    case=record["case_id"],
                    event=record["lifecycle_event"],
                    system=row["system"],
                    env=row["environment"] or "—",
                    intent=row["intent"],
                    status=row["status"],
                    gap=(row["what_would_settle_it"] or "—"),
                )
            )
    out.append("")

    out.append("## Case summary")
    out.append("")
    out.append("| case | event | worker | case status | systems not confirmed |")
    out.append("|---|---|---|---|---|")
    for record in result["cases"]:
        out.append(
            f"| `{record['case_id']}` | {record['lifecycle_event']} | "
            f"{record['worker_type'] or '—'} | **{record['case_status']}** | "
            + (", ".join(record["systems_not_confirmed"]) or "none")
            + " |"
        )
    out.append("")

    stale_rows = [
        (record["case_id"], row["system"], excluded)
        for record in result["cases"]
        for row in record["per_system"]
        for excluded in row["evidence_excluded_as_stale"]
    ]
    if stale_rows:
        out.append("## Evidence excluded as stale")
        out.append("")
        out.append(
            "An observation taken before the change cannot show the change "
            "reached the system. These were excluded from the conclusion and are "
            "listed rather than dropped."
        )
        out.append("")
        out.append("| case | system | observed | change effective | excluded because |")
        out.append("|---|---|---|---|---|")
        for case_id, system, excluded in stale_rows:
            out.append(
                f"| `{case_id}` | {system} | {excluded['observed_on']} | "
                f"{excluded['reference_date']} | {excluded['why_excluded']} |"
            )
        out.append("")

    out.append("## Limits")
    out.append("")
    for limit in result["limits"]:
        out.append(f"- {limit}")
    out.append("")
    return "\n".join(out)


def render_scenarios(result: Dict[str, Any]) -> str:
    """Fictional role-change scenarios, written for use in interviews."""
    result = _readable_result(result)
    out: List[str] = []
    out.append("# Fictional role-change scenarios for interviews")
    out.append("")
    out.append(
        "**SYNTHETIC.** These scenarios are invented. They are prompts for a "
        "conversation, not findings, and not descriptions of anything observed."
    )
    out.append("")
    out.append(
        "Each scenario states what the evidence establishes, what it does not, "
        "and the questions that would close the gap. The questions ask for "
        "**records**, because a description of the process is not evidence about "
        "the case."
    )
    out.append("")
    for record in result["cases"]:
        out.append(f"## `{record['case_id']}` — {record['summary']}")
        out.append("")
        out.append(
            f"*Event:* {record['lifecycle_event']}"
            + (f" · *Worker:* {record['worker_type']}" if record["worker_type"] else "")
            + (f" · *Role:* {record['person_role']}" if record["person_role"] else "")
            + (f" · *Date:* {record['event_on']}" if record["event_on"] else "")
        )
        out.append("")
        out.append(f"**Case status: `{record['case_status']}`** — {record['case_status_basis']}")
        out.append("")
        out.append("| system | intent | status |")
        out.append("|---|---|---|")
        for row in record["per_system"]:
            out.append(
                f"| {row['system']} | {row['intent']} | `{row['status']}` |"
            )
        out.append("")
        unresolved = [
            row for row in record["per_system"] if row["what_would_settle_it"]
        ]
        if unresolved:
            out.append("**What to ask for:**")
            out.append("")
            for row in unresolved:
                out.append(f"- *{row['system']}* — {row['what_would_settle_it']}")
            out.append("")
        if record["interview_prompts"]:
            out.append("**Interview prompts:**")
            out.append("")
            for prompt in record["interview_prompts"]:
                out.append(f"- {prompt}")
            out.append("")
        if record["notes"]:
            out.append(f"*Note:* {record['notes']}")
            out.append("")
    out.append("---")
    out.append("")
    out.append(
        "No person is assessed by any scenario above. The subject is always a "
        "system's recorded state, never an individual's performance."
    )
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(
        prog="access_lifecycle.py",
        description=(
            "Review joiner/mover/leaver access evidence per system, treating no "
            "written policy as proof about a case."
        ),
    )
    parser.add_argument(
        "--cases", default=os.path.join(here, "fixtures", "lifecycle_cases.json")
    )
    parser.add_argument("--json-out")
    parser.add_argument("--csv-out")
    parser.add_argument("--matrix-out")
    parser.add_argument("--scenarios-out")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        cases = load_cases(read_json(args.cases))
        result = review_all(cases)
    except AccessReviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        outputs: List[Tuple[str, str]] = []
        if args.json_out:
            outputs.append((args.json_out, json.dumps(result, indent=2, sort_keys=True) + "\n"))
        if args.csv_out:
            outputs.append((args.csv_out, csv_text(result)))
        if args.matrix_out:
            outputs.append((args.matrix_out, render_matrix(result)))
        if args.scenarios_out:
            outputs.append((args.scenarios_out, render_scenarios(result)))
        _write_new_outputs(outputs)
        if not outputs:
            print(render_matrix(result))
    except (AccessReviewError, OSError, UnicodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    counts = result["counts"]
    print(
        f"[access] {counts['cases']} cases, {counts['systems_reviewed']} system "
        f"rows; system status "
        + ", ".join(
            f"{k}={v}"
            for k, v in sorted(
                counts["system_status"].items(),
                key=lambda kv: STATUS_RANK[kv[0]],
            )
        )
        + f"; lifecycle events covered "
        f"{len(result['coverage']['lifecycle_events_covered'])}/"
        f"{len(LIFECYCLE_EVENTS)}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
