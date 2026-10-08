"""Read-only, request-budgeted audit of waiver language in original-author bounty submissions."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

SCHEMA = "commons.bounty_claim_waiver_audit/v1"
SNAPSHOT_SCHEMA = "commons.bounty_claim_waiver_snapshot/v1"
PATTERNS = (
    ("REWARD_DISCLAIMER", re.compile(r"\b(?:I\s+am|we\s+are)\s+not\s+claiming\s+(?:any\s+)?(?:reward|bounty|payment)\b", re.I)),
    ("NOT_A_CLAIM", re.compile(r"\b(?:this|it)\s+is\s+not\s+(?:a\s+)?(?:bounty\s+)?claim\b", re.I)),
    ("CLAIM_WAIVER", re.compile(r"\b(?:no\s+(?:bounty|payment|reward)\s+claim|not\s+(?:claiming|requesting|seeking)\s+(?:any\s+|a\s+|the\s+)?(?:bounty|reward|payment))\b", re.I)),
    ("PAYMENT_WAIVER", re.compile(r"\b(?:no|without)\s+(?:payment|reward)\s+expected\b", re.I)),
)
ISSUE_URL = re.compile(r"^https://github\.com/([A-Za-z\d_.-]+)/([A-Za-z\d_.-]+)/(issues|pull)/(\d+)(?:#issuecomment-(\d+))?$")

class ScanError(Exception):
    pass


def positive_number(raw: str) -> int:
    try:
        number = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


def record_from_api(kind: str, item: dict, issue: int) -> dict:
    if not isinstance(item, dict):
        raise ScanError("provider record must be an object")
    author = item.get("user") or {}
    if not isinstance(author, dict):
        author = {}
    url = item.get("html_url")
    body = item.get("body")
    if not isinstance(url, str) or not isinstance(body, str):
        raise ScanError("provider record missing URL or text body")
    login = author.get("login")
    if not isinstance(login, str):
        raise ScanError("provider record has no author identity")
    return {"kind": kind, "issue_or_pr": issue, "author": login, "url": url, "body": body}


def provider_page(url: str, state: dict, token: str | None) -> tuple[object, str | None]:
    if state["requests"] >= state["max_requests"]:
        raise ScanError("request budget exhausted; unvisited pages remain")
    state["requests"] += 1
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "commons-bounty-waiver-audit", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with urlopen(Request(url, headers=headers), timeout=12) as response:
            payload = json.load(response)
            link = response.headers.get("Link", "")
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining is not None and remaining.isdecimal() and int(remaining) <= 1:
                state["low_quota"] = True
    except HTTPError as exc:
        if exc.code in (403, 429):
            raise ScanError("provider limited the request (HTTP %d); remaining coverage unknown" % exc.code) from exc
        raise ScanError("GitHub HTTP %d; remaining coverage unknown" % exc.code) from exc
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        raise ScanError("GitHub read failed (%s); remaining coverage unknown" % type(exc).__name__) from exc
    next_url = None
    for component in link.split(","):
        if 'rel="next"' in component:
            next_url = component.partition("<")[2].partition(">")[0]
            if not next_url.startswith("https://api.github.com/repos/"):
                raise ScanError("unexpected pagination target")
    return payload, next_url


def online_sources(repo: str, issues: list[int], prs: list[int], state: dict, token: str | None):
    root = "https://api.github.com/repos/" + "/".join(quote(part, safe="") for part in repo.split("/"))
    for number in issues:
        url = f"{root}/issues/{number}/comments?per_page=100"
        while url:
            data, next_url = provider_page(url, state, token)
            if not isinstance(data, list):
                raise ScanError("issue comments response was not an array")
            for item in data:
                yield record_from_api("issue_comment", item, number)
            if state["low_quota"] and next_url:
                raise ScanError("GitHub read quota nearly exhausted; pagination incomplete")
            url = next_url
    for number in prs:
        data, _ = provider_page(f"{root}/pulls/{number}", state, token)
        yield record_from_api("pull_request", data, number)


def snapshot_sources(path: str, repo: str):
    try:
        with open(path, "r", encoding="utf-8") as stream:
            snapshot = json.load(stream)
    except (OSError, ValueError) as exc:
        raise ScanError("snapshot cannot be read: " + type(exc).__name__) from exc
    if not isinstance(snapshot, dict) or snapshot.get("schema") != SNAPSHOT_SCHEMA or snapshot.get("repository") != repo:
        raise ScanError("snapshot schema/repository does not match")
    if snapshot.get("complete") is not True:
        raise ScanError("snapshot does not attest complete source coverage")
    rows = snapshot.get("records")
    if not isinstance(rows, list):
        raise ScanError("snapshot records must be an array")
    for row in rows:
        if not isinstance(row, dict) or row.get("kind") not in ("issue_comment", "pull_request"):
            raise ScanError("snapshot record kind invalid")
        if type(row.get("issue_or_pr")) is not int or row["issue_or_pr"] < 1:
            raise ScanError("snapshot record issue/pr invalid")
        if not isinstance(row.get("url"), str) or not isinstance(row.get("body"), str) or not isinstance(row.get("author"), str):
            raise ScanError("snapshot record fields incomplete")
        yield row


def scan(rows, *, owner: str, repo: str) -> dict:
    findings = []
    checked = 0
    ignored = 0
    seen = set()
    for row in rows:
        url = row["url"].split("?", 1)[0].rstrip("/")
        match = ISSUE_URL.fullmatch(url)
        if not match or f"{match[1]}/{match[2]}".casefold() != repo.casefold():
            raise ScanError("record URL does not belong to requested GitHub repository")
        if (row["kind"] == "pull_request" and match[3] != "pull") or (row["kind"] == "issue_comment" and (match[3] != "issues" or not match[5])):
            raise ScanError("record kind and URL disagree")
        if int(match[4]) != row["issue_or_pr"]:
            raise ScanError("record issue/PR number and URL disagree")
        key = (row["kind"], url)
        if key in seen:
            raise ScanError("duplicate provider record URL")
        seen.add(key)
        if row["author"].casefold() != owner.casefold():
            ignored += 1
            continue
        checked += 1
        hits = []
        for kind, pattern in PATTERNS:
            for found in pattern.finditer(row["body"]):
                excerpt = row["body"][max(0, found.start() - 55):min(len(row["body"]), found.end() + 55)].replace("\n", " ")
                hits.append({"reason": kind, "matched_text": found.group(0), "excerpt": excerpt})
        if hits:
            findings.append({"kind": row["kind"], "url": url, "issue_or_pr": row["issue_or_pr"], "author": row["author"], "action": "REVIEW_AND_EDIT_EXISTING_ORIGINAL", "matches": hits})
    return {"checked_owned": checked, "skipped_other_authors": ignored, "findings": findings}


def markdown(report: dict) -> str:
    lines = [f"# Bounty claim waiver audit: {report['repository']}", "", f"Owned account: `{report['owner']}`; source coverage: **{report['coverage']}**; requests: {report['requests_used']}.", f"Scanned owned messages: {report['checked_owned']}; flags: {len(report['findings'])}; other authors preserved: {report['skipped_other_authors']}.", ""]
    if report["error"]:
        lines += ["**Coverage incomplete:** " + report["error"], "Do not interpret missing findings as clearance.", ""]
    for hit in report["findings"]:
        lines += [f"- **Review original {hit['kind']}** [#{hit['issue_or_pr']}]({hit['url']}) (author `{hit['author']}`): {', '.join(sorted({m['reason'] for m in hit['matches']}))}. Correct the existing original item under the same identity; preserve contribution and payment claim."]
    if not report["findings"] and report["coverage"] == "COMPLETE":
        lines.append("No matching waiver expressions in the fully scanned owned records. This does not establish portal registration or payment.")
    lines += ["", "Read-only: no claim, comment, PR, provider-registration, award, or payment mutation occurred. This audit never forfeits a claim."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="GitHub owner/repository")
    parser.add_argument("--owner", default="woahwhattheheck", help="Original owner account to audit")
    parser.add_argument("--issue", action="append", type=positive_number, default=[], help="Issue whose comments to read (repeatable)")
    parser.add_argument("--pr", action="append", type=positive_number, default=[], help="Pull request body to read (repeatable)")
    parser.add_argument("--snapshot", help="Offline fully-captured first-party provider records in JSON")
    parser.add_argument("--max-requests", type=positive_number, default=12, help="Hard cap on GitHub GETs (default 12)")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", help="Create-exclusive report path; default stdout")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo, re.ASCII) or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", args.owner):
        parser.error("invalid GitHub repository/owner")
    if (args.snapshot is None) == (not (args.issue or args.pr)):
        parser.error("supply either --snapshot or at least one --issue/--pr")
    if len(set(args.issue)) != len(args.issue) or len(set(args.pr)) != len(args.pr):
        parser.error("duplicate issue or PR number")
    state = {"max_requests": args.max_requests, "requests": 0, "low_quota": False}
    report = {"schema": SCHEMA, "repository": args.repo, "owner": args.owner, "coverage": "INCOMPLETE", "requests_used": 0, "checked_owned": 0, "skipped_other_authors": 0, "findings": [], "error": None, "payment_status": "NOT_VERIFIED_IN_THIS_RUN"}
    try:
        rows = snapshot_sources(args.snapshot, args.repo) if args.snapshot else online_sources(args.repo, args.issue, args.pr, state, os.getenv("GITHUB_TOKEN"))
        values = scan(rows, owner=args.owner, repo=args.repo)
        report.update(values)
        report["coverage"] = "COMPLETE"
    except ScanError as exc:
        report["error"] = str(exc)
    report["requests_used"] = state["requests"]
    output = markdown(report) if args.format == "markdown" else json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    try:
        if args.output:
            with open(args.output, "x", encoding="utf-8") as destination:
                destination.write(output)
        else:
            sys.stdout.write(output)
    except OSError as exc:
        print("report output failed: " + str(exc), file=sys.stderr)
        return 2
    return 2 if report["coverage"] != "COMPLETE" else (1 if report["findings"] else 0)


if __name__ == "__main__":
    sys.exit(main())
