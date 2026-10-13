from __future__ import annotations

from datetime import datetime
from typing import Any

from ._common import (
    AUTHORITY,
    COLLABORATIVE_READY,
    EXPECTED_SOURCE_CONTRACT_SHA256,
    HOLD,
    NO_BID,
    PRIME_READY,
    RECEIPT_SCHEMA,
    QualificationInputError,
    _format_utc,
    _instant,
    _load_source_contract,
    digest,
)
from ._semantic import _semantic_document_states
from ._snapshot import _parse_snapshot

def _evaluate(
    snapshot: Any,
    *,
    evaluated: datetime,
    expected_rfp_sha256: str,
    authority: dict[str, Any] | None,
    semantic_authority_mode: str,
    clock_authority: str,
) -> dict[str, Any]:
    contract = _load_source_contract()
    released = _instant(contract["released_at"], "source contract released_at")
    deadline = _instant(contract["proposal_due_at"], "source contract proposal_due_at")
    if evaluated < released:
        raise QualificationInputError("evaluation time cannot predate RFP release")
    parsed = _parse_snapshot(
        snapshot,
        contract=contract,
        evaluated=evaluated,
        expected_rfp_sha256=expected_rfp_sha256,
    )
    qualification_holds = set(parsed["source_holds"])
    for doc_id in parsed["missing_documents"]:
        qualification_holds.add(f"DOCUMENT_NOT_READY:{doc_id}")
    missing_caps = [cap for cap, providers in parsed["coverage"].items() if not providers]
    for cap in missing_caps:
        qualification_holds.add(f"CAPABILITY_NOT_COVERED:{cap}")
    for cap in parsed["stale_caps"]:
        if cap in missing_caps:
            qualification_holds.add(f"CAPABILITY_EVIDENCE_EXPIRED:{cap}")
    for partner_id, caps in parsed["uncommitted"].items():
        if set(missing_caps).intersection(caps):
            qualification_holds.add(f"PARTNER_NOT_COMMITTED:{partner_id}")
    semantic_holds, semantic_states = _semantic_document_states(
        documents=parsed["documents"],
        contract=contract,
        evaluated=evaluated,
        authority=authority,
    )
    qualification_holds.update(semantic_holds)

    hard_constraints = list(parsed["hard_constraints"])
    if evaluated >= deadline:
        hard_constraints = sorted(set(hard_constraints) | {"PROPOSAL_DEADLINE_PASSED"})

    partner_coverage: dict[str, list[str]] = {}
    bidder_coverage: list[str] = []
    for cap, providers in parsed["coverage"].items():
        if parsed["bidder_id"] in providers:
            bidder_coverage.append(cap)
        for provider in providers:
            if provider != parsed["bidder_id"]:
                partner_coverage.setdefault(provider, []).append(cap)
    bidder_coverage.sort()
    for provider in partner_coverage:
        partner_coverage[provider].sort()

    if hard_constraints:
        candidate_decision = NO_BID
    elif qualification_holds:
        candidate_decision = HOLD
    elif partner_coverage:
        candidate_decision = COLLABORATIVE_READY
    else:
        candidate_decision = PRIME_READY

    final_holds = set(qualification_holds)
    production_current = semantic_authority_mode == "HOST_HMAC" and clock_authority == "PROCESS_UTC"
    if not hard_constraints and not production_current:
        if clock_authority != "PROCESS_UTC":
            final_holds.add("NON_PROCESS_CLOCK_AUTHORITY")
        if semantic_authority_mode != "HOST_HMAC":
            final_holds.add("NON_PRODUCTION_SEMANTIC_AUTHORITY")
    if hard_constraints:
        decision = NO_BID
    elif final_holds:
        decision = HOLD
    elif partner_coverage:
        decision = COLLABORATIVE_READY
    else:
        decision = PRIME_READY

    evaluated_at = _format_utc(evaluated)
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "decision": decision,
        "candidate_decision": candidate_decision,
        "authority": AUTHORITY,
        "current_authority": production_current,
        "clock_authority": clock_authority,
        "semantic_authority_mode": semantic_authority_mode,
        "semantic_authority_key_id": None if authority is None else authority["key_id"],
        "semantic_authority_generation_id": None if authority is None else authority["generation_id"],
        "semantic_authority_envelope_sha256": None if authority is None else authority["envelope_sha256"],
        "bid_id": contract["bid_id"],
        "bidder_id": parsed["bidder_id"],
        "organization_type": parsed["organization_type"],
        "evaluated_at": evaluated_at,
        "proposal_due_at": contract["proposal_due_at"],
        "source_contract_sha256": EXPECTED_SOURCE_CONTRACT_SHA256,
        "snapshot_sha256": digest(snapshot),
        "rfp_document_sha256": parsed["source"]["document_sha256"],
        "source_updates_checked_at": parsed["source"]["updates_checked_at_text"],
        "source_addenda_complete": parsed["source"]["addenda_complete"],
        "source_questions_answers_complete": parsed["source"]["questions_answers_complete"],
        "holds": sorted(final_holds),
        "qualification_holds": sorted(qualification_holds),
        "hard_constraints": hard_constraints,
        "missing_documents": sorted(parsed["missing_documents"]),
        "missing_capabilities": sorted(missing_caps),
        "bidder_coverage": bidder_coverage,
        "partner_coverage": {key: partner_coverage[key] for key in sorted(partner_coverage)},
        "document_states": {
            key: parsed["document_states"][key] for key in sorted(parsed["document_states"])
        },
        "document_semantic_states": semantic_states,
        "scoring_sections": {
            key: contract["scoring_sections"][key] for key in sorted(contract["scoring_sections"])
        },
        "collaborative_proposals_strongly_encouraged": contract[
            "collaborative_proposals_strongly_encouraged"
        ],
        "proposal_submission_authorized": False,
        "external_contact_authorized": False,
        "pricing_authorized": False,
        "certification_signature_authorized": False,
        "participant_data_authorized": False,
        "employer_commitment_inferred": False,
        "contract_awarded_inferred": False,
        "payment_received_inferred": False,
        "revenue_recognized_inferred": False,
    }
    receipt["receipt_sha256"] = digest(receipt)
    return {"receipt": receipt}
