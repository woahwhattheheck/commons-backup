"""Offline incumbent-PR reference audit for GrantFox issue-comment snapshots.

This is a review gate, NOT a PR-state/award/claim detector. A linked PR might
be closed, stale, authored by somebody else, or unrelated to acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ISSUE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+$")
PR_LINK = re.compile(
    r"https://github\.com/([A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+)/pull/([1-9][0-9]*)",
    re.IGNORECASE,
)
PR_NUMBER = re.compile(r"\b(?:PR|pull request)\s*#\s*([1-9][0-9]*)\b", re.IGNORECASE)
MAX_ISSUES = 5000
MAX_COMMENTS_PER_ISSUE = 5000


def _load(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    if raw.lstrip().startswith("["):
        items = json.loads(raw)
    else:
        items = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if not isinstance(items, list) or len(items) > MAX_ISSUES:
        raise ValueError("expected JSON array or JSONL with at most 5000 issues")
    if not all(isinstance(row, dict) for row in items):
        raise ValueError("issue snapshots must be objects")
    return items


def _identity(row: dict[str, Any]) -> tuple[str, int]:
    repo = row.get("repository", row.get("repo"))
    number = row.get("number", row.get("issue_number"))
    if not isinstance(repo, str) or not ISSUE_KEY.fullmatch(repo):
        raise ValueError("issue requires canonical owner/repository")
    if type(number) is not int or number < 1:
        raise ValueError(f"{repo}: issue number must be positive integer")
    return repo, number


def _comment_ref(repo: str, number: int, comment: dict[str, Any]) -> dict[str, Any]:
    source_id = comment.get("id")
    source_id = source_id if type(source_id) is int and source_id > 0 else None
    author = comment.get("user")
    if isinstance(author, dict):
        author = author.get("login")
    if not isinstance(author, str):
        author = None
    return {
        "comment_id": source_id,
        "comment_url": (
            f"https://github.com/{repo}/issues/{number}#issuecomment-{source_id}"
            if source_id is not None else None
        ),
        "comment_author": author,
    }


def _links(repo: str, text: str) -> set[str]:
    """Only PRs in the same sponsor repository; never guess linked PR state."""
    links = {
        f"https://github.com/{repo}/pull/{int(match.group(2))}"
        for match in PR_LINK.finditer(text)
        if match.group(1).lower() == repo.lower()
    }
    links.update(
        f"https://github.com/{repo}/pull/{int(match.group(1))}"
        for match in PR_NUMBER.finditer(text)
    )
    return links


def audit_issues(records: list[dict[str, Any]]) -> dict[str, Any]:
    if len(records) > MAX_ISSUES:
        raise ValueError("too many issue snapshots")
    seen: set[str] = set()
    issues: list[dict[str, Any]] = []
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("issue snapshots must be objects")
        repo, number = _identity(row)
        identity = f"{repo.lower()}#{number}"
        if identity in seen:
            raise ValueError(f"duplicate sponsor issue: {identity}")
        seen.add(identity)
        supplied = "issue_comments" in row
        comments = row.get("issue_comments") if supplied else []
        if not isinstance(comments, list) or len(comments) > MAX_COMMENTS_PER_ISSUE:
            raise ValueError(f"{identity}: issue_comments must be a bounded list")
        refs: dict[str, list[dict[str, Any]]] = {}
        for comment in comments:
            if not isinstance(comment, dict) or not isinstance(comment.get("body"), str):
                raise ValueError(f"{identity}: comments require body text")
            receipt = _comment_ref(repo, number, comment)
            for url in _links(repo, comment["body"]):
                evidence = refs.setdefault(url, [])
                if receipt not in evidence:
                    evidence.append(receipt)
        pr_refs = [
            {
                "pr_url": url,
                "operation_id": "GFOX-PRREF-" + hashlib.sha256(
                    f"{identity}|{url.lower()}".encode("utf-8")
                ).hexdigest()[:16],
                "pr_open_verified": False,
                "sources": sorted(
                    refs[url],
                    key=lambda e: (e["comment_id"] or 0, e["comment_author"] or ""),
                ),
            }
            for url in sorted(refs)
        ]
        issues.append({
            "issue_key": f"{repo}#{number}",
            "issue_url": f"https://github.com/{repo}/issues/{number}",
            "comment_census_supplied": supplied,
            "comments_scanned": len(comments),
            "status": (
                "PR_REFERENCE_REVIEW" if pr_refs else
                "NO_PR_LINKS_IN_SUPPLIED_CENSUS" if supplied else
                "COMMENT_CENSUS_MISSING"
            ),
            "pr_references": pr_refs,
        })
    issues.sort(key=lambda i: i["issue_key"].lower())
    return {
        "schema_version": 1,
        "issue_count": len(issues),
        "reference_review_issues": sum(
            i["status"] == "PR_REFERENCE_REVIEW" for i in issues
        ),
        "missing_comment_censuses": sum(
            i["status"] == "COMMENT_CENSUS_MISSING" for i in issues
        ),
        "provider_queries_executed": 0,
        "claims_created": 0,
        "rewards_received_usd": None,
        "issues": issues,
    }


def render_slack(report: dict[str, Any], limit: int = 20) -> str:
    """Bound the display while preserving every issue in full JSON output."""
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be positive")
    lines = [
        "GRANTFOX PR REFERENCE AUDIT / OFFLINE",
        f"{report['issue_count']} issue snapshots; "
        f"{report['reference_review_issues']} with incumbent PR references; "
        f"{report['missing_comment_censuses']} missing comment censuses; "
        "0 provider API calls.",
    ]
    flagged = [
        issue for issue in report["issues"]
        if issue["status"] != "NO_PR_LINKS_IN_SUPPLIED_CENSUS"
    ]
    for issue in flagged[:limit]:
        urls = ", ".join(ref["pr_url"] for ref in issue["pr_references"])
        line = (
            f"{issue['status']} | {issue['issue_url']}"
            + (f" | {urls}" if urls else "")
        )
        if sum(map(len, lines)) + len(line) + len(lines) >= 4600:
            break
        lines.append(line)
    if len(flagged) > limit or len(lines) - 2 < min(len(flagged), limit):
        lines.append("More issue rows in JSON; do not infer unlisted rows are clear.")
    lines.append(
        "HOLD for original-PR author/state/issue acceptance readback before "
        "dispatching duplicate work. Comment references do NOT prove PR open, "
        "bounty entitlement, claim registration, or payment."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="verified issue JSON array/JSONL")
    parser.add_argument("--format", choices=("json", "slack"), default="slack")
    parser.add_argument("--max-issues", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        result = audit_issues(_load(args.input))
        print(
            json.dumps(result, indent=2, sort_keys=True)
            if args.format == "json" else
            render_slack(result, args.max_issues)
        )
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as error:
        print(f"INPUT_HOLD: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
