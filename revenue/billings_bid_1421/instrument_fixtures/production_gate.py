from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_REQUIREMENTS = HERE / "production_acceptance_requirements.json"
DEFAULT_CANDIDATE = HERE / "production_candidate_evidence.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_EVIDENCE_KEYS = {
    "password", "secret", "token", "api_key", "apikey", "credential",
    "private_key", "connection_string",
}


class GateInputError(ValueError):
    pass


def _reject_secret_keys(value: Any, path: str = "candidate") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_EVIDENCE_KEYS:
                raise GateInputError(f"forbidden secret-bearing key at {path}.{key}")
            _reject_secret_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_keys(child, f"{path}[{index}]")


def _validate_evidence(evidence: dict, gate_id: str) -> None:
    required = {"uri", "sha256", "artifact_type", "verification"}
    missing = sorted(required - set(evidence))
    if missing:
        raise GateInputError(f"{gate_id}: evidence missing fields {missing}")
    if not isinstance(evidence["uri"], str) or not evidence["uri"].strip():
        raise GateInputError(f"{gate_id}: evidence uri is empty")
    if not SHA256_RE.fullmatch(str(evidence["sha256"])):
        raise GateInputError(f"{gate_id}: evidence sha256 must be 64 lowercase hex characters")
    if not isinstance(evidence["artifact_type"], str) or not evidence["artifact_type"].strip():
        raise GateInputError(f"{gate_id}: evidence artifact_type is empty")
    if not isinstance(evidence["verification"], str) or not evidence["verification"].strip():
        raise GateInputError(f"{gate_id}: evidence verification is empty")


def evaluate(requirements: dict, candidate: dict) -> dict:
    _reject_secret_keys(candidate)
    if candidate.get("requirements_id") != requirements.get("requirements_id"):
        raise GateInputError("candidate requirements_id does not match")
    requirement_rows = requirements.get("requirements")
    if not isinstance(requirement_rows, list) or not requirement_rows:
        raise GateInputError("requirements list is empty")
    candidate_gates = candidate.get("gates")
    if not isinstance(candidate_gates, dict):
        raise GateInputError("candidate gates must be an object")

    requirement_ids = [row.get("gate_id") for row in requirement_rows]
    if None in requirement_ids or len(requirement_ids) != len(set(requirement_ids)):
        raise GateInputError("requirement gate ids must be unique and nonempty")
    missing_gate_records = sorted(set(requirement_ids) - set(candidate_gates))
    extra_gate_records = sorted(set(candidate_gates) - set(requirement_ids))
    if missing_gate_records or extra_gate_records:
        raise GateInputError(
            f"candidate gate-set mismatch missing={missing_gate_records} extra={extra_gate_records}"
        )

    satisfied: list[str] = []
    unsatisfied: list[dict[str, str]] = []
    for requirement in requirement_rows:
        gate_id = requirement["gate_id"]
        row = candidate_gates[gate_id]
        state = row.get("state")
        if state not in {"SATISFIED", "MISSING", "FAILED"}:
            raise GateInputError(f"{gate_id}: unsupported state {state!r}")
        if state == "SATISFIED":
            evidence = row.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                raise GateInputError(f"{gate_id}: SATISFIED requires evidence")
            for artifact in evidence:
                if not isinstance(artifact, dict):
                    raise GateInputError(f"{gate_id}: evidence entries must be objects")
                _validate_evidence(artifact, gate_id)
            expected_assertions = set(requirement.get("acceptance_assertions", []))
            actual_assertions = set(row.get("assertions_passed", []))
            if actual_assertions != expected_assertions:
                raise GateInputError(
                    f"{gate_id}: assertions mismatch missing={sorted(expected_assertions - actual_assertions)} "
                    f"extra={sorted(actual_assertions - expected_assertions)}"
                )
            if not row.get("verified_by") or not row.get("verified_at"):
                raise GateInputError(f"{gate_id}: SATISFIED requires verified_by and verified_at")
            satisfied.append(gate_id)
        else:
            unsatisfied.append({"gate_id": gate_id, "state": state, "gap": row.get("gap") or "unspecified"})

    ready = not unsatisfied
    expected_decision = "PRODUCTION_READY" if ready else "NOT_READY"
    if candidate.get("release_decision") != expected_decision:
        raise GateInputError(
            f"release_decision must be {expected_decision} for the measured gate state"
        )
    return {
        "candidate_id": candidate.get("candidate_id"),
        "production_ready": ready,
        "release_decision": expected_decision,
        "required_gates": len(requirement_rows),
        "satisfied_gates": len(satisfied),
        "unsatisfied_gates": len(unsatisfied),
        "satisfied_gate_ids": satisfied,
        "unsatisfied": unsatisfied,
    }


def load_and_evaluate(requirements_path: Path, candidate_path: Path) -> dict:
    requirements = json.loads(requirements_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    return evaluate(requirements, candidate)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed AquaTrace production acceptance gate")
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = load_and_evaluate(args.requirements, args.candidate)
    except (OSError, json.JSONDecodeError, GateInputError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True))
        return 1
    if args.json:
        print(json.dumps({"valid": True, **result}, indent=2, sort_keys=True))
    else:
        print(
            f"{result['release_decision']} required={result['required_gates']} "
            f"satisfied={result['satisfied_gates']} unsatisfied={result['unsatisfied_gates']}"
        )
    return 0 if result["production_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
