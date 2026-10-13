from __future__ import annotations

import datetime as _dt
from typing import Any

from ._source_bound_common import _authority_false, _require_utc_instant, _sha, _workshare
from ._source_bound_constants import (
    CONTRACT_REVIEW_GATES,
    CONTRACT_SOURCE_CONFLICTS,
    INTENT_DEADLINE,
    OPPORTUNITY_ID,
    PROFESSIONAL_SERVICES_CONTRACT_SHA256,
    PROPOSAL_DEADLINE,
    SCHEMA_PACKET,
    ContractError,
)
from ._source_bound_facts import _normalize_facts

def intent_receipt_is_verified(
    receipt: dict[str, str] | None,
    verified_sha256: str | None,
    verified_submitted_at: str | None,
) -> bool:
    if receipt is None:
        return False
    if verified_sha256 is None or verified_submitted_at is None:
        return False
    expected_time = _require_utc_instant(
        verified_submitted_at,
        "internal verified intent receipt submitted_at",
    )
    return receipt == {
        "provider_event_sha256": verified_sha256,
        "submitted_at": expected_time,
    }

def _as_utc(value: _dt.datetime) -> _dt.datetime:
    if type(value) is not _dt.datetime or value.tzinfo is None:
        raise ContractError("internal evaluation instant must be timezone-aware datetime")
    return value.astimezone(_dt.timezone.utc)

def _gap_blockers(requirements: list[dict[str, Any]]) -> list[str]:
    return [
        f"{row['state']}:{row['requirement_id']}"
        for row in requirements
        if row["state"] != "SATISFIED"
    ]

def _basis_counts(requirements: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"RESPONDENT": 0, "NAMED_COMMITTED_TEAM_PARTNER": 0, "UNSATISFIED": 0}
    for row in requirements:
        if row["state"] != "SATISFIED":
            counts["UNSATISFIED"] += 1
        else:
            counts[row["basis"]] += 1
    return counts

def _contract_review() -> dict[str, Any]:
    return {
        "professional_services_contract_sha256": PROFESSIONAL_SERVICES_CONTRACT_SHA256,
        "normalized_review_gates": list(CONTRACT_REVIEW_GATES),
        "source_conflicts": list(CONTRACT_SOURCE_CONFLICTS),
        "owner_review_required_before_contract_acceptance": True,
        "contract_acceptance_inferred": False,
    }

