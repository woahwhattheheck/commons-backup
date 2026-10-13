"""Pinned facts for the UIOWA-106 enrollment-period demo.

Synthetic only. Consumes published UIOWA-023/031 field names read-only.
Does not invent a new register contract. Required checks use raise.
"""

from __future__ import annotations

SCHEMA = "uiowa-106-enrollment-demo/1"

COMMERCIAL_BLOB = "b6e9ca58984c15d96b497f3bb51000992fdb9b5f"
GRANITE_REGISTER_PATH = "revenue/uiowa_rfq_18649_evidence_register"
WORKSHARE_023_CSV = (
    "revenue/uiowa_rfq_18649_workshare/methodology/23-synthetic-evidence-register.csv"
)

# Published UIOWA-031 additions; names must match GRANITE exactly.
REGISTER_FIELDS_FROM_023 = [
    "evidence_id",
    "observation_id",
    "finding_id",
    "group",
    "area",
    "source_type",
    "source_ref",
    "custodian_or_owner",
    "content_digest",
    "captured_at",
    "represented_period",
    "claim",
    "scope_limit",
    "directness",
    "recency",
    "representativeness",
    "corroboration",
    "evidence_state",
    "confidence",
    "conflict_group",
    "universe_definition",
    "enumerator_authority",
    "completeness_basis",
    "follow_up",
]
REGISTER_FIELDS_ADDED_BY_031 = ["source_id", "excerpt_locator", "practice_supported"]
REGISTER_FIELDS = REGISTER_FIELDS_FROM_023 + REGISTER_FIELDS_ADDED_BY_031
MANIFEST_FIELDS = [
    "source_id",
    "title",
    "document_location",
    "document_version",
    "owner",
    "supplied_date",
    "source_type",
    "sha256",
    "retention_note",
]

CELLS = (("ESS", "SD"), ("ESS", "DEP"), ("IAM", "SEC"))

AUTHORITY = {
    "buyer_contact": False,
    "live_systems": False,
    "university_finding": False,
    "scheduling": False,
    "outreach": False,
}
