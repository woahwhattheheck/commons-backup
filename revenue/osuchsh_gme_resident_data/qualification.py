"""Source-pinned current qualification state for the OSU-CHS pursuit.

Trust-bearing bid evidence is deliberately not accepted as a runtime argument.
Changing this opportunity from TEAMING_REQUIRED requires a reviewed source/evidence
change (and composition with the shared bidder-vault/pursuit bridge), not caller input.
"""

from __future__ import annotations

from .core import digest


def _build_current_qualification():
    opportunity_id = "OSUTUL-RFP-001864-2027"
    holds = (
        "CONTROLLING_PACKET_NOT_RETAINED",
        "THREE_SIMILAR_REFERENCES_NOT_EVIDENCED",
        "NON_COLLUSION_OWNER_CONFIRMATION_MISSING",
        "PORTAL_REGISTRATION_NOT_CONFIRMED",
        "PRICING_OWNER_CONFIRMATION_MISSING",
    )
    retained_evidence = {
        "opportunity_id": opportunity_id,
        "controlling_packet_sha256": None,
        "similar_reference_receipt_count": 0,
        "non_collusion_owner_confirmed": False,
        "portal_registration_confirmed": False,
        "pricing_owner_confirmed": False,
    }
    evidence_digest = digest(retained_evidence)

    def current_qualification() -> dict:
        # Build fresh containers so callers cannot mutate future evaluations.
        return {
            "schema": "osuchsh-gme-qualification-v2",
            "opportunity_id": opportunity_id,
            "status": "TEAMING_REQUIRED",
            "holds": list(holds),
            "retained_evidence": dict(retained_evidence),
            "evidence_digest": evidence_digest,
            "submission_authorized": False,
            "buyer_contact_authorized": False,
            "award_or_payment_claimed": False,
        }

    return current_qualification


current_qualification = _build_current_qualification()
del _build_current_qualification
