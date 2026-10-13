# SPDX-License-Identifier: Apache-2.0
"""Frozen grid, provenance, and policy validation."""
from __future__ import annotations

from typing import Any, Mapping

from gate_common import GateError, SCHEMA_VERSION, finite_number, is_int

POLICY_FIELDS = {
    "min_mean_own_delta",
    "min_median_own_delta",
    "min_mean_margin_delta",
    "min_positive_cell_fraction",
    "min_positive_pair_fraction",
    "max_result_regressions",
    "max_baseline_win_regressions",
    "max_new_losses",
    "max_negative_opponent_strata",
    "max_negative_seat_strata",
    "min_worst_cell_own_delta",
    "require_any_change",
}
PROVENANCE_FIELDS = {
    "engine_commit",
    "engine_sha256",
    "runner_commit",
    "runner_sha256",
    "baseline_artifact_sha256",
    "candidate_artifact_sha256",
}


def _unique_ints(values: Any, *, label: str) -> list[int]:
    if not isinstance(values, list) or not values:
        raise GateError(f"{label}: expected a non-empty list")
    out: list[int] = []
    seen: set[int] = set()
    for index, value in enumerate(values):
        if not is_int(value):
            raise GateError(f"{label}[{index}]: expected an integer")
        if value in seen:
            raise GateError(f"{label}: duplicate value {value}")
        seen.add(value)
        out.append(value)
    return out


def _unique_strings(values: Any, *, label: str) -> list[str]:
    if not isinstance(values, list) or not values:
        raise GateError(f"{label}: expected a non-empty list")
    out: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise GateError(f"{label}[{index}]: expected a non-empty string")
        if value in seen:
            raise GateError(f"{label}: duplicate value {value!r}")
        seen.add(value)
        out.append(value)
    return out


def _hex(value: Any, *, lengths: tuple[int, ...], label: str) -> str:
    if not isinstance(value, str) or len(value) not in lengths:
        choices = " or ".join(str(length) for length in lengths)
        raise GateError(f"{label}: expected {choices} hexadecimal characters")
    try:
        int(value, 16)
    except ValueError as exc:
        raise GateError(f"{label}: expected hexadecimal characters") from exc
    return value.lower()


