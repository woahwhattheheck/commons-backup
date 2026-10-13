"""CLI for compiling a fail-closed Sasria RFP2026/22 readiness pack."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .core import (
    BuyerTechnicalScore,
    EvidenceRef,
    PaidWorkshare,
    PrimeCandidate,
    SubmissionAuthority,
    TrainingPathway,
    compile_readiness_pack,
    render_markdown,
)


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    return data


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _array(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _strings(value: Any, field: str) -> tuple[str, ...]:
    rows = _array(value, field)
    if any(not isinstance(item, str) for item in rows):
        raise ValueError(f"{field} must contain only strings")
    return tuple(rows)


def _ref(value: Any, field: str) -> EvidenceRef | None:
    if value is None:
        return None
    row = _object(value, field)
    if set(row) - {"label", "locator", "note"}:
        raise ValueError(f"{field} has unknown fields")
    label, locator, note = row.get("label", ""), row.get("locator", ""), row.get("note", "")
    if not all(isinstance(part, str) for part in (label, locator, note)):
        raise ValueError(f"{field} fields must be strings")
    return EvidenceRef(label=label, locator=locator, note=note)


def _refs(value: Any, field: str) -> tuple[EvidenceRef, ...]:
    rows = _array(value, field)
    out: list[EvidenceRef] = []
    for index, item in enumerate(rows):
        ref = _ref(item, f"{field}[{index}]")
        if ref is None:
            raise ValueError(f"{field}[{index}] must be an object")
        out.append(ref)
    return tuple(out)


def compile_from_dict(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    prime_data = _object(data.get("prime", {}), "prime")
    score_data = _object(data.get("technical_score", {}), "technical_score")
    workshare_data = _object(data.get("paid_workshare", {}), "paid_workshare")
    authority_data = _object(data.get("submission_authority", {}), "submission_authority")

    returnables = _object(prime_data.get("returnables", {}), "prime.returnables")
    if any(not isinstance(key, str) or not isinstance(value, bool) for key, value in returnables.items()):
        raise ValueError("prime.returnables must map string keys to booleans")
    legal_name = prime_data.get("legal_name", "")
    if not isinstance(legal_name, str):
        raise ValueError("prime.legal_name must be a string")
    count = prime_data.get("ai_trainings_last_3y")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int)):
        raise ValueError("prime.ai_trainings_last_3y must be an integer or null")

    prime = PrimeCandidate(
        legal_name=legal_name,
        company_profile_ref=_ref(prime_data.get("company_profile_ref"), "prime.company_profile_ref"),
        returnables=returnables,
        framework_alignment=_strings(prime_data.get("framework_alignment", []), "prime.framework_alignment"),
        framework_evidence=_refs(prime_data.get("framework_evidence", []), "prime.framework_evidence"),
        training_body_accreditation_ref=_ref(prime_data.get("training_body_accreditation_ref"), "prime.training_body_accreditation_ref"),
        recognized_certification_capability_ref=_ref(prime_data.get("recognized_certification_capability_ref"), "prime.recognized_certification_capability_ref"),
        platform_access_12_months_ref=_ref(prime_data.get("platform_access_12_months_ref"), "prime.platform_access_12_months_ref"),
        regulated_environment_training_ref=_ref(prime_data.get("regulated_environment_training_ref"), "prime.regulated_environment_training_ref"),
        financial_services_training_ref=_ref(prime_data.get("financial_services_training_ref"), "prime.financial_services_training_ref"),
        facilitator_refs=_refs(prime_data.get("facilitator_refs", []), "prime.facilitator_refs"),
        reference_letter_refs=_refs(prime_data.get("reference_letter_refs", []), "prime.reference_letter_refs"),
        ai_trainings_last_3y=count,
    )

    scores = _object(score_data.get("scores", {}), "technical_score.scores")
    technical_score = BuyerTechnicalScore(
        scores=scores,
        evidence_refs=_refs(score_data.get("evidence_refs", []), "technical_score.evidence_refs"),
    )

    path_rows = _array(data.get("training_pathways", []), "training_pathways")
    pathways: list[TrainingPathway] = []
    for index, raw in enumerate(path_rows):
        row = _object(raw, f"training_pathways[{index}]")
        role = row.get("role_group", "")
        if not isinstance(role, str):
            raise ValueError(f"training_pathways[{index}].role_group must be a string")
        pathways.append(TrainingPathway(
            role_group=role,
            learning_outcomes=_strings(row.get("learning_outcomes", []), f"training_pathways[{index}].learning_outcomes"),
            delivery_modes=_strings(row.get("delivery_modes", []), f"training_pathways[{index}].delivery_modes"),
            evaluation_methods=_strings(row.get("evaluation_methods", []), f"training_pathways[{index}].evaluation_methods"),
            artefacts=_strings(row.get("artefacts", []), f"training_pathways[{index}].artefacts"),
        ))

    owner = workshare_data.get("owner", "")
    commercial_state = workshare_data.get("commercial_state", "PAID_SCOPE_TO_BE_AGREED")
    if not isinstance(owner, str) or not isinstance(commercial_state, str):
        raise ValueError("paid_workshare owner/commercial_state must be strings")
    workshare = PaidWorkshare(
        owner=owner,
        deliverables=_strings(workshare_data.get("deliverables", []), "paid_workshare.deliverables"),
        acceptance_criteria=_strings(workshare_data.get("acceptance_criteria", []), "paid_workshare.acceptance_criteria"),
        exclusions=_strings(workshare_data.get("exclusions", []), "paid_workshare.exclusions"),
        commercial_state=commercial_state,
    )

    # Candidate assertions remain visible in receipts, but core v2 hard-HOLDs them.
    authority = SubmissionAuthority(
        portal_account_confirmed=authority_data.get("portal_account_confirmed") is True,
        authorized_signatory_confirmed=authority_data.get("authorized_signatory_confirmed") is True,
        prime_approved_submission=authority_data.get("prime_approved_submission") is True,
    )
    return compile_readiness_pack(
        prime=prime,
        technical_score=technical_score,
        pathways=tuple(pathways),
        workshare=workshare,
        submission_authority=authority,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile Sasria RFP2026/22 evidence without inventing prime qualifications.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args(argv)
    try:
        pack = compile_from_dict(_load(args.input))
    except Exception as exc:
        print(f"INPUT_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(pack, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    try:
        if args.json_out:
            args.json_out.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        if args.markdown_out:
            args.markdown_out.write_text(render_markdown(pack), encoding="utf-8")
    except Exception as exc:
        print(f"OUTPUT_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0 if pack["submission_status"] == "SUBMISSION_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
