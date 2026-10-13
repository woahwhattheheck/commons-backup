"""Historical-only route reconstruction for DCSA Innovation Call #01.

This module deliberately has no current-authority mode and no callable that can emit current
work authority. Explicit-time/raw-authority inputs are historical-only and always
produce outward HOLD.
"""
from __future__ import annotations

import datetime as dt
import hmac
from typing import Any, Mapping

from .contracts import (
    CONCEPT_DEADLINE, ESTIMATED_START_DATE, GENERAL_SOLICITATION_ID, LIVE_QA_AT,
    MAX_SOURCE_OBSERVATION_AGE, NOTICE_ID, QUESTION_DEADLINE, REPORT_SCHEMA,
    REQUIRED_CAPABILITIES, _sha256, authority_sha256, normalize_authority,
    normalize_candidate, normalize_floor, normalize_source_ledger,
)
from .strict import ValidationError, canonical_json_bytes, format_utc, parse_utc


def _verified(row: Mapping[str, Any]) -> bool:
    return row["state"] == "VERIFIED"


def _historical_projection(
    candidate: Mapping[str, Any],
    source: Mapping[str, Any],
    authority: Mapping[str, Any] | None,
    floor: Mapping[str, Any] | None,
    as_of: dt.datetime,
) -> tuple[str, list[str], dict[str, Any]]:
    """Compute a non-authorizing historical projection.

    The return value is descriptive evidence only. It is never a current report and
    cannot set current_work_authorized.
    """
    blockers: list[str] = []
    evidence: dict[str, Any] = {
        "source_complete": bool(source["complete"]),
        "authority_loaded": authority is not None,
        "authority_floor_loaded": floor is not None,
        "required_capabilities_declared": set(candidate["declared_capabilities"]) == set(REQUIRED_CAPABILITIES),
    }
    observed = parse_utc(source["observed_at"], field="source observed_at")
    if observed > as_of:
        blockers.append("SOURCE_OBSERVED_IN_FUTURE")
    if as_of - observed > MAX_SOURCE_OBSERVATION_AGE:
        blockers.append("SOURCE_OBSERVATION_STALE")
    if not source["complete"]:
        blockers.append("CONTROLLING_SOURCE_BYTES_INCOMPLETE")
    if as_of >= CONCEPT_DEADLINE:
        blockers.append("CONCEPT_PAPER_DEADLINE_CLOSED")
    if set(candidate["declared_capabilities"]) != set(REQUIRED_CAPABILITIES):
        blockers.append("REQUIRED_CAPABILITY_DECLARATIONS_INCOMPLETE")
    if authority is None:
        blockers.append("HISTORICAL_AUTHORITY_UNAVAILABLE")
    if floor is None:
        blockers.append("HISTORICAL_AUTHORITY_FLOOR_UNAVAILABLE")
    if authority is None or floor is None:
        return "HOLD", sorted(set(blockers)), evidence

    digest = authority_sha256(authority)
    evidence.update({
        "authority_generation": authority["generation"],
        "authority_sha256": digest,
        "authority_valid_until": authority["valid_until"],
    })
    if authority["generation"] != floor["generation"]:
        blockers.append("AUTHORITY_GENERATION_NOT_CURRENT")
    if not hmac.compare_digest(digest, floor["authority_sha256"]):
        blockers.append("AUTHORITY_DIGEST_NOT_CURRENT")
    if not hmac.compare_digest(authority["source_generation_sha256"], floor["source_generation_sha256"]):
        blockers.append("AUTHORITY_SOURCE_FLOOR_MISMATCH")
    if not hmac.compare_digest(source["source_generation_sha256"], authority["source_generation_sha256"]):
        blockers.append("AUTHORITY_SOURCE_GENERATION_MISMATCH")
    if authority["subject_id"] != candidate["subject_id"]:
        blockers.append("AUTHORITY_SUBJECT_MISMATCH")
    issued = parse_utc(authority["issued_at"], field="authority issued_at")
    valid = parse_utc(authority["valid_until"], field="authority valid_until")
    if issued > as_of:
        blockers.append("AUTHORITY_ISSUED_IN_FUTURE")
    if valid <= as_of:
        blockers.append("AUTHORITY_EXPIRED")

    unverified = sorted(row["capability"] for row in authority["capability_evidence"] if row["state"] != "VERIFIED")
    evidence["unverified_capabilities"] = unverified
    if unverified:
        blockers.append("CAPABILITY_EVIDENCE_INCOMPLETE")
    owner = authority["owner_decisions"]
    if candidate["rom_state"] != "OWNER_APPROVED" or not owner["rom_approved"]:
        blockers.append("ROM_OWNER_APPROVAL_REQUIRED")

    direct_rows = [
        authority["direct_clearance"]["active_top_secret_fcl"],
        authority["personnel"]["all_assigned_us_citizens"],
        authority["personnel"]["all_assigned_interim_secret_or_higher"],
        authority["personnel"]["privileged_users_t5_or_ts_start"],
        authority["personnel"]["cac_operability"],
        authority["ota_eligibility"]["direct_path"],
    ]
    direct_ready = all(_verified(row) for row in direct_rows)
    team_ready = _verified(authority["ota_eligibility"]["teaming_prime_path"])
    evidence["direct_eligibility_verified"] = direct_ready
    evidence["teaming_prime_eligibility_verified"] = team_ready

    common = {
        "SOURCE_OBSERVED_IN_FUTURE", "SOURCE_OBSERVATION_STALE",
        "CONTROLLING_SOURCE_BYTES_INCOMPLETE", "CONCEPT_PAPER_DEADLINE_CLOSED",
        "REQUIRED_CAPABILITY_DECLARATIONS_INCOMPLETE", "AUTHORITY_GENERATION_NOT_CURRENT",
        "AUTHORITY_DIGEST_NOT_CURRENT", "AUTHORITY_SOURCE_FLOOR_MISMATCH",
        "AUTHORITY_SOURCE_GENERATION_MISMATCH", "AUTHORITY_SUBJECT_MISMATCH",
        "AUTHORITY_ISSUED_IN_FUTURE", "AUTHORITY_EXPIRED",
        "CAPABILITY_EVIDENCE_INCOMPLETE", "ROM_OWNER_APPROVAL_REQUIRED",
    }
    if common.intersection(blockers):
        return "HOLD", sorted(set(blockers)), evidence
    preference = candidate["route_preference"]
    if preference in {"AUTO", "DIRECT"} and direct_ready and owner["direct_route_approved"]:
        return "DIRECT_READY", [], evidence
    if team_ready and owner["teaming_route_approved"]:
        return "TEAMING_REQUIRED", sorted(set(blockers)), evidence
    if not direct_ready:
        blockers.append("DIRECT_CLEARANCE_OR_PERSONNEL_NOT_VERIFIED")
    if not owner["direct_route_approved"]:
        blockers.append("DIRECT_ROUTE_NOT_OWNER_APPROVED")
    if not team_ready:
        blockers.append("TEAMING_PRIME_ELIGIBILITY_NOT_VERIFIED")
    if not owner["teaming_route_approved"]:
        blockers.append("TEAMING_ROUTE_NOT_OWNER_APPROVED")
    return "HOLD", sorted(set(blockers)), evidence


