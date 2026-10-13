from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

INPUT_SCHEMA = "legal-aid-ai-architecture-rfi-input/v1"
PACKET_SCHEMA = "legal-aid-ai-architecture-rfi-packet/v1"
RECEIPT_SCHEMA = "legal-aid-ai-architecture-rfi-receipt/v1"

RFI_URL = "https://www.lsntap.org/sites/default/files/2026-08/request-for-information-ai-architecture.pdf"
RFI_LISTING_URL = "https://www.lsntap.org/jobs-rfps/rfi-ai-architecture-governance-and-security-consulting-services"
RESPONSE_EMAIL = "aiarchitecture@legalaidchicago.org"
SUBJECT_LINE = "RFI Response – AI Architecture, Planning, and Governance Consulting"
DEADLINE_DATE = "2026-09-30"
QUESTION_COUNT = 31

EVIDENCE_KINDS = {"BUYER", "OWNER", "PROVIDER", "PUBLIC", "REPO"}
ANSWER_STATUSES = {"ANSWERED", "NOT_APPLICABLE", "OWNER_INPUT_REQUIRED"}
PRICING_OPTIONS = {
    "AI_READINESS_ONLY",
    "GOVERNANCE_POLICY_ONLY",
    "ARCHITECTURE_VENDOR_STRATEGY_ONLY",
    "FULL_PLANNING_ENGAGEMENT",
}
PRICING_MODELS = {"FIXED_FEE", "TIME_AND_MATERIALS", "MILESTONE", "BLENDED", "ROLE_HOURLY", "OTHER"}
CURRENCY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,7}$")

SECTION_TITLES = {
    "A": "Vendor Profile and Qualifications",
    "B": "Relevant Experience",
    "C": "Proposed Approach",
    "D": "Governance, Privacy, Security, and Risk Management",
    "E": "Staffing and Team Structure",
    "F": "Timeline and Level of Effort",
    "G": "Estimated Costs",
    "H": "Deliverables and Documentation",
    "I": "References",
}

# The key strings are concise, non-substitutive identifiers for the buyer's 31
# questions. They intentionally do not reproduce the RFI prose.
QUESTION_SPECS = (
    ("Q01", "A", "company_name_hq_year", False, {"OWNER", "PUBLIC"}),
    ("Q02", "A", "firm_overview_core_services", False, {"OWNER", "PUBLIC"}),
    ("Q03", "A", "relevant_ai_governance_architecture_security_sector_experience", False, {"OWNER", "PUBLIC", "PROVIDER"}),
    ("Q04", "A", "firm_size_ai_consulting_staff", False, {"OWNER", "PUBLIC"}),
    ("Q05", "A", "prime_subcontractor_posture", False, {"OWNER"}),
    ("Q06", "A", "subcontractor_use_and_functions", False, {"OWNER"}),
    ("Q07", "B", "up_to_five_comparable_projects", True, {"OWNER", "PUBLIC", "PROVIDER"}),
    ("Q08", "B", "comparable_project_details", True, {"OWNER", "PUBLIC", "PROVIDER"}),
    ("Q09", "C", "recommended_planning_methodology", False, {"OWNER", "REPO", "PUBLIC", "BUYER"}),
    ("Q10", "C", "direct_vs_partner_activities", False, {"OWNER", "REPO"}),
    ("Q11", "C", "client_information_access_participation_needs", False, {"OWNER", "REPO", "PUBLIC", "BUYER"}),
    ("Q12", "C", "risks_dependencies_common_barriers", False, {"OWNER", "REPO", "PUBLIC", "BUYER"}),
    ("Q13", "C", "typical_deliverables", False, {"OWNER", "REPO", "PUBLIC", "BUYER"}),
    ("Q14", "D", "ai_governance_framework_experience", False, {"OWNER", "PUBLIC", "PROVIDER", "REPO"}),
    ("Q15", "D", "confidentiality_privacy_security_bias_risk_evaluation", False, {"OWNER", "PUBLIC", "REPO"}),
    ("Q16", "D", "risk_security_governance_frameworks_used", False, {"OWNER", "PUBLIC", "REPO"}),
    ("Q17", "D", "third_party_ai_vendor_due_diligence", False, {"OWNER", "PUBLIC", "REPO"}),
    ("Q18", "D", "sensitive_confidential_client_data_environment_experience", True, {"OWNER", "PUBLIC", "PROVIDER"}),
    ("Q19", "E", "assigned_team_roles_expertise_experience_employment", False, {"OWNER"}),
    ("Q20", "E", "project_lead_qualifications", False, {"OWNER"}),
    ("Q21", "E", "team_expertise_coverage", False, {"OWNER"}),
    ("Q22", "F", "recommended_project_duration", False, {"OWNER", "REPO", "PUBLIC"}),
    ("Q23", "F", "major_project_phases_workstreams", False, {"OWNER", "REPO", "PUBLIC"}),
    ("Q24", "F", "scope_schedule_budget_assumptions", False, {"OWNER", "REPO", "PUBLIC"}),
    ("Q25", "G", "nonbinding_cost_ranges_by_option", True, {"OWNER"}),
    ("Q26", "G", "pricing_model", False, {"OWNER"}),
    ("Q27", "G", "hourly_rate_ranges_if_used", True, {"OWNER"}),
    ("Q28", "G", "principal_cost_drivers_optional_items", False, {"OWNER"}),
    ("Q29", "G", "cost_estimate_assumptions", False, {"OWNER"}),
    ("Q30", "H", "comparable_deliverable_examples_or_descriptions", True, {"OWNER", "REPO", "PUBLIC", "PROVIDER"}),
    ("Q31", "I", "two_or_three_similar_client_references_if_available", True, {"OWNER", "PROVIDER"}),
)
QUESTION_BY_ID = {
    qid: {
        "question_id": qid,
        "section": section,
        "key": key,
        "allow_not_applicable": allow_na,
        "allowed_evidence_kinds": frozenset(kinds),
    }
    for qid, section, key, allow_na, kinds in QUESTION_SPECS
}

