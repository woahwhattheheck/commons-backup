#!/usr/bin/env python3
"""Fail-closed whole-cycle certificate for TITAN W10 fertilizer experiments.

The checker compares two deterministic observation traces from the same
engine, evaluator, opponent, seed, start state, protected commitments and
horizon. It certifies a fertilizer change only when additional production is
actually harvested, deposited, sold and retained as positive net cash without
new loss or protected-obligation regressions.

This module is deliberately observation-only. It does not choose actions or
mutate the canonical TITAN producer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

TRACE_SCHEMA = "titan.w10.realized-fertilizer-trace/v1"
CERTIFICATE_SCHEMA = "titan.w10.realized-fertilizer-certificate/v1"

_TOP_LEVEL_KEYS = {
    "schema",
    "variant",
    "policy_sha256",
    "identity",
    "capacity",
    "snapshots",
}
_IDENTITY_KEYS = {
    "engine_sha256",
    "evaluator_sha256",
    "opponent_sha256",
    "start_state_sha256",
    "counterfactual_protocol_sha256",
    "protected_commitments_sha256",
    "seed",
    "controlled_player",
    "horizon_tick",
    "worker_tick_budget",
    "product",
}
_CAPACITY_KEYS = {"carry_units", "shed_units"}
_SNAPSHOT_FIELDS = (
    "tick",
    "fertilizer_actions",
    "produced_units",
    "harvested_units",
    "deposited_units",
    "sold_units",
    "cash",
    "discarded_units",
    "worker_ticks_used",
    "travel_steps",
    "watering_actions",
    "harvest_actions",
    "deposit_actions",
    "sale_actions",
    "protected_obligation_misses",
    "protected_stock_shortfall_units",
    "carry_units",
    "shed_units",
)
_SNAPSHOT_KEYS = set(_SNAPSHOT_FIELDS)
_CUMULATIVE_FIELDS = (
    "fertilizer_actions",
    "produced_units",
    "harvested_units",
    "deposited_units",
    "sold_units",
    "discarded_units",
    "worker_ticks_used",
    "travel_steps",
    "watering_actions",
    "harvest_actions",
    "deposit_actions",
    "sale_actions",
    "protected_obligation_misses",
    "protected_stock_shortfall_units",
)
_ACTION_COUNTER_FIELDS = (
    "fertilizer_actions",
    "travel_steps",
    "watering_actions",
    "harvest_actions",
    "deposit_actions",
    "sale_actions",
)
_OUTPUT_FIELDS = (
    "produced_units",
    "harvested_units",
    "deposited_units",
    "sold_units",
)
_REPORT_DELTA_FIELDS = (
    *_CUMULATIVE_FIELDS,
    "cash",
    "carry_units",
    "shed_units",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PRODUCT_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")


class TraceValidationError(ValueError):
    """Raised when an input trace cannot safely participate in a comparison."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_sha256(value: Any) -> str:
    """Return the SHA-256 of canonical compact JSON for *value*."""

    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _safe_sha256(value: Any) -> str | None:
    try:
        return canonical_sha256(value)
    except (TypeError, ValueError):
        return None


def _require_mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TraceValidationError(f"{where} must be an object")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        pieces: list[str] = []
        if missing:
            pieces.append("missing=" + ",".join(missing))
        if extra:
            pieces.append("extra=" + ",".join(extra))
        raise TraceValidationError(f"{where} keys invalid ({'; '.join(pieces)})")


