#!/usr/bin/env python3
"""Fail-closed qualification compiler for USAC RFP IT-26-139.

This module evaluates bidder-path evidence. It does not create submission,
signature, pricing, contract, award, payment, or revenue authority.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOLICITATION_ID = "IT-26-139"
ISSUE_DATE = "2026-08-31"
DEADLINE = "2026-09-30T11:00:00-04:00"
OFFICIAL_PAGE = (
    "https://www.usac.org/about/procurement/"
    "rfp-it-26-139-artificial-intelligence-ai-consulting-and-support-services/"
)
REQUIRED_DOCUMENT_IDS = {"RFP", "QNA", "BID_SHEET", "CONFIDENTIALITY"}
RECENT_CUTOFF = "2023-08-31"
MAX_KEY_PERSONNEL = 4
VALID_HOLDERS = {"prime", "teaming_partner"}


class QualificationError(ValueError):
    """Raised for malformed evidence packets."""


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise QualificationError("timestamp must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QualificationError(f"invalid timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise QualificationError("timestamp must include timezone")
    return parsed


def _date(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise QualificationError(f"{field} must be YYYY-MM-DD")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise QualificationError(f"{field} must be YYYY-MM-DD") from exc
    return value


def _bool(obj: dict[str, Any], field: str) -> bool:
    value = obj.get(field)
    if type(value) is not bool:
        raise QualificationError(f"{field} must be boolean")
    return value


def load_json(path: str | Path) -> dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise QualificationError(f"{path}: top level must be an object")
    return raw


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if manifest.get("solicitation_id") != SOLICITATION_ID:
        problems.append("SOURCE_SOLICITATION_ID_MISMATCH")
    if manifest.get("official_page") != OFFICIAL_PAGE:
        problems.append("SOURCE_OFFICIAL_PAGE_MISMATCH")
    if manifest.get("authority") != "USAC_OFFICIAL_PROCUREMENT_PAGE":
        problems.append("SOURCE_AUTHORITY_UNVERIFIED")
    if manifest.get("current_page_verified") is not True:
        problems.append("SOURCE_CURRENTNESS_UNVERIFIED")

    docs = manifest.get("documents")
    if not isinstance(docs, list):
        return problems + ["SOURCE_DOCUMENTS_MALFORMED"]
    ids: set[str] = set()
    for doc in docs:
        if not isinstance(doc, dict):
            problems.append("SOURCE_DOCUMENT_MALFORMED")
            continue
        doc_id = doc.get("document_id")
        if not isinstance(doc_id, str) or not doc_id:
            problems.append("SOURCE_DOCUMENT_ID_MISSING")
            continue
        if doc_id in ids:
            problems.append(f"SOURCE_DOCUMENT_DUPLICATE:{doc_id}")
        ids.add(doc_id)
        if doc.get("authority") != "USAC":
            problems.append(f"SOURCE_DOCUMENT_AUTHORITY_UNVERIFIED:{doc_id}")
        if doc.get("listed_on_official_page") is not True:
            problems.append(f"SOURCE_DOCUMENT_NOT_LISTED:{doc_id}")
        # We intentionally distinguish URL-bound public-source evidence from
        # exact-byte binding. A missing hash is never represented as byte-bound.
        byte_bound = doc.get("byte_bound")
        sha = doc.get("sha256")
        if byte_bound is True:
            if not isinstance(sha, str) or len(sha) != 64:
                problems.append(f"SOURCE_BYTE_BINDING_INVALID:{doc_id}")
        elif byte_bound is not False:
            problems.append(f"SOURCE_BYTE_BOUND_FLAG_INVALID:{doc_id}")
    for missing in sorted(REQUIRED_DOCUMENT_IDS - ids):
        problems.append(f"SOURCE_REQUIRED_DOCUMENT_MISSING:{missing}")
    return sorted(set(problems))


def _qualifying_contract(item: Any) -> tuple[bool, str]:
    if not isinstance(item, dict):
        return False, "contract evidence must be object"
    holder = item.get("holder")
    if holder not in VALID_HOLDERS:
        return False, "holder must be prime or teaming_partner"
    for flag in (
        "similar_scope",
        "regulated_or_federal_oversight",
        "reference_reachable",
        "reference_permission_confirmed",
    ):
        if type(item.get(flag)) is not bool:
            return False, f"{flag} must be boolean"
        if item.get(flag) is not True:
            return False, f"{flag} not proven"
    try:
        relevant_date = _date(item.get("relevant_date"), "relevant_date")
    except QualificationError as exc:
        return False, str(exc)
    if relevant_date < RECENT_CUTOFF:
        return False, "past performance older than three-year recency window"
    contract_ref = item.get("contract_ref")
    client = item.get("client")
    if not isinstance(contract_ref, str) or not contract_ref.strip():
        return False, "contract_ref missing"
    if not isinstance(client, str) or not client.strip():
        return False, "client missing"
    return True, ""


def _key_personnel(facts: dict[str, Any]) -> tuple[bool, list[str]]:
    people = facts.get("key_personnel")
    if not isinstance(people, list):
        return False, ["KEY_PERSONNEL_MALFORMED"]
    problems: list[str] = []
    if len(people) > MAX_KEY_PERSONNEL:
        problems.append("KEY_PERSONNEL_LIMIT_EXCEEDED")
    ai_smes = 0
    for idx, person in enumerate(people):
        if not isinstance(person, dict):
            problems.append(f"KEY_PERSONNEL_MALFORMED:{idx}")
            continue
        name = person.get("name")
        role = person.get("role")
        affiliation = person.get("affiliation")
        committed = person.get("committed")
        if not isinstance(name, str) or not name.strip():
            problems.append(f"KEY_PERSONNEL_NAME_MISSING:{idx}")
        if affiliation not in VALID_HOLDERS:
            problems.append(f"KEY_PERSONNEL_AFFILIATION_INVALID:{idx}")
        if type(committed) is not bool or committed is not True:
            problems.append(f"KEY_PERSONNEL_NOT_COMMITTED:{idx}")
        if role == "AI Subject Matter Expert":
            ai_smes += 1
    if ai_smes != 1:
        problems.append("AI_SME_EXACTLY_ONE_REQUIRED")
    return not problems, problems


def _submission_readiness(facts: dict[str, Any]) -> tuple[bool, list[str]]:
    proposal = facts.get("proposal")
    if not isinstance(proposal, dict):
        return False, ["PROPOSAL_EVIDENCE_MALFORMED"]
    required = (
        "corporate_volume_complete",
        "technical_volume_complete",
        "past_performance_volume_complete",
        "price_volume_complete",
        "confidentiality_signed",
        "bid_sheet_without_ai_complete",
        "page_limits_validated",
        "official_source_rechecked_before_submission",
        "submission_email_package_ready",
    )
    missing: list[str] = []
    for field in required:
        if type(proposal.get(field)) is not bool:
            missing.append(f"PROPOSAL_FIELD_MALFORMED:{field}")
        elif proposal.get(field) is not True:
            missing.append(f"PROPOSAL_NOT_READY:{field}")

    ai = facts.get("ai_delivery")
    if not isinstance(ai, dict):
        missing.append("AI_DELIVERY_EVIDENCE_MALFORMED")
    else:
        requested = ai.get("ai_use_requested")
        if type(requested) is not bool:
            missing.append("AI_USE_REQUEST_FLAG_MALFORMED")
        elif requested:
            if proposal.get("bid_sheet_with_ai_complete") is not True:
                missing.append("PROPOSAL_NOT_READY:bid_sheet_with_ai_complete")
            if ai.get("ai_use_described_in_technical_volume") is not True:
                missing.append("AI_USE_NOT_DESCRIBED")
    return not missing, sorted(set(missing))


def evaluate(
    manifest: dict[str, Any],
    facts: dict[str, Any],
    *,
    as_of: str,
) -> dict[str, Any]:
    """Return a deterministic, fail-closed qualification receipt."""
    source_problems = validate_manifest(manifest)
    try:
        now = _parse_time(as_of)
        deadline = _parse_time(DEADLINE)
    except QualificationError as exc:
        return _receipt("HOLD", False, [f"TIME_INVALID:{exc}"], [], [], facts)

    blockers = list(source_problems)
    warnings: list[str] = []
    if now >= deadline:
        blockers.append("DEADLINE_PASSED")

    org = facts.get("organization")
    if not isinstance(org, dict):
        blockers.append("ORGANIZATION_EVIDENCE_MALFORMED")
        org = {}
    if org.get("us_performance_capable") is not True:
        blockers.append("US_PERFORMANCE_CAPABILITY_UNPROVEN")
    legal_name = org.get("legal_name")
    if not isinstance(legal_name, str) or not legal_name.strip():
        blockers.append("LEGAL_OFFEROR_IDENTITY_UNPROVEN")

    personnel_ok, personnel_problems = _key_personnel(facts)
    if not personnel_ok:
        blockers.extend(personnel_problems)

    contracts = facts.get("past_performance")
    if not isinstance(contracts, list):
        contracts = []
        blockers.append("PAST_PERFORMANCE_MALFORMED")

    prime_count = 0
    team_count = 0
    contract_rejections: list[str] = []
    for idx, item in enumerate(contracts):
        ok, reason = _qualifying_contract(item)
        if not ok:
            contract_rejections.append(f"PAST_PERFORMANCE_REJECTED:{idx}:{reason}")
            continue
        if item["holder"] == "prime":
            prime_count += 1
        else:
            team_count += 1

    route = "HOLD"
    route_reason = "insufficient qualifying corporate past performance"
    if prime_count >= 2:
        route = "PRIME_READY"
        route_reason = "at least two qualifying prime-held corporate past-performance contracts"
    elif prime_count + team_count >= 2 and team_count > 0:
        route = "TEAMING_REQUIRED"
        route_reason = (
            "prime has fewer than two qualifying contracts; combined prime/team evidence "
            "can reach the RFP past-performance floor"
        )
    else:
        blockers.append("QUALIFYING_CORPORATE_PAST_PERFORMANCE_LT_2")

    # Structural/source/personnel blockers override bidder-path optimism.
    hard_blocker_prefixes = (
        "SOURCE_",
        "DEADLINE_",
        "US_PERFORMANCE_",
        "LEGAL_",
        "KEY_PERSONNEL_",
        "AI_SME_",
        "PAST_PERFORMANCE_MALFORMED",
    )
    if any(b.startswith(hard_blocker_prefixes) for b in blockers):
        route = "HOLD"
        route_reason = "one or more mandatory qualification/source gates are unproven"

    submission_ready, submission_gaps = _submission_readiness(facts)
    if route == "HOLD":
        submission_ready = False
    if not manifest.get("all_documents_byte_bound", False):
        warnings.append(
            "PUBLIC_SOURCES_URL_BOUND_NOT_BYTE_BOUND: re-fetch and hash controlling "
            "RFP/Q&A/attachments immediately before proposal finalization"
        )

    ai = facts.get("ai_delivery") if isinstance(facts.get("ai_delivery"), dict) else {}
    ai_requested = ai.get("ai_use_requested") is True
    written_ai_approval = ai.get("usac_written_ai_approval_received") is True
    performance_ai_authorized = bool(ai_requested and written_ai_approval)
    if ai_requested and not written_ai_approval:
        warnings.append(
            "AI_PERFORMANCE_NOT_AUTHORIZED: proposal may describe AI use, but actual "
            "performance requires prior USAC written approval"
        )

    blockers.extend(contract_rejections)
    return _receipt(
        route,
        submission_ready,
        sorted(set(blockers)),
        sorted(set(submission_gaps)),
        sorted(set(warnings)),
        facts,
        prime_count=prime_count,
        team_count=team_count,
        route_reason=route_reason,
        performance_ai_authorized=performance_ai_authorized,
        source_binding=(
            "BYTE_BOUND"
            if manifest.get("all_documents_byte_bound") is True
            else "URL_BOUND_OFFICIAL_PAGE_ONLY"
        ),
    )


def _receipt(
    decision: str,
    submission_ready: bool,
    blockers: list[str],
    submission_gaps: list[str],
    warnings: list[str],
    facts: dict[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "solicitation_id": SOLICITATION_ID,
        "decision": decision,
        "submission_ready": submission_ready,
        "submission_authority": False,
        "contract_authority": False,
        "award_claimed": False,
        "payment_claimed": False,
        "revenue_claimed": False,
        "blockers": blockers,
        "submission_gaps": submission_gaps,
        "warnings": warnings,
        "evidence_owner": facts.get("organization", {}).get("legal_name")
        if isinstance(facts.get("organization"), dict)
        else None,
        "authority_note": (
            "Qualification evidence only. Human owner review, current-source recheck, "
            "authorized signature, and authorized submission remain separate gates."
        ),
        **extra,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--facts", required=True)
    parser.add_argument("--as-of", required=True, help="timezone-aware ISO-8601 timestamp")
    parser.add_argument(
        "--require-submission-ready",
        action="store_true",
        help="exit non-zero unless qualification route is non-HOLD and submission_ready=true",
    )
    args = parser.parse_args(argv)
    try:
        receipt = evaluate(
            load_json(args.manifest),
            load_json(args.facts),
            as_of=args.as_of,
        )
    except (QualificationError, OSError, json.JSONDecodeError) as exc:
        receipt = {
            "solicitation_id": SOLICITATION_ID,
            "decision": "HOLD",
            "submission_ready": False,
            "submission_authority": False,
            "blockers": [f"INPUT_INVALID:{exc}"],
        }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if args.require_submission_ready:
        return 0 if receipt.get("decision") != "HOLD" and receipt.get("submission_ready") is True else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
