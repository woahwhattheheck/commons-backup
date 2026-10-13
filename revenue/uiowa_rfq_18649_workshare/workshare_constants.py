#!/usr/bin/env python3
"""Strict schemas, canonical encoding, and evidence-authority normalization."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from typing import Any

SCHEMA_VERSION = 2
CANDIDATE_SCHEMA = "uiowa-rfq18649-workshare-candidate/v2"
AUTHORITY_SCHEMA = "uiowa-rfq18649-evidence-authority/v2"
REPORT_SCHEMA = "uiowa-rfq18649-workshare-report/v2"
CURRENT_VERIFICATION_SCHEMA = "uiowa-rfq18649-current-verification/v2"

MODE_CURRENT = "CURRENT_TRUSTED_HOST"
MODE_HISTORICAL = "HISTORICAL_NON_CURRENT"
MODE_UNTRUSTED = "UNTRUSTED_INSPECTION"

SOLICITATION_ID = "18649"
BUYER = "University of Iowa"
SUBCONTRACTOR = "TJLabs"
BASE_FEE_USD = 24_000
OPTIONAL_READOUT_USD = 4_000
MAX_EVIDENCE_AGE_SECONDS = 120 * 24 * 60 * 60
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_SOURCES = 256

GROUPS = ("ESS", "RIS", "IAM")
DIMENSIONS = ("software", "security", "deployment", "ai_readiness")
EVIDENCE_KINDS = ("artifact", "demo", "interview", "metric")

_PAYMENT_SCHEDULE_ROWS = (
    ("written authorization / kickoff", 40, 9_600),
    ("draft technical work package", 40, 9_600),
    ("accepted final technical work package", 20, 4_800),
)

_EXTERNAL_AUTHORITY_KEYS = (
    "contact_buyer",
    "submit_university_response",
    "sign_teaming_or_prime_contract",
    "accept_contract_or_award",
    "commit_travel_or_spend",
    "issue_invoice_or_payment_request",
    "claim_payment_or_cash",
    "recognize_revenue",
)

_DELIVERABLE_ROWS = (
    (
        "D1",
        "Evidence map and interview/artifact register",
        "Every source record is rooted to one exact authority generation, AIS group, and assessment dimension.",
    ),
    (
        "D2",
        "Technical maturity and gap matrix",
        "All 12 ESS/RIS/IAM × software/security/deployment/AI-readiness cells are classified; no candidate-authored maturity exists.",
    ),
    (
        "D3",
        "Draft finding and phased-roadmap production support",
        "Only independently rooted, current, non-conflicting source records produce a current maturity finding.",
    ),
    (
        "D4",
        "Reproducibility and currentness receipt",
        "Historical integrity and current authority are distinct; current verification re-evaluates freshness using verifier-owned UTC.",
    ),
)

_PRIME_RETENTION_ROWS = (
    "University relationship and all bidder communications",
    "proposal submission and bidder-of-record responsibility",
    "three comparable client references and reference permissions",
    "insurance and contracting qualifications",
    "final professional judgments, benchmarking conclusions, and recommendations",
    "onsite commitments, travel authorization, staffing promises, and final readout",
)


def _payment_schedule() -> list[dict[str, Any]]:
    return [
        {"milestone": milestone, "percent": percent, "amount_usd": amount}
        for milestone, percent, amount in _PAYMENT_SCHEDULE_ROWS
    ]


def _external_authority() -> dict[str, bool]:
    return {key: False for key in _EXTERNAL_AUTHORITY_KEYS}


def _deliverables() -> list[dict[str, str]]:
    return [
        {"id": item_id, "name": name, "acceptance": acceptance}
        for item_id, name, acceptance in _DELIVERABLE_ROWS
    ]


def _prime_retains() -> list[str]:
    return list(_PRIME_RETENTION_ROWS)

_CANDIDATE_KEYS = {"schema", "engagement", "authority_generation", "source_ids"}
_ENGAGEMENT_KEYS = {
    "solicitation_id",
    "buyer",
    "prime_candidate",
    "subcontractor",
    "base_fee_usd",
    "optional_readout_usd",
}
_AUTHORITY_KEYS = {"schema", "generation", "solicitation_id", "prime_candidate", "sources"}
_SOURCE_KEYS = {
    "source_id",
    "authority_generation",
    "solicitation_id",
    "prime_candidate",
    "group",
    "dimension",
    "evidence_kind",
    "source_ref",
    "source_content_sha256",
    "observed_at",
    "claim",
    "maturity",
    "confidence_bp",
}
_REPORT_KEYS = {
    "schema",
    "schema_version",
    "operation",
    "mode",
    "evaluated_at",
    "max_evidence_age_seconds",
    "candidate",
    "evidence_authority",
    "authority_root_sha256",
    "source_receipts",
    "trust",
    "commercial_terms",
    "deliverables",
    "prime_retains",
    "external_authority",
    "assessment_matrix",
    "status_counts",
    "aggregate_state",
    "receipt_sha256",
}

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")
_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class ContractError(ValueError):
    """Input, report, or filesystem state violates the bounded contract."""

