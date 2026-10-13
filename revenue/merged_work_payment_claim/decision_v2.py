from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .codec_v2 import ClaimError, utc

STATES = frozenset({
    "READY_FOR_MUSE_PAYMENT_REQUEST",
    "HOLD_ALREADY_PAID",
    "HOLD_COOLDOWN",
    "HOLD_INELIGIBLE",
    "HOLD_STALE",
    "HOLD_NO_COMPENSATION_EVIDENCE",
    "HOLD_NO_ACCEPTANCE_EVIDENCE",
    "HOLD_PAYMENT_STATUS_UNKNOWN",
    "HOLD_EVIDENCE_CONFLICT",
    "HOLD_INCOMPLETE_EVIDENCE",
})


def _age_hours(now: datetime, stamp: str) -> float:
    return (now - utc(stamp, "evidence timestamp")[1]).total_seconds() / 3600


def _select_compensation(rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    if not rows:
        return None, "missing"
    by_id = {row["offer_id"]: row for row in rows}
    for offer_id in by_id:
        seen: set[str] = set()
        current: str | None = offer_id
        while current is not None:
            if current in seen:
                return None, "conflict"
            seen.add(current)
            current = by_id[current]["supersedes_offer_id"] if current in by_id else None
    superseded = {row["supersedes_offer_id"] for row in rows if row["supersedes_offer_id"] is not None}
    active = [row for row in rows if row["offer_id"] not in superseded]
    if len(active) != 1:
        return None, "conflict"
    selected = active[0]
    if selected["amount_minor"] is None and selected["terms_text"] is None:
        return None, "missing"
    return selected, None


def _future_evidence(doc: dict[str, Any], now: datetime) -> None:
    stamps = [doc["work"]["merged_at"]]
    stamps.extend(row["advertised_at"] for row in doc["compensation"])
    if doc["acceptance"] is not None:
        stamps.append(doc["acceptance"]["accepted_at"])
    if doc["eligibility"] is not None:
        stamps.append(doc["eligibility"]["observed_at"])
    stamps.extend(row["observed_at"] for row in doc["followups"])
    stamps.append(doc["payment_status"]["observed_at"])
    if any(utc(stamp, "evidence timestamp")[1] > now for stamp in stamps):
        raise ClaimError("future evidence relative to evaluation time")


def decide(doc: dict[str, Any], now: datetime, *, historical_replay: bool) -> tuple[str, list[str], dict[str, Any] | None]:
    _future_evidence(doc, now)
    payment = doc["payment_status"]
    if payment["status"] == "PAID":
        return "HOLD_ALREADY_PAID", ["retained_payment_status_is_paid"], None

    compensation, comp_error = _select_compensation(doc["compensation"])
    if comp_error == "missing":
        return "HOLD_NO_COMPENSATION_EVIDENCE", ["current_compensation_missing"], None
    if comp_error == "conflict":
        return "HOLD_EVIDENCE_CONFLICT", ["compensation_generation_conflict"], None
    assert compensation is not None

    acceptance = doc["acceptance"]
    if acceptance is None:
        return "HOLD_NO_ACCEPTANCE_EVIDENCE", ["acceptance_evidence_missing"], None
    if compensation["expires_at"] is not None and now > utc(compensation["expires_at"], "compensation.expires_at")[1]:
        return "HOLD_STALE", ["advertised_compensation_expired"], None

    eligibility = doc["eligibility"]
    if compensation["eligibility_required"]:
        if eligibility is None or eligibility["status"] in ("UNKNOWN", "NOT_REQUIRED"):
            return "HOLD_INCOMPLETE_EVIDENCE", ["eligibility_not_proven"], None
        if eligibility["status"] == "INELIGIBLE":
            return "HOLD_INELIGIBLE", ["retained_eligibility_is_ineligible"], None
    elif eligibility is not None and eligibility["status"] == "INELIGIBLE":
        return "HOLD_INELIGIBLE", ["retained_eligibility_is_ineligible"], None

    if payment["status"] == "UNKNOWN":
        return "HOLD_PAYMENT_STATUS_UNKNOWN", ["payment_status_unknown"], None
    if payment["status"] == "UNPAID" and payment["provenance_class"] == "UNKNOWN":
        return "HOLD_PAYMENT_STATUS_UNKNOWN", ["unpaid_provenance_unknown"], None

    max_age = doc["policy"]["max_status_age_hours"]
    stale: list[str] = []
    if compensation["eligibility_required"] and eligibility is not None and _age_hours(now, eligibility["observed_at"]) > max_age:
        stale.append("eligibility_status_stale")
    if _age_hours(now, payment["observed_at"]) > max_age:
        stale.append("payment_status_stale")
    if stale:
        return "HOLD_STALE", stale, None

    if any(row["kind"] == "PAYMENT_REJECTED" for row in doc["followups"]):
        return "HOLD_EVIDENCE_CONFLICT", ["prior_payment_rejection_requires_review"], None

    sent = [row for row in doc["followups"] if row["kind"] == "PAYMENT_REQUEST_SENT"]
    if sent and doc["policy"]["cooldown_hours"]:
        latest = max(utc(row["observed_at"], "followup.observed_at")[1] for row in sent)
        if now - latest < timedelta(hours=doc["policy"]["cooldown_hours"]):
            return "HOLD_COOLDOWN", ["prior_payment_request_inside_cooldown"], None

    if historical_replay:
        return "HOLD_STALE", ["historical_replay_non_authorizing"], None

    request = {
        "claim_id": doc["claim_id"],
        "claimant_id": doc["claimant_id"],
        "counterparty_id": doc["counterparty_id"],
        "opportunity_id": doc["opportunity_id"],
        "work_id": doc["work"]["work_id"],
        "repository": doc["work"]["repository"],
        "pr_number": doc["work"]["pr_number"],
        "merged_commit_sha": doc["work"]["merged_commit_sha"],
        "advertised_currency": compensation["currency"],
        "advertised_amount_minor": compensation["amount_minor"],
        "advertised_terms_text": compensation["terms_text"],
        "offer_id": compensation["offer_id"],
        "compensation_source_ref": compensation["source_ref"],
        "acceptance_source_ref": acceptance["source_ref"],
        "recipient": None,
        "route": None,
    }
    return "READY_FOR_MUSE_PAYMENT_REQUEST", [], request
