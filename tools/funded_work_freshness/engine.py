"""Fail-closed funded-work preflight engine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.parse import quote

from amount_chronology import authoritative_amount_state
from constants import ACCEPTANCE_RE, GITHUB_ITEM_RE, SECURITY_RE, SPONSOR_RE
from errors import EvidenceError, PreflightInputError
from evaluation import (
    active_competing_prs,
    authoritative_funding_state,
    canonical_text,
    descriptive_issue_text,
    iso,
    last_activity,
    visible_claimants,
)
from github_evidence import (
    api_item_url,
    classify_http_failure,
    fetch_json_pages,
    github_parts,
    resolve_candidate,
)
from models import Candidate, Transport, validate_github_item_url
from receipt import base_receipt, finalize


def _deleted_receipt(receipt: dict[str, Any], canonical_url: str | None) -> dict[str, Any]:
    receipt.update(
        {
            "canonical": {"url": canonical_url, "state": "deleted_or_missing"},
            "checks": {"evidence_complete": True, "canonical_state_open": False},
            "freshness_status": "stale",
            "route": "reject",
            "reasons": ["canonical_target_deleted_or_missing"],
        }
    )
    return finalize(receipt)


def preflight(
    candidate: Candidate,
    transport: Transport,
    *,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate one candidate and always return a deterministic fail-closed receipt."""

    now = observed_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise PreflightInputError("observed_at must be timezone-aware")
    now = now.astimezone(timezone.utc)
    receipt = base_receipt(candidate, now)

    try:
        resolution = resolve_candidate(candidate, transport)
        receipt["resolution"] = {
            "candidate_final_url": resolution.candidate_final_url,
            "candidate_http_status": resolution.candidate_status,
            "canonical_url": resolution.canonical_url,
            "canonical_hint": resolution.canonical_hint,
        }
        if resolution.canonical_hint == "deleted_or_missing":
            return _deleted_receipt(receipt, resolution.canonical_url)
        assert resolution.canonical_url is not None

        item_response = transport.fetch(
            api_item_url(resolution.canonical_url), accept="application/vnd.github+json"
        )
        if item_response.status in {404, 410}:
            return _deleted_receipt(receipt, resolution.canonical_url)
        if item_response.status < 200 or item_response.status >= 300:
            raise classify_http_failure(item_response, "canonical_issue")
        issue = item_response.json()
        if not isinstance(issue, Mapping):
            raise EvidenceError(
                "canonical_issue_invalid_json", "canonical issue was not a JSON object"
            )

        html_url = issue.get("html_url")
        canonical_url = (
            validate_github_item_url(html_url)
            if isinstance(html_url, str) and GITHUB_ITEM_RE.fullmatch(html_url)
            else resolution.canonical_url
        )
        owner, repo, kind, number = github_parts(canonical_url)
        state = str(issue.get("state") or "unknown").lower()
        assignees_raw = issue.get("assignees") if isinstance(issue.get("assignees"), list) else []
        assignees = sorted(
            {
                str(row.get("login"))
                for row in assignees_raw
                if isinstance(row, Mapping) and row.get("login")
            }
        )
        labels = issue.get("labels") if isinstance(issue.get("labels"), list) else []
        label_names = sorted(
            {
                str(row.get("name")) if isinstance(row, Mapping) else str(row)
                for row in labels
                if (isinstance(row, Mapping) and row.get("name")) or isinstance(row, str)
            }
        )
        receipt["canonical"] = {
            "url": canonical_url,
            "requested_url": resolution.canonical_url,
            "moved": canonical_url != resolution.canonical_url,
            "owner": owner,
            "repository": repo,
            "kind": kind,
            "number": number,
            "title": str(issue.get("title") or "")[:500],
            "state": state,
            "assignees": assignees,
            "labels": label_names,
            "updated_at": issue.get("updated_at"),
        }
        if state == "closed":
            # Canonical closure is enough to reject this candidate. Do not spend
            # quota on comments/timeline or let their failures hide the known state.
            receipt.update(
                {
                    "checks": {"evidence_complete": True, "canonical_state_open": False},
                    "freshness_status": "stale",
                    "route": "reject",
                    "reasons": ["canonical_state_closed"],
                }
            )
            return finalize(receipt)

        base = f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}/issues/{number}"
        comments = fetch_json_pages(
            transport, f"{base}/comments?per_page=100", prefix="comments"
        )
        timeline = fetch_json_pages(
            transport, f"{base}/timeline?per_page=100", prefix="timeline"
        )
        comments = [row for row in comments if isinstance(row, Mapping)]
        timeline = [row for row in timeline if isinstance(row, Mapping)]
        claimants = visible_claimants(comments)
        competing_prs = active_competing_prs(timeline)
        authority_text = canonical_text(issue, comments)
        sponsor_present = bool(SPONSOR_RE.search(authority_text))
        amount_state = authoritative_amount_state(
            issue,
            comments,
            candidate.advertised_amount,
            candidate.currency,
        )
        amount_present = bool(amount_state["matches_advertised"])
        acceptance_reachable = bool(ACCEPTANCE_RE.search(authority_text))
        funding_state = authoritative_funding_state(
            issue,
            comments,
            candidate.advertised_amount,
            candidate.currency,
        )
        security_text = descriptive_issue_text(issue) + "\n" + authority_text
        security_sensitive = bool(
            SECURITY_RE.search(security_text + "\n" + "\n".join(label_names))
        )
        activity = last_activity(issue, comments)
        activity_in_future = activity is not None and activity > now + timedelta(minutes=5)
        age_days = None if activity is None else max(
            0.0, (now - activity).total_seconds() / 86400.0
        )

        receipt["checks"] = {
            "evidence_complete": True,
            "canonical_state_open": state == "open",
            "assignee_count": len(assignees),
            "visible_claim_count": len(claimants),
            "visible_claimants": claimants,
            "active_competing_pr_count": len(competing_prs),
            "active_competing_prs": competing_prs,
            "last_substantive_activity": iso(activity) if activity else None,
            "activity_age_days": None if age_days is None else round(age_days, 3),
            "activity_timestamp_in_future": activity_in_future,
            "max_age_days": candidate.max_age_days,
            "sponsor_mechanism_present": sponsor_present,
            "advertised_amount_supported_by_canonical_evidence": amount_present,
            "authoritative_amount_state": amount_state["status"],
            "canonical_current_reward_currency": amount_state["currency"],
            "canonical_current_reward_amount": amount_state["amount"],
            "acceptance_criteria_reachable": acceptance_reachable,
            "authoritative_funding_state": funding_state,
            "security_sensitive": security_sensitive,
        }

        reasons: list[str] = []
        route = "reject"
        if state != "open":
            status = "stale"
            reasons.append(f"canonical_state_{state}")
        elif activity is None:
            status = "ambiguous"
            reasons.append("missing_substantive_activity_timestamp")
        elif activity_in_future:
            status = "ambiguous"
            reasons.append("substantive_activity_timestamp_in_future")
        elif age_days is not None and age_days > candidate.max_age_days:
            status = "stale"
            reasons.append("canonical_activity_too_old")
        elif funding_state == "withdrawn":
            status = "ambiguous"
            reasons.append("canonical_funding_authoritatively_withdrawn")
        elif security_sensitive:
            status = "ambiguous"
            route = "research_only"
            reasons.append("security_scope_requires_research_only_route")
        elif assignees or len(claimants) > candidate.max_visible_claims or competing_prs:
            status = "occupied"
            if assignees:
                reasons.append("canonical_issue_assigned")
            if len(claimants) > candidate.max_visible_claims:
                reasons.append("visible_claim_threshold_exceeded")
            if competing_prs:
                reasons.append("active_competing_pull_requests")
        elif not sponsor_present:
            status = "ambiguous"
            reasons.append("canonical_sponsor_mechanism_not_found")
        elif amount_state["status"] == "ambiguous":
            status = "ambiguous"
            reasons.append("canonical_reward_amount_ambiguous")
        elif not amount_present:
            status = "ambiguous"
            if amount_state["status"] == "resolved":
                reasons.append("advertised_amount_superseded_by_newer_canonical_evidence")
            else:
                reasons.append("advertised_amount_not_supported_by_canonical_evidence")
        elif not acceptance_reachable:
            status = "ambiguous"
            reasons.append("acceptance_criteria_not_reachable")
        else:
            # Defer the extra repo API call until all cheaper funded-work
            # qualification gates pass. An open issue in an archived repo
            # cannot accept the pull request required for reward delivery.
            repository_url = f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}"
            repository_response = transport.fetch(
                repository_url, accept="application/vnd.github+json"
            )
            if repository_response.status < 200 or repository_response.status >= 300:
                raise classify_http_failure(repository_response, "canonical_repository")
            repository_metadata = repository_response.json()
            if not isinstance(repository_metadata, Mapping) or not isinstance(
                repository_metadata.get("archived"), bool
            ):
                raise EvidenceError(
                    "canonical_repository_archived_state_missing",
                    "canonical repository metadata did not provide a boolean archived state",
                )
            repository_archived = repository_metadata["archived"]
            receipt["canonical"]["repository_archived"] = repository_archived
            if repository_archived:
                status = "stale"
                reasons.append("canonical_repository_archived")
            else:
                status = "actionable"
                route = "qualified_for_human_claim_decision"
                reasons.append("canonical_evidence_fresh_open_unoccupied_and_funded")

        receipt["freshness_status"] = status
        receipt["route"] = route
        receipt["reasons"] = reasons
        return finalize(receipt)
    except EvidenceError as exc:
        receipt.update(
            {
                "checks": {"evidence_complete": False},
                "freshness_status": "ambiguous",
                "route": "reject",
                "reasons": [exc.code],
                "error": {"code": exc.code, "detail": exc.detail[:500]},
            }
        )
        return finalize(receipt)
