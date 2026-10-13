#!/usr/bin/env python3
"""Fail-closed verifier for the UT Austin 721-27005 pursuit carrier."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_MANIFEST = "tjlabs.ut_austin_721_27005.pursuit_manifest.v1"
SCHEMA_QUAL = "tjlabs.ut_austin_721_27005.qualification.v1"

MANDATORY_SOURCE_IDS = {"txsmartbuy", "bonfire"}
EXPECTED = {
    "solicitation_number": "721-27005",
    "portal_opportunity_id": "250679",
    "intent_to_bid_deadline": "2026-09-28T12:00:00-05:00",
    "submission_deadline": "2026-09-28T14:30:00-05:00",
    "question_deadline": "2026-09-14T14:30:00-05:00",
}
REQUIRED_ARTIFACTS = {
    "Execution of Offer Form",
    "Detailed Pricing Per Phase - BidTable 1",
    "Pricing for Optional Services - BidTable 2",
    "Total Cost of Proposed Services",
    "Terms and Conditions / Exceptions Disposition",
    "Renewal Pricing",
    "Cover Letter",
    "Appendix One - Execution of Offer",
    "Addenda Acknowledgement",
    "Price List and Additional/Related Services",
    "Qualifications, Abilities, and Reputation",
    "Comparable Project Experience",
    "Curated Portfolio",
    "Quality of Proposed Services",
    "Proposed Approach and Timeline",
    "Implementation Artifact Sample",
    "Projects We Admire",
    "Ability to Meet University's Needs",
    "Pricing and Delivery Schedule",
    "Cancellation Policy",
    "Staffing Resources and Past Business Relationship",
    "Company and Financial Information Questionnaire",
    "Vendor Product Security Assessment",
    "Response to EIR Specifications",
    "Response to Information Security Requirements and Questions",
    "Execution & Upload of Proposal Schedule",
}
PRIME_GATES = (
    "authorized_signatory",
    "comparable_project_experience",
    "curated_ux_portfolio",
    "named_staffing_commitments",
    "authorized_pricing",
    "company_financial_questionnaire",
    "vendor_product_security_assessment",
    "eir_response",
    "information_security_response",
    "terms_exceptions_disposition",
    "addenda_verified",
)
ALLOWED_EVIDENCE_STATUS = {"VERIFIED", "MISSING", "OWNER_ONLY", "NOT_APPLICABLE"}
FORBIDDEN_ACTION_KEYS = (
    "buyer_contact",
    "partner_contact",
    "portal_registration",
    "intent_to_bid",
    "terms_acceptance",
    "signature",
    "submission",
    "spend",
    "award_or_revenue_claim",
)

class VerificationError(ValueError):
    pass

def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{path}: unreadable JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise VerificationError(f"{path}: root must be an object")
    return data

def _verified(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("status") != "VERIFIED":
        return False
    refs = entry.get("refs")
    return isinstance(refs, list) and bool(refs) and all(isinstance(x, str) and x.strip() for x in refs)

def verify(manifest: dict[str, Any], qualification: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []

    if manifest.get("schema") != SCHEMA_MANIFEST:
        errors.append("manifest schema mismatch")
    if qualification.get("schema") != SCHEMA_QUAL:
        errors.append("qualification schema mismatch")

    opp = manifest.get("opportunity")
    if not isinstance(opp, dict):
        errors.append("manifest opportunity missing")
        opp = {}
    for key, expected in EXPECTED.items():
        if opp.get(key) != expected:
            errors.append(f"opportunity.{key} must equal {expected!r}")

    sources = manifest.get("sources")
    if not isinstance(sources, list):
        errors.append("sources must be a list")
        sources = []
    source_ids = {s.get("id") for s in sources if isinstance(s, dict)}
    missing_sources = sorted(MANDATORY_SOURCE_IDS - source_ids)
    if missing_sources:
        errors.append("missing mandatory official source locators: " + ", ".join(missing_sources))
    for source in sources:
        if not isinstance(source, dict):
            errors.append("every source must be an object")
            continue
        if not isinstance(source.get("url"), str) or not source["url"].startswith("https://"):
            errors.append(f"source {source.get('id')!r} lacks https URL")

    artifacts = manifest.get("required_submission_artifacts")
    if not isinstance(artifacts, list):
        errors.append("required_submission_artifacts must be a list")
        artifacts = []
    missing_artifacts = sorted(REQUIRED_ARTIFACTS - set(x for x in artifacts if isinstance(x, str)))
    if missing_artifacts:
        errors.append("missing requested submission artifacts: " + "; ".join(missing_artifacts))

    constraints = manifest.get("submission_constraints")
    if not isinstance(constraints, dict):
        errors.append("submission_constraints missing")
        constraints = {}
    if constraints.get("portal_only") is not True:
        errors.append("portal_only must remain true")
    if constraints.get("intent_to_bid_required") is not True:
        errors.append("intent_to_bid_required must remain true")
    if constraints.get("question_period_closed") is not True:
        errors.append("question_period_closed must remain true")

    evidence = qualification.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("qualification evidence missing")
        evidence = {}
    for key, entry in evidence.items():
        if not isinstance(entry, dict) or entry.get("status") not in ALLOWED_EVIDENCE_STATUS:
            errors.append(f"evidence.{key} has invalid status")
            continue
        if entry.get("status") == "VERIFIED":
            refs = entry.get("refs")
            if not isinstance(refs, list) or not refs or not all(isinstance(x, str) and x.strip() for x in refs):
                errors.append(f"evidence.{key} VERIFIED requires nonempty refs")

    action = qualification.get("action_authority")
    if not isinstance(action, dict):
        errors.append("action_authority missing")
        action = {}
    for key in FORBIDDEN_ACTION_KEYS:
        if action.get(key) is not False:
            errors.append(f"action_authority.{key} must be false in this internal carrier")

    prime_missing = [key for key in PRIME_GATES if not _verified(evidence.get(key))]
    teaming_ready = _verified(evidence.get("implementation_artifact_candidate")) and _verified(
        evidence.get("bounded_complementary_scope")
    )
    posture = "PRIME_READY" if not prime_missing else ("TEAMING_READY" if teaming_ready else "HOLD")

    asserted = qualification.get("asserted_posture")
    if asserted != posture:
        errors.append(f"asserted_posture={asserted!r} contradicts derived posture={posture!r}")

    if errors:
        raise VerificationError("\n".join(errors))

    return {
        "ok": True,
        "posture": posture,
        "prime_ready": posture == "PRIME_READY",
        "teaming_ready": teaming_ready,
        "prime_missing_gates": prime_missing,
        "submission_authorized": False,
        "buyer_contact_authorized": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("source_manifest.json"))
    parser.add_argument("--qualification", type=Path, default=Path(__file__).with_name("qualification.json"))
    args = parser.parse_args()
    try:
        result = verify(_load(args.manifest), _load(args.qualification))
    except VerificationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
