"""Offline, deterministic claim-aware sprint planner for verified bounty manifests.

No provider calls, GitHub writes, identity switching, secrets, or payout mutations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ISSUE_RE = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)/?$")
PR_RE = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/([1-9][0-9]*)/?$")
PLATFORMS = {"algora", "bountyhub", "issuehunt", "grantfox", "proven_payer"}
FUNDING = {"escrow_verified", "provider_listed", "promised", "conditional", "unverified"}
ELIGIBILITY = {"eligible", "human_required", "assignment_required", "unknown", "ineligible"}
STATES = {"open", "closed", "unknown"}
SOURCES = {"none", "building", "ready", "published"}
CLAIMS = {"unknown", "not_submitted", "submitted", "accepted", "rejected", "paid"}
COMPETITION = {"none", "other_pr", "ours", "unknown"}


def github_identity(url: str, kind: str) -> tuple[str, str, int]:
    if not isinstance(url, str):
        raise ValueError("GitHub URL must be text")
    u = urlsplit(url)
    if u.scheme != "https" or u.netloc.lower() != "github.com" or u.query or u.fragment:
        raise ValueError("canonical HTTPS github.com URL required")
    match = (ISSUE_RE if kind == "issue" else PR_RE).fullmatch(u.path)
    if match is None:
        raise ValueError("invalid GitHub %s URL" % kind)
    owner, repo, number = match.groups()
    return owner.lower(), repo.lower(), int(number)


def timestamp(raw: str) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("timestamp must be timezone-aware ISO 8601 text")
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid ISO 8601 timestamp") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamp must carry an explicit timezone")
    return result


def enum(record: dict, field: str, choices: set[str]) -> str:
    value = record.get(field, "unknown")
    if value not in choices:
        raise ValueError("invalid %s: %s" % (field, value))
    return value


def normalize(record: dict, now: datetime, max_age_hours: int) -> dict:
    if not isinstance(record, dict):
        raise ValueError("each candidate must be an object")
    owner, repo, number = github_identity(record.get("issue_url"), "issue")
    platform = enum(record, "platform", PLATFORMS)
    funding = enum(record, "funding", FUNDING)
    eligibility = enum(record, "eligibility", ELIGIBILITY)
    state = enum(record, "issue_state", STATES)
    source = enum(record, "source_state", SOURCES)
    competition = enum(record, "competition", COMPETITION)
    claim = enum(record, "claim_state", CLAIMS)
    amount = record.get("reward_usd")
    if amount is not None and (type(amount) not in (float, int) or not 0 <= amount <= 10_000_000):
        raise ValueError("reward_usd must be a nonnegative finite numeric amount or null")
    if isinstance(amount, float) and (amount != amount or amount == float("inf")):
        raise ValueError("reward_usd must be finite")
    pr = record.get("pr_url")
    if pr is not None:
        pr_owner, pr_repo, _ = github_identity(pr, "pr")
        if (pr_owner, pr_repo) != (owner, repo):
            raise ValueError("pr_url must be a sponsor-repository PR; put fork carriers in source_pr_url")
    author = record.get("pr_author")
    if author is not None and (not isinstance(author, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", author)):
        raise ValueError("invalid PR author")
    source_pr = record.get("source_pr_url")
    source_author = record.get("source_pr_author")
    if source_pr is not None:
        src_owner, src_repo, _ = github_identity(source_pr, "pr")
        if (src_owner, src_repo) == (owner, repo):
            raise ValueError("source_pr_url must refer to a different, source-carrier repository")
        if not isinstance(source_author, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", source_author):
            raise ValueError("source_pr_url needs a valid source_pr_author")
        if source == "none" and not pr:
            raise ValueError("fork source requires an explicit building or ready source_state")
    elif source_author is not None:
        raise ValueError("source_pr_author requires source_pr_url")
    if source == "published" and (not pr or not author):
        raise ValueError("published source needs PR URL and author")
    if source != "published" and pr:
        # An upstream PR is an existing contribution even when the input
        # claims source=none; do not accidentally spawn a duplicate author.
        source = "published"
        if not author:
            raise ValueError("existing PR needs author")
    verified = timestamp(record.get("checked_at"))
    age = now - verified
    fresh = timedelta(0) <= age <= timedelta(hours=max_age_hours)
    funding_url = record.get("funding_url")
    if funding_url is not None and (not isinstance(funding_url, str) or not funding_url.startswith("https://")):
        raise ValueError("funding_url must be HTTPS")
    occupied = record.get("active_owner")
    if occupied is not None and (not isinstance(occupied, str) or not occupied.strip()):
        raise ValueError("active_owner must be nonempty text or null")
    return {
        "issue_url": "https://github.com/%s/%s/issues/%s" % (owner, repo, number),
        "issue_key": "%s/%s#%s" % (owner, repo, number),
        "repo": "%s/%s" % (owner, repo),
        "number": number, "platform": platform, "funding": funding,
        "funding_url": funding_url, "eligibility": eligibility,
        "issue_state": state, "source_state": source, "competition": competition,
        "claim_state": claim, "reward_usd": amount, "pr_url": pr,
        "pr_author": author.lower() if author else None,
        "source_pr_url": source_pr,
        "source_pr_author": source_author.lower() if source_author else None,
        "active_owner": occupied, "fresh": fresh,
        "checked_at": verified.isoformat(),
        "note": str(record.get("note") or "")[:300],
    }


def action(item: dict, min_usd: float, actor: str) -> tuple[str, str]:
    """Returns a non-mutating action and a precise reason; never awards payout."""
    if not item["fresh"]:
        return "REFRESH_CANONICAL", "Issue/funding/PR evidence is stale or future-dated"
    if item["claim_state"] == "paid":
        return "VERIFY_SETTLEMENT", "Claim says paid; independently verify receiving-rail receipt"
    if item["source_state"] != "published" and item["claim_state"] in {"submitted", "accepted", "rejected"}:
        return "CLAIM_SOURCE_HOLD", "Portal claim exists but its upstream PR is not verified; reconcile before building or publishing"
    if item["source_state"] == "published":
        if item["pr_author"] != actor.lower():
            return "PRESERVE_FOREIGN_PR", "Existing PR belongs to another author; do not replace their claim"
        if item["eligibility"] != "eligible":
            return "ELIGIBILITY_HOLD", "Contribution eligibility requires independent confirmation"
        if item["claim_state"] == "not_submitted":
            return "SUBMIT_EXISTING_CLAIM", "Original-author PR is published; check same-account portal registration now"
        if item["claim_state"] == "unknown":
            return "VERIFY_CLAIM", "Unknown portal state is not proof of missing claim"
        if item["claim_state"] == "submitted":
            return "AWAIT_ACCEPTANCE", "Submitted claim is neither awarded nor paid"
        if item["claim_state"] == "accepted":
            return "VERIFY_SETTLEMENT", "Accepted claim requires independent payout/receipt evidence"
        return "REVIEW_REJECTION", "Inspect provider rejection/appeal terms on original PR"
    if item["source_pr_url"] and item["source_pr_author"] != actor.lower():
        return "PRESERVE_FOREIGN_PR", "Fork source carrier belongs to another author; keep their attribution and submission path"
    if item["issue_state"] != "open":
        return "ISSUE_STATE_HOLD", "No confirmed open sponsor issue for fresh engineering"
    if item["funding"] == "unverified" or not item["funding_url"]:
        return "FUNDING_HOLD", "Verified platform or sponsor payment evidence is missing"
    if item["eligibility"] != "eligible":
        return "ELIGIBILITY_HOLD", "Assignment, human-contribution, or program eligibility gate"
    if item["source_state"] == "ready":
        return "PUBLISH_EXISTING", "Already-built original-owner source should be submitted, not rebuilt"
    if item["competition"] in {"ours", "other_pr", "unknown"}:
        return "COMPETITION_REVIEW", "Current competing work must be resolved before any new build"
    if item["source_state"] == "building":
        return "OWNER_CONTINUES", "Build is already in progress; do not double-assign"
    if item["active_owner"]:
        return "OWNER_CONTINUES", "Another owner holds the work; do not double-assign"
    if item["reward_usd"] is None or item["reward_usd"] < min_usd:
        return "AMOUNT_HOLD", "No verified advertised amount meeting the configured minimum"
    return "BUILD", "No known owner/PR; eligible for exactly one sourced engineering assignment"


def plan(manifest: dict, *, min_usd: float = 15, max_builds: int = 8,
         per_repo_builds: int = 2, max_age_hours: int = 6,
         actor: str = "woahwhattheheck") -> dict:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("records"), list):
        raise ValueError("manifest must contain a records array")
    if any(type(x) is not int or x <= 0 for x in (max_builds, per_repo_builds, max_age_hours)):
        raise ValueError("capacity limits must be positive integers")
    if type(min_usd) not in (float, int) or not 0 <= min_usd <= 10_000_000:
        raise ValueError("invalid minimum amount")
    observed_at = datetime.now(timezone.utc)
    snapshot_at = timestamp(manifest["as_of"])
    snapshot_age = observed_at - snapshot_at
    if not timedelta(minutes=-5) <= snapshot_age <= timedelta(hours=max_age_hours):
        raise ValueError("manifest as_of must be a fresh, timezone-aware collection timestamp")
    now = observed_at
    if len(manifest["records"]) > 5000:
        raise ValueError("manifest exceeds 5000 records")
    items = [normalize(r, now, max_age_hours) for r in manifest["records"]]
    # One sponsor issue has one engineering carrier, but independent funded
    # listings for that issue still need their own claim/settlement outcomes.
    for item in items:
        item["action"], item["reason"] = action(item, min_usd, actor)
    keyed: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        keyed[item["issue_key"]].append(item)
    portal_actions = {"SUBMIT_EXISTING_CLAIM", "VERIFY_CLAIM",
                      "AWAIT_ACCEPTANCE", "VERIFY_SETTLEMENT", "REVIEW_REJECTION"}
    for group in keyed.values():
        if len(group) == 1:
            continue
        has_published_pr = any(x["fresh"] and x["source_state"] == "published" for x in group)
        has_ready_source = any(x["action"] == "PUBLISH_EXISTING" for x in group)
        build_taken = False
        publication_taken = False
        seen_portal_actions: set[tuple] = set()
        for item in sorted(group, key=lambda x: (-(x["reward_usd"] or 0),
                                                  x["platform"], x["funding_url"] or "",
                                                  x["pr_url"] or "")):
            kind = item["action"]
            if kind == "BUILD":
                if has_published_pr:
                    item["action"] = "RECONCILE_SHARED_PR"
                    item["reason"] = "Another listing has a published PR; confirm applicability before a new build"
                elif has_ready_source:
                    item["action"] = "RECONCILE_SHARED_SOURCE"
                    item["reason"] = "Another listing already has source ready; reconcile the source owner"
                elif build_taken:
                    item["action"] = "DUPLICATE_ISSUE_HOLD"
                    item["reason"] = "Only one engineering build per canonical sponsor issue"
                else:
                    build_taken = True
            elif kind == "PUBLISH_EXISTING":
                if has_published_pr:
                    item["action"] = "RECONCILE_SHARED_PR"
                    item["reason"] = "An upstream PR already exists for this issue; do not republish source"
                elif publication_taken:
                    item["action"] = "SOURCE_COLLISION_HOLD"
                    item["reason"] = "Multiple ready source carriers for one issue; resolve ownership before publishing"
                else:
                    publication_taken = True
            elif kind in portal_actions:
                # Identical listing/action pairs must not generate duplicate
                # submissions; different providers remain separately actionable.
                listing_action = (item["platform"], item["funding_url"], kind)
                if listing_action in seen_portal_actions:
                    item["action"] = "DUPLICATE_LISTING_HOLD"
                    item["reason"] = "Duplicate provider listing/action; reconcile the original claim"
                else:
                    seen_portal_actions.add(listing_action)
    for item in items:
        kind = item["action"]
        operation_id = "MOVA-%s-%s-%s" % (
            item["repo"].replace("/", "-"), item["number"], kind)
        if kind in portal_actions | {"CLAIM_SOURCE_HOLD", "DUPLICATE_LISTING_HOLD",
                                    "RECONCILE_SHARED_PR", "RECONCILE_SHARED_SOURCE"}:
            # Claim actions are per listing, not just per issue; a stable URL
            # digest keeps IDs distinct even on two listings of one platform.
            receipt_key = item["funding_url"] or item["issue_url"]
            receipt_hash = hashlib.sha256(receipt_key.encode("utf-8")).hexdigest()[:10]
            operation_id += "-%s-%s" % (item["platform"], receipt_hash)
        item["operation_id"] = operation_id
    # High-value ready engineering first, but bounded to protect shared API
    # quota and prevent all workers stampeding one sponsor at once.
    builds = sorted((x for x in items if x["action"] == "BUILD"),
                    key=lambda x: (-(x["reward_usd"] or 0), x["issue_key"]))
    admitted = 0
    repo_count: Counter[str] = Counter()
    for item in builds:
        if admitted >= max_builds or repo_count[item["repo"]] >= per_repo_builds:
            item["action"] = "QUEUED_CAPACITY"
            item["reason"] = "Engineering candidate preserved for later quota-safe dispatch"
            item["operation_id"] = "MOVA-%s-%s-QUEUED_CAPACITY" % (item["repo"].replace("/", "-"), item["number"])
        else:
            admitted += 1
            repo_count[item["repo"]] += 1
    order = {"PUBLISH_EXISTING": 0, "SUBMIT_EXISTING_CLAIM": 1,
             "VERIFY_CLAIM": 2, "BUILD": 3, "OWNER_CONTINUES": 4,
             "AWAIT_ACCEPTANCE": 5, "VERIFY_SETTLEMENT": 6}
    items.sort(key=lambda x: (order.get(x["action"], 20), -(x["reward_usd"] or 0), x["issue_key"], x["platform"]))
    counts = dict(sorted(Counter(x["action"] for x in items).items()))
    return {"as_of": now.isoformat(), "actor": actor,
            "advertised_total_usd": round(sum(x["reward_usd"] or 0 for x in items), 2),
            "verified_earned_usd": None, "count": len(items), "build_slots_admitted": admitted,
            "actions": counts, "work_orders": items}


def render_slack(batch: dict) -> str:
    lines = ["MOVA REPEATABLE BOUNTY SPRINT | %s" % batch["as_of"],
             "Advertised inventory $%.2f across %d entries; NOT awarded/paid. Source/build slots: %d." %
             (batch["advertised_total_usd"], batch["count"], batch["build_slots_admitted"])]
    for item in batch["work_orders"]:
        amount = "UNPRICED" if item["reward_usd"] is None else "$%.2f" % item["reward_usd"]
        lines.append("%s | %s | %s | %s | %s | %s" %
                     (item["action"], item["issue_key"], amount, item["platform"], item["operation_id"], item["reason"]))
    lines.append("No provider action was executed. Fresh GitHub/marketplace proof and ownership re-fence required before publication or claim.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("manifest", type=Path, help="Preverified canonical sponsor/platform manifest JSON")
    cli.add_argument("--format", choices=("json", "slack"), default="slack")
    cli.add_argument("--min-usd", type=float, default=15)
    cli.add_argument("--max-builds", type=int, default=8)
    cli.add_argument("--per-repo-builds", type=int, default=2)
    cli.add_argument("--max-age-hours", type=int, default=6)
    cli.add_argument("--actor", default="woahwhattheheck")
    args = cli.parse_args(argv)
    try:
        batch = plan(json.loads(args.manifest.read_text(encoding="utf-8")),
                     min_usd=args.min_usd, max_builds=args.max_builds,
                     per_repo_builds=args.per_repo_builds, max_age_hours=args.max_age_hours,
                     actor=args.actor)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print("INPUT_HOLD: %s" % error, file=sys.stderr)
        return 2
    print(json.dumps(batch, indent=2, sort_keys=True) if args.format == "json" else render_slack(batch))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
