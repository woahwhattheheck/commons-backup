"""Classify GrantFox provider state without mutating ownership or provider state."""

from __future__ import annotations

from dataclasses import dataclass

from integrations.command_center.grantfox_overlap_triage import (
    ISSUE_CLOSED,
    NEEDS_REFRESH as OVERLAP_NEEDS_REFRESH,
    OVERLAP_OPEN_PR,
    READY,
    SATISFIED_DEFAULT_BRANCH,
)

APPLICATION_REQUIRED = "APPLICATION_REQUIRED"
WAIT_PROVIDER_ASSIGNMENT = "WAIT_PROVIDER_ASSIGNMENT"
IMPLEMENTATION_READY = "IMPLEMENTATION_READY"
PROVIDER_ASSIGNED_OTHER = "PROVIDER_ASSIGNED_OTHER"
RESEARCH_ONLY = "RESEARCH_ONLY"
OVERLAP_EXISTING_WORK = "OVERLAP_EXISTING_WORK"
CLOSED_OR_SATISFIED = "CLOSED_OR_SATISFIED"
NEEDS_REFRESH = "NEEDS_REFRESH"

_VALID_APPLICATION_STATES = {
    "not_submitted",
    "submitted",
    "rejected",
    "withdrawn",
    "ineligible",
}
_VALID_ASSIGNMENT_STATES = {
    "unassigned",
    "pending",
    "assigned_current_contributor",
    "assigned_other",
}


@dataclass(frozen=True)
class GrantFoxExecutionEvidence:
    repository: str
    issue_number: int
    issue_state: str
    overlap_verdict: str
    grantfox_candidate_verified: bool
    application_state: str | None
    assignment_state: str | None
    provider_state_observed: bool


def classify_execution(evidence: GrantFoxExecutionEvidence) -> dict:
    """Return an advisory execution state from a provider-state snapshot.

    This reducer performs no network I/O and does not claim or assign work.
    Research/baseline work remains available in every non-terminal state.
    Missing or malformed observations require refresh, not inferred closure or
    eligibility; positive provider observations must be actual booleans.
    """
    issue_state = _normalized(evidence.issue_state)
    if issue_state == "closed" or evidence.overlap_verdict in {
        ISSUE_CLOSED,
        SATISFIED_DEFAULT_BRANCH,
    }:
        return _result(evidence, CLOSED_OR_SATISFIED)

    if issue_state != "open":
        return _result(evidence, NEEDS_REFRESH)

    if evidence.overlap_verdict == OVERLAP_OPEN_PR:
        return _result(evidence, OVERLAP_EXISTING_WORK)

    if evidence.overlap_verdict == OVERLAP_NEEDS_REFRESH:
        return _result(evidence, NEEDS_REFRESH)

    if evidence.overlap_verdict != READY:
        return _result(evidence, NEEDS_REFRESH)

    if evidence.grantfox_candidate_verified is not True or evidence.provider_state_observed is not True:
        return _result(evidence, NEEDS_REFRESH)

    application_state = _normalized(evidence.application_state)
    assignment_state = _normalized(evidence.assignment_state)
    if application_state not in _VALID_APPLICATION_STATES:
        return _result(evidence, NEEDS_REFRESH)
    if assignment_state not in _VALID_ASSIGNMENT_STATES:
        return _result(evidence, NEEDS_REFRESH)

    if application_state in {"rejected", "withdrawn", "ineligible"}:
        if assignment_state != "unassigned":
            return _result(evidence, NEEDS_REFRESH)
        return _result(evidence, RESEARCH_ONLY)

    if application_state == "not_submitted":
        if assignment_state != "unassigned":
            return _result(evidence, NEEDS_REFRESH)
        return _result(evidence, APPLICATION_REQUIRED)

    if assignment_state == "assigned_current_contributor":
        return _result(evidence, IMPLEMENTATION_READY)
    if assignment_state == "assigned_other":
        return _result(evidence, PROVIDER_ASSIGNED_OTHER)

    return _result(evidence, WAIT_PROVIDER_ASSIGNMENT)


def _normalized(value: str | None) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _result(evidence: GrantFoxExecutionEvidence, verdict: str) -> dict:
    return {
        "repository": evidence.repository,
        "issue_number": evidence.issue_number,
        "verdict": verdict,
        "research_allowed": verdict != CLOSED_OR_SATISFIED,
        "application_allowed": verdict == APPLICATION_REQUIRED,
        "implementation_allowed": verdict == IMPLEMENTATION_READY,
    }
