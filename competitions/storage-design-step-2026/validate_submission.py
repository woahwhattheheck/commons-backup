"""Fail-closed readiness gate for the STEP submission packet."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED_FALSE_TO_TRUE = (
    "owner_eligibility_verified",
    "competitor_background_owner_verified",
    "independent_novelty_search_complete",
    "quote_backed_manufacturing_model_complete",
    "ehs_hazmat_review_complete",
    "final_public_slide_human_reviewed",
    "final_90s_video_complete",
    "technical_claims_human_reviewed",
    "hero_x_terms_accepted_by_owner",
    "human_submission_authorized",
)


def validate(raw: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["root must be an object"]
    expected = {"schema", "op", "state", "ai_disclosure_present", "gates", "truth"}
    if set(raw) != expected:
        errors.append(f"root keys must equal {sorted(expected)}")
        return errors
    if raw["schema"] != "step-readiness/v1":
        errors.append("unsupported schema")
    if raw["op"] != "DOE-STORAGE-DESIGN-STEP-ZRVQ7M2-20260913":
        errors.append("wrong operation id")
    if raw["ai_disclosure_present"] is not True:
        errors.append("AI disclosure must be present")
    gates = raw["gates"]
    if not isinstance(gates, dict) or set(gates) != set(REQUIRED_FALSE_TO_TRUE):
        errors.append("gate set mismatch")
        return errors
    if any(not isinstance(v, bool) for v in gates.values()):
        errors.append("all gates must be booleans")
    truth = raw["truth"]
    if not isinstance(truth, dict):
        errors.append("truth must be an object")
        return errors
    required_truth = {
        "literature_performance_is_not_entrant_test_data": True,
        "synthetic_cost_scenario_is_not_supplier_quote": True,
        "no_prize_or_submission_claim": True,
    }
    if truth != required_truth:
        errors.append("truth boundary mismatch")
    ready = not errors and all(gates.values())
    expected_state = "READY_FOR_HUMAN_SUBMISSION" if ready else "BLOCKED"
    if raw["state"] != expected_state:
        errors.append(f"state must be {expected_state}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", default=str(Path(__file__).with_name("readiness.json")))
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    raw = json.loads(Path(args.packet).read_text(encoding="utf-8"))
    errors = validate(raw)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    if args.require_ready and raw["state"] != "READY_FOR_HUMAN_SUBMISSION":
        print("BLOCKED: unresolved human/evidence gates remain")
        return 3
    print(raw["state"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
