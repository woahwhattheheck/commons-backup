"""Read-only reconciliation of canonical GitHub submissions against provider claims.

Consumes already-retrieved, explicitly scoped first-party snapshots. It never
queries a provider, sends a claim, assumes that a pledged bounty is earned, or
converts a provider's paid flag into bank-settled cash.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit
from typing import Any

from .core import ContractError, canonical_bytes, loads_strict

SCHEMA = "commons.portal_registration_audit/v1"
REPORT_SCHEMA = "commons.portal_registration_report/v1"
PROVIDERS = {"issuehunt", "bountyhub"}
HOSTS = {"issuehunt": {"oss.issuehunt.io"}, "bountyhub": {"bountyhub.dev", "www.bountyhub.dev"}}
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


def _pr_url(value: Any, repo: str, where: str) -> str:
    if type(value) is not str or len(value) > 250:
        raise ContractError(f"{where} must be an exact GitHub PR URL")
    parsed = urlsplit(value)
    if (parsed.scheme, parsed.netloc.casefold()) != ("https", "github.com") or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ContractError(f"{where} must use the public github.com HTTPS origin")
    match = PR.fullmatch(parsed.path)
    if match is None or f"{match.group(1)}/{match.group(2)}".casefold() != repo:
        raise ContractError(f"{where} must match the repository's PR")
    return f"https://github.com/{repo}/pull/{int(match.group(3))}"


def _source_url(value: Any, provider: str, repo: str, issue: int, where: str) -> str:
    if type(value) is not str or len(value) > 500:
        raise ContractError(f"{where} must be a first-party portal source URL")
    u = urlsplit(value)
    if u.scheme != "https" or u.netloc.casefold() not in HOSTS[provider] or not u.path.startswith("/") or u.username or u.password or u.fragment:
        raise ContractError(f"{where} must be an HTTPS first-party {provider} URL")
    if provider == "issuehunt" and (u.path.casefold() != f"/r/{repo}/issues/{issue}" or u.query):
        raise ContractError(f"{where} must identify the exact IssueHunt repository and issue")
    if provider == "bountyhub" and not u.path.startswith(("/en/bounty/", "/bounty/")):
        raise ContractError(f"{where} must be a BountyHub bounty listing")
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
    root = _fields(payload, {"schema", "submissions", "portal_snapshots"}, set(), "input")
    if root["schema"] != SCHEMA:
        raise ContractError(f"schema must be {SCHEMA}")
    if type(root["submissions"]) is not list or type(root["portal_snapshots"]) is not list:
        raise ContractError("submissions and portal_snapshots must be arrays")

    submissions: dict[str, dict[str, Any]] = {}
    for i, raw in enumerate(root["submissions"]):
        w = f"submissions[{i}]"
        s = _fields(raw, {"provider", "repository", "issue", "claimant", "pr_url", "head_sha", "github_state"}, {"settlement"}, w)
        provider = _provider(s["provider"])
        repo = _repo(s["repository"], f"{w}.repository")
        issue = _issue(s["issue"], f"{w}.issue")
        claimant = _actor(s["claimant"], f"{w}.claimant")
        pr = _pr_url(s["pr_url"], repo, f"{w}.pr_url")
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
                      "github_state": s["github_state"], "settlement": settlement}
        if key in submissions and submissions[key] != normalized:
            raise ContractError(f"conflicting GitHub evidence for {key}")
        submissions[key] = normalized

    snapshots: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for i, raw in enumerate(root["portal_snapshots"]):
        w = f"portal_snapshots[{i}]"
        s = _fields(raw, {"provider", "repository", "issue", "source_url", "observed_at", "complete", "claims"}, set(), w)
        provider, repo, issue = _provider(s["provider"]), _repo(s["repository"], f"{w}.repository"), _issue(s["issue"], f"{w}.issue")
        src = _source_url(s["source_url"], provider, repo, issue, f"{w}.source_url")
        when, iso = _instant(s["observed_at"], f"{w}.observed_at")
        if type(s["complete"]) is not bool or type(s["claims"]) is not list:
            raise ContractError(f"{w} must have boolean complete and array claims")
        claims: dict[str, dict[str, Any]] = {}
        for j, rawclaim in enumerate(s["claims"]):
            cw = f"{w}.claims[{j}]"
            claim = _fields(rawclaim, {"pr_url", "claimant", "awarded", "is_paid"}, set(), cw)
            cp = _pr_url(claim["pr_url"], repo, f"{cw}.pr_url")
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
            "complete": s["complete"], "claims": claims,
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
            signatures = {hashlib.sha256(canonical_bytes({"source_url": s["source_url"], "complete": s["complete"], "claims": s["claims"]})).hexdigest() for s in current}
            if len(signatures) != 1:
                reason = "conflicting_latest_snapshots"
            else:
                snapshot = current[0]
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
                        reason = "portal_registration_confirmed_award_unknown"
                elif not snapshot["complete"]:
                    reason = "partial_portal_snapshot"
                elif same_pr_other_claimant:
                    reason = "portal_pr_author_mismatch"
                else:
                    status, reason = "GITHUB_SUBMITTED_PORTAL_NOT_REGISTERED", "complete_portal_inventory_missing_exact_pr"
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
    report = {"schema": REPORT_SCHEMA, "rows": results,
              "actionable_registration_gaps": sorted(actions.values(), key=lambda r: r["operation_id"]),
              "authority": {"provider_mutation": False, "claim_submission": False, "settlement_inference": False}}
    report["audit_digest"] = hashlib.sha256(canonical_bytes(report)).hexdigest()
    return report


def audit_json(raw: str | bytes) -> dict[str, Any]:
    return audit(loads_strict(raw))
