#!/usr/bin/env python3
"""Offline canonical-source fence for Algora issue bounties.

Reconciles retained first-party Algora listings with separately collected,
fresh GitHub issue and claim-PR evidence. It never fetches providers,
claims an opportunity, creates a PR, or equates advertised dollars to cash.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

SCHEMA = "commons.algora_canonical_intake.v1"
REPORT_SCHEMA = "commons.algora_canonical_intake_report.v1"
ISSUE_PATH = re.compile(r"^/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)/issues/([1-9][0-9]*)/?$")
PULL_PATH = re.compile(r"^/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)/pull/([1-9][0-9]*)/?$")
LISTING_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
PRUNE_REASONS = {"BOARD_NOT_OPEN", "CANONICAL_CLOSED", "CANONICAL_NOT_FOUND", "REPOSITORY_ARCHIVED"}


class IntakeError(ValueError):
    """Schema/provenance error: never silently make a build decision."""


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise IntakeError(f"{label} must be an offset-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntakeError(f"{label} invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IntakeError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _github_url(value: object, kind: str) -> str:
    if not isinstance(value, str):
        raise IntakeError(f"{kind} URL must be a string")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise IntakeError(f"{kind} URL must use https://github.com")
    if parsed.username or parsed.password or parsed.port:
        raise IntakeError(f"{kind} URL contains unexpected credentials or port")
    rx = ISSUE_PATH if kind == "issue" else PULL_PATH
    match = rx.fullmatch(parsed.path)
    if not match:
        raise IntakeError(f"invalid canonical GitHub {kind} URL: {value}")
    owner, repo, number = match.groups()
    segment = "issues" if kind == "issue" else "pull"
    return f"https://github.com/{owner.lower()}/{repo.lower()}/{segment}/{int(number)}"


def _amount(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise IntakeError("advertised_usd must be a decimal amount")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise IntakeError("advertised_usd invalid") from exc
    if not number.is_finite() or number < 0 or number.as_tuple().exponent < -2:
        raise IntakeError("advertised_usd must be a nonnegative amount in cents")
    return number


def _array(value: object, field: str) -> list:
    if not isinstance(value, list):
        raise IntakeError(f"{field} must be an array")
    return value


def _age_ok(timestamp: datetime, now: datetime, ttl: timedelta) -> bool:
    age = now - timestamp
    return -timedelta(minutes=5) <= age <= ttl


def reconcile(
    payload: dict,
    *,
    now: datetime,
    max_age_hours: float = 6.0,
    minimum_usd: Decimal = Decimal("15"),
) -> dict:
    """Return cautious, idempotent issue-level build candidates or hold reasons."""
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise IntakeError(f"input schema must be {SCHEMA}")
    if not 0 < max_age_hours <= 168:
        raise IntakeError("max_age_hours must be in (0, 168]")
    if minimum_usd < 0:
        raise IntakeError("minimum_usd must be nonnegative")
    if now.tzinfo is None or now.utcoffset() is None:
        raise IntakeError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    ttl = timedelta(hours=max_age_hours)

    source = payload.get("provider_source")
    if not isinstance(source, str):
        raise IntakeError("provider_source must be an Algora HTTPS URL")
    parsed = urlsplit(source)
    if parsed.scheme != "https" or parsed.hostname not in {
        "algora.io", "www.algora.io", "console.algora.io"
    } or parsed.username or parsed.password or parsed.port:
        raise IntakeError("provider_source must be an official Algora HTTPS URL")
    provider_checked = _timestamp(payload.get("provider_observed_at"), "provider_observed_at")
    provider_fresh = _age_ok(provider_checked, now, ttl)

    groups: dict[str, list[dict]] = defaultdict(list)
    seen_listings: set[str] = set()
    listings = _array(payload.get("listings"), "listings")
    for raw in listings:
        if not isinstance(raw, dict):
            raise IntakeError("every listing must be an object")
        listing_id = raw.get("listing_id")
        if not isinstance(listing_id, str) or not LISTING_ID.fullmatch(listing_id):
            raise IntakeError("listing_id must be a short stable token")
        if listing_id in seen_listings:
            raise IntakeError(f"duplicate Algora listing_id: {listing_id}")
        seen_listings.add(listing_id)
        issue = _github_url(raw.get("issue_url"), "issue")
        state = raw.get("board_state")
        if state not in ("open", "closed"):
            raise IntakeError(f"board_state must be open or closed: {listing_id}")
        claims = raw.get("board_claims")
        if claims is not None and (isinstance(claims, bool) or
                                   not isinstance(claims, int) or claims < 0):
            raise IntakeError(f"board_claims must be nonnegative integer or null: {listing_id}")
        groups[issue].append({
            "listing_id": listing_id,
            "advertised_usd": _amount(raw.get("advertised_usd")),
            "board_state": state,
            "board_claims": claims,
        })

    evidence: dict[str, dict] = {}
    for raw in _array(payload.get("github_issues"), "github_issues"):
        if not isinstance(raw, dict):
            raise IntakeError("each GitHub issue evidence must be an object")
        issue = _github_url(raw.get("issue_url"), "issue")
        if issue in evidence:
            raise IntakeError(f"duplicate GitHub evidence for {issue}")
        state = raw.get("state")
        if state not in ("open", "closed", "not_found"):
            raise IntakeError(f"GitHub state must be open, closed or not_found: {issue}")
        archived = raw.get("repository_archived")
        complete = raw.get("claim_scan_complete")
        if not isinstance(archived, bool) or not isinstance(complete, bool):
            raise IntakeError("repository_archived and claim_scan_complete must be booleans")
        assignees = _array(raw.get("assignees"), "assignees")
        if any(not isinstance(a, str) or not a.strip() for a in assignees):
            raise IntakeError("assignees must be usernames")
        prs = _array(raw.get("claim_pr_urls"), "claim_pr_urls")
        canonical_prs = sorted({_github_url(pr, "pull") for pr in prs})
        evidence[issue] = {
            "state": state,
            "repository_archived": archived,
            "claim_scan_complete": complete,
            "assignees": assignees,
            "claim_pr_urls": canonical_prs,
            "checked_at": _timestamp(raw.get("checked_at"), f"GitHub checked_at for {issue}"),
        }

    decisions = []
    work_orders = []
    for issue in sorted(groups):
        rows = sorted(groups[issue], key=lambda row: row["listing_id"])
        open_rows = [row for row in rows if row["board_state"] == "open"]
        proof = evidence.get(issue)
        reasons = []
        if not open_rows:
            reasons.append("BOARD_NOT_OPEN")
        if not provider_fresh:
            reasons.append("PROVIDER_SNAPSHOT_STALE")
        # Historical CLOSED listings remain visible in the audit ledger but
        # never decide eligibility, claims or price for an OPEN listing.
        if open_rows and all(row["advertised_usd"] < minimum_usd for row in open_rows):
            reasons.append("BELOW_MINIMUM_USD")
        if any(row["board_claims"] is None for row in open_rows):
            reasons.append("BOARD_CLAIMS_UNKNOWN")
        if any((row["board_claims"] or 0) > 0 for row in open_rows):
            reasons.append("BOARD_CLAIM_PRESENT")

        if proof is None:
            reasons.append("GITHUB_EVIDENCE_MISSING")
            prs = []
        else:
            prs = proof["claim_pr_urls"]
            if not _age_ok(proof["checked_at"], now, ttl):
                reasons.append("GITHUB_SNAPSHOT_STALE")
            if proof["state"] == "closed":
                reasons.append("CANONICAL_CLOSED")
            elif proof["state"] == "not_found":
                reasons.append("CANONICAL_NOT_FOUND")
            if proof["repository_archived"]:
                reasons.append("REPOSITORY_ARCHIVED")
            if proof["assignees"]:
                reasons.append("CANONICAL_ASSIGNED")
            if not proof["claim_scan_complete"]:
                reasons.append("CLAIM_SCAN_INCOMPLETE")
            if prs:
                reasons.append("CLAIM_PR_EXISTS")

        if not reasons:
            decision = "READY_FOR_COORDINATED_TAKE"
        elif any(reason in PRUNE_REASONS for reason in reasons):
            decision = "PRUNE"
        else:
            decision = "HOLD"

        # Zero active amount when every listing is CLOSED. Historical prices
        # remain individually recorded, never masquerading as live payouts.
        maximum = max((row["advertised_usd"] for row in open_rows), default=Decimal("0"))
        record = {
            "issue_url": issue,
            "decision": decision,
            "reasons": sorted(reasons),
            "listing_ids": [row["listing_id"] for row in rows],
            "open_listing_ids": [row["listing_id"] for row in open_rows],
            # No summation: rows can duplicate one sponsored opportunity.
            "advertised_max_usd": f"{maximum:.2f}",
            "advertised_listings": [
                {"listing_id": row["listing_id"],
                 "board_state": row["board_state"],
                 "board_claims": row["board_claims"],
                 "advertised_usd": f"{row['advertised_usd']:.2f}"}
                for row in rows
            ],
            "claim_pr_urls": prs,
            "reward_awarded": "UNKNOWN",
            "payment_received": "UNKNOWN",
        }
        decisions.append(record)
        if decision == "READY_FOR_COORDINATED_TAKE":
            work_orders.append({
                "operation_id": "ALGORA:" + issue.removeprefix("https://github.com/"),
                "issue_url": issue,
                "provider_source": source,
                "listing_ids": record["open_listing_ids"],
                "advertised_max_usd": record["advertised_max_usd"],
                "reward_awarded": "UNKNOWN",
                "payment_received": "UNKNOWN",
                "next_step": (
                    "Reserve this issue in Slack after a fresh owner/collision check. "
                    "Verify canonical issue, claim PRs and first-party payout terms "
                    "again before submitting an original-author contribution."
                ),
            })

    work_orders.sort(key=lambda row: (
        -Decimal(row["advertised_max_usd"]), row["issue_url"]
    ))
    counts = {state: sum(d["decision"] == state for d in decisions) for state in
              ("READY_FOR_COORDINATED_TAKE", "HOLD", "PRUNE")}
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "provider_source": source,
        "provider_observed_at": provider_checked.isoformat().replace("+00:00", "Z"),
        "snapshot_complete": provider_fresh,
        "summary": {
            "provider_listing_rows": len(listings),
            "unique_canonical_issues": len(decisions),
            "ready": counts["READY_FOR_COORDINATED_TAKE"],
            "hold": counts["HOLD"],
            "prune": counts["PRUNE"],
        },
        "decisions": decisions,
        "work_orders": work_orders,
        "settlement": "No award, bounty claim, escrow, payout or cash receipt inferred.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="retained first-party provider + GitHub evidence JSON")
    parser.add_argument("--output", type=Path, help="optional JSON report destination")
    parser.add_argument("--as-of", help="fixed ISO timestamp for repeatable reconciliation")
    parser.add_argument("--max-age-hours", type=float, default=6.0)
    parser.add_argument("--minimum-usd", default="15")
    args = parser.parse_args(argv)
    try:
        now = _timestamp(args.as_of, "--as-of") if args.as_of else datetime.now(timezone.utc)
        minimum = _amount(args.minimum_usd)
        payload = json.loads(args.snapshot.read_text(encoding="utf-8"))
        result = reconcile(payload, now=now,
                           max_age_hours=args.max_age_hours, minimum_usd=minimum)
        output = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
        return 0
    except (IntakeError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"algora canonical intake: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
