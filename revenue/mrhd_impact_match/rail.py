"""Deterministic evidence rail for MRHD Impact Match grant reconciliation.

This module is intentionally evidence-only. It does not decide applicant
eligibility, score projects, approve awards, value contributions, authorize
reimbursements, or certify compliance. It consumes already-approved,
buyer-owned events and emits arithmetic/lineage state plus fail-closed HOLD
receipts for named human review.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from copy import deepcopy
from typing import Any, Iterable

MATCH_NUMERATOR = 25
MATCH_DENOMINATOR = 100
MAX_IN_KIND_SHARE_NUMERATOR = 50
MAX_IN_KIND_SHARE_DENOMINATOR = 100

FOCUS_CATEGORIES = (
    "economic_development_community_improvement_tourism",
    "human_services_health_services",
    "civic_public_charitable_patriotic_religious",
    "leisure_cultural_historical",
    "education",
)

ELIGIBLE_GEOGRAPHIES = (
    "IA:Cherokee",
    "IA:Crawford",
    "IA:Ida",
    "IA:Monona",
    "IA:Plymouth",
    "IA:Woodbury",
    "SD:Union",
    "NE:Dakota",
)

EVENT_TYPES = {
    "AWARD_APPROVED",
    "MATCH_COMMITMENT",
    "CONTRIBUTION_VERIFIED",
    "AMENDMENT_APPROVED",
    "PARTNER_CHANGED",
    "MILESTONE_RECORDED",
    "RETURN_RECORDED",
    "CLOSEOUT_REQUESTED",
}

REVIEW_ACTIONS = ("REVIEW", "APPROVE", "FREEZE")


class EvidenceInputError(ValueError):
    """Raised when the event envelope itself cannot be trusted."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _require_exact_int(value: Any, field: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceInputError(f"{field} must be an integer")
    if positive and value <= 0:
        raise EvidenceInputError(f"{field} must be positive")
    if not positive and value < 0:
        raise EvidenceInputError(f"{field} must be non-negative")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceInputError(f"{field} must be non-empty text")
    return value.strip()


def _exact_required_match(award_cents: int) -> int:
    numerator = award_cents * MATCH_NUMERATOR
    if numerator % MATCH_DENOMINATOR:
        raise EvidenceInputError(
            "award_cents does not yield an exact-cent 25% match"
        )
    return numerator // MATCH_DENOMINATOR


def _max_in_kind(required_match_cents: int) -> int:
    numerator = required_match_cents * MAX_IN_KIND_SHARE_NUMERATOR
    if numerator % MAX_IN_KIND_SHARE_DENOMINATOR:
        raise EvidenceInputError(
            "required_match_cents does not yield an exact-cent 50% in-kind cap"
        )
    return numerator // MAX_IN_KIND_SHARE_DENOMINATOR


def _hold(
    code: str,
    *,
    event_id: str,
    award_id: str | None,
    message: str,
    action: str = "REVIEW",
) -> dict[str, Any]:
    if action not in REVIEW_ACTIONS:
        raise EvidenceInputError("unknown human review action")
    return {
        "code": code,
        "event_id": event_id,
        "award_id": award_id,
        "action": action,
        "owner_role": "MRHD_STAFF",
        "message": message,
    }


