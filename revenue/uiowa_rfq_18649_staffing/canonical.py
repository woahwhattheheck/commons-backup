"""Pinned staffing-planning facts for UIOWA-002.

Dates are relative weeks. Hours are assumptions, not committed staffing.
Onsite is a subset of productive hours, not additive. Travel excluded.
Required checks use raise, never assert (python -O safe).
"""

from __future__ import annotations

from decimal import Decimal

SCHEMA = "uiowa-002-staffing/1"

COMMERCIAL_PATH = "revenue/uiowa_rfq_18649_workshare/COMMERCIAL.md"
COMMERCIAL_BLOB = "b6e9ca58984c15d96b497f3bb51000992fdb9b5f"
EXHIBIT_PATH = "revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT.md"
EXHIBIT_BLOB = "48465060fff1402af966871352e894686fffe05e"

GROUPS = ("ESS", "RIS", "IAM")
DIMENSIONS = ("software", "security", "deployment", "ai_readiness")
INTERVIEW_SESSIONS = len(GROUPS) * len(DIMENSIONS)  # 12 cells; not headcount

ROLES = {"principal": "prime", "specialist": "subcontract", "university": "buyer_side"}
TRAVEL = "excluded_from_base"
SPECIALIST_DEFAULT_LOCATION = "remote"

# Hypothetical specialist hours reconciling to the published 160h workshare pin.
SPECIALIST_HOURS_IN_BASE = Decimal("160.00")

TASKS = (
    "preparation",
    "evidence_processing",
    "interview_support",
    "synthesis",
    "review",
    "correction",
)

# Onsite is a subset label, never added on top of the productive tasks.
ONSITE_SUBSET_OF = "interview_support"

PARTICIPANT_SCENARIOS = (18, 21, 24)

AUTHORITY = {
    "buyer_contact": False,
    "submission": False,
    "invoice": False,
    "payment": False,
    "scheduling": False,
    "travel": False,
    "staffing_commitment": False,
}
