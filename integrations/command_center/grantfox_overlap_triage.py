"""Classify bounty issue snapshots so concurrent builders can avoid duplicate work."""

from __future__ import annotations

import re
from dataclasses import dataclass

READY = "READY"
OVERLAP_OPEN_PR = "OVERLAP_OPEN_PR"
SATISFIED_DEFAULT_BRANCH = "SATISFIED_DEFAULT_BRANCH"
ISSUE_CLOSED = "ISSUE_CLOSED"
NEEDS_REFRESH = "NEEDS_REFRESH"

_CLOSING_REF = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*#(?P<number>\d+)\b"
)
_ISSUE_URL = re.compile(
    r"https?://(?:github\.com/|api\.github\.com/repos/)"
    r"(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/"
    r"(?P<number>\d+)(?=$|[/?#\s<>\[\]()\"'`.,;:!])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PullRequestEvidence:
    number: int
    state: str
    title: str = ""
    body: str = ""
    url: str = ""
    draft: bool = False
    merged: bool = False


@dataclass(frozen=True)
class CandidateEvidence:
    repository: str
    issue_number: int
    issue_state: str
    default_branch_sha: str | None = None
    default_branch_satisfied: bool | None = None
    pull_requests: tuple[PullRequestEvidence, ...] = ()


def _explicit_reference(pr: PullRequestEvidence, issue_number: int, repository: str) -> bool:
    text = f"{pr.title}\n{pr.body}\n{pr.url}"
    return any(int(m.group("number")) == issue_number for m in _CLOSING_REF.finditer(text)) or any(
        int(m.group("number")) == issue_number
        and m.group("repository").casefold() == repository.casefold()
        for m in _ISSUE_URL.finditer(text)
    )


def _normalized(value: str | None) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def classify(candidate: CandidateEvidence) -> dict:
    issue_state = _normalized(candidate.issue_state)
    if issue_state == "closed":
        return _result(candidate, ISSUE_CLOSED)
    if issue_state != "open":
        return _result(candidate, NEEDS_REFRESH)
    if candidate.default_branch_satisfied is True:
        return _result(candidate, SATISFIED_DEFAULT_BRANCH)

    overlaps = set()
    uncertain_overlap = False
    for pr in candidate.pull_requests:
        if pr.merged is True or not _explicit_reference(pr, candidate.issue_number, candidate.repository):
            continue
        state = _normalized(pr.state)
        if state == "open" and pr.merged is False:
            overlaps.add(pr.number)
        elif state != "closed":
            # A partial PR snapshot is not evidence that no competing work exists.
            uncertain_overlap = True
    if overlaps:
        return _result(candidate, OVERLAP_OPEN_PR, sorted(overlaps))
    if uncertain_overlap or candidate.default_branch_satisfied is not False:
        return _result(candidate, NEEDS_REFRESH)
    return _result(candidate, READY)


def _result(candidate: CandidateEvidence, verdict: str, overlaps=()) -> dict:
    return {
        "repository": candidate.repository,
        "issue_number": candidate.issue_number,
        "default_branch_sha": candidate.default_branch_sha,
        "verdict": verdict,
        "overlapping_prs": list(overlaps),
    }
