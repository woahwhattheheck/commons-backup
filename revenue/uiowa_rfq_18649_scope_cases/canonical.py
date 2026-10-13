"""Pinned RFQ 18649 acceptance-exhibit facts for UIOWA-139 packets.

Source is the published workshare exhibit. This module does not edit it.
Required checks use raise, never assert (python -O safe).
"""

from __future__ import annotations

EXHIBIT_PATH = "revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT.md"
EXHIBIT_BLOB = "48465060fff1402af966871352e894686fffe05e"
COMMERCIAL_PATH = "revenue/uiowa_rfq_18649_workshare/COMMERCIAL.md"

SCHEMA = "uiowa-139-scope-cases/1"

BASELINE = {
    "rfq_id": "18649",
    "currency": "USD",
    "workshare_base_usd": 24000,
    "workshare_option_usd": 4000,
    "status": "PROPOSED_NOT_ACCEPTED",
    "roles": {"principal": "prime", "specialist": "subcontract"},
    "travel_treatment": "excluded_from_base",
    "groups": ("ESS", "RIS", "IAM"),
    "dimensions": ("software", "security", "deployment", "ai_readiness"),
}

# Section 2 commercial triggers. Packets must not rewrite these.
SECTION_2_TRIGGERS = (
    {
        "milestone": "kickoff",
        "share_pct": 40,
        "amount_usd": 9600,
        "trigger": "written_authorization",
        "acceptance_triggered": False,
    },
    {
        "milestone": "draft_technical_work_package",
        "share_pct": 40,
        "amount_usd": 9600,
        "trigger": "delivery",
        "acceptance_triggered": False,
    },
    {
        "milestone": "final_technical_work_package",
        "share_pct": 20,
        "amount_usd": 4800,
        "trigger": "acceptance",
        "acceptance_triggered": True,
    },
)

CLAUSES = {
    "S2_TRIGGERS": {
        "section": "2",
        "title": "Commercial milestones",
        "rule": (
            "Kickoff is written-authorization triggered; draft is delivery "
            "triggered; only the final base milestone is acceptance-triggered. "
            "Artifact cure does not rewrite those triggers."
        ),
    },
    "S3_NO_FABRICATE": {
        "section": "3",
        "title": "Schedule boundary",
        "rule": "Blocked items are identified; unavailable inputs are not fabricated.",
    },
    "S4_5_VENDOR": {
        "section": "4.5",
        "title": "RFQ product/vendor recommendation exclusion",
        "rule": (
            "The assessment must not recommend, rank, shortlist, endorse, "
            "select, or prescribe a specific commercial product or vendor. "
            "Prime direction and ordinary change control cannot widen this."
        ),
    },
    "S5_2_1_TRACE": {
        "section": "5.2.1",
        "title": "Draft traceability",
        "rule": "Every populated technical conclusion traces to one or more source IDs.",
    },
    "S5_2_3_NO_PROMOTE": {
        "section": "5.2.3",
        "title": "No silent promotion",
        "rule": (
            "Missing, stale, conflicting, or untrusted evidence is visibly "
            "bounded and cannot silently promote a cell to a supported state."
        ),
    },
    "S5_2_6_COMMENTS": {
        "section": "5.2.6",
        "title": "Prime review comments",
        "rule": (
            "Comments that correct TJLabs artifact nonconformance are "
            "incorporated; comments that require prime judgment, new evidence, "
            "or scope change are recorded as bounded open items."
        ),
    },
    "S5_3_DISAGREEMENT": {
        "section": "5.3",
        "title": "Final disagreement is not a defect",
        "rule": (
            "A disagreement with a technically supported conclusion is not by "
            "itself an artifact defect. Rejections should identify the affected "
            "artifact and criterion."
        ),
    },
    "S7_CHANGE_CONTROL": {
        "section": "7",
        "title": "Change-control boundary",
        "rule": (
            "The $24,000 base does not silently expand. Additional groups, "
            "new deliverables, onsite/travel, implementation engineering, and "
            "optional readout require separate authorization."
        ),
    },
    "S7_CURE_NOT_SCOPE": {
        "section": "7",
        "title": "Cure is not new scope",
        "rule": (
            "A small correction to a TJLabs-authored artifact that fails an "
            "agreed acceptance criterion is not treated as a new scope item."
        ),
    },
    "S7_VENDOR_NOT_CHANGE": {
        "section": "7",
        "title": "Vendor exclusion is not change-control",
        "rule": (
            "The product/vendor recommendation exclusion cannot be added "
            "merely because the prime asks for it."
        ),
    },
    "S9_PRIME_JUDGMENT": {
        "section": "9",
        "title": "Responsibility boundary",
        "rule": (
            "The prospective prime retains professional judgment, benchmarking "
            "conclusions, final recommendations, University-facing narrative, "
            "and contracting authority."
        ),
    },
    "S10_PROTOCOL": {
        "section": "10",
        "title": "Acceptance protocol and authority ceiling",
        "rule": (
            "TJLabs corrects actual artifact nonconformance, documents a "
            "blocker, or identifies the request as a scope/evidence/judgment "
            "change. Exhibit remains nonbinding until authorized writing."
        ),
    },
}

AUTHORITY = {
    "buyer_contact": False,
    "submission": False,
    "invoice": False,
    "payment": False,
    "revenue": False,
    "scheduling": False,
    "travel": False,
    "auto_accept": False,
    "auto_scope_expand": False,
    "product_vendor_recommendation": False,
}

# Hypothetical incremental catalog, labeled not accepted. Mirrors UIOWA-133
# published numbers without importing that package.
HYPOTHETICAL_CATALOG = {
    "additional_group": {
        "hours": 32,
        "usd": 2400,
        "label": "HYPOTHETICAL / NOT ACCEPTED",
    },
    "new_deliverable_implementation_plan": {
        "hours": 24,
        "usd": 1800,
        "label": "HYPOTHETICAL / NOT ACCEPTED",
    },
}
