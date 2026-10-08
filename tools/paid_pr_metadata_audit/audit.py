#!/usr/bin/env python3
"""Offline audit of original-author paid PR metadata; never publishes or claims."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "commons.paid_pr_metadata_audit.v1"
REPORT_SCHEMA = "commons.paid_pr_metadata_report.v1"
ISSUE_PATH = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([1-9]\d*)/?$")
PR_PATH = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/([1-9]\d*)/?$")
ISSUE_MENTION = re.compile(
    r"\b(?:closes?|closed|fix(?:es|ed)?|resolves?|refs?|references?|related(?:\s+to)?|issue|for)"
    r"\s*(?:issue\s*)?:?\s*"
    r"(?:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))?"
    r"#(?P<number>[1-9]\d*)\b",
    re.I,
)
ISSUE_URL_MENTION = re.compile(
    r"https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/issues/(?P<number>[1-9]\d*)\b",
    re.I,
)
LOGIN = re.compile(r"^[A-Za-z\d](?:[A-Za-z\d-]{0,37}[A-Za-z\d])?$")
SHA = re.compile(r"^[a-fA-F\d]{40}$")
PLATFORMS = {"grantfox", "algora", "bountyhub", "issuehunt", "proven_payer"}
STATES = {"open", "closed"}
AFFIRMATIVE = (
    re.compile(r"\b(?:i|we)\s+(?:hereby\s+)?(?:request|seek|claim|apply\s+for)\b.{0,140}\b(?:compensation|bounty|reward|payment|payout)\b", re.I | re.S),
    re.compile(r"\b(?:compensation|bounty|reward|payment|payout)\s+(?:is\s+)?(?:requested|sought|claimed)\b", re.I),
)
WAIVER = (
    re.compile(r"\b(?:i|we)\s+(?:am|are)\s+not\s+(?:claiming|requesting|seeking)\s+(?:any\s+)?(?:bounty|reward|compensation|payment)\b", re.I),
    re.compile(r"\b(?:waiv(?:e|ing)|forfeit(?:ing)?)\b.{0,90}\b(?:reward|compensation|bounty|payment|payout)\b", re.I | re.S),
)


class AuditError(ValueError):
    pass


def time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise AuditError(f"{label} must be an offset-aware ISO timestamp")
    try:
        out = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditError(f"invalid {label}") from exc
    if out.tzinfo is None or out.utcoffset() is None:
        raise AuditError(f"{label} must be timezone-aware")
    return out.astimezone(timezone.utc)


def github_url(value: object, kind: str) -> tuple[str, str, int, str]:
    if not isinstance(value, str):
        raise AuditError(f"{kind} URL must be text")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.hostname != "github.com" or
        parsed.port is not None or parsed.username or parsed.password or
        parsed.query or parsed.fragment):
        raise AuditError(f"{kind} must be a canonical HTTPS GitHub URL")
    match = (ISSUE_PATH if kind == "issue" else PR_PATH).fullmatch(parsed.path)
    if not match:
        raise AuditError(f"invalid {kind} URL")
    owner, repo, number = match.groups()
    path = "issues" if kind == "issue" else "pull"
    return owner.lower(), repo.lower(), int(number), f"https://github.com/{owner.lower()}/{repo.lower()}/{path}/{int(number)}"


def prose(body: str) -> str:
    """Ignore quoted examples and fenced code when looking for claim language."""
    kept, fenced = [], False
    for line in body.splitlines():
        if line.lstrip().startswith("```") or line.lstrip().startswith("~~~"):
            fenced = not fenced
            continue
        if not fenced and not line.lstrip().startswith(">"):
            kept.append(line)
    return "\n".join(kept)


def sponsor_issue_link(body: str, owner: str, repo: str, number: int) -> bool:
    """Find explicit, same-repository issue refs without requiring auto-close.

    A different-repository #number is not proof of this sponsor's issue.
    """
    repository = f"{owner}/{repo}".lower()
    for match in ISSUE_MENTION.finditer(body):
        qualifier = match.group("repo")
        if int(match.group("number")) == number and (
            qualifier is None or qualifier.lower() == repository
        ):
            return True
    for match in ISSUE_URL_MENTION.finditer(body):
        if (int(match.group("number")) == number and
            f"{match.group('owner')}/{match.group('repo')}".lower() == repository):
            return True
    return False


def claim_in_comments(comments: list[dict], actor: str, number: int) -> bool:
    rx = re.compile(r"(?<!\S)/claim\s*#" + str(number) + r"\b", re.I)
    return any(isinstance(x, dict) and str(x.get("author", "")).lower() == actor
               and isinstance(x.get("body"), str) and rx.search(prose(x["body"]))
               for x in comments)


def audit(data: dict, *, now: datetime, ttl_hours: float = 6) -> dict:
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise AuditError(f"expected schema {SCHEMA}")
    if not (isinstance(ttl_hours, (int, float)) and not isinstance(ttl_hours, bool)
            and 0 < ttl_hours <= 168):
        raise AuditError("ttl_hours must be between 0 and 168")
    actor = data.get("actor")
    if not isinstance(actor, str) or not LOGIN.fullmatch(actor):
        raise AuditError("actor must be a valid GitHub login")
    actor = actor.lower()
    records = data.get("records")
    if not isinstance(records, list) or len(records) > 5000:
        raise AuditError("records must be an array of <=5000 rows")
    checked = time(data.get("as_of"), "as_of")
    if not timedelta(minutes=-5) <= now - checked <= timedelta(hours=ttl_hours):
        raise AuditError("as_of snapshot is stale or future-dated")
    seen, output = set(), []
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            raise AuditError(f"record {index} must be an object")
        owner, repo, issue_no, issue_url = github_url(row.get("issue_url"), "issue")
        po, pr, pr_no, pr_url = github_url(row.get("pr_url"), "pull")
        if (owner, repo) != (po, pr):
            raise AuditError("PR must be the sponsor-repository PR, not a fork carrier")
        if pr_url in seen:
            raise AuditError("duplicate sponsor PR in audit snapshot")
        seen.add(pr_url)
        provider = row.get("platform")
        if provider not in PLATFORMS:
            raise AuditError("invalid platform")
        author = row.get("pr_author")
        if not isinstance(author, str) or not LOGIN.fullmatch(author):
            raise AuditError("invalid pr_author")
        if row.get("pr_state") not in STATES or row.get("issue_state") not in STATES:
            raise AuditError("invalid issue/pr state")
        head = row.get("pr_head_sha")
        if head is not None and (not isinstance(head, str) or not SHA.fullmatch(head)):
            raise AuditError("pr_head_sha must be a 40-character Git SHA")
        body = row.get("pr_body")
        if not isinstance(body, str):
            raise AuditError("pr_body must be complete text")
        labels, comments = row.get("issue_labels"), row.get("issue_comments")
        if not isinstance(labels, list) or any(not isinstance(x, str) for x in labels):
            raise AuditError("issue_labels must be an array of strings")
        if not isinstance(comments, list) or any(not isinstance(c, dict) or
             not isinstance(c.get("author"), str) or not isinstance(c.get("body"), str)
             for c in comments):
            raise AuditError("issue_comments must be full author/body records")
        complete = row.get("comments_complete")
        if not isinstance(complete, bool):
            raise AuditError("comments_complete must be boolean")
        checked_at = time(row.get("checked_at"), "checked_at")
        fresh = timedelta(minutes=-5) <= now - checked_at <= timedelta(hours=ttl_hours)
        context = prose(body)
        owned = author.lower() == actor
        issue_claim = claim_in_comments(comments, actor, issue_no) if complete else None
        affirmative = any(pattern.search(context) for pattern in AFFIRMATIVE)
        waiver = any(pattern.search(context) for pattern in WAIVER)
        issue_link = sponsor_issue_link(context, owner, repo, issue_no)
        campaign = (provider != "grantfox" or
                    {"grantfox oss", "maybe rewarded"}.issubset({v.lower() for v in labels}))
        findings = []
        if not issue_link:
            findings.append("SPONSOR_ISSUE_LINK_NOT_FOUND")
        if not affirmative:
            findings.append("PR_COMPENSATION_REQUEST_NOT_FOUND")
        if waiver:
            findings.append("PR_WAIVER_LANGUAGE_REVIEW")
        if issue_claim is False:
            findings.append("ISSUE_CLAIM_NOT_FOUND")
        if issue_claim is None:
            findings.append("ISSUE_COMMENT_CENSUS_INCOMPLETE")
        if not campaign:
            findings.append("PROGRAM_LABEL_EVIDENCE_MISSING")
        if not fresh:
            decision = "HOLD_STALE_EVIDENCE"
        elif not owned:
            decision = "PRESERVE_FOREIGN_AUTHOR"
        elif not campaign:
            decision = "HOLD_PROVIDER_ELIGIBILITY"
        elif not complete:
            decision = "HOLD_INCOMPLETE_CLAIM_CENSUS"
        elif findings:
            decision = "MANUAL_METADATA_REVIEW"
        else:
            decision = "NO_METADATA_GAP_DETECTED"
        output.append({
            "operation_id": f"PAID-PR-META:{owner}/{repo}#{pr_no}",
            "issue_url": issue_url, "pr_url": pr_url,
            "pr_author": author.lower(), "pr_head_sha": head,
            "platform": provider, "issue_state": row["issue_state"],
            "pr_state": row["pr_state"], "checked_at": checked_at.isoformat(),
            "decision": decision, "findings": sorted(findings),
            "existing_issue_claim_by_actor": issue_claim,
            "affirmative_request_detected": bool(affirmative),
            "waiver_language_detected": bool(waiver),
            "original_author_matches_actor": owned,
        })
    output.sort(key=lambda row: (row["decision"], row["operation_id"]))
    return {
        "schema": REPORT_SCHEMA, "actor": actor,
        "as_of": checked.isoformat(), "generated_at": now.isoformat(),
        "summary": dict(sorted(Counter(r["decision"] for r in output).items())),
        "records": output,
        "disclaimer": "Lexical manual-review candidates only. No award, eligibility, payment, accepted claim or provider write is inferred."
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="fresh, complete first-party issue/PR metadata snapshot")
    parser.add_argument("--output", type=Path, help="optional JSON output file")
    parser.add_argument("--as-of", help="fixed offset-aware time for reproducible audit")
    parser.add_argument("--ttl-hours", type=float, default=6)
    args = parser.parse_args(argv)
    try:
        now = time(args.as_of, "--as-of") if args.as_of else datetime.now(timezone.utc)
        report = audit(json.loads(args.snapshot.read_text(encoding="utf-8")),
                       now=now, ttl_hours=args.ttl_hours)
        content = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if args.output:
            args.output.write_text(content, encoding="utf-8")
        else:
            sys.stdout.write(content)
        return 0
    except (AuditError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"paid PR metadata audit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())