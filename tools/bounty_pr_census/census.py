#!/usr/bin/env python3
"""Conservative, offline, one-census check for issue-linked sponsor PR collisions.

Only consumes page-complete captured first-party GitHub REST pull-list JSON.
It NEVER claims that missing issue tags prove a bounty has no incumbent.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

MAX_SNAPSHOT_AGE = timedelta(minutes=15)
MAX_FUTURE_SKEW = timedelta(minutes=1)

# Match explicit closing/issue references and issue-key suffixes, not every #N
# (a PR may legitimately mention tests, changelogs, and unrelated PR numbers).
ACTION = re.compile(
    r"\b(?:closes?|closed|fix(?:es|ed)?|resolves?|resolved|addresses?|addressed|"
    r"implements?|implemented|for|issue)\s*(?:issue\s*)?:?\s*"
    r"(?:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))?"
    r"#(?P<number>[0-9]{1,8})\b", re.I,
)
TITLE_SUFFIX = re.compile(r"\(#([0-9]{1,8})\)\s*$")
ISSUE_URL = re.compile(
    r"https://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/"
    r"(?P<number>[0-9]{1,8})\b", re.I,
)


class IncompleteSnapshot(ValueError):
    """Fail closed if the supplier cannot demonstrate a complete fresh census."""


def _timestamp(raw: Any) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise IncompleteSnapshot("captured_at must be an offset-aware ISO timestamp")
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IncompleteSnapshot("invalid captured_at timestamp") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise IncompleteSnapshot("captured_at must include a timezone")
    return stamp.astimezone(timezone.utc)


def _references(title: str, body: str, repository: str) -> set[int]:
    refs: set[int] = set()
    target = repository.lower()
    for text in (title, body):
        for match in ACTION.finditer(text):
            qualifier = match.group("repo")
            if qualifier is None or qualifier.lower() == target:
                refs.add(int(match.group("number")))
        for match in ISSUE_URL.finditer(text):
            if match.group("repo").lower() == target:
                refs.add(int(match.group("number")))
    suffix = TITLE_SUFFIX.search(title)
    if suffix:
        refs.add(int(suffix.group(1)))
    return refs


def _records(snapshot: dict[str, Any], repository: str, now: datetime) -> tuple[list[dict[str, Any]], datetime]:
    if snapshot.get("repository", "").lower() != repository.lower():
        raise IncompleteSnapshot("snapshot repository mismatch")
    # This is a declaration by the collector, not authentication performed by
    # this offline tool. Verify the original collector's provider receipt.
    if snapshot.get("source") != "github-rest-pulls-authenticated":
        raise IncompleteSnapshot("missing authenticated-provider source declaration")
    captured = _timestamp(snapshot.get("captured_at"))
    if now - captured > MAX_SNAPSHOT_AGE or captured - now > MAX_FUTURE_SKEW:
        raise IncompleteSnapshot("stale or future-dated snapshot")
    size = snapshot.get("page_size")
    if type(size) is not int or not (1 <= size <= 100):
        raise IncompleteSnapshot("page_size must be an integer between 1 and 100")
    pages = snapshot.get("pages")
    if not isinstance(pages, list) or not pages:
        raise IncompleteSnapshot("missing numbered PR pages")
    rows: list[dict[str, Any]] = []
    seen_numbers: set[int] = set()
    for i, page in enumerate(pages, 1):
        if not isinstance(page, dict) or page.get("page") != i:
            raise IncompleteSnapshot("missing or out-of-order page")
        prs = page.get("pull_requests")
        if not isinstance(prs, list) or len(prs) > size:
            raise IncompleteSnapshot("invalid PR page size")
        if i != len(pages) and len(prs) != size:
            raise IncompleteSnapshot("partial nonfinal page: pagination incomplete")
        # Exactly full final page requires a subsequent empty last page,
        # otherwise more open PRs may have been silently omitted.
        if i == len(pages) and len(prs) == size:
            raise IncompleteSnapshot("full final page: collect next page to prove exhaustion")
        for pr in prs:
            if not isinstance(pr, dict) or pr.get("state") != "open":
                raise IncompleteSnapshot("non-open or malformed PR in open-only census")
            number = pr.get("number")
            if type(number) is not int or number < 1 or number in seen_numbers:
                raise IncompleteSnapshot("missing, repeated or invalid PR number")
            seen_numbers.add(number)
            if not isinstance(pr.get("title"), str):
                raise IncompleteSnapshot("PR title missing")
            # GitHub returns body:null legitimately; cannot assume that means
            # no issue reference. We report such PRs for manual review.
            rows.append(pr)
    return rows, captured


def evaluate(snapshot: dict[str, Any], repository: str, issue_number: int,
             now: datetime | None = None) -> dict[str, Any]:
    if not repository or "/" not in repository or issue_number < 1:
        raise ValueError("use owner/repository and positive issue number")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    rows, captured = _records(snapshot, repository, current)
    matches: list[dict[str, Any]] = []
    review: list[int] = []
    for pr in rows:
        body = pr.get("body")
        title = pr["title"]
        refs = _references(title, body if isinstance(body, str) else "", repository)
        if issue_number in refs:
            user = pr.get("user") or {}
            head = pr.get("head") or {}
            author = user.get("login") if isinstance(user, dict) else None
            sha = head.get("sha") if isinstance(head, dict) else pr.get("head_sha")
            url = pr.get("html_url") or pr.get("url")
            matches.append({
                "number": pr["number"], "url": url,
                "author": author, "head_sha": sha, "title": title,
            })
        if not refs or not isinstance(body, str):
            review.append(pr["number"])
    matches.sort(key=lambda x: x["number"])
    status = ("HOLD_COLLISION" if len(matches) > 1
              else "HOLD_EXISTING" if matches else "REVIEW_NO_MATCH")
    return {
        "repository": repository, "issue": issue_number,
        "status": status,
        "captured_at": captured.isoformat(),
        "open_prs_checked": len(rows),
        "incumbents": matches,
        "unmapped_pr_count": len(review),
        "unmapped_pr_numbers": review[:25],
        "next_action": (
            "Preserve incumbents; reconcile original author, branch/head and payout. Do not create another issue-key PR."
            if matches else
            "No explicit issue-key carrier seen. Manually review unmapped PRs, merged PRs and sponsor main source before any TAKE or submission."
        ),
        "provenance_warning": (
            "Collector's authenticated-source declaration is not cryptographically verified by this offline reader."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="captured paginated GitHub /pulls snapshot JSON")
    parser.add_argument("--repo", required=True, help="case-insensitive owner/repository")
    parser.add_argument("--issue", required=True, type=int, help="sponsor issue number")
    args = parser.parse_args(argv)
    try:
        snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
        report = evaluate(snapshot, args.repo, args.issue)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "HOLD_INCOMPLETE", "error": str(exc)}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    # A no-match still needs human/source review: NEVER signal automatic GO.
    return 3 if report["status"].startswith("HOLD") else 4


if __name__ == "__main__":
    sys.exit(main())
