"""Proposed incremental scope-change catalog for RFQ 18649.

These are planning assumptions, not accepted prices, invoices, or
travel authorizations. The $24,000 baseline is the TJLabs subcontract
workshare, not the prime bid fee.
"""

from __future__ import annotations

BASELINE = {
    "rfq_id": "18649",
    "currency": "USD",
    "workshare_base_usd": 24000,
    "workshare_option_usd": 4000,
    "milestone_split": (40, 40, 20),
    "milestone_amounts_usd": (9600, 9600, 4800),
    "groups": ("ESS", "RIS", "IAM"),
    "dimensions": ("software", "security", "deployment", "ai_readiness"),
    "horizon_weeks": (6, 8),
    "travel_treatment": "excluded_from_base",
    "roles": {"principal": "prime", "specialist": "subcontract"},
    "specialist_hours_in_base": 160,
}

# Incremental specialist hours and proposed USD. Onsite cannot invent travel.
CHANGE_TYPES = {
    "additional_group": {
        "label": "Additional AIS group beyond ESS/RIS/IAM",
        "hours": 32,
        "usd": 2400,
        "travel": False,
        "option": False,
    },
    "extra_interview_cycle": {
        "label": "Extra interview cycle (one group x one dimension)",
        "hours": 12,
        "usd": 900,
        "travel": False,
        "option": False,
    },
    "new_analysis_domain": {
        "label": "New analysis domain outside the 12-cell matrix",
        "hours": 24,
        "usd": 1800,
        "travel": False,
        "option": False,
    },
    "additional_readout": {
        "label": "Additional final-readout support (uses the $4,000 option when qty=1)",
        "hours": 16,
        "usd": 4000,
        "travel": False,
        "option": True,
    },
    "added_onsite_day": {
        "label": "Added onsite day",
        "hours": 8,
        "usd": None,  # cannot invent travel/onsite spend
        "travel": True,
        "option": False,
    },
}

IN_SCOPE_CORRECTION = "in_scope_defect_correction"

AUTHORITY = {
    "buyer_contact": False,
    "submission": False,
    "invoice": False,
    "payment": False,
    "revenue": False,
    "scheduling": False,
    "travel": False,
}
