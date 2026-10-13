"""Consortium and applicant validation for Water4All readiness."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from .common import (
    APPLICANT_ROLES,
    FORMAL_ROLES,
    KNOWN_NONPARTICIPATING_FUNDED_COUNTRIES,
    ReadinessError,
    _expect_bool,
    _expect_country,
    _expect_dict,
    _expect_id,
    _expect_int,
    _expect_list,
    _expect_str,
    _reason,
)


def _validate_consortium(raw_consortium: Any) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    consortium = _expect_dict(raw_consortium, "$.consortium")
    raw_members = _expect_list(consortium.get("members"), "$.consortium.members")
    reasons: List[Dict[str, Any]] = []
    members: List[Dict[str, Any]] = []
    by_id: Dict[str, Dict[str, Any]] = {}

    for index, raw in enumerate(raw_members):
        path = "$.consortium.members[%d]" % index
        member = _expect_dict(raw, path)
        partner_id = _expect_id(member.get("partner_id"), path + ".partner_id")
        if partner_id in by_id:
            raise ReadinessError("duplicate consortium partner_id: %s" % partner_id)
        role = _expect_str(member.get("role"), path + ".role")
        if role not in FORMAL_ROLES:
            raise ReadinessError("consortium member role must be FUNDED_PARTNER or SELF_FUNDED_PARTNER")
        normalized = {
            "partner_id": partner_id,
            "organization_label": _expect_str(member.get("organization_label"), path + ".organization_label"),
            "country_code": _expect_country(member.get("country_code"), path + ".country_code"),
            "role": role,
            "eu_or_associated": _expect_bool(member.get("eu_or_associated"), path + ".eu_or_associated"),
            "participating_fpo_country": _expect_bool(member.get("participating_fpo_country"), path + ".participating_fpo_country"),
            "fpo_eligibility_verified": _expect_bool(member.get("fpo_eligibility_verified"), path + ".fpo_eligibility_verified"),
            "undersubscribed_fpo": _expect_bool(member.get("undersubscribed_fpo"), path + ".undersubscribed_fpo"),
            "legal_entity_verified": _expect_bool(member.get("legal_entity_verified"), path + ".legal_entity_verified"),
            "pic_verified": _expect_bool(member.get("pic_verified"), path + ".pic_verified"),
            "self_funding_commitment_verified": _expect_bool(member.get("self_funding_commitment_verified"), path + ".self_funding_commitment_verified"),
            "coordinator": _expect_bool(member.get("coordinator"), path + ".coordinator"),
            "person_months_milli": _expect_int(member.get("person_months_milli"), path + ".person_months_milli", 0),
            "synthetic_placeholder": _expect_bool(member.get("synthetic_placeholder", False), path + ".synthetic_placeholder"),
            "water4all_partnership_beneficiary": _expect_bool(member.get("water4all_partnership_beneficiary", False), path + ".water4all_partnership_beneficiary"),
        }
        members.append(normalized)
        by_id[partner_id] = normalized

    funded = [member for member in members if member["role"] == "FUNDED_PARTNER"]
    self_funded = [member for member in members if member["role"] == "SELF_FUNDED_PARTNER"]
    coordinators = [member for member in members if member["coordinator"]]
    beneficiary_members = [member for member in members if member["water4all_partnership_beneficiary"]]

    if len(funded) < 3:
        reasons.append(_reason("CONSORTIUM_FUNDED_PARTNER_MINIMUM", "at least three funded partners are required"))
    if len(set(member["country_code"] for member in funded)) < 3:
        reasons.append(_reason("CONSORTIUM_FUNDED_COUNTRY_MINIMUM", "funded partners must span at least three countries"))
    if sum(1 for member in funded if member["eu_or_associated"]) < 2:
        reasons.append(_reason("CONSORTIUM_EU_ASSOCIATED_MINIMUM", "at least two funded partners must be from EU or associated countries"))
    if len(self_funded) > 1:
        reasons.append(_reason("CONSORTIUM_SELF_FUNDED_MAXIMUM", "at most one self-funded partner is allowed", [m["partner_id"] for m in self_funded]))
    if len(coordinators) != 1:
        reasons.append(_reason("CONSORTIUM_COORDINATOR_COUNT", "exactly one coordinator is required", [m["partner_id"] for m in coordinators]))
    elif coordinators[0]["role"] != "FUNDED_PARTNER" or not coordinators[0]["fpo_eligibility_verified"]:
        reasons.append(_reason("CONSORTIUM_COORDINATOR_INELIGIBLE", "the coordinator must be a verified funded partner", [coordinators[0]["partner_id"]]))

    beneficiary_cap = 2 if len(members) <= 5 else 3
    if len(beneficiary_members) > beneficiary_cap:
        reasons.append(_reason(
            "PARTNERSHIP_BENEFICIARY_ENTITY_CAP_EXCEEDED",
            "Water4All Partnership beneficiary entity count exceeds the call cap of %d for this consortium size" % beneficiary_cap,
            [m["partner_id"] for m in beneficiary_members],
        ))

    pi_raw = consortium.get("coordinator_pi_cross_proposal_evidence")
    pi_evidence = None
    if pi_raw is None:
        reasons.append(_reason("COORDINATOR_PI_CROSS_PROPOSAL_EVIDENCE_MISSING", "coordinating PI needs retained evidence that they do not participate in another JTC/ECR proposal"))
    else:
        pi = _expect_dict(pi_raw, "$.consortium.coordinator_pi_cross_proposal_evidence")
        pi_evidence = {
            "pi_id": _expect_id(pi.get("pi_id"), "$.consortium.coordinator_pi_cross_proposal_evidence.pi_id"),
            "evidence_id": _expect_id(pi.get("evidence_id"), "$.consortium.coordinator_pi_cross_proposal_evidence.evidence_id"),
            "participates_in_other_jtc_or_ecr_proposal": _expect_bool(pi.get("participates_in_other_jtc_or_ecr_proposal"), "$.consortium.coordinator_pi_cross_proposal_evidence.participates_in_other_jtc_or_ecr_proposal"),
            "verified": _expect_bool(pi.get("verified"), "$.consortium.coordinator_pi_cross_proposal_evidence.verified"),
        }
        if pi_evidence["participates_in_other_jtc_or_ecr_proposal"]:
            reasons.append(_reason("COORDINATOR_PI_CROSS_PROPOSAL_CONFLICT", "coordinating PI is recorded as participating in another JTC/ECR proposal", [pi_evidence["pi_id"], pi_evidence["evidence_id"]]))
        if not pi_evidence["verified"]:
            reasons.append(_reason("COORDINATOR_PI_CROSS_PROPOSAL_EVIDENCE_UNVERIFIED", "coordinating PI cross-proposal evidence is not verified", [pi_evidence["pi_id"], pi_evidence["evidence_id"]]))

    max_members = 8 if any(member["role"] == "FUNDED_PARTNER" and member["undersubscribed_fpo"] for member in members) else 7
    if len(members) > max_members:
        reasons.append(_reason("CONSORTIUM_PARTNER_MAXIMUM", "consortium exceeds the applicable partner maximum"))

    for member in members:
        refs = [member["partner_id"]]
        if member["synthetic_placeholder"]:
            reasons.append(_reason("CONSORTIUM_SYNTHETIC_PLACEHOLDER", "synthetic placeholder cannot satisfy consortium authority", refs))
        if not member["legal_entity_verified"]:
            reasons.append(_reason("CONSORTIUM_LEGAL_ENTITY_UNVERIFIED", "partner legal entity is not verified", refs))
        if not member["pic_verified"]:
            reasons.append(_reason("CONSORTIUM_PIC_UNVERIFIED", "partner PIC is not verified", refs))
        if member["role"] == "FUNDED_PARTNER":
            if member["country_code"] in KNOWN_NONPARTICIPATING_FUNDED_COUNTRIES:
                reasons.append(_reason("CONSORTIUM_KNOWN_NONPARTICIPATING_FUNDED_COUNTRY", "country is known not to be a participating funding country for this call", refs))
            if not member["participating_fpo_country"]:
                reasons.append(_reason("CONSORTIUM_FUNDED_COUNTRY_NOT_PARTICIPATING", "funded partner country is not represented by a participating FPO", refs))
            if not member["fpo_eligibility_verified"]:
                reasons.append(_reason("CONSORTIUM_FPO_ELIGIBILITY_UNVERIFIED", "funded partner FPO eligibility is not verified", refs))
        else:
            if member["coordinator"]:
                reasons.append(_reason("SELF_FUNDED_COORDINATOR_FORBIDDEN", "self-funded partner cannot coordinate", refs))
            if not member["self_funding_commitment_verified"]:
                reasons.append(_reason("SELF_FUNDING_COMMITMENT_UNVERIFIED", "self-funded partner commitment is not verified", refs))

    total_pm = sum(member["person_months_milli"] for member in members)
    if total_pm <= 0:
        reasons.append(_reason("CONSORTIUM_WORKLOAD_MISSING", "positive consortium person-month workload is required"))
    else:
        for member in members:
            if member["person_months_milli"] * 2 > total_pm:
                reasons.append(_reason("PARTNER_WORKLOAD_OVER_HALF", "a partner exceeds 50 percent of total person months", [member["partner_id"]]))
        country_totals: Dict[str, int] = {}
        for member in members:
            country_totals[member["country_code"]] = country_totals.get(member["country_code"], 0) + member["person_months_milli"]
        for country, amount in sorted(country_totals.items()):
            if amount * 2 > total_pm:
                reasons.append(_reason("COUNTRY_WORKLOAD_OVER_HALF", "partners from one country exceed 50 percent of total person months", [country]))

    members.sort(key=lambda item: item["partner_id"])
    summary = {
        "members": members,
        "funded_partner_count": len(funded),
        "self_funded_partner_count": len(self_funded),
        "funded_country_count": len(set(member["country_code"] for member in funded)),
        "eu_or_associated_funded_count": sum(1 for member in funded if member["eu_or_associated"]),
        "partner_limit": max_members,
        "partnership_beneficiary_entity_count": len(beneficiary_members),
        "partnership_beneficiary_entity_cap": beneficiary_cap,
        "coordinator_pi_cross_proposal_evidence": pi_evidence,
        "total_person_months_milli": total_pm,
    }
    return summary, reasons, by_id


def _validate_applicant(raw_applicant: Any, consortium_by_id: Mapping[str, Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    applicant = _expect_dict(raw_applicant, "$.applicant")
    applicant_id = _expect_id(applicant.get("applicant_id"), "$.applicant.applicant_id")
    role = _expect_str(applicant.get("intended_role"), "$.applicant.intended_role")
    if role not in APPLICANT_ROLES:
        raise ReadinessError("unsupported applicant intended role")
    normalized = {
        "applicant_id": applicant_id,
        "organization_label": _expect_str(applicant.get("organization_label"), "$.applicant.organization_label"),
        "country_code": _expect_country(applicant.get("country_code"), "$.applicant.country_code"),
        "intended_role": role,
        "legal_entity_verified": _expect_bool(applicant.get("legal_entity_verified"), "$.applicant.legal_entity_verified"),
        "pic_verified": _expect_bool(applicant.get("pic_verified"), "$.applicant.pic_verified"),
        "paid_role_authority_verified": _expect_bool(applicant.get("paid_role_authority_verified"), "$.applicant.paid_role_authority_verified"),
        "subcontract_rule_verified": _expect_bool(applicant.get("subcontract_rule_verified"), "$.applicant.subcontract_rule_verified"),
        "synthetic_placeholder": _expect_bool(applicant.get("synthetic_placeholder", False), "$.applicant.synthetic_placeholder"),
    }
    reasons: List[Dict[str, Any]] = []
    refs = [applicant_id]
    if normalized["synthetic_placeholder"]:
        reasons.append(_reason("APPLICANT_SYNTHETIC_PLACEHOLDER", "synthetic applicant cannot satisfy applicant authority", refs))
    if not normalized["legal_entity_verified"]:
        reasons.append(_reason("APPLICANT_LEGAL_ENTITY_UNVERIFIED", "applicant legal entity is not verified", refs))
    if not normalized["pic_verified"]:
        reasons.append(_reason("APPLICANT_PIC_UNVERIFIED", "applicant PIC is not verified", refs))
    if role in FORMAL_ROLES:
        member = consortium_by_id.get(applicant_id)
        if member is None:
            reasons.append(_reason("APPLICANT_NOT_IN_CONSORTIUM", "formal applicant role requires a matching consortium member", refs))
        elif member["role"] != role or member["country_code"] != normalized["country_code"]:
            reasons.append(_reason("APPLICANT_CONSORTIUM_ROLE_MISMATCH", "applicant role or country does not match consortium generation", refs))
    else:
        if applicant_id in consortium_by_id:
            reasons.append(_reason("SUBCONTRACT_CANDIDATE_COUNTED_AS_PARTNER", "paid subcontract candidate must not be counted as a formal consortium partner", refs))
        if not normalized["paid_role_authority_verified"]:
            reasons.append(_reason("PAID_ROLE_AUTHORITY_UNVERIFIED", "paid technical role has not been accepted or authorized", refs))
        if not normalized["subcontract_rule_verified"]:
            reasons.append(_reason("SUBCONTRACT_RULE_UNVERIFIED", "specific call/national/consortium subcontract eligibility is not verified", refs))
        reasons.append(_reason("SUBCONTRACT_CANDIDATE_OWNER_REVIEW_REQUIRED", "v1 cannot authorize a paid subcontract role; buyer-specific owner review remains mandatory", refs))
    return normalized, reasons
