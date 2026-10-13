#!/usr/bin/env python3
"""Offline, evidence-conservative marketplace claim-roster reconciliation.

Input is a manually verified snapshot. This tool never calls an API, submits a
claim, changes a PR, or infers payment from an advertised bounty amount.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+$")
REJECTED = {"rejected", "withdrawn", "cancelled", "canceled", "invalid"}


def canonical_pr(value: object) -> str | None:
    """Accept only canonical, numeric GitHub upstream pull-request URLs."""
    if not isinstance(value, str) or not value:
        return None
    parsed = urlsplit(value)
    parts = parsed.path.strip("/").split("/")
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"github.com", "www.github.com"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or len(parts) != 4
        or parts[2] != "pull"
        or not LOGIN.fullmatch(parts[0])
        or not REPO.fullmatch(parts[1])
        or not parts[3].isdigit()
        or int(parts[3]) < 1
    ):
        return None
    return f"https://github.com/{parts[0].lower()}/{parts[1].lower()}/pull/{int(parts[3])}"


def listing_key(provider: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("listing_url is required")
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    allowed = {"bountyhub": {"bountyhub.dev", "www.bountyhub.dev"},
               "algora": {"algora.io", "www.algora.io"}}[provider]
    if parsed.scheme != "https" or host not in allowed or not parsed.path.strip("/"):
        raise ValueError(f"Invalid {provider} listing_url")
    return f"{provider}:{host.removeprefix('www.')}{parsed.path.rstrip('/')}"


def review(item: dict) -> dict:
    provider = item.get("provider")
    if provider not in ("bountyhub", "algora"):
        raise ValueError("provider must be bountyhub or algora")
    key = listing_key(provider, item.get("listing_url"))
    login = item.get("expected_login")
    if not isinstance(login, str) or not LOGIN.fullmatch(login):
        raise ValueError("expected_login must be a valid GitHub login")
    if type(item.get("roster_complete")) is not bool:
        raise ValueError("roster_complete must be a verified boolean")
    if not isinstance(item.get("claims"), list):
        raise ValueError("claims must be a list of provider-visible claim records")
    if not isinstance(item.get("checked_at"), str) or not item["checked_at"].strip():
        raise ValueError("checked_at must be supplied by the snapshot collector")

    pr = canonical_pr(item.get("source_pr_url"))
    author = item.get("source_pr_author")
    if author is not None and (not isinstance(author, str) or not LOGIN.fullmatch(author)):
        raise ValueError("source_pr_author must be a valid GitHub login")
    same_login = lambda name: isinstance(name, str) and name.casefold() == login.casefold()
    own = []
    other = []
    for claim in item["claims"]:
        if not isinstance(claim, dict) or not isinstance(claim.get("claimant"), str):
            raise ValueError("each claim requires a claimant")
        matched_pr = canonical_pr(claim.get("pr_url"))
        if same_login(claim["claimant"]):
            own.append((matched_pr, str(claim.get("status") or "unknown").lower()))
        elif pr is not None and matched_pr == pr:
            other.append(claim["claimant"])

    if not pr:
        status, action = "PR_UNVERIFIED", "PUBLISH_OR_VERIFY_UPSTREAM_PR"
    elif not isinstance(author, str) or not same_login(author):
        status, action = "AUTHOR_UNVERIFIED_OR_MISMATCHED", "VERIFY_ORIGINAL_PR_AUTHOR"
    elif any(p == pr and state not in REJECTED for p, state in own):
        status, action = "EXACT_CLAIM_VISIBLE", "PRESERVE_AND_CHECK_PROVIDER_STATUS"
    elif any(p == pr and state in REJECTED for p, state in own):
        status, action = "REJECTED_OR_WITHDRAWN_CLAIM_VISIBLE", "REVIEW_EXISTING_PROVIDER_DECISION"
    elif own:
        status, action = "CLAIMANT_VISIBLE_PR_UNVERIFIED", "INSPECT_OWN_PROVIDER_CLAIMS"
    elif other:
        status, action = "PR_ASSOCIATED_WITH_OTHER_ACCOUNT", "ESCALATE_CLAIM_IDENTITY_CONFLICT"
    elif item["roster_complete"]:
        status, action = "ABSENT_FROM_COMPLETE_ROSTER", "CHECK_ELIGIBILITY_THEN_REGISTER_PR"
    else:
        status, action = "ROSTER_INCOMPLETE", "REFRESH_COMPLETE_PROVIDER_ROSTER"

    # A portal record never establishes a payout, and owner-submission eligibility
    # cannot be established solely from a public GitHub PR.
    if item.get("manual_contribution_required") is True and action == "CHECK_ELIGIBILITY_THEN_REGISTER_PR":
        action = "HUMAN_CONTRIBUTION_ELIGIBILITY_REVIEW"
    return {
        "listing_key": key, "checked_at": item["checked_at"],
        "source_pr": pr, "expected_login": login,
        "roster_complete": item["roster_complete"],
        "status": status, "next_action": action,
        "payment_status": "NOT_EVALUATED",
    }


def audit(snapshot: dict) -> dict:
    entries = snapshot.get("listings")
    if not isinstance(entries, list):
        raise ValueError("top-level listings must be a list")
    seen = set()
    results = []
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("each listing must be an object")
        result = review(item)
        if result["listing_key"] in seen:
            raise ValueError(f"Duplicate marketplace listing: {result['listing_key']}")
        seen.add(result["listing_key"])
        results.append(result)
    results.sort(key=lambda row: row["listing_key"])
    return {"count": len(results), "statuses": dict(sorted(Counter(r["status"] for r in results).items())), "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="JSON with a top-level listings array")
    args = parser.parse_args(argv)
    try:
        result = audit(json.loads(args.snapshot.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as exc:
        print(f"claim-roster: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
