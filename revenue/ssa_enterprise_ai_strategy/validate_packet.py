#!/usr/bin/env python3
"""Fail-closed packaging validator for the SSA agentic-reliability workstream.

This checks claim/evidence boundaries in ``acceptance_matrix.json``. It does
not validate any SSA system, policy, compliance regime, production model, or
customer outcome.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_MATRIX = HERE / "acceptance_matrix.json"
EXPECTED_SOLICITATION = "28321326RI0000041"
REQUIRED_FORBIDDEN_CLAIMS = {
    "ssa_endorsement_or_award",
    "prime_eligibility_without_verified_entity_facts",
    "federal_contract_vehicle_without_evidence",
    "compliance_certification_without_authority",
    "production_readiness_from_synthetic_evidence",
    "autonomous_irreversible_decision_authority",
    "realized_roi_without_measured_baseline",
}
REQUIRED_CONTROL_FIELDS = {
    "id",
    "category",
    "objective",
    "fixture",
    "failure_injection",
    "pass_condition",
    "evidence",
    "human_authority",
    "human_authority_required",
    "baseline_required",
}


class PacketError(ValueError):
    """Raised when the packet weakens a mandatory claim/evidence boundary."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PacketError(message)


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_packet(packet: dict[str, Any]) -> None:
    _require(packet.get("schema_version") == 1, "schema_version must be 1")
    _require(
        packet.get("solicitation") == EXPECTED_SOLICITATION,
        f"solicitation must be {EXPECTED_SOLICITATION}",
    )
    _require(
        packet.get("procurement_state") == "market_research_rfi",
        "procurement_state must stay market_research_rfi",
    )
    _require(
        packet.get("customer_authority_retained") is True,
        "customer_authority_retained must be true",
    )
    _require(
        packet.get("production_write_allowed") is False,
        "production_write_allowed must remain false",
    )
    _require(
        packet.get("direct_agency_submission_authorized") is False,
        "direct_agency_submission_authorized must remain false",
    )

    qualifications = packet.get("qualification_evidence")
    _require(isinstance(qualifications, dict), "qualification_evidence must be an object")
    for field in ("uei_verified", "federal_vehicle_verified", "ssa_past_performance_verified"):
        _require(
            qualifications.get(field) is False,
            f"{field} may change only after a separately verified owner update",
        )

    forbidden = packet.get("forbidden_claims")
    _require(isinstance(forbidden, list), "forbidden_claims must be a list")
    _require(
        REQUIRED_FORBIDDEN_CLAIMS.issubset(set(forbidden)),
        "forbidden_claims is missing a mandatory non-claim",
    )

    controls = packet.get("controls")
    _require(isinstance(controls, list) and controls, "controls must be a non-empty list")

    seen_ids: set[str] = set()
    categories: set[str] = set()
    for index, control in enumerate(controls):
        _require(isinstance(control, dict), f"control[{index}] must be an object")
        missing = REQUIRED_CONTROL_FIELDS - set(control)
        _require(not missing, f"control[{index}] missing fields: {sorted(missing)}")

        control_id = control["id"]
        _require(_nonempty_string(control_id), f"control[{index}].id must be non-empty")
        _require(control_id not in seen_ids, f"duplicate control id: {control_id}")
        seen_ids.add(control_id)

        for field in ("category", "objective", "fixture", "failure_injection", "pass_condition", "human_authority"):
            _require(
                _nonempty_string(control[field]),
                f"{control_id}.{field} must be a non-empty string",
            )
        categories.add(control["category"])

        evidence = control["evidence"]
        _require(
            isinstance(evidence, list) and len(evidence) >= 2,
            f"{control_id}.evidence must name at least two retained evidence fields",
        )
        _require(
            all(_nonempty_string(item) for item in evidence),
            f"{control_id}.evidence contains an invalid entry",
        )
        _require(
            len(evidence) == len(set(evidence)),
            f"{control_id}.evidence contains duplicate entries",
        )
        _require(
            control["human_authority_required"] is True,
            f"{control_id}.human_authority_required must remain true",
        )
        _require(
            isinstance(control["baseline_required"], bool),
            f"{control_id}.baseline_required must be boolean",
        )
        if control["category"] == "measurement":
            _require(
                control["baseline_required"] is True,
                f"{control_id}: measurement claims require a baseline",
            )
            _require(
                "baseline_id" in evidence and "observed_values" in evidence,
                f"{control_id}: measurement evidence must bind baseline and observations",
            )

    required_categories = {
        "reliability",
        "governance",
        "access_control",
        "auditability",
        "failure_handling",
        "data_handling",
        "recovery",
        "measurement",
    }
    _require(
        required_categories.issubset(categories),
        f"controls missing categories: {sorted(required_categories - categories)}",
    )


def load_packet(path: Path = DEFAULT_MATRIX) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PacketError(f"cannot load packet: {exc}") from exc
    _require(isinstance(data, dict), "packet root must be an object")
    return data


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) > 1:
        print("usage: validate_packet.py [acceptance_matrix.json]", file=sys.stderr)
        return 2
    path = Path(args[0]) if args else DEFAULT_MATRIX
    try:
        validate_packet(load_packet(path))
    except PacketError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    print(f"VALID: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