def compile_historical_report(
    candidate_value: Any,
    source_value: Any,
    authority_value: Any | None,
    floor_value: Any | None,
    *,
    as_of: dt.datetime,
) -> dict[str, Any]:
    """Reconstruct integrity at an explicit time; outward state is always HOLD."""
    if not isinstance(as_of, dt.datetime) or as_of.tzinfo is None:
        raise ValidationError("historical evaluation time must be timezone-aware")
    when = as_of.astimezone(dt.timezone.utc).replace(microsecond=0)
    candidate = normalize_candidate(candidate_value)
    source = normalize_source_ledger(source_value)
    authority = None if authority_value is None else normalize_authority(authority_value)
    floor = None if floor_value is None else normalize_floor(floor_value)
    projection, blockers, evidence = _historical_projection(candidate, source, authority, floor, when)
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "mode": "HISTORICAL_INTEGRITY_ONLY",
        "evaluated_at": format_utc(when),
        "notice_id": NOTICE_ID,
        "general_solicitation_id": GENERAL_SOLICITATION_ID,
        "subject_id": candidate["subject_id"],
        "operation_id": candidate["operation_id"],
        "concept_title": candidate["concept_title"],
        "state": "HOLD",
        "historical_route_projection": projection,
        "blockers": blockers,
        "question_window": "OPEN" if when < QUESTION_DEADLINE else "CLOSED",
        "question_deadline": format_utc(QUESTION_DEADLINE),
        "live_qa_at": format_utc(LIVE_QA_AT),
        "concept_deadline": format_utc(CONCEPT_DEADLINE),
        "estimated_start_date": ESTIMATED_START_DATE,
        "source_generation_sha256": source["source_generation_sha256"],
        "evidence_summary": evidence,
        "external_contact_authorized": False,
        "external_submission_authorized": False,
        "signature_authorized": False,
        "pricing_commitment_authorized": False,
        "clearance_claim_authorized": False,
        "award_or_revenue_claimed": False,
        "current_work_authorized": False,
        "receipt_sha256": "",
    }
    report["receipt_sha256"] = _sha256(canonical_json_bytes({**report, "receipt_sha256": ""}))
    return report
