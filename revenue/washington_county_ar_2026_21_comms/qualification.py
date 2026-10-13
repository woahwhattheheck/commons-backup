"""Fail-closed qualification gate for Washington County AR BID 2026-21.

This module never submits, signs, prices, or represents partner/customer facts. It only
classifies supplied evidence against source-bound mandatory gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

PACKET_SHA256 = "930817f2052fc6fcc1616f2ee1ed5cb1352695e0b1635ab662a844e28a18c15f"
REQUIRED_TECHNICAL = {
    "one_platform",
    "unified_constituent_record",
    "live_record_lookup",
    "identity_gate",
    "voice_sms",
    "voice_email_case_continuity",
    "voice_case_transcript_summary",
    "automatic_language_detection",
    "live_chat_escalation",
    "availability_queue",
    "chat_to_email_case",
    "native_email_case_management",
    "agency_domain_email_auth",
    "cama_read_integration",
    "legacy_read_only_integration",
    "ten_business_day_two_channel_review",
    "historical_inquiry_validation",
}
REQUIRED_PRICING = {
    "year_one_implementation_cents",
    "annual_subscription_cents",
    "overage_rate",
    "additional_license_rate",
    "sms_rate",
    "year_one_total_cents",
    "concurrent_session_cap",
}

class EvidenceError(ValueError):
    pass


def _load_no_duplicates(path: Path) -> dict[str, Any]:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in pairs:
            if k in out:
                raise EvidenceError(f"duplicate key: {k}")
            out[k] = v
        return out
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=hook)
    if not isinstance(value, dict):
        raise EvidenceError("top-level evidence must be an object")
    return value


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _verified_project(project: Any) -> bool:
    if not isinstance(project, dict):
        return False
    needed = ("jurisdiction", "start_date", "end_date", "scope", "channels", "evidence_url")
    return all(_nonempty_string(project.get(k)) for k in needed) and project.get("completed") is True


def _verified_integration(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    needed = ("client", "system_of_record", "production_date", "approach", "reference_or_evidence")
    return all(_nonempty_string(item.get(k)) for k in needed) and item.get("production") is True


def evaluate(e: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    warnings: list[str] = []

    if e.get("schema_version") != 1:
        reasons.append("E_SCHEMA_VERSION")
    if e.get("packet_sha256") != PACKET_SHA256:
        reasons.append("E_PACKET_DIGEST")

    legal_entity = _nonempty_string(e.get("legal_entity"))
    signer = _nonempty_string(e.get("authorized_signer"))
    prime = _nonempty_string(e.get("prime_candidate"))
    partner_authorized = e.get("partner_authorized") is True

    technical = e.get("technical_support")
    if not isinstance(technical, dict):
        technical = {}
    missing_technical = sorted(k for k in REQUIRED_TECHNICAL if technical.get(k) is not True)
    if missing_technical:
        reasons.append("E_TECHNICAL_SUPPORT")

    projects = e.get("five_project_matrix")
    if not isinstance(projects, list):
        projects = []
    project_count = sum(_verified_project(p) for p in projects)
    if project_count < 5:
        reasons.append("E_FIVE_PROJECTS")

    integrations = e.get("system_of_record_integrations")
    if not isinstance(integrations, list):
        integrations = []
    integration_count = sum(_verified_integration(i) for i in integrations)
    if integration_count < 1:
        reasons.append("E_PRODUCTION_SOR_INTEGRATION")

    lead = e.get("implementation_lead")
    if not (isinstance(lead, dict) and _nonempty_string(lead.get("name")) and _nonempty_string(lead.get("evidence")) and lead.get("similar_government_deployment") is True):
        reasons.append("E_IMPLEMENTATION_LEAD")

    vpat = e.get("vpat")
    if not (isinstance(vpat, dict) and _nonempty_string(vpat.get("document")) and vpat.get("wcag_2_1_aa") is True):
        reasons.append("E_VPAT")

    if not _nonempty_string(e.get("insurance_letter")):
        reasons.append("E_INSURANCE_LETTER")
    if not _nonempty_string(e.get("proof_of_insurance")):
        reasons.append("E_PROOF_INSURANCE")
    if e.get("boycott_certification_authorized") is not True:
        reasons.append("E_BOYCOTT_CERT_AUTH")

    if not _nonempty_string(e.get("telephony_registration_plan")):
        reasons.append("E_TELEPHONY_REGISTRATION_PLAN")
    if not isinstance(e.get("supported_languages"), list) or not e.get("supported_languages"):
        reasons.append("E_SUPPORTED_LANGUAGES")
    if not _nonempty_string(e.get("language_fallback")):
        reasons.append("E_LANGUAGE_FALLBACK")

    pricing = e.get("pricing")
    if not isinstance(pricing, dict):
        pricing = {}
    if pricing.get("voice_capacity_interactions") != 50000:
        reasons.append("E_VOICE_CAPACITY")
    missing_pricing = sorted(k for k in REQUIRED_PRICING if pricing.get(k) is None)
    if missing_pricing:
        reasons.append("E_PRICING")
    for money_key in ("year_one_implementation_cents", "annual_subscription_cents", "year_one_total_cents"):
        value = pricing.get(money_key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            reasons.append(f"E_PRICE_TYPE_{money_key.upper()}")

    if e.get("all_known_addenda_acknowledged") is not True:
        reasons.append("E_ADDENDA")
    if not legal_entity:
        reasons.append("E_LEGAL_ENTITY")
    if not signer:
        reasons.append("E_AUTHORIZED_SIGNER")

    if e.get("submission_authorized") is True:
        warnings.append("W_SUBMISSION_AUTHORITY_IS_EXTERNAL_TO_THIS_GATE")

    reasons = sorted(set(reasons))
    technical_partner_gap = any(code in reasons for code in (
        "E_TECHNICAL_SUPPORT", "E_FIVE_PROJECTS", "E_PRODUCTION_SOR_INTEGRATION",
        "E_IMPLEMENTATION_LEAD", "E_VPAT"
    ))

    if not prime:
        posture = "HOLD_PRIME_OR_PARTNER"
    elif not partner_authorized:
        posture = "HOLD_PARTNER_CONFIRMATION"
    elif reasons:
        posture = "HOLD_EVIDENCE_AND_COMMERCIAL_GATES"
    else:
        posture = "READY_FOR_OWNER_SUBMISSION_REVIEW"

    if technical_partner_gap and not partner_authorized:
        commercial_route = "TEAM_WITH_EVIDENCED_GOVTECH_PRIME"
    elif technical_partner_gap:
        commercial_route = "PARTNER_EVIDENCE_INCOMPLETE"
    else:
        commercial_route = "PRIME_OR_TEAM_ROUTE_EVIDENCE_COMPLETE"

    return {
        "schema_version": 1,
        "solicitation": "BID 2026-21",
        "packet_sha256": PACKET_SHA256,
        "posture": posture,
        "commercial_route": commercial_route,
        "reason_codes": reasons,
        "missing_technical": missing_technical,
        "verified_project_count": project_count,
        "verified_production_sor_integration_count": integration_count,
        "warnings": warnings,
        "submission_authorized_by_gate": False,
    }


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    evidence = _load_no_duplicates(args.evidence)
    report = evaluate(evidence)
    digest = hashlib.sha256(canonical_bytes(report)).hexdigest()
    print(json.dumps({"report": report, "report_sha256": digest}, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
