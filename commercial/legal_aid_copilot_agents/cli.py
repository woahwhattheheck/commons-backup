"""CLI for compiling a deterministic Copilot-agent training evidence pack."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
from typing import Any

from .core import (
    AdoptionMetrics,
    ComparableEngagement,
    EvaluationCase,
    GovernanceReview,
    PartnerEvidence,
    Reference,
    Trainer,
    compile_delivery_pack,
    render_markdown,
)


_INPUT_ERRORS = (
    OSError,
    UnicodeError,
    json.JSONDecodeError,
    TypeError,
    ValueError,
    KeyError,
    AttributeError,
)


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    return data


def _build_partner(data: dict[str, Any]) -> PartnerEvidence:
    trainer_data = data.get("trainer")
    trainer = None
    if trainer_data:
        trainer = Trainer(
            name=trainer_data["name"],
            role=trainer_data["role"],
            copilot_experience_summary=trainer_data["copilot_experience_summary"],
            availability_start=date.fromisoformat(trainer_data["availability_start"]),
            availability_end=date.fromisoformat(trainer_data["availability_end"]),
        )
    return PartnerEvidence(
        company_name=data.get("company_name", ""),
        company_profile=data.get("company_profile", ""),
        trainer=trainer,
        comparable_engagements=tuple(ComparableEngagement(**item) for item in data.get("comparable_engagements", [])),
        references=tuple(Reference(**item) for item in data.get("references", [])),
        subcontract_role=data.get("subcontract_role", ""),
        commercial_split_discussed=data.get("commercial_split_discussed") is True,
        sample_agreement_available=data.get("sample_agreement_available") is True,
    )


def compile_from_dict(data: dict[str, Any]) -> dict[str, Any]:
    return compile_delivery_pack(
        partner=_build_partner(data.get("partner", {})),
        governance=GovernanceReview(
            controls=data.get("governance", {}).get("controls", {}),
            notes=data.get("governance", {}).get("notes", {}),
        ),
        evaluations=tuple(
            EvaluationCase(
                case_id=item["case_id"],
                scores=item.get("scores", {}),
                evidence_refs=tuple(item.get("evidence_refs", [])),
                observed_result=item.get("observed_result", ""),
            )
            for item in data.get("evaluations", [])
        ),
        adoption=AdoptionMetrics(**data.get("adoption", {})),
    )


def _invalid_input_pack() -> dict[str, Any]:
    return {
        "schema": "tjlabs.copilot_agent_training_evidence.v1",
        "delivery_status": "HOLD",
        "delivery_blockers": ["invalid_input_evidence"],
        "error": {"code": "invalid_input_evidence"},
        "claims_boundary": "Malformed or unavailable evidence cannot satisfy a proposal or delivery gate.",
    }


def _render_invalid_markdown(pack: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Copilot Agent Training Evidence Pack",
            "",
            "- Delivery status: **HOLD**",
            "- Error: `invalid_input_evidence`",
            "",
            str(pack["claims_boundary"]),
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile Copilot-agent training evidence without inventing missing proof.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args(argv)

    invalid_input = False
    try:
        pack = compile_from_dict(_load(args.input))
    except _INPUT_ERRORS:
        pack = _invalid_input_pack()
        invalid_input = True

    rendered_json = json.dumps(pack, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        args.json_out.write_text(rendered_json, encoding="utf-8")
    else:
        print(rendered_json, end="")
    if args.markdown_out:
        rendered_markdown = _render_invalid_markdown(pack) if invalid_input else render_markdown(pack)
        args.markdown_out.write_text(rendered_markdown, encoding="utf-8")
    return 0 if pack["delivery_status"] == "ACCEPTANCE_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
