"""Deterministic evidence gates for Copilot-agent training proposals and delivery."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, Sequence

RFP_START = date(2026, 10, 1)
RFP_END = date(2026, 11, 20)
REQUIRED_GOVERNANCE_CONTROLS = (
    "approved_data_sources",
    "least_privilege_access",
    "human_escalation",
    "logging_and_audit",
    "retention_and_deletion",
)
RUBRIC_DIMENSIONS = (
    "task_success",
    "groundedness",
    "permission_boundaries",
    "safe_failure",
    "human_handoff",
)


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sorted_unique(values: Iterable[str]) -> list[str]:
    return sorted({v.strip() for v in values if isinstance(v, str) and v.strip()})


def _canonical_json(value: Any) -> str:
    # ASCII-escaped canonical JSON keeps valid JSON strings containing lone
    # surrogates hashable without leaking a raw UnicodeEncodeError at UTF-8.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _semantic_key(*values: object) -> tuple[str, ...]:
    """Canonical evidence identity used only for duplicate detection.

    Case and surrounding whitespace cannot mint a second evidence item. All
    substantive fields participate, so genuinely different evidence remains
    distinct without inventing a provider-supplied identifier.
    """
    return tuple(value.strip().casefold() if isinstance(value, str) else "" for value in values)


@dataclass(frozen=True)
class Reference:
    organization: str
    contact_name: str
    contact_route: str
    engagement_summary: str

    def valid(self) -> bool:
        return all(_nonempty(v) for v in (self.organization, self.contact_name, self.contact_route, self.engagement_summary))

    def evidence_key(self) -> tuple[str, ...]:
        return _semantic_key(self.organization, self.contact_name, self.contact_route, self.engagement_summary)


@dataclass(frozen=True)
class ComparableEngagement:
    client_label: str
    scope: str
    outcome: str
    evidence_route: str

    def valid(self) -> bool:
        return all(_nonempty(v) for v in (self.client_label, self.scope, self.outcome, self.evidence_route))

    def evidence_key(self) -> tuple[str, ...]:
        return _semantic_key(self.client_label, self.scope, self.outcome, self.evidence_route)


@dataclass(frozen=True)
class Trainer:
    name: str
    role: str
    copilot_experience_summary: str
    availability_start: date
    availability_end: date

    def covers_window(self, start: date = RFP_START, end: date = RFP_END) -> bool:
        return self.availability_start <= start and self.availability_end >= end

    def valid(self) -> bool:
        return (
            _nonempty(self.name)
            and _nonempty(self.role)
            and _nonempty(self.copilot_experience_summary)
            and isinstance(self.availability_start, date)
            and isinstance(self.availability_end, date)
            and self.availability_start <= self.availability_end
        )


@dataclass(frozen=True)
class PartnerEvidence:
    company_name: str
    company_profile: str
    trainer: Trainer | None
    comparable_engagements: tuple[ComparableEngagement, ...] = ()
    references: tuple[Reference, ...] = ()
    subcontract_role: str = ""
    commercial_split_discussed: bool = False
    sample_agreement_available: bool = False

    def proposal_gate(self) -> dict[str, Any]:
        blockers: list[str] = []
        if not _nonempty(self.company_name):
            blockers.append("missing_company_name")
        if not _nonempty(self.company_profile):
            blockers.append("missing_company_profile")
        if self.trainer is None or not isinstance(self.trainer, Trainer) or not self.trainer.valid():
            blockers.append("missing_or_invalid_named_trainer")
        elif not self.trainer.covers_window():
            blockers.append("trainer_does_not_cover_delivery_window")

        valid_engagements = [item for item in self.comparable_engagements if isinstance(item, ComparableEngagement) and item.valid()]
        distinct_engagement_keys = {item.evidence_key() for item in valid_engagements}
        if len(distinct_engagement_keys) < len(valid_engagements):
            blockers.append("duplicate_comparable_engagement_evidence")
        if len(distinct_engagement_keys) < 2:
            blockers.append("fewer_than_two_comparable_engagements")

        valid_refs = [item for item in self.references if isinstance(item, Reference) and item.valid()]
        distinct_reference_keys = {item.evidence_key() for item in valid_refs}
        if len(distinct_reference_keys) < len(valid_refs):
            blockers.append("duplicate_reference_evidence")
        if len(distinct_reference_keys) < 2:
            blockers.append("fewer_than_two_valid_references")

        if not _nonempty(self.subcontract_role):
            blockers.append("subcontract_role_not_defined")
        if self.commercial_split_discussed is not True:
            blockers.append("commercial_role_split_not_discussed")
        if self.sample_agreement_available is not True:
            blockers.append("sample_agreement_not_available")
        blockers.sort()
        return {
            "status": "TEAMING_READY" if not blockers else "HOLD",
            "blockers": blockers,
            "valid_comparable_engagements": len(distinct_engagement_keys),
            "valid_references": len(distinct_reference_keys),
            "delivery_window": {"start": RFP_START.isoformat(), "end": RFP_END.isoformat()},
        }


@dataclass(frozen=True)
class GovernanceReview:
    controls: Mapping[str, bool]
    notes: Mapping[str, str] = field(default_factory=dict)

    def result(self) -> dict[str, Any]:
        missing = sorted(control for control in REQUIRED_GOVERNANCE_CONTROLS if self.controls.get(control) is not True)
        notes = {
            key: value
            for key, value in self.notes.items()
            if isinstance(key, str) and isinstance(value, str)
        }
        return {
            "status": "PASS" if not missing else "HOLD",
            "required_controls": list(REQUIRED_GOVERNANCE_CONTROLS),
            "missing_controls": missing,
            "notes": {k: notes[k] for k in sorted(notes)},
        }


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    scores: Mapping[str, int]
    evidence_refs: tuple[str, ...] = ()
    observed_result: str = ""

    def result(self, minimum_dimension_score: int = 3) -> dict[str, Any]:
        if not _nonempty(self.case_id):
            raise ValueError("case_id must be non-empty")
        if (
            isinstance(minimum_dimension_score, bool)
            or not isinstance(minimum_dimension_score, int)
            or minimum_dimension_score < 0
            or minimum_dimension_score > 5
        ):
            raise ValueError("minimum_dimension_score must be an integer between 0 and 5")
        missing = [dim for dim in RUBRIC_DIMENSIONS if dim not in self.scores]
        invalid = {
            dim: value
            for dim, value in self.scores.items()
            if dim in RUBRIC_DIMENSIONS
            and (not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 5)
        }
        below = {
            dim: self.scores[dim]
            for dim in RUBRIC_DIMENSIONS
            if dim in self.scores
            and isinstance(self.scores[dim], int)
            and not isinstance(self.scores[dim], bool)
            and self.scores[dim] < minimum_dimension_score
        }
        evidence_refs = _sorted_unique(self.evidence_refs)
        observed_result = self.observed_result.strip() if isinstance(self.observed_result, str) else ""
        blockers: list[str] = []
        if missing:
            blockers.append("missing_rubric_dimensions")
        if invalid:
            blockers.append("invalid_rubric_scores")
        if below:
            blockers.append("score_below_threshold")
        if not evidence_refs:
            blockers.append("missing_evidence_refs")
        if not observed_result:
            blockers.append("missing_observed_result")
        blockers.sort()
        recorded_scores = {dim: self.scores[dim] for dim in RUBRIC_DIMENSIONS if dim in self.scores}
        return {
            "case_id": self.case_id.strip(),
            "status": "PASS" if not blockers else "HOLD",
            "blockers": blockers,
            "missing_dimensions": sorted(missing),
            "invalid_scores": {k: invalid[k] for k in sorted(invalid)},
            "below_threshold": {k: below[k] for k in sorted(below)},
            "scores": {k: recorded_scores[k] for k in sorted(recorded_scores)},
            "evidence_refs": evidence_refs,
            "observed_result": observed_result,
        }


@dataclass(frozen=True)
class AdoptionMetrics:
    invited_staff: int
    trained_staff: int
    builders: int
    functioning_agents: int
    evaluated_agents: int

    def result(self) -> dict[str, Any]:
        values = {
            "invited_staff": self.invited_staff,
            "trained_staff": self.trained_staff,
            "builders": self.builders,
            "functioning_agents": self.functioning_agents,
            "evaluated_agents": self.evaluated_agents,
        }
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in values.values()):
            raise ValueError("adoption metrics must be non-negative integers")
        if self.trained_staff > self.invited_staff:
            raise ValueError("trained_staff cannot exceed invited_staff")
        if self.builders > self.trained_staff:
            raise ValueError("builders cannot exceed trained_staff")
        if self.functioning_agents > self.builders:
            raise ValueError("functioning_agents cannot exceed builders")
        if self.evaluated_agents > self.functioning_agents:
            raise ValueError("evaluated_agents cannot exceed functioning_agents")
        training_rate = round(self.trained_staff / self.invited_staff, 4) if self.invited_staff else 0.0
        outcome_pass = self.trained_staff >= 1 and self.builders >= 1 and self.functioning_agents >= 1
        return {
            **values,
            "training_completion_rate": training_rate,
            "buyer_outcome_status": "PASS" if outcome_pass else "HOLD",
        }


def compile_delivery_pack(*, partner: PartnerEvidence, governance: GovernanceReview, evaluations: Sequence[EvaluationCase], adoption: AdoptionMetrics) -> dict[str, Any]:
    evaluation_results = sorted((case.result() for case in evaluations), key=lambda row: row["case_id"])
    duplicate_ids = sorted(
        case_id
        for case_id in {row["case_id"] for row in evaluation_results}
        if sum(row["case_id"] == case_id for row in evaluation_results) > 1
    )
    proposal_gate = partner.proposal_gate()
    governance_result = governance.result()
    adoption_result = adoption.result()
    blockers: list[str] = []
    if proposal_gate["status"] != "TEAMING_READY":
        blockers.append("proposal_evidence_gate")
    if governance_result["status"] != "PASS":
        blockers.append("governance_gate")
    if not evaluation_results:
        blockers.append("no_agent_evaluation_cases")
    elif any(row["status"] != "PASS" for row in evaluation_results):
        blockers.append("agent_evaluation_gate")
    if duplicate_ids:
        blockers.append("duplicate_evaluation_case_ids")
    if adoption_result["buyer_outcome_status"] != "PASS":
        blockers.append("functioning_agent_outcome_gate")
    blockers.sort()
    payload = {
        "schema": "tjlabs.copilot_agent_training_evidence.v1",
        "proposal_gate": proposal_gate,
        "governance": governance_result,
        "evaluations": evaluation_results,
        "adoption": adoption_result,
        "duplicate_evaluation_case_ids": duplicate_ids,
        "delivery_status": "ACCEPTANCE_READY" if not blockers else "HOLD",
        "delivery_blockers": blockers,
        "claims_boundary": (
            "This packet records supplied evidence only; it does not independently verify Microsoft credentials, "
            "client references, legal compliance, security compliance, procurement eligibility, partnership, award, or payment."
        ),
    }
    payload["receipt_sha256"] = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return payload


def render_markdown(pack: Mapping[str, Any]) -> str:
    lines = [
        "# Copilot Agent Training Evidence Pack",
        "",
        f"- Delivery status: **{pack['delivery_status']}**",
        f"- Receipt SHA-256: `{pack['receipt_sha256']}`",
        f"- Proposal gate: **{pack['proposal_gate']['status']}**",
        f"- Governance gate: **{pack['governance']['status']}**",
        f"- Functioning agents: **{pack['adoption']['functioning_agents']}**",
        "",
        "## Delivery blockers",
    ]
    blockers = pack.get("delivery_blockers") or []
    lines.extend([f"- `{item}`" for item in blockers] or ["- none"])
    lines.extend(["", "## Proposal blockers"])
    proposal_blockers = pack["proposal_gate"].get("blockers") or []
    lines.extend([f"- `{item}`" for item in proposal_blockers] or ["- none"])
    lines.extend(["", "## Evaluation cases"])
    for row in pack.get("evaluations", []):
        lines.append(f"- `{row['case_id']}` — **{row['status']}**")
    lines.extend(["", "## Claims boundary", str(pack["claims_boundary"]), ""])
    return "\n".join(lines)
