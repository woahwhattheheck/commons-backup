#!/usr/bin/env python3
"""Fail-closed validator for the Ingham 112-26 acceptance-workshare package.

No network access or third-party packages are required. The validator checks only
repository-local truth and intentionally cannot turn unknown procurement facts into
positive claims.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "response_readiness.json"

REQUIRED_DOC_TOKENS = {
    "README.md": ["CONTACT_HOLD", "paid specialist", "Single-writer / outreach fence"],
    "SOURCE_LEDGER.md": ["Official current-solicitation facts", "Current unresolved gates", "UNKNOWN"],
    "OPPORTUNITY_AND_WORKSHARE.md": ["paid specialist work package", "Binary technical acceptance criteria", "Explicit exclusions"],
    "ACCEPTANCE_HARNESS.md": ["Duplicate / replay / ambiguous retry", "Case denominator integrity", "Human-review boundary"],
    "INTEGRATION_AND_MEASUREMENT.md": ["Human authority classes", "Data boundary", "Workforce / quality instrumentation"],
    "PREPROPOSAL_BRIEF.md": ["Internal only", "Procurement questions", "Fast partner qualification"],
}

REQUIRED_SOURCE_UNKNOWN = {
    "controlling_rfp_packet",
    "addendum_1",
    "evaluation_criteria",
    "mandatory_forms",
    "price_format",
    "contract_value",
    "vendor_qualifications",
    "insurance_requirements",
    "security_requirements",
    "subcontracting_rules",
}

REQUIRED_COMMERCIAL_UNKNOWN = {
    "eligible_prime_or_allowed_direct_role",
    "mandatory_meeting_gate_satisfied",
    "specialist_workshare_permitted",
    "interested_authorized_partner_or_buyer",
    "selected_workflows",
    "authorized_test_environment",
    "data_classification_and_boundary",
    "security_privacy_owner",
    "operational_acceptance_owner",
    "schedule_and_dependencies",
    "pricing_authority_and_contract_path",
}

REQUIRED_NONCLAIMS = {
    "prime_bidder_status",
    "meeting_attendance_or_registration",
    "proposal_submission_authority",
    "cad_che_or_telephony_prime_capability",
    "live_emergency_operations_authority",
    "autonomous_emergency_dispatch_authority",
    "cjis_hipaa_or_legal_certification",
    "unverified_vendor_qualifications",
    "unverified_client_references",
    "unverified_insurance_or_security_compliance",
    "teaming_acceptance",
    "buyer_acceptance",
    "award",
    "payment",
    "revenue",
}


def validate_state(data: dict) -> list[str]:
    errors: list[str] = []

    if data.get("operation") != "INGHAM-11226-911-ACCEPTANCE-ZSOL13-20260913":
        errors.append("wrong operation id")
    if data.get("solicitation") != "112-26":
        errors.append("wrong solicitation id")
    if data.get("commercial_path") != "PAID_SPECIALIST_ACCEPTANCE_WORKSHARE":
        errors.append("commercial path must remain paid specialist acceptance workshare")

    schedule = data.get("verified_official_schedule", {})
    expected_schedule = {
        "mandatory_preproposal_meeting": "2026-09-17T11:00:00-04:00",
        "questions_deadline": "2026-09-24T15:00:00-04:00",
        "proposal_deadline": "2026-10-15T11:00:00-04:00",
    }
    for key, expected in expected_schedule.items():
        if schedule.get(key) != expected:
            errors.append(f"official schedule mismatch: {key}")

    collision = data.get("collision", {})
    if collision.get("new_external_contact_authorized") is not False:
        errors.append("external contact must remain unauthorized")
    if collision.get("meeting_registration_authorized") is not False:
        errors.append("meeting registration must remain unauthorized")
    if collision.get("proposal_submission_authorized") is not False:
        errors.append("proposal submission must remain unauthorized")
    if collision.get("slack_route_check") != "UNKNOWN_RATE_LIMITED":
        errors.append("Slack collision state cannot be promoted without evidence")
    if collision.get("gmail_route_check") != "UNKNOWN_RATE_LIMITED":
        errors.append("Gmail collision state cannot be promoted without evidence")

    source = data.get("source_gates", {})
    missing_source = REQUIRED_SOURCE_UNKNOWN - set(source)
    if missing_source:
        errors.append(f"missing source gate(s): {sorted(missing_source)}")
    unresolved_source = {k for k in REQUIRED_SOURCE_UNKNOWN if str(source.get(k, "")).startswith("UNKNOWN")}

    commercial = data.get("commercial_gates", {})
    missing_commercial = REQUIRED_COMMERCIAL_UNKNOWN - set(commercial)
    if missing_commercial:
        errors.append(f"missing commercial gate(s): {sorted(missing_commercial)}")
    unresolved_commercial = {k for k in REQUIRED_COMMERCIAL_UNKNOWN if commercial.get(k) == "UNKNOWN"}

    if data.get("state") not in {"CONTACT_HOLD", "CONTACT_READY"}:
        errors.append("state must be CONTACT_HOLD or CONTACT_READY")
    if data.get("proposal_state") not in {"PROPOSAL_HOLD", "PROPOSAL_READY"}:
        errors.append("proposal_state must be PROPOSAL_HOLD or PROPOSAL_READY")

    if data.get("state") == "CONTACT_READY":
        if unresolved_source:
            errors.append(f"CONTACT_READY forbidden while source gates remain unknown: {sorted(unresolved_source)}")
        if unresolved_commercial:
            errors.append(f"CONTACT_READY forbidden while commercial gates remain unknown: {sorted(unresolved_commercial)}")
        if collision.get("external_route_owner") == "UNKNOWN":
            errors.append("CONTACT_READY forbidden while external route owner is unknown")
        if collision.get("new_external_contact_authorized") is not True:
            errors.append("CONTACT_READY requires explicit contact authorization")

    if data.get("proposal_state") == "PROPOSAL_READY":
        if unresolved_source or unresolved_commercial:
            errors.append("PROPOSAL_READY forbidden while required source/commercial facts remain unknown")
        if collision.get("proposal_submission_authorized") is not True:
            errors.append("PROPOSAL_READY requires explicit submission authorization")

    safety = data.get("safety", {})
    forbidden_true = {
        "live_911_intervention_authorized",
        "autonomous_dispatch_authorized",
        "live_record_modification_authorized",
        "production_credentials_authorized",
        "disruptive_live_testing_authorized",
        "restricted_data_publication_authorized",
        "regulatory_certification_claimed",
    }
    for key in forbidden_true:
        if safety.get(key) is not False:
            errors.append(f"safety.{key} must remain false in this generic package")
    if safety.get("default_data") != "SYNTHETIC_OR_PROPERLY_DEIDENTIFIED":
        errors.append("default data boundary changed")

    truth = data.get("commercial_truth", {})
    for key in (
        "price_committed",
        "team_relationship_confirmed",
        "buyer_acceptance_confirmed",
        "award_confirmed",
        "payment_confirmed",
        "revenue_confirmed",
    ):
        if truth.get(key) is not False:
            errors.append(f"commercial_truth.{key} must be false without evidence")

    nonclaims = set(data.get("explicit_nonclaims", []))
    missing_nonclaims = REQUIRED_NONCLAIMS - nonclaims
    if missing_nonclaims:
        errors.append(f"missing explicit nonclaim(s): {sorted(missing_nonclaims)}")

    return errors


def validate_docs() -> list[str]:
    errors: list[str] = []
    for name, tokens in REQUIRED_DOC_TOKENS.items():
        path = ROOT / name
        if not path.is_file():
            errors.append(f"missing required document: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                errors.append(f"{name} missing token {token!r}")
    return errors


def self_test(good: dict) -> list[str]:
    errors: list[str] = []

    bad = copy.deepcopy(good)
    bad["state"] = "CONTACT_READY"
    if not validate_state(bad):
        errors.append("self-test failed: false CONTACT_READY was accepted")

    bad = copy.deepcopy(good)
    bad["proposal_state"] = "PROPOSAL_READY"
    if not validate_state(bad):
        errors.append("self-test failed: false PROPOSAL_READY was accepted")

    bad = copy.deepcopy(good)
    bad["collision"]["new_external_contact_authorized"] = True
    if not validate_state(bad):
        errors.append("self-test failed: external-contact authorization mutation was accepted")

    bad = copy.deepcopy(good)
    bad["safety"]["autonomous_dispatch_authorized"] = True
    if not validate_state(bad):
        errors.append("self-test failed: autonomous-dispatch mutation was accepted")

    bad = copy.deepcopy(good)
    bad["commercial_truth"]["revenue_confirmed"] = True
    if not validate_state(bad):
        errors.append("self-test failed: unsupported revenue mutation was accepted")

    bad = copy.deepcopy(good)
    bad["explicit_nonclaims"].remove("unverified_client_references")
    if not validate_state(bad):
        errors.append("self-test failed: nonclaim removal was accepted")

    return errors


def main() -> int:
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot load {STATE.name}: {exc}")
        return 2

    errors = validate_state(data) + validate_docs() + self_test(data)
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PASS: Ingham 112-26 response carrier is fail-closed and internally consistent")
    print(f"state={data['state']}")
    print(f"proposal_state={data['proposal_state']}")
    print("external_contact_authorized=false")
    print("live_911_intervention_authorized=false")
    print("commercial_path=PAID_SPECIALIST_ACCEPTANCE_WORKSHARE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
