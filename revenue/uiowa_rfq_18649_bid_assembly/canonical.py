"""Pinned assembly facts for University of Iowa RFQ 18649.

Consumes landed UIOWA-132 commercial-facts when that sibling package is
present. Local pins must match; divergence is a CURRENTNESS hold, not a
silent overwrite. These values are not buyer acceptance, a submitted
bid, an invoice, or revenue.
"""

from __future__ import annotations

import importlib.util
import os

# TJLabs subcontract workshare. Attribute 9's all-inclusive prime bid
# fee is a different number and is not supplied here.
WORKSHARE_BASE_USD = 24000
WORKSHARE_OPTION_USD = 4000
WORKSHARE_SPLIT = (40, 40, 20)
WORKSHARE_AMOUNTS_USD = (9600, 9600, 4800)

# Printed on the recovered Bid Invitation. Workshare overlay is 29 Sep.
RFQ_PRINTED_DEADLINE = "2026-09-22 15:00 America/Chicago"
WORKSHARE_OVERLAY_DEADLINE = "2026-09-29 15:00 America/Chicago"

PINNED_COMMERCIAL = {
    "schema": "uiowa-rfq-18649-commercial-facts/v1",
    "rfq_id": "18649",
    "currency": "USD",
    "deadline_date": "2026-09-22",
    "deadline_local": "2026-09-22 15:00",
    "deadline_timezone": "America/Chicago",
    "deadline_iso": "2026-09-22T15:00:00-05:00",
    "base_amount_usd": WORKSHARE_BASE_USD,
    "option_amount_usd": WORKSHARE_OPTION_USD,
    "option_label": "readout_option",
    "option_included_in_base": False,
    "milestone_split": WORKSHARE_SPLIT,
    "milestone_amounts_usd": WORKSHARE_AMOUNTS_USD,
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
}

AUTHORITY = {
    "buyer_contact": False,
    "submission": False,
    "invoice": False,
    "payment": False,
    "revenue": False,
    "scheduling": False,
    "qualification_certification": False,
}

REQUIRED_ATTACHMENTS = (
    {
        "id": "ATT-PROP-01",
        "title": "Detailed proposal (Attribute 9)",
        "category": "proposal",
        "required": True,
        "rfq_attr": "9",
    },
    {
        "id": "ATT-FIN-01",
        "title": "Audited financial statements, preceding two years (Attribute 19)",
        "category": "financial",
        "required": True,
        "rfq_attr": "19",
    },
    {
        "id": "ATT-FIN-02",
        "title": "Annual reports, preceding two years (Attribute 19)",
        "category": "financial",
        "required": True,
        "rfq_attr": "19",
    },
    {
        "id": "ATT-QUAL-01",
        "title": "Key personnel resumes (Attribute 10/11)",
        "category": "qualification",
        "required": True,
        "rfq_attr": "10",
    },
    {
        "id": "ATT-QUAL-02",
        "title": "References / comparable engagements",
        "category": "qualification",
        "required": True,
        "rfq_attr": "11",
    },
    {
        "id": "ATT-FEE-01",
        "title": "Prime all-inclusive Fee for Services (Attribute 9 / Bid Line 1)",
        "category": "financial",
        "required": True,
        "rfq_attr": "9",
    },
)

FORBIDDEN_STATUS_TOKENS = (
    "approved",
    "submitted",
    "accepted",
    "awarded",
    "signed",
    "authorized-to-submit",
)

FICTION_NOTICE = (
    "REVIEW DRAFT ONLY. This folder is an internal assembly of prepared "
    "components. It is not a University of Iowa submission, not Clark's "
    "Consulting's bid, not an assertion of qualifications or insurance, "
    "and not an invoice, payment, or schedule. Missing financial and "
    "qualification attachments remain missing."
)


def _load_landed_commercial_facts():
    here = os.path.dirname(os.path.abspath(__file__))
    sibling = os.path.normpath(
        os.path.join(here, "..", "uiowa_rfq_18649_commercial_facts", "canonical.py")
    )
    if not os.path.isfile(sibling):
        return None, sibling
    spec = importlib.util.spec_from_file_location(
        "uiowa_rfq_18649_commercial_facts.canonical", sibling
    )
    if spec is None or spec.loader is None:
        return None, sibling
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "CANONICAL", None), sibling


def commercial_facts():
    """Return (facts, source, mismatch_keys).

    mismatch_keys is empty when the landed 132 package is absent or when
    every pinned key matches. A mismatch is a hold, not a rewrite.
    """
    landed, path = _load_landed_commercial_facts()
    if landed is None:
        return dict(PINNED_COMMERCIAL), "pinned-local", ()
    mismatch = []
    for key, value in PINNED_COMMERCIAL.items():
        if key == "schema":
            continue
        if key not in landed or landed[key] != value:
            mismatch.append(key)
    return dict(landed), path, tuple(mismatch)
