#!/usr/bin/env python3
"""Deterministic failure/recovery proof for the Same-Day Agent Survival offer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class InjectedCrash(RuntimeError):
    """Intentional halt after the failure checkpoint for resume verification."""


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def apply_effect(state: dict[str, Any], operation_key: str) -> str:
    effects = state.setdefault("effects", {})
    if operation_key in effects:
        return "DEDUPED"
    effects[operation_key] = {"result": "PUBLIC_SAFE_EFFECT_APPLIED"}
    return "APPLIED"


def run_canary(
    intake_path: Path,
    state_path: Path,
    receipt_path: Path,
    halt_after_injected_failure: bool = False,
) -> dict[str, Any]:
    intake = read_json(intake_path)
    sentence = intake.get("sentence")
    if not isinstance(sentence, str) or not sentence.strip():
        raise ValueError("intake.sentence must be a non-empty string")

    sentence = sentence.strip()
    intake_hash = sha256_text(sentence)
    operation_key = f"survival-proof:{intake_hash[:16]}"
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    if state_path.exists():
        state = read_json(state_path)
        if state.get("intake_sha256") != intake_hash:
            raise ValueError("existing state belongs to a different intake sentence")
    else:
        state = {
            "phase": "PREPARED",
            "intake_sha256": intake_hash,
            "operation_key": operation_key,
            "failure_injected": False,
            "attempts": 0,
            "dedupe_hits": 0,
            "effects": {},
        }
        write_json(state_path, state)

    if state.get("phase") != "DONE":
        state["attempts"] += 1
        first_result = apply_effect(state, operation_key)
        state["phase"] = "EFFECT_OBSERVED_BEFORE_CHECKPOINT"
        write_json(state_path, state)

        if not state["failure_injected"]:
            state["failure_injected"] = True
            state["failure_point"] = "after_effect_before_done_checkpoint"
            write_json(state_path, state)

            if halt_after_injected_failure:
                raise InjectedCrash(
                    "intentional halt after persisted failure checkpoint"
                )

            state["attempts"] += 1
            recovery_result = apply_effect(state, operation_key)
            if recovery_result == "DEDUPED":
                state["dedupe_hits"] += 1
            state["recovery_result"] = recovery_result
        else:
            if first_result == "DEDUPED":
                state["dedupe_hits"] += 1
            state["recovery_result"] = first_result

        state["phase"] = "DONE"
        write_json(state_path, state)

    effect_count = len(state.get("effects", {}))
    accepted = (
        state.get("phase") == "DONE"
        and state.get("failure_injected") is True
        and effect_count == 1
        and state.get("dedupe_hits", 0) >= 1
    )

    receipt = {
        "offer_id": "same-day-agent-survival-proof",
        "status": "LANDED" if accepted else "BLOCKED",
        "contract": {
            "input": "one non-confidential outcome/failure sentence",
            "expected_output": (
                "forced failure is visible; recovery reaches DONE with exactly one effect"
            ),
            "environment": {
                "runtime": "Python 3 standard library",
                "system": "provider-controlled public-safe filesystem",
            },
            "window": {
                "kind": "PUBLIC_EXAMPLE_NOT_CUSTOMER_SLA",
                "timezone": "America/New_York",
                "window_start": None,
                "window_end": None,
            },
        },
        "intake": {"sentence": sentence, "sha256": intake_hash},
        "canary": {
            "operation_key": operation_key,
            "failure_injected": bool(state.get("failure_injected")),
            "failure_point": state.get("failure_point"),
            "attempts": state.get("attempts", 0),
            "recovery_result": state.get("recovery_result"),
            "dedupe_hits": state.get("dedupe_hits", 0),
            "external_effect_count": effect_count,
            "final_phase": state.get("phase"),
        },
        "acceptance": {
            "forced_failure_visible": bool(state.get("failure_injected")),
            "recovery_reached_done": state.get("phase") == "DONE",
            "exactly_once_effect": effect_count == 1,
            "replay_deduped": state.get("dedupe_hits", 0) >= 1,
        },
        "artifacts": {
            "code": "revenue/production_survival/survival_canary.py",
            "code_sha256": code_hash,
            "intake": "revenue/production_survival/example_intake.json",
            "receipt": "revenue/production_survival/example_receipt.json",
            "schema": "revenue/production_survival/receipt.schema.json",
        },
        "limits": [
            "uses synthetic public-safe state",
            "does not access or fix a buyer production system",
            "demonstrates the receipt and exactly-once recovery pattern only",
        ],
    }
    if not accepted:
        receipt["blocked_edge"] = (
            "canary did not prove visible failure and exactly-once recovery"
        )
    write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument(
        "--halt-after-injected-failure",
        action="store_true",
        help="Exit 75 after persisting the failure checkpoint; rerun without this flag",
    )
    args = parser.parse_args()

    try:
        receipt = run_canary(
            args.intake,
            args.state,
            args.receipt,
            halt_after_injected_failure=args.halt_after_injected_failure,
        )
    except InjectedCrash as error:
        print(str(error))
        return 75
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "LANDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
