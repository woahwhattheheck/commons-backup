"""Pinned commercial facts for the UIOWA-009 cash-flow model.

Relative weeks only. Does not copy the exhibit deadline paragraph.
Required checks use raise, never assert (python -O safe).
"""

from __future__ import annotations

from decimal import Decimal

SCHEMA = "uiowa-009-cashflow/1"

COMMERCIAL_PATH = "revenue/uiowa_rfq_18649_workshare/COMMERCIAL.md"
COMMERCIAL_BLOB = "b6e9ca58984c15d96b497f3bb51000992fdb9b5f"
# Issue 16092 cited an older exhibit blob. Current published exhibit is
# 48465060…; this model still uses relative weeks and does not copy dates.
EXHIBIT_PATH = "revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT.md"
EXHIBIT_BLOB_CURRENT = "48465060fff1402af966871352e894686fffe05e"

BASE_MILESTONES = (
    {
        "id": "kickoff",
        "share_pct": 40,
        "amount": Decimal("9600.00"),
        "event": "written_authorization",
        "acceptance_triggered": False,
    },
    {
        "id": "draft",
        "share_pct": 40,
        "amount": Decimal("9600.00"),
        "event": "draft_delivery",
        "acceptance_triggered": False,
    },
    {
        "id": "final",
        "share_pct": 20,
        "amount": Decimal("4800.00"),
        "event": "written_final_acceptance",
        "acceptance_triggered": True,
    },
)

BASE_TOTAL = Decimal("24000.00")
OPTIONAL_READOUT = Decimal("4000.00")

ROLES = {"principal": "prime", "specialist": "subcontract"}

AUTHORITY = {
    "buyer_contact": False,
    "submission": False,
    "invoice_live": False,
    "payment": False,
    "revenue": False,
    "bank_access": False,
    "scheduling": False,
    "travel": False,
}

SCENARIOS = ("prompt", "delayed_collection", "extended_final_review")