def _require_int(value: Any, where: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TraceValidationError(f"{where} must be an integer (booleans are rejected)")
    if minimum is not None and value < minimum:
        raise TraceValidationError(f"{where} must be >= {minimum}")
    return value


def _require_sha256(value: Any, where: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise TraceValidationError(f"{where} must be a lowercase 64-character SHA-256")
    return value


def _validate_identity(raw: Any, where: str) -> dict[str, Any]:
    identity = _require_mapping(raw, where)
    _require_exact_keys(identity, _IDENTITY_KEYS, where)
    normalized: dict[str, Any] = {}
    for field in (
        "engine_sha256",
        "evaluator_sha256",
        "opponent_sha256",
        "start_state_sha256",
        "counterfactual_protocol_sha256",
        "protected_commitments_sha256",
    ):
        normalized[field] = _require_sha256(identity[field], f"{where}.{field}")
    normalized["seed"] = _require_int(identity["seed"], f"{where}.seed", minimum=0)
    normalized["controlled_player"] = _require_int(
        identity["controlled_player"], f"{where}.controlled_player", minimum=0
    )
    normalized["horizon_tick"] = _require_int(
        identity["horizon_tick"], f"{where}.horizon_tick", minimum=1
    )
    normalized["worker_tick_budget"] = _require_int(
        identity["worker_tick_budget"], f"{where}.worker_tick_budget", minimum=1
    )
    product = identity["product"]
    if not isinstance(product, str) or _PRODUCT_RE.fullmatch(product) is None:
        raise TraceValidationError(f"{where}.product must match {_PRODUCT_RE.pattern!r}")
    normalized["product"] = product
    return normalized


def _validate_capacity(raw: Any, where: str) -> dict[str, int]:
    capacity = _require_mapping(raw, where)
    _require_exact_keys(capacity, _CAPACITY_KEYS, where)
    return {
        "carry_units": _require_int(capacity["carry_units"], f"{where}.carry_units", minimum=0),
        "shed_units": _require_int(capacity["shed_units"], f"{where}.shed_units", minimum=0),
    }


def _validate_snapshot(
    raw: Any,
    *,
    where: str,
    capacity: Mapping[str, int],
    horizon_tick: int,
    worker_tick_budget: int,
) -> dict[str, int]:
    snapshot = _require_mapping(raw, where)
    _require_exact_keys(snapshot, _SNAPSHOT_KEYS, where)
    normalized: dict[str, int] = {}
    for field in _SNAPSHOT_FIELDS:
        minimum = None if field == "cash" else 0
        normalized[field] = _require_int(snapshot[field], f"{where}.{field}", minimum=minimum)
    if normalized["tick"] > horizon_tick:
        raise TraceValidationError(
            f"{where}.tick={normalized['tick']} exceeds horizon_tick={horizon_tick}"
        )
    if normalized["carry_units"] > capacity["carry_units"]:
        raise TraceValidationError(f"{where}.carry_units exceeds declared carry capacity")
    if normalized["shed_units"] > capacity["shed_units"]:
        raise TraceValidationError(f"{where}.shed_units exceeds declared shed capacity")
    if normalized["worker_ticks_used"] > worker_tick_budget:
        raise TraceValidationError(f"{where}.worker_ticks_used exceeds worker_tick_budget")
    accounted_actions = sum(normalized[field] for field in _ACTION_COUNTER_FIELDS)
    if accounted_actions > normalized["worker_ticks_used"]:
        raise TraceValidationError(f"{where} action counters exceed worker_ticks_used")
    return normalized


def validate_trace(raw: Any, *, expected_variant: str) -> dict[str, Any]:
    """Validate and normalize one trace using a fixed validation order."""

    trace = _require_mapping(raw, expected_variant)
    _require_exact_keys(trace, _TOP_LEVEL_KEYS, expected_variant)
    if trace["schema"] != TRACE_SCHEMA:
        raise TraceValidationError(f"{expected_variant}.schema must equal {TRACE_SCHEMA!r}")
    if trace["variant"] != expected_variant:
        raise TraceValidationError(
            f"{expected_variant}.variant must equal {expected_variant!r}"
        )
    policy_sha256 = _require_sha256(trace["policy_sha256"], f"{expected_variant}.policy_sha256")
    identity = _validate_identity(trace["identity"], f"{expected_variant}.identity")
    capacity = _validate_capacity(trace["capacity"], f"{expected_variant}.capacity")
    raw_snapshots = trace["snapshots"]
    if isinstance(raw_snapshots, (str, bytes)) or not isinstance(raw_snapshots, Sequence):
        raise TraceValidationError(f"{expected_variant}.snapshots must be an array")
    if len(raw_snapshots) < 2:
        raise TraceValidationError(f"{expected_variant}.snapshots must contain at least two rows")
    if len(raw_snapshots) > 100_000:
        raise TraceValidationError(f"{expected_variant}.snapshots exceeds the 100000-row limit")
    snapshots = [
        _validate_snapshot(
            item,
            where=f"{expected_variant}.snapshots[{index}]",
            capacity=capacity,
            horizon_tick=identity["horizon_tick"],
            worker_tick_budget=identity["worker_tick_budget"],
        )
        for index, item in enumerate(raw_snapshots)
    ]
    previous = snapshots[0]
    for index, current in enumerate(snapshots[1:], start=1):
        if current["tick"] <= previous["tick"]:
            raise TraceValidationError(
                f"{expected_variant}.snapshots[{index}].tick must be strictly increasing"
            )
        for field in _CUMULATIVE_FIELDS:
            if current[field] < previous[field]:
                raise TraceValidationError(
                    f"{expected_variant}.snapshots[{index}].{field} must be cumulative"
                )
        previous = current
    if snapshots[-1]["tick"] != identity["horizon_tick"]:
        raise TraceValidationError(
            f"{expected_variant} terminal tick {snapshots[-1]['tick']} must equal "
            f"horizon_tick {identity['horizon_tick']}"
        )
    return {
        "schema": TRACE_SCHEMA,
        "variant": expected_variant,
        "policy_sha256": policy_sha256,
        "identity": identity,
        "capacity": capacity,
        "snapshots": snapshots,
    }


def _value_at(snapshots: Sequence[Mapping[str, int]], tick: int, field: str) -> int:
    value = snapshots[0][field]
    for snapshot in snapshots[1:]:
        if snapshot["tick"] > tick:
            break
        value = snapshot[field]
    return value


def _first_positive_delta_tick(
    control: Mapping[str, Any], candidate: Mapping[str, Any], field: str
) -> int | None:
    ticks = sorted(
        {snapshot["tick"] for snapshot in control["snapshots"]}
        | {snapshot["tick"] for snapshot in candidate["snapshots"]}
    )
    for tick in ticks:
        if _value_at(candidate["snapshots"], tick, field) > _value_at(
            control["snapshots"], tick, field
        ):
            return tick
    return None


def _rejected_invalid(reason: str, *, side: str, raw: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": CERTIFICATE_SCHEMA,
        "decision": "REJECTED",
        "reasons": [f"invalid-{side}:{reason}"],
        "gates": {"valid_input": False},
        "identity": None,
        "trace_sha256": {
            "control": _safe_sha256(raw) if side == "control" else None,
            "candidate": _safe_sha256(raw) if side == "candidate" else None,
        },
        "deltas": None,
        "milestones": None,
    }
    body["certificate_sha256"] = canonical_sha256(body)
    return body


def certify_realized_fertilizer(control_raw: Any, candidate_raw: Any) -> dict[str, Any]:
    """Return a deterministic certificate; malformed input is rejected safely."""

    try:
        control = validate_trace(control_raw, expected_variant="control")
    except (TraceValidationError, TypeError, ValueError) as exc:
        return _rejected_invalid(str(exc), side="control", raw=control_raw)
    try:
        candidate = validate_trace(candidate_raw, expected_variant="fertilized")
    except (TraceValidationError, TypeError, ValueError) as exc:
        body = _rejected_invalid(str(exc), side="candidate", raw=candidate_raw)
        body["trace_sha256"]["control"] = canonical_sha256(control)
        body["certificate_sha256"] = canonical_sha256(
            {key: value for key, value in body.items() if key != "certificate_sha256"}
        )
        return body

    gates: dict[str, bool] = {}
    reasons: list[str] = []

    def gate(name: str, passed: bool, failure_reason: str) -> None:
        gates[name] = bool(passed)
        if not passed:
            reasons.append(failure_reason)

    same_identity = control["identity"] == candidate["identity"]
    gate("same_identity", same_identity, "identity-mismatch")
    same_capacity = control["capacity"] == candidate["capacity"]
    gate("same_capacity", same_capacity, "capacity-mismatch")
    start_fields = tuple(field for field in _SNAPSHOT_FIELDS if field != "tick")
    same_start = (
        control["snapshots"][0]["tick"] == candidate["snapshots"][0]["tick"]
        and all(
            control["snapshots"][0][field] == candidate["snapshots"][0][field]
            for field in start_fields
        )
    )
    gate("same_start_state", same_start, "start-state-metrics-mismatch")

    control_terminal = control["snapshots"][-1]
    candidate_terminal = candidate["snapshots"][-1]
    deltas = {
        field: candidate_terminal[field] - control_terminal[field]
        for field in _REPORT_DELTA_FIELDS
    }
    gate("fertilizer_used", deltas["fertilizer_actions"] > 0, "no-additional-fertilizer-action")
    gate("additional_production", deltas["produced_units"] > 0, "no-additional-produced-output")
    gate("additional_harvest", deltas["harvested_units"] > 0, "no-additional-harvest")
    gate("additional_deposit", deltas["deposited_units"] > 0, "no-additional-deposit")
    gate("additional_sale", deltas["sold_units"] > 0, "no-additional-sale")
    gate("positive_net_cash", deltas["cash"] > 0, "nonpositive-net-cash")

    chain_values = [deltas[field] for field in _OUTPUT_FIELDS]
    output_chain = (
        all(value > 0 for value in chain_values)
        and deltas["produced_units"] >= deltas["harvested_units"]
        and deltas["harvested_units"] >= deltas["deposited_units"]
        and deltas["deposited_units"] >= deltas["sold_units"]
    )
    gate("attributable_output_chain", output_chain, "extra-output-chain-not-attributable")
    gate("no_extra_discard", deltas["discarded_units"] <= 0, "extra-discarded-output")
    gate(
        "protected_obligations_preserved",
        deltas["protected_obligation_misses"] <= 0,
        "protected-obligation-regression",
    )
    gate(
        "protected_stock_preserved",
        deltas["protected_stock_shortfall_units"] <= 0,
        "protected-stock-regression",
    )

    milestones = {
        "fertilizer_tick": _first_positive_delta_tick(control, candidate, "fertilizer_actions"),
        "production_tick": _first_positive_delta_tick(control, candidate, "produced_units"),
        "harvest_tick": _first_positive_delta_tick(control, candidate, "harvested_units"),
        "deposit_tick": _first_positive_delta_tick(control, candidate, "deposited_units"),
        "sale_tick": _first_positive_delta_tick(control, candidate, "sold_units"),
    }
    milestone_values = list(milestones.values())
    ordered_milestones = all(value is not None for value in milestone_values)
    if ordered_milestones:
        concrete = [int(value) for value in milestone_values if value is not None]
        ordered_milestones = concrete == sorted(concrete)
    gate(
        "ordered_milestone_chain",
        ordered_milestones,
        "fertilizer-output-milestones-not-ordered",
    )

    body: dict[str, Any] = {
        "schema": CERTIFICATE_SCHEMA,
        "decision": "CERTIFIED" if all(gates.values()) else "REJECTED",
        "reasons": reasons,
        "gates": gates,
        "identity": control["identity"] if same_identity else None,
        "trace_sha256": {
            "control": canonical_sha256(control),
            "candidate": canonical_sha256(candidate),
        },
        "policy_sha256": {
            "control": control["policy_sha256"],
            "candidate": candidate["policy_sha256"],
        },
        "deltas": deltas,
        "milestones": milestones,
        "terminal": {"control": control_terminal, "candidate": candidate_terminal},
    }
    body["certificate_sha256"] = canonical_sha256(body)
    return body


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Certify a paired TITAN W10 fertilizer observation trace."
    )
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        control = _load_json(args.control)
        candidate = _load_json(args.candidate)
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    certificate = certify_realized_fertilizer(control, candidate)
    rendered = json.dumps(
        certificate,
        sort_keys=True,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (",", ":"),
    ) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if certificate["decision"] == "CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