METHODOLOGY_BLUEPRINT = (
    "readiness_and_use_case_inventory",
    "data_classification_and_information_handling",
    "governance_risk_and_human_oversight",
    "secure_architecture_identity_access_retention_logging",
    "vendor_due_diligence_and_procurement_strategy",
    "phased_implementation_training_and_evaluation_roadmap",
)

VENDOR_DUE_DILIGENCE_DOMAINS = (
    "model_training_and_customer_data_use",
    "data_retention_and_deletion",
    "subprocessors_and_supply_chain",
    "security_audits_and_certifications",
    "incident_response_and_breach_notification",
    "access_controls_and_administrative_privileges",
)

AUTHORITY = {
    "buyer_contact_authorized": False,
    "rfi_submission_authorized": False,
    "pricing_commitment_authorized": False,
    "legal_compliance_conclusion_authorized": False,
    "security_certification_claim_authorized": False,
    "contract_acceptance_authorized": False,
    "award_claim_authorized": False,
    "invoice_or_payment_mutation_authorized": False,
    "revenue_recognition_authorized": False,
}


class RFIError(ValueError):
    pass


def _reject_float(token: str) -> None:
    raise RFIError(f"floats/non-finite numbers are forbidden: {token}")


def _parse_int(token: str) -> int:
    digits = token[1:] if token.startswith("-") else token
    if len(digits) > 128:
        raise RFIError("integer token too long")
    return int(token)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise RFIError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: str) -> Any:
    if not isinstance(raw, str):
        raise RFIError("JSON source must be text")
    try:
        return json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_int=_parse_int,
            parse_constant=_reject_float,
        )
    except RFIError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise RFIError(f"invalid JSON: {exc}") from None


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n"
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise RFIError(f"cannot canonicalize: {exc}") from None


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _public_question_manifest() -> list[dict[str, Any]]:
    return [
        {
            "question_id": qid,
            "section": section,
            "key": key,
            "allow_not_applicable": allow_na,
            "allowed_evidence_kinds": sorted(kinds),
        }
        for qid, section, key, allow_na, kinds in QUESTION_SPECS
    ]


REQUIREMENT_MANIFEST = {
    "buyer": "Legal Aid Chicago",
    "document_url": RFI_URL,
    "listing_url": RFI_LISTING_URL,
    "response_email": RESPONSE_EMAIL,
    "subject_line": SUBJECT_LINE,
    "deadline_date": DEADLINE_DATE,
    "question_count": QUESTION_COUNT,
    "questions": _public_question_manifest(),
    "vendor_due_diligence_domains": list(VENDOR_DUE_DILIGENCE_DOMAINS),
}
REQUIREMENT_MANIFEST_SHA256 = _sha256(REQUIREMENT_MANIFEST)


def source_binding() -> dict[str, Any]:
    return {
        "document_url": RFI_URL,
        "response_email": RESPONSE_EMAIL,
        "subject_line": SUBJECT_LINE,
        "deadline_date": DEADLINE_DATE,
        "question_count": QUESTION_COUNT,
        "requirement_manifest_sha256": REQUIREMENT_MANIFEST_SHA256,
    }