def compile_at(
    facts_obj: Any,
    now: _dt.datetime,
    *,
    verified_intent_receipt_sha256: str | None,
    verified_intent_receipt_submitted_at: str | None,
) -> dict[str, Any]:
    facts = _normalize_facts(facts_obj)
    now_utc = _as_utc(now)
    intent_utc = INTENT_DEADLINE.astimezone(_dt.timezone.utc)
    proposal_utc = PROPOSAL_DEADLINE.astimezone(_dt.timezone.utc)
    blockers: list[str] = []
    actions: list[str] = []
    gaps = _gap_blockers(facts["requirements"])

    if now_utc >= proposal_utc:
        status = "CLOSED_DEADLINE"
        blockers.append("PROPOSAL_DEADLINE_REACHED")
        actions.append("ARCHIVE_OR_WAIT_FOR_REISSUE")
    else:
        receipt = facts["intent_receipt"]
        receipt_time = None
        if receipt is not None:
            receipt_time = _dt.datetime.fromisoformat(receipt["submitted_at"].replace("Z", "+00:00"))

        if receipt_time is not None and receipt_time > intent_utc:
            status = "HOLD_INTENT_CHRONOLOGY"
            blockers.append("INTENT_RECEIPT_AFTER_CONFIRMED_DEADLINE")
            actions.append("VERIFY_INTENT_ACCEPTANCE_WITH_PROCUREMENT")
        elif now_utc >= intent_utc and receipt is None:
            status = "HOLD_INTENT_DEADLINE"
            blockers.append("NO_INTENT_RECEIPT_AT_OR_AFTER_DEADLINE")
            actions.append("VERIFY_WITH_PROCUREMENT_WHETHER_RESPONSE_REMAINS_ELIGIBLE")
        elif now_utc >= intent_utc and not intent_receipt_is_verified(
            receipt,
            verified_intent_receipt_sha256,
            verified_intent_receipt_submitted_at,
        ):
            status = "HOLD_INTENT_RECEIPT_UNVERIFIED"
            blockers.append("INTENT_RECEIPT_NOT_PROVIDER_AUTHENTICATED")
            actions.append("BIND_INDEPENDENTLY_VERIFIED_PROVIDER_INTENT_EVENT")
        elif facts["route"] == "UNKNOWN":
            status = "HOLD_ROUTE_UNKNOWN"
            blockers.append("PRIME_OR_TEAMING_ROUTE_NOT_SELECTED")
            blockers.extend(gaps)
            actions.append("SELECT_PRIME_OR_TEAMING_ROUTE")
        elif facts["route"] == "PRIME":
            if gaps:
                status = "HOLD_PRIME_QUALIFICATION"
                blockers.extend(gaps)
                actions.append("DO_NOT_CLAIM_PRIME_ELIGIBILITY_WITHOUT_RESPONDENT_EVIDENCE")
            elif not facts["owner_reviewed"]:
                status = "HOLD_OWNER_REVIEW"
                blockers.append("FACTS_NOT_OWNER_REVIEWED")
                actions.append("OWNER_REVIEW_SOURCE_BOUND_REQUIREMENTS")
            else:
                status = "READY_FOR_OWNER_PRIME_REVIEW"
                actions.append("OWNER_REVIEW_PRIME_RESPONSE_PLAN")
        else:
            commitment = facts["teaming_commitment"]
            if commitment["status"] != "CONFIRMED":
                status = "TEAMING_CANDIDATE"
                blockers.append("NO_NAMED_COMMITTED_TEAM_PARTNER")
                blockers.extend(gaps)
                actions.extend([
                    "OBTAIN_NAMED_COMMITTED_TEAM_PARTNER",
                    "CLOSE_TEAM_COMPOSABLE_GAPS_WITH_SOURCE_EVIDENCE",
                ])
            elif gaps:
                status = "HOLD_TEAM_QUALIFICATION"
                blockers.extend(gaps)
                actions.append("CLOSE_REMAINING_TEAM_QUALIFICATION_GAPS")
            elif not facts["owner_reviewed"]:
                status = "HOLD_OWNER_REVIEW"
                blockers.append("FACTS_NOT_OWNER_REVIEWED")
                actions.append("OWNER_REVIEW_SOURCE_BOUND_TEAM_EVIDENCE")
            else:
                status = "READY_FOR_OWNER_TEAMING_REVIEW"
                actions.append("OWNER_REVIEW_PAID_WORKSHARE_WITH_CONFIRMED_PRIME")

    if status != "CLOSED_DEADLINE":
        actions.append("OWNER_REVIEW_PSC_GATES_AND_PAYMENT_TERM_CONFLICT_BEFORE_CONTRACT_ACCEPTANCE")

    trust_root_configured = (
        verified_intent_receipt_sha256 is not None
        and verified_intent_receipt_submitted_at is not None
    )
    packet = {
        "schema": SCHEMA_PACKET,
        "opportunity_id": OPPORTUNITY_ID,
        "evaluation_utc": now_utc.isoformat().replace("+00:00", "Z"),
        "deadlines": {
            "intent_to_bid": INTENT_DEADLINE.isoformat(),
            "proposal_due": PROPOSAL_DEADLINE.isoformat(),
            "intent_route": "BRIEF_EMAIL_TO_ISSUING_CONTACT",
        },
        "source_binding": facts["source_binding"],
        "source_policy": {
            "buyer_source_files_published_to_public_repo": False,
            "source_digest_match_required": True,
            "attachment_provenance_authenticated_by_code": False,
            "intent_receipt_trust_root_configured": trust_root_configured,
        },
        "contract_review": _contract_review(),
        "route": facts["route"],
        "status": status,
        "blockers": sorted(set(blockers)),
        "next_actions": actions,
        "requirements": facts["requirements"],
        "qualification_basis_counts": _basis_counts(facts["requirements"]),
        "teaming_commitment": facts["teaming_commitment"],
        "facts_sha256": _sha(facts),
        "workshare": _workshare(),
        "authority": _authority_false(),
        "truth_boundary": {
            "unconfirmed_outreach_target_contributes_qualifications": False,
            "named_committed_team_partner_may_supply_source_bound_qualification_evidence": True,
            "prime_remains_responsible": True,
            "respondent_identity_code_pinned": True,
            "professional_services_contract_hash_pinned": True,
            "contract_terms_accepted": False,
            "payment_terms_source_conflict_resolved": False,
            "unverified_intent_receipt_clears_deadline_hold": False,
            "strongest_output_is_owner_review_only": True,
            "external_send_authorized": False,
        },
    }
    packet["packet_sha256"] = _sha(packet)
    return packet
