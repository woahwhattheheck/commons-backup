#!/usr/bin/env python3
"""Fail-closed validator for the TTUHSC/Keywell response-readiness carrier.

No network access or third-party packages are required.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "response_readiness.json"
REQUIRED_DOCS = {
    "README.md": ["HOLD_FOR_PARTNER_FACTS", "paid", "single-writer"],
    "KEYWELL_WORKSTREAM.md": ["Commercial basis", "Binary acceptance criteria", "Explicit exclusions"],
    "ACCEPTANCE_HARNESS.md": ["Duplicate / retry", "Human approval boundary", "Pilot-ready gate"],
    "RACI_SECURITY_ROI.md": ["RACI boundary", "Security and data-handling boundary", "ROI and adoption instrumentation"],
    "SOURCE_LEDGER.md": ["Controlling solicitation text", "Reconciled discrepancy", "Source-currentness rule"],
}

REQUIRED_UNKNOWN_FACTS = {
    "keywell_pursuing_rfp",
    "keywell_procurement_eligibility",
    "prebid_or_addenda_gate_satisfied_if_required",
    "keywell_accepts_tjlabs_work_package",
    "selected_workflows",
    "authorized_environment",
    "security_privacy_owner",
    "production_data_boundary",
    "prime_reference_owner",
    "prime_vethub_owner",
    "prime_bidder_compliance_owner",
    "schedule_and_dependencies",
    "pricing_authority_and_contract_path",
}

FORBIDDEN_CLAIMS = {
    "prime_bidder_status",
    "three_qualifying_client_references",
    "healthcare_or_legal_compliance_certification",
    "vethub_plan_ownership",
    "tx_ramp_status",
    "texas_franchise_tax_status",
    "insurance_sufficiency",
    "proposal_submission_authority",
    "clinical_decision_authority",
    "teaming_acceptance",
    "award",
    "payment",
    "revenue",
}


def validate_state(data: dict) -> list[str]:
    errors: list[str] = []

    if data.get("rfp") != "739-SL3821039":
        errors.append("wrong RFP identifier")

    outreach = data.get("outreach_policy", {})
    if outreach.get("new_external_contact_authorized") is not False:
        errors.append("new external contact must remain unauthorized")
    if outreach.get("duplicate_outreach_forbidden") is not True:
        errors.append("duplicate outreach fence must remain enabled")

    commercial = data.get("commercial", {})
    for key in ("price_committed", "team_relationship_confirmed", "award_confirmed", "revenue_confirmed"):
        if commercial.get(key) is not False:
            errors.append(f"commercial.{key} must be false without evidence")
    if commercial.get("path") != "PAID_SUBCONTRACT_WORK_PACKAGE":
        errors.append("commercial path must remain paid subcontract work package")

    facts = data.get("required_partner_facts", {})
    missing_fact_keys = REQUIRED_UNKNOWN_FACTS - set(facts)
    if missing_fact_keys:
        errors.append(f"missing required partner fact keys: {sorted(missing_fact_keys)}")
    unknown = {key for key in REQUIRED_UNKNOWN_FACTS if facts.get(key) == "UNKNOWN"}
    if data.get("state") == "READY" and unknown:
        errors.append(f"READY forbidden while partner facts remain UNKNOWN: {sorted(unknown)}")
    if data.get("state") not in {"HOLD_FOR_PARTNER_FACTS", "READY"}:
        errors.append("state must be HOLD_FOR_PARTNER_FACTS or READY")

    exclusions = set(data.get("tjlabs_does_not_claim", []))
    missing_exclusions = FORBIDDEN_CLAIMS - exclusions
    if missing_exclusions:
        errors.append(f"missing explicit non-claim(s): {sorted(missing_exclusions)}")

    rfp = data.get("controlling_base_rfp", {})
    if rfp.get("written_question_deadline") != "2026-08-21":
        errors.append("base-RFP written-question deadline must be 2026-08-21")
    if rfp.get("service_specifications_weight_pct") != 55:
        errors.append("service specification weight must be 55")
    if rfp.get("pricing_weight_pct") != 30:
        errors.append("pricing weight must be 30")
    if rfp.get("experience_reputation_weight_pct") != 15:
        errors.append("experience/reputation weight must be 15")
    if rfp.get("vethub_plan_required") is not True:
        errors.append("VetHUB requirement must remain explicit")

    return errors


def validate_docs() -> list[str]:
    errors: list[str] = []
    for name, tokens in REQUIRED_DOCS.items():
        path = ROOT / name
        if not path.is_file():
            errors.append(f"missing required document: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                errors.append(f"{name} missing required token: {token!r}")
    return errors


def run_self_test(good: dict) -> list[str]:
    errors: list[str] = []

    bad = copy.deepcopy(good)
    bad["state"] = "READY"
    if not any("READY forbidden" in item for item in validate_state(bad)):
        errors.append("self-test failed: false READY state was accepted")

    bad = copy.deepcopy(good)
    bad["outreach_policy"]["new_external_contact_authorized"] = True
    if not validate_state(bad):
        errors.append("self-test failed: duplicate-contact fence mutation was accepted")

    bad = copy.deepcopy(good)
    bad["commercial"]["award_confirmed"] = True
    if not validate_state(bad):
        errors.append("self-test failed: unsupported award mutation was accepted")

    bad = copy.deepcopy(good)
    bad["tjlabs_does_not_claim"].remove("three_qualifying_client_references")
    if not validate_state(bad):
        errors.append("self-test failed: unsupported reference non-claim removal was accepted")

    return errors


def main() -> int:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot load {STATE_PATH.name}: {exc}")
        return 2

    errors = validate_state(data) + validate_docs() + run_self_test(data)
    if errors:
        print("FAIL")
        for item in errors:
            print(f"- {item}")
        return 1

    print("PASS: TTUHSC/Keywell response-readiness carrier is fail-closed and internally consistent")
    print(f"state={data['state']}")
    print("external_contact_authorized=false")
    print("commercial_path=PAID_SUBCONTRACT_WORK_PACKAGE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