def _provenance(value: Any, *, label: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise GateError(f"{label}: expected an object")
    missing = sorted(PROVENANCE_FIELDS - set(value))
    extra = sorted(set(value) - PROVENANCE_FIELDS)
    if missing or extra:
        raise GateError(f"{label}: provenance keys mismatch; missing={missing}, extra={extra}")
    return {
        "engine_commit": _hex(value["engine_commit"], lengths=(40, 64), label=f"{label}.engine_commit"),
        "engine_sha256": _hex(value["engine_sha256"], lengths=(64,), label=f"{label}.engine_sha256"),
        "runner_commit": _hex(value["runner_commit"], lengths=(40, 64), label=f"{label}.runner_commit"),
        "runner_sha256": _hex(value["runner_sha256"], lengths=(64,), label=f"{label}.runner_sha256"),
        "baseline_artifact_sha256": _hex(
            value["baseline_artifact_sha256"], lengths=(64,), label=f"{label}.baseline_artifact_sha256"
        ),
        "candidate_artifact_sha256": _hex(
            value["candidate_artifact_sha256"], lengths=(64,), label=f"{label}.candidate_artifact_sha256"
        ),
    }


def _nonnegative_int(value: Any, *, label: str) -> int:
    if not is_int(value) or value < 0:
        raise GateError(f"{label}: expected a non-negative integer")
    return value


def _fraction(value: Any, *, label: str) -> float:
    result = finite_number(value, label=label)
    if not 0.0 <= result <= 1.0:
        raise GateError(f"{label}: expected a value in [0, 1]")
    return result


def _policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError("contract.policy: expected an object")
    missing = sorted(POLICY_FIELDS - set(value))
    extra = sorted(set(value) - POLICY_FIELDS)
    if missing or extra:
        raise GateError(f"contract.policy keys mismatch; missing={missing}, extra={extra}")
    policy = {
        "min_mean_own_delta": finite_number(value["min_mean_own_delta"], label="policy.min_mean_own_delta"),
        "min_median_own_delta": finite_number(value["min_median_own_delta"], label="policy.min_median_own_delta"),
        "min_mean_margin_delta": finite_number(value["min_mean_margin_delta"], label="policy.min_mean_margin_delta"),
        "min_positive_cell_fraction": _fraction(value["min_positive_cell_fraction"], label="policy.min_positive_cell_fraction"),
        "min_positive_pair_fraction": _fraction(value["min_positive_pair_fraction"], label="policy.min_positive_pair_fraction"),
        "max_result_regressions": _nonnegative_int(value["max_result_regressions"], label="policy.max_result_regressions"),
        "max_baseline_win_regressions": _nonnegative_int(
            value["max_baseline_win_regressions"], label="policy.max_baseline_win_regressions"
        ),
        "max_new_losses": _nonnegative_int(value["max_new_losses"], label="policy.max_new_losses"),
        "max_negative_opponent_strata": _nonnegative_int(
            value["max_negative_opponent_strata"], label="policy.max_negative_opponent_strata"
        ),
        "max_negative_seat_strata": _nonnegative_int(
            value["max_negative_seat_strata"], label="policy.max_negative_seat_strata"
        ),
        "min_worst_cell_own_delta": None,
        "require_any_change": value["require_any_change"],
    }
    if value["min_worst_cell_own_delta"] is not None:
        policy["min_worst_cell_own_delta"] = finite_number(
            value["min_worst_cell_own_delta"], label="policy.min_worst_cell_own_delta"
        )
    if not isinstance(policy["require_any_change"], bool):
        raise GateError("policy.require_any_change: expected a boolean")
    return policy


def validate_contract(obj: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "schema_version", "panel_id", "baseline_name", "candidate_name",
        "seeds", "opponents", "seats", "expected_cells", "provenance", "policy",
    }
    missing, extra = sorted(fields - set(obj)), sorted(set(obj) - fields)
    if missing or extra:
        raise GateError(f"contract keys mismatch; missing={missing}, extra={extra}")
    if not is_int(obj["schema_version"]) or obj["schema_version"] != SCHEMA_VERSION:
        raise GateError(f"contract.schema_version must equal integer {SCHEMA_VERSION}")
    for key in ("panel_id", "baseline_name", "candidate_name"):
        if not isinstance(obj[key], str) or not obj[key].strip():
            raise GateError(f"contract.{key}: expected a non-empty string")
    if obj["baseline_name"] == obj["candidate_name"]:
        raise GateError("contract baseline_name and candidate_name must differ")
    seeds = _unique_ints(obj["seeds"], label="contract.seeds")
    opponents = _unique_strings(obj["opponents"], label="contract.opponents")
    seats = _unique_ints(obj["seats"], label="contract.seats")
    if set(seats) != {0, 1} or len(seats) != 2:
        raise GateError("contract.seats must contain exactly [0, 1] in either order")
    expected = len(seeds) * len(opponents) * 2
    if not is_int(obj["expected_cells"]) or obj["expected_cells"] != expected:
        raise GateError(f"contract.expected_cells must equal grid size {expected}")
    return {
        "schema_version": SCHEMA_VERSION,
        "panel_id": obj["panel_id"],
        "baseline_name": obj["baseline_name"],
        "candidate_name": obj["candidate_name"],
        "seeds": seeds,
        "opponents": opponents,
        "seats": seats,
        "expected_cells": expected,
        "provenance": _provenance(obj["provenance"], label="contract.provenance"),
        "policy": _policy(obj["policy"]),
    }


def validate_evidence(obj: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"schema_version", "panel_id", "provenance", "exact_command"}
    missing, extra = sorted(fields - set(obj)), sorted(set(obj) - fields)
    if missing or extra:
        raise GateError(f"evidence keys mismatch; missing={missing}, extra={extra}")
    if not is_int(obj["schema_version"]) or obj["schema_version"] != SCHEMA_VERSION:
        raise GateError(f"evidence.schema_version must equal integer {SCHEMA_VERSION}")
    if obj["panel_id"] != contract["panel_id"]:
        raise GateError("evidence.panel_id does not match contract")
    if not isinstance(obj["exact_command"], str) or not obj["exact_command"].strip():
        raise GateError("evidence.exact_command: expected a non-empty string")
    provenance = _provenance(obj["provenance"], label="evidence.provenance")
    if provenance != contract["provenance"]:
        drift = {
            key: {"expected": contract["provenance"][key], "observed": provenance[key]}
            for key in provenance if provenance[key] != contract["provenance"][key]
        }
        raise GateError(f"provenance drift: {drift}")
    return {"provenance": provenance, "exact_command": obj["exact_command"]}
