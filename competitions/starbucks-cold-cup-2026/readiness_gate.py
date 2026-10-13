#!/usr/bin/env python3
"""Fail-closed release gate for the Starbucks ClearFiber Shell proposal.

This tool does not establish truth. It verifies that a human release packet
contains explicit evidence references for every challenge-critical field.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "starbucks-clearfiber-readiness/v1"

REQUIRED_EVIDENCE = (
    "astm_d1003_haze_le_5",
    "plastic_free_formulation_review",
    "prohibited_substances_analytical",
    "bpi_compostability_path",
    "food_contact_regulatory_path",
    "lid_application_rigidity",
    "espresso_heat_deformation",
    "organoleptic_pass",
    "liquid_hold_24h",
    "filled_drop_1m",
    "comparative_lca",
    "hundreds_tons_scale_evidence",
    "forming_trial",
    "human_experience_section",
    "ip_ownership_review",
    "challenge_agreement_human_acceptance",
    "substantive_human_contribution",
)


def _is_plain_dict(value: Any) -> bool:
    return type(value) is dict


def _validate_evidence(value: Any, key: str) -> list[str]:
    errors: list[str] = []
    if not _is_plain_dict(value):
        return [f"{key}: evidence must be an object"]
    if set(value) != {"status", "references"}:
        errors.append(f"{key}: evidence keys must be exactly status,references")
        return errors
    if value["status"] != "verified":
        errors.append(f"{key}: status must be verified")
    refs = value["references"]
    if type(refs) is not list or not refs:
        errors.append(f"{key}: references must be a non-empty list")
    elif any(type(ref) is not str or not ref.strip() for ref in refs):
        errors.append(f"{key}: every reference must be a non-empty string")
    return errors


def evaluate(packet: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not _is_plain_dict(packet):
        return {"schema": SCHEMA, "ready": False, "errors": ["packet must be an object"]}

    allowed = {"schema", "candidate", "evidence", "release"}
    unexpected = sorted(set(packet) - allowed)
    missing = sorted(allowed - set(packet))
    if unexpected:
        errors.append("unexpected top-level keys: " + ",".join(unexpected))
    if missing:
        errors.append("missing top-level keys: " + ",".join(missing))

    if packet.get("schema") != SCHEMA:
        errors.append(f"schema must equal {SCHEMA}")

    candidate = packet.get("candidate")
    if not _is_plain_dict(candidate) or set(candidate) != {"name", "version"}:
        errors.append("candidate must contain exactly name,version")
    else:
        if candidate["name"] != "ClearFiber Shell":
            errors.append("candidate.name must be ClearFiber Shell")
        if type(candidate["version"]) is not str or not candidate["version"].strip():
            errors.append("candidate.version must be a non-empty string")

    evidence = packet.get("evidence")
    if not _is_plain_dict(evidence):
        errors.append("evidence must be an object")
    else:
        expected = set(REQUIRED_EVIDENCE)
        if set(evidence) != expected:
            miss = sorted(expected - set(evidence))
            extra = sorted(set(evidence) - expected)
            if miss:
                errors.append("missing evidence keys: " + ",".join(miss))
            if extra:
                errors.append("unexpected evidence keys: " + ",".join(extra))
        for key in REQUIRED_EVIDENCE:
            if key in evidence:
                errors.extend(_validate_evidence(evidence[key], key))

    release = packet.get("release")
    if not _is_plain_dict(release) or set(release) != {
        "external_submission_authorized",
        "solver_identity_verified",
        "solver_eligibility_verified",
    }:
        errors.append(
            "release must contain exactly external_submission_authorized,"
            "solver_identity_verified,solver_eligibility_verified"
        )
    else:
        for key, value in release.items():
            if value is not True:
                errors.append(f"release.{key} must be true")

    return {"schema": SCHEMA, "ready": not errors, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        packet = json.loads(args.packet.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    result = evaluate(packet)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("READY" if result["ready"] else "BLOCKED")
        for error in result["errors"]:
            print(f"- {error}")
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
