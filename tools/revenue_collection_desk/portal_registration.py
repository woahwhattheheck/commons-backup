"""Read-only reconciliation of canonical GitHub submissions against provider claims.

Consumes already-retrieved, explicitly scoped first-party snapshots. It never
queries a provider, sends a claim, assumes that a pledged bounty is earned, or
converts a provider's paid flag into bank-settled cash.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit
from typing import Any

from .core import ContractError, canonical_bytes, loads_strict

SCHEMA = "commons.portal_registration_audit/v1"
REPORT_SCHEMA = "commons.portal_registration_report/v1"
PROVIDERS = {"issuehunt", "bountyhub"}
HOSTS = {"issuehunt": {"oss.issuehunt.io"}, "bountyhub": {"bountyhub.dev", "www.bountyhub.dev", "api.bountyhub.dev"}}
MAX_EVIDENCE_AGE_SECONDS = 7200
BOUNTY_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
ACTOR = re.compile(r"[A-Za-z0-9-]{1,39}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
EVIDENCE = re.compile(r"[0-9a-f]{64}\Z")
PR = re.compile(r"/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/([1-9][0-9]*)/?\Z")


def _fields(value: Any, required: set[str], optional: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError(f"{where} must be an object")
    missing = required - value.keys()
    excess = value.keys() - required - optional
    if missing or excess:
        raise ContractError(f"{where} fields invalid: missing={sorted(missing)} extra={sorted(excess)}")
    return value


def _repo(value: Any, where: str) -> str:
    if type(value) is not str or not REPO.fullmatch(value):
        raise ContractError(f"{where} must be owner/repo")
    return value.casefold()


def _actor(value: Any, where: str) -> str:
    if type(value) is not str or not ACTOR.fullmatch(value):
        raise ContractError(f"{where} must be a GitHub login")
    return value.casefold()


def _issue(value: Any, where: str) -> int:
    if type(value) is not int or value < 1:
        raise ContractError(f"{where} must be positive integer")
    return value


def _provider(value: Any) -> str:
    if type(value) is not str or value not in PROVIDERS:
        raise ContractError("provider must be issuehunt or bountyhub")
    return value


def _pr_url(value: Any, repo: str | None, where: str) -> str:
    if type(value) is not str or len(value) > 250:
        raise ContractError(f"{where} must be an exact GitHub PR URL")
    parsed = urlsplit(value)
    if (parsed.scheme, parsed.netloc.casefold()) != ("https", "github.com") or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ContractError(f"{where} must use the public github.com HTTPS origin")
    match = PR.fullmatch(parsed.path)
    if match is None or (repo is not None and f"{match.group(1)}/{match.group(2)}".casefold() != repo):
        raise ContractError(f"{where} must match the repository's PR")
    return f"https://github.com/{match.group(1).casefold()}/{match.group(2).casefold()}/pull/{int(match.group(3))}"


def _issue_url(value: Any, repo: str, issue: int, where: str) -> str:
    if type(value) is not str or len(value) > 250:
        raise ContractError(f"{where} must be an exact GitHub issue URL")
    u = urlsplit(value)
    expected = f"/{repo}/issues/{issue}"
    if (u.scheme != "https" or u.netloc.casefold() != "github.com"
            or u.query or u.fragment or u.path.casefold().rstrip("/") != expected):
        raise ContractError(f"{where} must identify the exact GitHub issue")
    return f"https://github.com{expected}"


def _source_url(value: Any, provider: str, repo: str, issue: int, where: str) -> str:
    if type(value) is not str or len(value) > 500:
        raise ContractError(f"{where} must be a first-party portal source URL")
    u = urlsplit(value)
    host = u.netloc.casefold()
    if (u.scheme != "https" or host not in HOSTS[provider] or u.query
            or u.fragment or u.username or u.password):
        raise ContractError(f"{where} must be an exact HTTPS first-party {provider} URL")
    if provider == "issuehunt":
        if u.path.casefold().rstrip("/") != f"/r/{repo}/issues/{issue}":
            raise ContractError(f"{where} must identify the exact IssueHunt issue")
    else:
        parts = u.path.strip("/").split("/")
        if host == "api.bountyhub.dev":
            valid = len(parts) == 3 and parts[:2] == ["api", "bounties"] and bool(BOUNTY_ID.fullmatch(parts[2]))
        else:
            # Public BountyHub pages: /en/bounty/view/UUID/slug or /bounty/view/UUID/slug
            if parts and parts[0] in {"en", "de", "fr"}:
                parts = parts[1:]
            valid = (len(parts) in {3, 4} and parts[:2] == ["bounty", "view"]
                     and bool(BOUNTY_ID.fullmatch(parts[2]))
                     and (len(parts) == 3 or bool(re.fullmatch(r"[A-Za-z0-9_-]+", parts[3]))))
        if not valid:
            raise ContractError(f"{where} must be an exact BountyHub bounty detail URL")
    return value


def _instant(value: Any, where: str) -> tuple[datetime, str]:
    if type(value) is not str or len(value) > 40:
        raise ContractError(f"{where} must be an offset-aware ISO-8601 datetime")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        if parsed.tzinfo is None:
            raise ValueError("missing UTC offset")
        utc = parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as e:
        raise ContractError(f"{where} is not an offset-aware ISO-8601 datetime") from e
    return utc, utc.isoformat().replace("+00:00", "Z")


def _key(provider: str, repo: str, issue: int, claimant: str, pr: str) -> str:
    return "|".join((provider, repo, str(issue), claimant, pr))


def audit(payload: dict[str, Any]) -> dict[str, Any]:
    root = _fields(payload, {"schema", "submissions", "portal_snapshots"}, {"evaluated_at", "max_evidence_age_seconds"}, "input")
    if root["schema"] != SCHEMA:
        raise ContractError(f"schema must be {SCHEMA}")
    if type(root["submissions"]) is not list or type(root["portal_snapshots"]) is not list:
        raise ContractError("submissions and portal_snapshots must be arrays")

    evaluated = None
    evaluated_iso = None
    if "evaluated_at" in root:
        evaluated, evaluated_iso = _instant(root["evaluated_at"], "evaluated_at")
    max_age = root.get("max_evidence_age_seconds", MAX_EVIDENCE_AGE_SECONDS)
    if type(max_age) is not int or not 60 <= max_age <= 604800:
        raise ContractError("max_evidence_age_seconds must be an integer between 60 and 604800")

    submissions: dict[str, dict[str, Any]] = {}
    for i, raw in enumerate(root["submissions"]):
        w = f"submissions[{i}]"
        s = _fields(raw, {"provider", "repository", "issue", "claimant", "pr_url", "head_sha", "github_state"}, {"settlement", "submission_repository", "github_checked_at", "github_submitted_at"}, w)
        provider = _provider(s["provider"])
        repo = _repo(s["repository"], f"{w}.repository")
        issue = _issue(s["issue"], f"{w}.issue")
        claimant = _actor(s["claimant"], f"{w}.claimant")
        pr_repo = _repo(s.get("submission_repository", repo), f"{w}.submission_repository")
        pr = _pr_url(s["pr_url"], pr_repo, f"{w}.pr_url")
        checked = submitted = None
        if "github_checked_at" in s:
            checked, _ = _instant(s["github_checked_at"], f"{w}.github_checked_at")
        if "github_submitted_at" in s:
            submitted, _ = _instant(s["github_submitted_at"], f"{w}.github_submitted_at")
        if checked and submitted and submitted > checked:
            raise ContractError(f"{w}: GitHub check cannot predate submission")
        if type(s["head_sha"]) is not str or not SHA.fullmatch(s["head_sha"]):
            raise ContractError(f"{w}.head_sha must be a commit SHA")
        if type(s["github_state"]) is not str or s["github_state"] not in {"open", "merged", "closed"}:
            raise ContractError(f"{w}.github_state invalid")
        settlement = s.get("settlement")
        if settlement is not None:
            _fields(settlement, {"evidence_sha256", "receiving_rail", "status"}, set(), f"{w}.settlement")
            if type(settlement["evidence_sha256"]) is not str or not EVIDENCE.fullmatch(settlement["evidence_sha256"]):
                raise ContractError(f"{w}.settlement evidence SHA invalid")
            if settlement["status"] != "settled" or type(settlement["receiving_rail"]) is not str or not settlement["receiving_rail"].strip():
                raise ContractError(f"{w}.settlement requires verified settled receiving rail evidence")
        key = _key(provider, repo, issue, claimant, pr)
        normalized = {"provider": provider, "repository": repo, "issue": issue,
                      "claimant": claimant, "pr_url": pr, "head_sha": s["head_sha"],
                      "github_state": s["github_state"], "settlement": settlement,
                      "github_checked_at": checked, "github_submitted_at": submitted,
                      "submission_repository": pr_repo}
        if key in submissions and submissions[key] != normalized:
            raise ContractError(f"conflicting GitHub evidence for {key}")
        submissions[key] = normalized

    snapshots: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for i, raw in enumerate(root["portal_snapshots"]):
        w = f"portal_snapshots[{i}]"
        s = _fields(raw, {"provider", "repository", "issue", "source_url", "observed_at", "complete", "claims"}, {"source_issue_url"}, w)
        provider, repo, issue = _provider(s["provider"]), _repo(s["repository"], f"{w}.repository"), _issue(s["issue"], f"{w}.issue")
        src = _source_url(s["source_url"], provider, repo, issue, f"{w}.source_url")
        source_bound = provider == "issuehunt"
        if "source_issue_url" in s:
            _issue_url(s["source_issue_url"], repo, issue, f"{w}.source_issue_url")
            source_bound = True
        when, iso = _instant(s["observed_at"], f"{w}.observed_at")
        if type(s["complete"]) is not bool or type(s["claims"]) is not list:
            raise ContractError(f"{w} must have boolean complete and array claims")
        claims: dict[str, dict[str, Any]] = {}
        for j, rawclaim in enumerate(s["claims"]):
            cw = f"{w}.claims[{j}]"
            claim = _fields(rawclaim, {"pr_url", "claimant", "awarded", "is_paid"}, set(), cw)
            # Provider inventories may contain PRs in other repositories. Match an
            # exact canonical PR URL against the separately verified GitHub
            # submission_repository, rather than requiring the funded issue repo.
            cp = _pr_url(claim["pr_url"], None, f"{cw}.pr_url")
            ca = _actor(claim["claimant"], f"{cw}.claimant")
            if claim["awarded"] is not None and type(claim["awarded"]) is not bool:
                raise ContractError(f"{cw}: awarded must be true, false or null")
            if claim["is_paid"] is not None and type(claim["is_paid"]) is not bool:
                raise ContractError(f"{cw}: is_paid must be true, false or null")
            if claim["is_paid"] is True and claim["awarded"] is False:
                raise ContractError(f"{cw}: paid cannot coexist with explicitly unawarded")
            ck = _key(provider, repo, issue, ca, cp)
            details = {"awarded": claim["awarded"], "is_paid": claim["is_paid"]}
            if ck in claims and claims[ck] != details:
                raise ContractError(f"{cw}: conflicting claim status")
            claims[ck] = details
        snapshots.setdefault((provider, repo, issue), []).append({
            "source_url": src, "observed_at": when, "observed_at_iso": iso,
            "complete": s["complete"], "claims": claims, "source_bound": source_bound,
        })

    results: list[dict[str, Any]] = []
    actions: dict[str, dict[str, Any]] = {}
    for key in sorted(submissions):
        sub = submissions[key]
        ckey = (sub["provider"], sub["repository"], sub["issue"])
        snap_rows = snapshots.get(ckey, [])
        reason = "no_first_party_snapshot"
        status = "UNKNOWN"
        snapshot = None
        if snap_rows:
            newest = max(s["observed_at"] for s in snap_rows)
            current = [s for s in snap_rows if s["observed_at"] == newest]
            signatures = {hashlib.sha256(canonical_bytes({
                "source_url": s["source_url"], "complete": s["complete"],
                "source_bound": s["source_bound"], "claims": s["claims"],
            })).hexdigest() for s in current}
            if len(signatures) != 1:
                reason = "conflicting_latest_snapshots"
            else:
                snapshot = current[0]
                checked = sub["github_checked_at"]
                submitted = sub["github_submitted_at"]
                if evaluated is None or checked is None or submitted is None:
                    reason = "missing_evaluation_or_github_freshness_evidence"
                elif sub["github_state"] == "closed":
                    reason = "github_pr_closed_without_merge"
                elif not (timedelta(0) <= evaluated - checked <= timedelta(seconds=max_age)):
                    reason = "github_read_stale_or_future"
                elif not (timedelta(0) <= evaluated - snapshot["observed_at"] <= timedelta(seconds=max_age)):
                    reason = "portal_read_stale_or_future"
                elif snapshot["observed_at"] < submitted:
                    reason = "portal_read_predates_pr"
                elif not snapshot["source_bound"]:
                    reason = "bountyhub_listing_missing_exact_issue_binding"
                else:
                    claim = snapshot["claims"].get(key)
                    same_pr_other_claimant = any(k.endswith("|" + sub["pr_url"]) for k in snapshot["claims"])
                    if claim is not None:
                        if not snapshot["complete"]:
                            reason = "partial_portal_snapshot"
                        elif claim["is_paid"] and sub["settlement"]:
                            status, reason = "PAID", "portal_paid_and_receiving_rail_settled"
                        elif claim["is_paid"] is True or claim["awarded"] is True:
                            status, reason = "AWARDED", "portal_award_recorded_settlement_unverified"
                        elif claim["awarded"] is False:
                            status, reason = "PORTAL_REGISTERED_UNAWARDED", "portal_registration_confirmed"
                        else:
                            status, reason = "PORTAL_REGISTERED_AWARD_UNKNOWN", "portal_registration_confirmed_award_unknown"
                    elif not snapshot["complete"]:
                        reason = "partial_portal_snapshot"
                    elif same_pr_other_claimant:
                        reason = "portal_pr_author_mismatch"
                    else:
                        status, reason = "GITHUB_SUBMITTED_PORTAL_NOT_REGISTERED", "complete_current_portal_inventory_missing_exact_pr"
        operation_id = "portal-reg:" + hashlib.sha256(key.encode()).hexdigest()[:24]
        result = {"key": key, "operation_id": operation_id, "status": status, "reason": reason,
                  "provider": sub["provider"], "repository": sub["repository"], "issue": sub["issue"],
                  "claimant": sub["claimant"], "pr_url": sub["pr_url"], "head_sha": sub["head_sha"],
                  "github_state": sub["github_state"], "snapshot_source_url": snapshot["source_url"] if snapshot else None,
                  "snapshot_observed_at": snapshot["observed_at_iso"] if snapshot else None,
                  "cash_settlement_verified": status == "PAID"}
        results.append(result)
        if status == "GITHUB_SUBMITTED_PORTAL_NOT_REGISTERED":
            actions[operation_id] = {"operation_id": operation_id, "action": "VERIFY_AND_REGISTER_EXACT_PR_WITH_PROVIDER",
                                     "provider": sub["provider"], "claimant": sub["claimant"], "pr_url": sub["pr_url"],
                                     "issue": f"{sub['repository']}#{sub['issue']}",
                                     "source_url": snapshot["source_url"]}
    report = {"schema": REPORT_SCHEMA, "evaluated_at": evaluated_iso, "max_evidence_age_seconds": max_age, "rows": results,
              "actionable_registration_gaps": sorted(actions.values(), key=lambda r: r["operation_id"]),
              "authority": {"provider_mutation": False, "claim_submission": False, "settlement_inference": False}}
    report["audit_digest"] = hashlib.sha256(canonical_bytes(report)).hexdigest()
    return report


def audit_json(raw: str | bytes) -> dict[str, Any]:
    return audit(loads_strict(raw))