def _normalize_event(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise EvidenceInputError("event must be an object")
    event = deepcopy(raw)
    event_id = _require_text(event.get("event_id"), "event_id")
    event_type = _require_text(event.get("event_type"), "event_type")
    if event_type not in EVENT_TYPES:
        raise EvidenceInputError(f"unknown event_type: {event_type}")
    sequence = _require_exact_int(event.get("sequence"), "sequence")
    award_id = event.get("award_id")
    if award_id is not None:
        award_id = _require_text(award_id, "award_id")
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise EvidenceInputError("payload must be an object")
    return {
        "event_id": event_id,
        "event_type": event_type,
        "sequence": sequence,
        "award_id": award_id,
        "payload": payload,
    }


def _new_award_state(
    *,
    award_id: str,
    applicant_id: str,
    project_id: str,
    cycle_id: str,
    category: str,
    geography: str,
    award_cents: int,
    required_match_cents: int,
    approval_id: str,
    sequence: int,
) -> dict[str, Any]:
    return {
        "award_id": award_id,
        "applicant_id": applicant_id,
        "project_id": project_id,
        "cycle_id": cycle_id,
        "category": category,
        "geography": geography,
        "award_cents": award_cents,
        "required_match_cents": required_match_cents,
        "max_in_kind_cents": _max_in_kind(required_match_cents),
        "returned_cents": 0,
        "cash_verified_cents": 0,
        "in_kind_verified_cents": 0,
        "commitments": {},
        "partners": [],
        "milestones": [],
        "amendments": [
            {
                "event_id": approval_id,
                "sequence": sequence,
                "award_cents": award_cents,
                "required_match_cents": required_match_cents,
                "kind": "INITIAL_APPROVAL",
            }
        ],
        "returns": [],
        "closeout_requests": [],
    }


def _public_award_state(state: dict[str, Any]) -> dict[str, Any]:
    commitments = []
    for key in sorted(state["commitments"]):
        item = state["commitments"][key]
        commitments.append(
            {
                "commitment_id": key,
                "kind": item["kind"],
                "committed_cents": item["committed_cents"],
                "realized_cents": item["realized_cents"],
                "source_id": item["source_id"],
                "valuation_method": item.get("valuation_method"),
                "evidence_hash": item.get("evidence_hash"),
                "verified_event_ids": list(item["verified_event_ids"]),
            }
        )

    cash = state["cash_verified_cents"]
    inkind = state["in_kind_verified_cents"]
    inkind_cap = state["max_in_kind_cents"]
    countable_inkind = min(inkind, inkind_cap)
    countable_match = cash + countable_inkind
    required = state["required_match_cents"]

    return {
        "award_id": state["award_id"],
        "applicant_id": state["applicant_id"],
        "project_id": state["project_id"],
        "cycle_id": state["cycle_id"],
        "category": state["category"],
        "geography": state["geography"],
        "award_cents": state["award_cents"],
        "returned_cents": state["returned_cents"],
        "net_unreturned_award_cents": state["award_cents"] - state["returned_cents"],
        "required_match_cents": required,
        "max_in_kind_cents": inkind_cap,
        "cash_verified_cents": cash,
        "in_kind_verified_cents": inkind,
        "countable_in_kind_cents": countable_inkind,
        "countable_match_cents": countable_match,
        "match_shortfall_cents": max(0, required - countable_match),
        "match_complete": countable_match >= required,
        "commitments": commitments,
        "partners": list(state["partners"]),
        "milestones": list(state["milestones"]),
        "amendments": list(state["amendments"]),
        "returns": list(state["returns"]),
        "closeout_requests": list(state["closeout_requests"]),
    }


def reconcile(
    records: Iterable[dict[str, Any]],
    *,
    signing_key: bytes,
) -> dict[str, Any]:
    """Reconcile approved evidence events into a deterministic signed manifest.

    ``signing_key`` is supplied by the caller and is used only to HMAC the final
    content-addressed manifest. It is never returned or persisted here.
    """
    if not isinstance(signing_key, (bytes, bytearray)) or not signing_key:
        raise EvidenceInputError("signing_key must be non-empty bytes")

    normalized = [_normalize_event(item) for item in records]
    normalized.sort(key=lambda e: (e["sequence"], e["event_id"], _sha256(e)))

    event_fingerprints: dict[str, str] = {}
    sequence_owners: dict[int, str] = {}
    awards: dict[str, dict[str, Any]] = {}
    holds: list[dict[str, Any]] = []
    accepted_event_ids: list[str] = []
    replay_event_ids: list[str] = []

    for event in normalized:
        event_id = event["event_id"]
        event_hash = _sha256(event)

        prior_hash = event_fingerprints.get(event_id)
        if prior_hash is not None:
            if hmac.compare_digest(prior_hash, event_hash):
                replay_event_ids.append(event_id)
                continue
            holds.append(
                _hold(
                    "IDEMPOTENCY_CONFLICT",
                    event_id=event_id,
                    award_id=event["award_id"],
                    message="same event_id was replayed with different content",
                    action="FREEZE",
                )
            )
            continue

        prior_sequence_event = sequence_owners.get(event["sequence"])
        if prior_sequence_event is not None and prior_sequence_event != event_id:
            holds.append(
                _hold(
                    "SEQUENCE_COLLISION",
                    event_id=event_id,
                    award_id=event["award_id"],
                    message=(
                        f"sequence {event['sequence']} already belongs to "
                        f"{prior_sequence_event}"
                    ),
                    action="FREEZE",
                )
            )
            event_fingerprints[event_id] = event_hash
            continue

        event_fingerprints[event_id] = event_hash
        sequence_owners[event["sequence"]] = event_id
        accepted_event_ids.append(event_id)
        event_type = event["event_type"]
        award_id = event["award_id"]
        p = event["payload"]

        if event_type == "AWARD_APPROVED":
            if award_id is None:
                holds.append(
                    _hold(
                        "MISSING_AWARD_ID",
                        event_id=event_id,
                        award_id=None,
                        message="award approval has no award_id",
                        action="FREEZE",
                    )
                )
                continue
            if award_id in awards:
                holds.append(
                    _hold(
                        "DUPLICATE_AWARD",
                        event_id=event_id,
                        award_id=award_id,
                        message="award_id already has an approved state",
                        action="FREEZE",
                    )
                )
                continue
            try:
                applicant_id = _require_text(p.get("applicant_id"), "applicant_id")
                project_id = _require_text(p.get("project_id"), "project_id")
                cycle_id = _require_text(p.get("cycle_id"), "cycle_id")
                category = _require_text(p.get("category"), "category")
                geography = _require_text(p.get("geography"), "geography")
                award_cents = _require_exact_int(
                    p.get("award_cents"), "award_cents", positive=True
                )
                required_match_cents = _require_exact_int(
                    p.get("required_match_cents"),
                    "required_match_cents",
                    positive=True,
                )
                expected_match = _exact_required_match(award_cents)
                if required_match_cents != expected_match:
                    raise EvidenceInputError(
                        "required_match_cents must equal exactly 25% of award_cents"
                    )
                if category not in FOCUS_CATEGORIES:
                    raise EvidenceInputError("category is outside configured focus areas")
                if geography not in ELIGIBLE_GEOGRAPHIES:
                    raise EvidenceInputError(
                        "geography is outside configured funding area"
                    )
                state = _new_award_state(
                    award_id=award_id,
                    applicant_id=applicant_id,
                    project_id=project_id,
                    cycle_id=cycle_id,
                    category=category,
                    geography=geography,
                    award_cents=award_cents,
                    required_match_cents=required_match_cents,
                    approval_id=event_id,
                    sequence=event["sequence"],
                )
            except EvidenceInputError as exc:
                holds.append(
                    _hold(
                        "INVALID_AWARD_APPROVAL",
                        event_id=event_id,
                        award_id=award_id,
                        message=str(exc),
                        action="FREEZE",
                    )
                )
                continue
            awards[award_id] = state
            continue

        if award_id is None or award_id not in awards:
            holds.append(
                _hold(
                    "UNKNOWN_AWARD",
                    event_id=event_id,
                    award_id=award_id,
                    message="event references no approved award",
                    action="FREEZE",
                )
            )
            continue

        state = awards[award_id]

        try:
            if event_type == "MATCH_COMMITMENT":
                commitment_id = _require_text(
                    p.get("commitment_id"), "commitment_id"
                )
                kind = _require_text(p.get("kind"), "kind")
                if kind not in {"cash", "in_kind"}:
                    raise EvidenceInputError("commitment kind must be cash or in_kind")
                committed_cents = _require_exact_int(
                    p.get("committed_cents"),
                    "committed_cents",
                    positive=True,
                )
                source_id = _require_text(p.get("source_id"), "source_id")
                if commitment_id in state["commitments"]:
                    holds.append(
                        _hold(
                            "DUPLICATE_COMMITMENT",
                            event_id=event_id,
                            award_id=award_id,
                            message="commitment_id already exists",
                        )
                    )
                    continue
                valuation_method = p.get("valuation_method")
                evidence_hash = p.get("evidence_hash")
                if kind == "in_kind":
                    valuation_method = _require_text(
                        valuation_method, "valuation_method"
                    )
                    evidence_hash = _require_text(evidence_hash, "evidence_hash")
                state["commitments"][commitment_id] = {
                    "kind": kind,
                    "committed_cents": committed_cents,
                    "realized_cents": 0,
                    "source_id": source_id,
                    "valuation_method": valuation_method,
                    "evidence_hash": evidence_hash,
                    "verified_event_ids": [],
                }

            elif event_type == "CONTRIBUTION_VERIFIED":
                commitment_id = _require_text(
                    p.get("commitment_id"), "commitment_id"
                )
                realized_cents = _require_exact_int(
                    p.get("realized_cents"),
                    "realized_cents",
                    positive=True,
                )
                evidence_hash = _require_text(p.get("evidence_hash"), "evidence_hash")
                reviewer_id = _require_text(p.get("reviewer_id"), "reviewer_id")
                commitment = state["commitments"].get(commitment_id)
                if commitment is None:
                    holds.append(
                        _hold(
                            "UNMATCHED_CONTRIBUTION",
                            event_id=event_id,
                            award_id=award_id,
                            message="verified contribution has no prior commitment",
                        )
                    )
                    continue
                if commitment["realized_cents"] + realized_cents > commitment["committed_cents"]:
                    holds.append(
                        _hold(
                            "OVER_REALIZED_COMMITMENT",
                            event_id=event_id,
                            award_id=award_id,
                            message=(
                                "verified realized amount exceeds committed amount; "
                                "requires named review"
                            ),
                        )
                    )
                    continue
                commitment["realized_cents"] += realized_cents
                commitment["evidence_hash"] = evidence_hash
                commitment["verified_event_ids"].append(event_id)
                if commitment["kind"] == "cash":
                    state["cash_verified_cents"] += realized_cents
                else:
                    state["in_kind_verified_cents"] += realized_cents
                    if state["in_kind_verified_cents"] > state["max_in_kind_cents"]:
                        holds.append(
                            _hold(
                                "IN_KIND_CAP_EXCEEDED",
                                event_id=event_id,
                                award_id=award_id,
                                message=(
                                    "verified in-kind total exceeds 50% of required "
                                    "match; excess is not countable"
                                ),
                            )
                        )
                _ = reviewer_id

            elif event_type == "AMENDMENT_APPROVED":
                amendment_id = _require_text(p.get("amendment_id"), "amendment_id")
                approver_id = _require_text(p.get("approver_id"), "approver_id")
                new_award_cents = _require_exact_int(
                    p.get("new_award_cents"), "new_award_cents", positive=True
                )
                new_required_match_cents = _require_exact_int(
                    p.get("new_required_match_cents"),
                    "new_required_match_cents",
                    positive=True,
                )
                if new_required_match_cents != _exact_required_match(new_award_cents):
                    raise EvidenceInputError(
                        "new_required_match_cents must equal exactly 25% "
                        "of new_award_cents"
                    )
                prior_award = state["award_cents"]
                prior_match = state["required_match_cents"]
                state["award_cents"] = new_award_cents
                state["required_match_cents"] = new_required_match_cents
                state["max_in_kind_cents"] = _max_in_kind(new_required_match_cents)
                state["amendments"].append(
                    {
                        "event_id": event_id,
                        "sequence": event["sequence"],
                        "kind": "APPROVED_AMENDMENT",
                        "amendment_id": amendment_id,
                        "approver_id": approver_id,
                        "prior_award_cents": prior_award,
                        "award_cents": new_award_cents,
                        "prior_required_match_cents": prior_match,
                        "required_match_cents": new_required_match_cents,
                    }
                )
                if state["in_kind_verified_cents"] > state["max_in_kind_cents"]:
                    holds.append(
                        _hold(
                            "IN_KIND_CAP_EXCEEDED_AFTER_AMENDMENT",
                            event_id=event_id,
                            award_id=award_id,
                            message=(
                                "approved amendment lowered the in-kind cap below "
                                "already-verified in-kind evidence"
                            ),
                        )
                    )

            elif event_type == "PARTNER_CHANGED":
                partner_id = _require_text(p.get("partner_id"), "partner_id")
                change = _require_text(p.get("change"), "change")
                if change not in {"added", "removed", "updated"}:
                    raise EvidenceInputError(
                        "partner change must be added, removed, or updated"
                    )
                approval_ref = _require_text(p.get("approval_ref"), "approval_ref")
                state["partners"].append(
                    {
                        "event_id": event_id,
                        "sequence": event["sequence"],
                        "partner_id": partner_id,
                        "change": change,
                        "approval_ref": approval_ref,
                    }
                )

            elif event_type == "MILESTONE_RECORDED":
                milestone_id = _require_text(p.get("milestone_id"), "milestone_id")
                due_on = _require_text(p.get("due_on"), "due_on")
                observed_on = _require_text(p.get("observed_on"), "observed_on")
                evidence_hash = _require_text(p.get("evidence_hash"), "evidence_hash")
                status = _require_text(p.get("status"), "status")
                if status not in {"complete", "partial", "missed"}:
                    raise EvidenceInputError(
                        "milestone status must be complete, partial, or missed"
                    )
                state["milestones"].append(
                    {
                        "event_id": event_id,
                        "sequence": event["sequence"],
                        "milestone_id": milestone_id,
                        "due_on": due_on,
                        "observed_on": observed_on,
                        "status": status,
                        "evidence_hash": evidence_hash,
                    }
                )
                if observed_on > due_on or status != "complete":
                    holds.append(
                        _hold(
                            "MILESTONE_REVIEW_REQUIRED",
                            event_id=event_id,
                            award_id=award_id,
                            message=(
                                "late, partial, or missed milestone remains visible "
                                "for named review"
                            ),
                        )
                    )

            elif event_type == "RETURN_RECORDED":
                return_id = _require_text(p.get("return_id"), "return_id")
                amount_cents = _require_exact_int(
                    p.get("amount_cents"), "amount_cents", positive=True
                )
                evidence_hash = _require_text(p.get("evidence_hash"), "evidence_hash")
                if state["returned_cents"] + amount_cents > state["award_cents"]:
                    holds.append(
                        _hold(
                            "RETURN_EXCEEDS_AWARD",
                            event_id=event_id,
                            award_id=award_id,
                            message="returned funds would exceed approved award",
                            action="FREEZE",
                        )
                    )
                    continue
                state["returned_cents"] += amount_cents
                state["returns"].append(
                    {
                        "event_id": event_id,
                        "sequence": event["sequence"],
                        "return_id": return_id,
                        "amount_cents": amount_cents,
                        "evidence_hash": evidence_hash,
                    }
                )

            elif event_type == "CLOSEOUT_REQUESTED":
                closeout_id = _require_text(p.get("closeout_id"), "closeout_id")
                evidence_hash = _require_text(p.get("evidence_hash"), "evidence_hash")
                state["closeout_requests"].append(
                    {
                        "event_id": event_id,
                        "sequence": event["sequence"],
                        "closeout_id": closeout_id,
                        "evidence_hash": evidence_hash,
                    }
                )
                public = _public_award_state(state)
                if not public["match_complete"]:
                    holds.append(
                        _hold(
                            "MATCH_INCOMPLETE_AT_CLOSEOUT",
                            event_id=event_id,
                            award_id=award_id,
                            message=(
                                "closeout request arrived before countable verified "
                                "match reached the required amount"
                            ),
                        )
                    )

        except EvidenceInputError as exc:
            holds.append(
                _hold(
                    "INVALID_EVENT_PAYLOAD",
                    event_id=event_id,
                    award_id=award_id,
                    message=str(exc),
                    action="FREEZE",
                )
            )

    public_awards = [_public_award_state(awards[key]) for key in sorted(awards)]

    for award in public_awards:
        if award["in_kind_verified_cents"] > award["max_in_kind_cents"]:
            holds.append(
                _hold(
                    "IN_KIND_CAP_EXCEEDED_FINAL",
                    event_id="FINAL",
                    award_id=award["award_id"],
                    message=(
                        "final verified in-kind evidence exceeds permitted "
                        "50% share; excess remains excluded from countable match"
                    ),
                )
            )
        if not award["match_complete"]:
            holds.append(
                _hold(
                    "MATCH_SHORTFALL",
                    event_id="FINAL",
                    award_id=award["award_id"],
                    message=(
                        f"countable match is short by "
                        f"{award['match_shortfall_cents']} cents"
                    ),
                )
            )

    holds.sort(
        key=lambda h: (
            "" if h["award_id"] is None else h["award_id"],
            h["event_id"],
            h["code"],
        )
    )

    cycle_award_cents = sum(a["award_cents"] for a in public_awards)
    cycle_returned_cents = sum(a["returned_cents"] for a in public_awards)
    cycle_required_match_cents = sum(a["required_match_cents"] for a in public_awards)
    cycle_countable_match_cents = sum(a["countable_match_cents"] for a in public_awards)

    body = {
        "schema": "mrhd-impact-match-evidence-v1",
        "authority": {
            "decision_authority": False,
            "human_owner": "MRHD_STAFF_GRANT_REVIEW_COMMITTEE_BOARD",
            "match_rate": "25%",
            "max_in_kind_share_of_required_match": "50%",
        },
        "awards": public_awards,
        "cycle": {
            "award_count": len(public_awards),
            "award_cents": cycle_award_cents,
            "returned_cents": cycle_returned_cents,
            "net_unreturned_award_cents": cycle_award_cents - cycle_returned_cents,
            "required_match_cents": cycle_required_match_cents,
            "countable_match_cents": cycle_countable_match_cents,
            "match_shortfall_cents": max(
                0, cycle_required_match_cents - cycle_countable_match_cents
            ),
        },
        "event_receipt": {
            "accepted_event_ids": sorted(accepted_event_ids),
            "replay_event_ids": sorted(replay_event_ids),
            "accepted_event_count": len(accepted_event_ids),
            "replay_event_count": len(replay_event_ids),
        },
        "holds": holds,
        "disposition": "HOLD" if holds else "PASS",
    }
    digest = hashlib.sha256(_canonical_json(body)).hexdigest()
    signature = hmac.new(bytes(signing_key), _canonical_json(body), hashlib.sha256).hexdigest()
    return {
        **body,
        "manifest_sha256": digest,
        "manifest_hmac_sha256": signature,
    }


def verify_manifest_signature(manifest: dict[str, Any], *, signing_key: bytes) -> bool:
    """Verify the manifest digest and HMAC without mutating the receipt."""
    if not isinstance(manifest, dict):
        return False
    digest = manifest.get("manifest_sha256")
    signature = manifest.get("manifest_hmac_sha256")
    if not isinstance(digest, str) or not isinstance(signature, str):
        return False
    body = {
        key: value
        for key, value in manifest.items()
        if key not in {"manifest_sha256", "manifest_hmac_sha256"}
    }
    expected_digest = hashlib.sha256(_canonical_json(body)).hexdigest()
    expected_signature = hmac.new(
        bytes(signing_key), _canonical_json(body), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(digest, expected_digest) and hmac.compare_digest(
        signature, expected_signature
    )
