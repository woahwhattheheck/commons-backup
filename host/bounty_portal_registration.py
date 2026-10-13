#!/usr/bin/env python3
"""Read-only paid PR -> provider-registration reconciliation.

Input is a retained, explicitly complete first-party provider observation plus
a separately verified GitHub PR. This script never signs into a platform,
submits a claim, assumes an advertised pledge is solver cash, or contacts a
sponsor. UNKNOWN is preferable to inventing a missing registration or payout.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


SCHEMA = "commons-bounty-portal-audit/v1"
PR_PATH = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/([1-9][0-9]*)$")
ISSUE_PATH = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)$")
SHA = re.compile(r"^[0-9a-f]{40}$")
BOUNTY_UUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
PROVIDERS = {"issuehunt": "oss.issuehunt.io", "bountyhub": "api.bountyhub.dev"}


class AuditError(ValueError):
    pass


def _utc(value, field):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AuditError(f"{field} requires UTC ISO-8601 ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise AuditError(f"{field} has an invalid timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise AuditError(f"{field} requires UTC")
    return parsed


def _github(url, pattern, field):
    if not isinstance(url, str):
        raise AuditError(f"{field} must be a canonical GitHub URL")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "github.com" or
            parsed.query or parsed.fragment):
        raise AuditError(f"{field} must be a canonical GitHub URL")
    match = pattern.fullmatch(parsed.path)
    if not match:
        raise AuditError(f"{field} must be an exact GitHub issue or PR URL")
    return (match[1] + "/" + match[2]).lower(), int(match[3])


def _provider(value):
    if not isinstance(value, str) or value.lower() not in PROVIDERS:
        raise AuditError("provider must be IssueHunt or BountyHub")
    return value.lower()


def _official(source, provider):
    if not isinstance(source, str):
        return False
    parsed = urlsplit(source)
    return (parsed.scheme == "https" and
            parsed.hostname == PROVIDERS[provider] and
            parsed.port is None and parsed.username is None and
            not parsed.fragment and not parsed.query)


def _key(provider, repo, issue, claimant, pr_repo, pr_number, listing_id=None):
    raw = f"{provider}|{repo}|{issue}|{claimant}|{pr_repo}|{pr_number}"
    # Keep legacy IssueHunt IDs stable, but never reuse a BountyHub action
    # identifier when an issue is re-listed as a different bounty.
    if listing_id:
        raw += f"|{listing_id}"
    return "portal-reg-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _candidate(row):
    if not isinstance(row, dict):
        raise AuditError("owned_prs entries must be objects")
    provider = _provider(row.get("provider"))
    repo, issue = _github(row.get("issue_url"), ISSUE_PATH, "issue_url")
    pr_repo, pr_number = _github(row.get("pr_url"), PR_PATH, "pr_url")
    listing_id = row.get("bounty_listing_id")
    if provider == "bountyhub":
        if listing_id is not None:
            if not isinstance(listing_id, str) or not BOUNTY_UUID.fullmatch(listing_id):
                raise AuditError("bounty_listing_id must be a canonical BountyHub UUID")
            listing_id = listing_id.lower()
    elif listing_id is not None:
        raise AuditError("bounty_listing_id is only valid for BountyHub")
    submission_repo = row.get("submission_repo", repo)
    if not isinstance(submission_repo, str) or submission_repo.lower() != pr_repo:
        raise AuditError("cross-repository PR requires an exact canonical submission_repo")
    claimant = row.get("claimant")
    if (not isinstance(claimant, str) or not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", claimant)):
        raise AuditError("claimant must be one GitHub login")
    head = row.get("head_sha")
    if not isinstance(head, str) or not SHA.fullmatch(head):
        raise AuditError("head_sha must be an exact lowercase 40-character Git SHA")
    state = row.get("github_state")
    if state not in ("open", "merged", "closed"):
        raise AuditError("github_state must be open, merged, or closed")
    submitted = _utc(row.get("github_submitted_at"), "github_submitted_at")
    checked = _utc(row.get("github_checked_at"), "github_checked_at")
    if checked < submitted:
        raise AuditError("GitHub check cannot predate submitted PR")
    identity = (provider, repo, issue)
    return {
        "identity": identity, "claimant": claimant.lower(), "pr_repo": pr_repo,
        "pr_number": pr_number, "bounty_listing_id": listing_id,
        "pr_url": f"https://github.com/{pr_repo}/pull/{pr_number}",
        "issue_url": f"https://github.com/{repo}/issues/{issue}",
        "head_sha": head, "github_state": state,
        "submitted_at": submitted, "checked_at": checked,
        "operation_id": _key(provider, repo, issue, claimant.lower(), pr_repo, pr_number, listing_id),
    }


def _snapshot(row):
    if not isinstance(row, dict):
        raise AuditError("provider_snapshots entries must be objects")
    provider = _provider(row.get("provider"))
    repo, issue = _github(row.get("issue_url"), ISSUE_PATH, "provider issue_url")
    source = row.get("source_url")
    if not _official(source, provider):
        raise AuditError("provider source_url must be an exact official platform URL")
    observed = _utc(row.get("observed_at"), "provider observed_at")
    if type(row.get("complete")) is not bool:
        raise AuditError("provider complete must be an explicit boolean")
    submissions = row.get("submissions")
    if not isinstance(submissions, list):
        raise AuditError("provider submissions must be an array, even when empty")
    parsed = urlsplit(source)
    listing_id = None
    if provider == "issuehunt":
        expected = f"/r/{repo}/issues/{issue}"
        if parsed.path.lower().rstrip("/") != expected:
            raise AuditError("IssueHunt source URL must identify the same funded issue")
    else:
        match = re.fullmatch(r"/api/bounties/([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})", parsed.path)
        if not match:
            raise AuditError("BountyHub source URL must identify one canonical listing UUID")
        listing_id = match[1].lower()
    return {
        "identity": (provider, repo, issue), "source_url": source,
        "observed": observed, "complete": row["complete"],
        "bounty_listing_id": listing_id, "submissions": submissions,
    }


def _submission_state(submission, candidate):
    if not isinstance(submission, dict):
        return "UNKNOWN", "malformed provider submission"
    url = submission.get("pr_url")
    claimant = submission.get("claimant")
    if not isinstance(url, str):
        if isinstance(claimant, str) and claimant.lower() == candidate["claimant"]:
            return "UNKNOWN", "own claimant has an unlinked provider output"
        return None, ""
    try:
        repo, number = _github(url, PR_PATH, "provider submission")
    except AuditError:
        return "UNKNOWN", "provider output has noncanonical PR identity"
    if repo != candidate["pr_repo"] or number != candidate["pr_number"]:
        return None, ""
    if not isinstance(claimant, str) or claimant.lower() != candidate["claimant"]:
        return "UNKNOWN", "exact PR has absent or mismatched provider claimant"
    state = submission.get("state", "REGISTERED")
    if state not in ("REGISTERED", "AWARDED", "PAID"):
        return "UNKNOWN", "unrecognized provider submission state"
    if state == "PAID":
        if submission.get("receiving_rail_verified") is True and submission.get("receipt_ref"):
            return "PAID", "actual receiving rail verified with retained receipt"
        return "UNKNOWN", "platform paid flag is not a receiving-rail settlement receipt"
    if state == "AWARDED":
        if submission.get("award_ref"):
            return "AWARDED", "specific provider award reference observed"
        return "UNKNOWN", "provider award asserted without award reference"
    return "PORTAL_REGISTERED_UNAWARDED", "exact owned PR registered; award not evidenced"


def reconcile(data, now, max_age):
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise AuditError(f"input schema must equal {SCHEMA}")
    owners = data.get("owned_prs")
    observations = data.get("provider_snapshots")
    if not isinstance(owners, list) or not isinstance(observations, list):
        raise AuditError("owned_prs and provider_snapshots must both be arrays")
    snapshots = {}
    for row in observations:
        snapshot = _snapshot(row)
        identity = snapshot["identity"]
        if identity in snapshots:
            raise AuditError("duplicate provider snapshot: " + str(identity))
        snapshots[identity] = snapshot
    results, actions, seen = [], [], set()
    for row in owners:
        candidate = _candidate(row)
        key = candidate["operation_id"]
        if key in seen:
            raise AuditError("duplicate owned PR/claimant operation: " + key)
        seen.add(key)
        provider, repo, issue = candidate["identity"]
        status, reason = "UNKNOWN", "no complete current provider observation"
        snapshot = snapshots.get(candidate["identity"])
        fresh_github = (timedelta(0) <= now - candidate["checked_at"] <= max_age)
        if candidate["github_state"] == "closed":
            reason = "GitHub PR closed without merge"
        elif not fresh_github:
            reason = "GitHub head/state read is stale or in the future"
        elif snapshot is not None and provider == "bountyhub" and (
                candidate["bounty_listing_id"] is None or
                candidate["bounty_listing_id"] != snapshot["bounty_listing_id"]):
            reason = "BountyHub listing UUID absent or mismatched; registration unverified"
        elif snapshot is not None:
            fresh_platform = timedelta(0) <= now - snapshot["observed"] <= max_age
            if not snapshot["complete"] or not fresh_platform:
                reason = "first-party provider coverage incomplete, stale or in the future"
            elif snapshot["observed"] < candidate["submitted_at"]:
                reason = "platform observation predates PR submission"
            else:
                status = "GITHUB_SUBMITTED_PORTAL_NOT_REGISTERED"
                reason = "complete first-party issue output has no exact owned PR"
                for submission in snapshot["submissions"]:
                    outcome, evidence = _submission_state(submission, candidate)
                    if outcome is not None:
                        status, reason = outcome, evidence
                        break
        result = {
            "operation_id": key, "provider": provider, "issue_url": candidate["issue_url"],
            "pr_url": candidate["pr_url"], "head_sha": candidate["head_sha"],
            "claimant": candidate["claimant"], "github_state": candidate["github_state"],
            "bounty_listing_id": candidate["bounty_listing_id"],
            "status": status, "reason": reason,
            "provider_source_url": snapshot["source_url"] if snapshot else None,
            "provider_observed_at": snapshot["observed"].isoformat() if snapshot else None,
        }
        results.append(result)
        if status == "GITHUB_SUBMITTED_PORTAL_NOT_REGISTERED":
            action = (
                "SUBMIT_CLAIM_FOR_PUBLISHED_PR" if provider == "bountyhub"
                else "VERIFY_AND_REGISTER_EXACT_PR"
            )
            actions.append({
                "operation_id": key, "action": action,
                "provider": provider, "issue_url": candidate["issue_url"],
                "pr_url": candidate["pr_url"], "claimant": candidate["claimant"],
                "source_url": snapshot["source_url"], "recheck_before_submit": True,
                "operator": "existing authenticated same-author portal operator",
            })
    return {"schema": SCHEMA, "evaluated_at": now.isoformat(),
            "result_count": len(results), "registration_gap_count": len(actions),
            "results": results, "action_items": actions,
            "settlement": "No payouts inferred from advertisements, pledges or creator fees."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="retained owned PRs + provider snapshots JSON")
    parser.add_argument("--output", type=Path, help="write exact JSON result to this path")
    parser.add_argument("--max-age-hours", type=float, default=2.0)
    args = parser.parse_args(argv)
    try:
        if not 0 < args.max_age_hours <= 168:
            raise AuditError("max-age-hours must be between 0 and 168")
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        result = reconcile(raw, datetime.now(timezone.utc), timedelta(hours=args.max_age_hours))
        text = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0
    except (AuditError, OSError, ValueError) as exc:
        print(f"portal-registration audit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
