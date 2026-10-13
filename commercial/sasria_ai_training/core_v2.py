"""Truth-narrow Sasria RFP2026/22 teaming readiness compiler.

Candidate/reviewer evidence may make response assembly reviewable. Nothing in this
module can mint procurement portal, signatory, prime submission, award, payment,
or revenue authority from caller-authored input.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

SCHEMA = "tjlabs.sasria_ai_training_readiness.v2"
REQUIRED_RETURNABLES = (
    "sbd_1_invitation_to_bid", "sbd_4_disclosure_declaration", "sbd_6_1_specific_goals",
    "annexure_a_confidentiality_nda", "annexure_b_bid_conditions_details",
    "annexure_c_shareholder_information", "annexure_d_experience_project_team",
    "csd_report", "bbbee_certificate_or_affidavit", "technical_proposal", "financial_proposal",
)
RECOGNIZED_FRAMEWORKS = frozenset({"ISO/IEC 42001", "NIST AI RMF", "Gartner AI Governance Playbook"})
ROLE_GROUPS = (
    "executives_and_senior_management", "specialists_and_general_employees", "ai_navigators",
    "ai_project_team", "technical_team", "business_process_owners",
)
TECHNICAL_SCORE_CAPS = {
    "company_profile": 20, "project_proposal_and_training_methodology": 40,
    "training_personnel": 10, "key_personnel_cvs": 10, "reference_letters": 20,
}
TECHNICAL_PASS_SCORE = 70


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _items(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return []
    return sorted({_text(item) for item in value if _text(item)})


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


@dataclass(frozen=True)
class EvidenceRef:
    label: str
    locator: str
    note: str = ""

    def valid(self) -> bool:
        return bool(_text(self.label)) and bool(_text(self.locator)) and isinstance(self.note, str)

    def as_dict(self) -> dict[str, str]:
        if not self.valid():
            raise ValueError("invalid evidence reference")
        return {"label": _text(self.label), "locator": _text(self.locator), "note": self.note.strip()}


@dataclass(frozen=True)
class PrimeCandidate:
    legal_name: str
    company_profile_ref: EvidenceRef | None
    returnables: Mapping[str, bool]
    framework_alignment: tuple[str, ...] = ()
    framework_evidence: tuple[EvidenceRef, ...] = ()
    training_body_accreditation_ref: EvidenceRef | None = None
    recognized_certification_capability_ref: EvidenceRef | None = None
    platform_access_12_months_ref: EvidenceRef | None = None
    regulated_environment_training_ref: EvidenceRef | None = None
    financial_services_training_ref: EvidenceRef | None = None
    facilitator_refs: tuple[EvidenceRef, ...] = ()
    reference_letter_refs: tuple[EvidenceRef, ...] = ()
    ai_trainings_last_3y: int | None = None

    def mandatory_gate(self) -> dict[str, Any]:
        blockers: list[str] = []
        warnings: list[str] = []
        if not _text(self.legal_name): blockers.append("missing_legal_name")
        if not isinstance(self.company_profile_ref, EvidenceRef) or not self.company_profile_ref.valid():
            blockers.append("missing_company_profile_evidence")
        if isinstance(self.returnables, Mapping):
            returns: Mapping[str, Any] = self.returnables
        else:
            returns = {}
            blockers.append("invalid_returnables_mapping")
        missing = sorted(name for name in REQUIRED_RETURNABLES if returns.get(name) is not True)
        if missing: blockers.append("missing_required_returnables")
        recognized = sorted(set(_items(self.framework_alignment)) & RECOGNIZED_FRAMEWORKS)
        if not recognized: blockers.append("missing_recognized_ai_governance_framework_alignment")
        framework_refs = self.framework_evidence if isinstance(self.framework_evidence, (list, tuple)) else ()
        valid_framework = [r for r in framework_refs if isinstance(r, EvidenceRef) and r.valid()]
        if not valid_framework: blockers.append("missing_framework_alignment_evidence")
        for name, ref in (
            ("training_body_accreditation", self.training_body_accreditation_ref),
            ("recognized_certification_capability", self.recognized_certification_capability_ref),
            ("post_training_platform_access_12_months", self.platform_access_12_months_ref),
        ):
            if not isinstance(ref, EvidenceRef) or not ref.valid(): blockers.append(f"missing_{name}_evidence")
        if self.ai_trainings_last_3y is None:
            warnings.append("ai_training_count_not_evidenced")
        elif isinstance(self.ai_trainings_last_3y, bool) or not isinstance(self.ai_trainings_last_3y, int) or self.ai_trainings_last_3y < 0:
            blockers.append("invalid_ai_training_count")
        elif self.ai_trainings_last_3y < 5:
            warnings.append("company_profile_may_not_reach_max_training_history_score")
        if not isinstance(self.regulated_environment_training_ref, EvidenceRef) or not self.regulated_environment_training_ref.valid():
            warnings.append("regulated_environment_training_evidence_missing")
        if not isinstance(self.financial_services_training_ref, EvidenceRef) or not self.financial_services_training_ref.valid():
            warnings.append("financial_services_training_evidence_missing")
        facilitators = self.facilitator_refs if isinstance(self.facilitator_refs, (list, tuple)) else ()
        references = self.reference_letter_refs if isinstance(self.reference_letter_refs, (list, tuple)) else ()
        valid_facilitators = [r for r in facilitators if isinstance(r, EvidenceRef) and r.valid()]
        valid_references = [r for r in references if isinstance(r, EvidenceRef) and r.valid()]
        if not valid_facilitators: warnings.append("facilitator_evidence_missing")
        if not valid_references: warnings.append("reference_letters_missing")
        return {
            "status": "PRIME_MANDATORY_READY" if not blockers else "HOLD",
            "blockers": sorted(set(blockers)), "warnings": sorted(set(warnings)),
            "missing_returnables": missing, "recognized_frameworks": recognized,
            "valid_framework_evidence_count": len(valid_framework),
            "valid_facilitator_evidence_count": len(valid_facilitators),
            "valid_reference_letter_count": len(valid_references),
            "ai_trainings_last_3y": self.ai_trainings_last_3y,
        }


@dataclass(frozen=True)
class BuyerTechnicalScore:
    scores: Mapping[str, int]
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def result(self) -> dict[str, Any]:
        blockers: list[str] = []
        scores: Mapping[str, Any]
        if isinstance(self.scores, Mapping): scores = self.scores
        else:
            scores = {}
            blockers.append("invalid_scores_mapping")
        normalized: dict[str, int] = {}
        if set(TECHNICAL_SCORE_CAPS) - set(scores): blockers.append("missing_technical_score_categories")
        if set(scores) - set(TECHNICAL_SCORE_CAPS): blockers.append("unknown_technical_score_categories")
        for category, cap in TECHNICAL_SCORE_CAPS.items():
            if category not in scores: continue
            value = scores[category]
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= cap:
                blockers.append(f"invalid_score:{category}")
            else: normalized[category] = value
        refs = self.evidence_refs if isinstance(self.evidence_refs, (list, tuple)) else ()
        evidence = [r.as_dict() for r in refs if isinstance(r, EvidenceRef) and r.valid()]
        if not evidence: blockers.append("missing_score_evidence")
        total = sum(normalized.values()) if len(normalized) == len(TECHNICAL_SCORE_CAPS) else None
        if total is not None and total < TECHNICAL_PASS_SCORE: blockers.append("technical_score_below_70")
        blockers = sorted(set(blockers))
        return {
            "status": "TECHNICAL_THRESHOLD_READY" if not blockers else "HOLD", "blockers": blockers,
            "scores": {k: normalized[k] for k in sorted(normalized)},
            "score_caps": dict(sorted(TECHNICAL_SCORE_CAPS.items())), "total": total,
            "pass_threshold": TECHNICAL_PASS_SCORE, "evidence_refs": evidence,
            "scoring_boundary": "Externally supplied review values only; this compiler does not award buyer points.",
        }


@dataclass(frozen=True)
class TrainingPathway:
    role_group: str
    learning_outcomes: tuple[str, ...]
    delivery_modes: tuple[str, ...]
    evaluation_methods: tuple[str, ...]
    artefacts: tuple[str, ...]

    def result(self) -> dict[str, Any]:
        role = _text(self.role_group)
        blockers: list[str] = []
        if role not in ROLE_GROUPS: blockers.append("unknown_role_group")
        outcomes, modes, evaluations, artefacts = map(_items, (self.learning_outcomes, self.delivery_modes, self.evaluation_methods, self.artefacts))
        if not outcomes: blockers.append("missing_learning_outcomes")
        if not modes: blockers.append("missing_delivery_modes")
        if not evaluations: blockers.append("missing_evaluation_methods")
        if not artefacts: blockers.append("missing_training_artefacts")
        return {"role_group": role, "status": "READY" if not blockers else "HOLD", "blockers": sorted(blockers), "learning_outcomes": outcomes, "delivery_modes": modes, "evaluation_methods": evaluations, "artefacts": artefacts}


@dataclass(frozen=True)
class PaidWorkshare:
    owner: str
    deliverables: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    exclusions: tuple[str, ...]
    commercial_state: str = "PAID_SCOPE_TO_BE_AGREED"

    def result(self) -> dict[str, Any]:
        owner = _text(self.owner)
        deliverables, acceptance, exclusions = map(_items, (self.deliverables, self.acceptance_criteria, self.exclusions))
        blockers: list[str] = []
        if not owner: blockers.append("missing_workshare_owner")
        if not deliverables: blockers.append("missing_workshare_deliverables")
        if not acceptance: blockers.append("missing_workshare_acceptance_criteria")
        if not exclusions: blockers.append("missing_workshare_exclusions")
        if self.commercial_state != "PAID_SCOPE_TO_BE_AGREED": blockers.append("unsupported_commercial_state")
        return {"status": "WORKSHARE_READY" if not blockers else "HOLD", "blockers": sorted(blockers), "owner": owner, "deliverables": deliverables, "acceptance_criteria": acceptance, "exclusions": exclusions, "commercial_state": self.commercial_state}


@dataclass(frozen=True)
class SubmissionAuthority:
    portal_account_confirmed: bool = False
    authorized_signatory_confirmed: bool = False
    prime_approved_submission: bool = False

    def result(self) -> dict[str, Any]:
        assertions = {
            "portal_account_confirmed": self.portal_account_confirmed is True,
            "authorized_signatory_confirmed": self.authorized_signatory_confirmed is True,
            "prime_approved_submission": self.prime_approved_submission is True,
        }
        blockers = ["trusted_submission_authority_not_bound"]
        if not assertions["portal_account_confirmed"]: blockers.append("portal_account_not_confirmed")
        if not assertions["authorized_signatory_confirmed"]: blockers.append("authorized_signatory_not_confirmed")
        if not assertions["prime_approved_submission"]: blockers.append("prime_submission_approval_not_confirmed")
        return {"status": "HOLD", "blockers": blockers, "candidate_assertions": assertions, "authority_boundary": "Caller-authored assertions are not submission authority; no separately trusted authority generation is bound."}


def compile_readiness_pack(*, prime: PrimeCandidate, technical_score: BuyerTechnicalScore, pathways: Sequence[TrainingPathway], workshare: PaidWorkshare, submission_authority: SubmissionAuthority | None = None) -> dict[str, Any]:
    prime_result, score_result = prime.mandatory_gate(), technical_score.result()
    paths = pathways if isinstance(pathways, (list, tuple)) else ()
    rows = sorted((p.result() for p in paths if isinstance(p, TrainingPathway)), key=lambda row: row["role_group"])
    represented = {row["role_group"] for row in rows if row["role_group"] in ROLE_GROUPS}
    missing_roles = sorted(set(ROLE_GROUPS) - represented)
    duplicate_roles = sorted(role for role in represented if sum(row["role_group"] == role for row in rows) > 1)
    workshare_result = workshare.result()
    authority_result = (submission_authority or SubmissionAuthority()).result()
    blockers: list[str] = []
    if prime_result["status"] != "PRIME_MANDATORY_READY": blockers.append("prime_mandatory_gate")
    if score_result["status"] != "TECHNICAL_THRESHOLD_READY": blockers.append("technical_score_gate")
    if missing_roles: blockers.append("missing_role_pathways")
    if duplicate_roles: blockers.append("duplicate_role_pathways")
    if any(row["status"] != "READY" for row in rows): blockers.append("pathway_content_gate")
    if len(rows) != len(paths): blockers.append("invalid_pathway_objects")
    if workshare_result["status"] != "WORKSHARE_READY": blockers.append("paid_workshare_gate")
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "opportunity": {"buyer": "Sasria SOC Ltd", "solicitation": "RFP2026/22", "closing": "2026-09-17T12:00:00+02:00", "submission_route": "Sasria Online Tender Portal"},
        "prime_gate": prime_result, "technical_score": score_result, "training_pathways": rows,
        "missing_role_pathways": missing_roles, "duplicate_role_pathways": duplicate_roles,
        "paid_workshare": workshare_result,
        "response_status": "RESPONSE_ASSEMBLY_READY" if not blockers else "HOLD",
        "response_blockers": sorted(set(blockers)), "submission_authority": authority_result,
        "submission_status": "HOLD",
        "claims_boundary": "Candidate/reviewer evidence only; no procurement, partnership, portal, signatory, submission, award, payment, or revenue authority is created.",
    }
    payload["receipt_sha256"] = sha256(_canon(payload).encode("utf-8")).hexdigest()
    return payload


def render_markdown(pack: Mapping[str, Any]) -> str:
    lines = ["# Sasria RFP2026/22 readiness pack", "", f"- Response assembly: **{pack['response_status']}**", f"- Submission: **{pack['submission_status']}**", f"- Prime mandatory gate: **{pack['prime_gate']['status']}**", f"- Technical threshold gate: **{pack['technical_score']['status']}**", f"- Paid workshare: **{pack['paid_workshare']['status']}**", f"- Receipt SHA-256: `{pack['receipt_sha256']}`", "", "## Response blockers"]
    lines.extend([f"- `{x}`" for x in (pack.get("response_blockers") or [])] or ["- none"])
    lines.extend(["", "## Prime blockers"])
    lines.extend([f"- `{x}`" for x in (pack["prime_gate"].get("blockers") or [])] or ["- none"])
    lines.extend(["", "## Submission authority"])
    lines.extend([f"- `{x}`" for x in (pack["submission_authority"].get("blockers") or [])] or ["- none"])
    lines.extend(["", "## Claims boundary", str(pack["claims_boundary"]), ""])
    return "\n".join(lines)
