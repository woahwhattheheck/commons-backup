"""Pinned commercial facts for University of Iowa RFQ 18649.

These values are the cross-document authority for UIOWA-132. They are
not buyer acceptance, a submitted bid, an invoice, or revenue.
"""

from __future__ import annotations

CANONICAL = {
    "schema": "uiowa-rfq-18649-commercial-facts/v1",
    "rfq_id": "18649",
    "currency": "USD",
    "deadline_date": "2026-09-22",
    "deadline_local": "2026-09-22 15:00",
    "deadline_timezone": "America/Chicago",
    "deadline_iso": "2026-09-22T15:00:00-05:00",
    "base_amount_usd": 24000,
    "option_amount_usd": 4000,
    "option_label": "readout_option",
    "option_included_in_base": False,
    "milestone_split": (40, 40, 20),
    "milestone_amounts_usd": (9600, 9600, 4800),
    "milestone_names": ("kickoff", "draft_delivery", "final_acceptance"),
    "milestone_triggers": ("commencement", "draft_delivery", "acceptance"),
    "kickoff_assumption": "after_award_no_travel",
    "travel_treatment": "excluded_from_base",
    "roles": {
        "principal": "prime",
        "specialist": "subcontract",
    },
    "deliverable_labels": {
        "kickoff": "kickoff packet",
        "draft": "draft delivery packet",
        "final": "final acceptance packet",
    },
    "authority": {
        "buyer_contact": False,
        "submission": False,
        "invoice": False,
        "payment": False,
        "revenue": False,
        "scheduling": False,
    },
}

STALE_SEPTEMBER_22_TOKENS = (
    "september 22, 2025",
    "22 september 2025",
    "sep 22, 2025",
    "9/22/2025",
    "2025-09-22",
)
