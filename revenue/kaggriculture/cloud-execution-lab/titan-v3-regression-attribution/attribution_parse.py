#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Strict grid, policy, terminal-ledger, and step-trace parsing."""
from __future__ import annotations

from typing import Any, Sequence

from attribution_common import (
    AttributionError,
    CellKey,
    GameCell,
    TraceStep,
    _canonical_bytes,
    _exact_keys,
    _finite,
    _hex_digest,
    _nonempty_string,
    _require_mapping,
    _sha256,
    _strict_int,
)


def _parse_grid(value: Any) -> tuple[list[CellKey], list[int], dict[str, Any]]:
    grid = _require_mapping(value, "grid")
    _exact_keys(
        grid,
        {"seeds", "opponents", "seats", "trace_step_start", "trace_step_end"},
        "grid",
    )
    raw_seeds = grid["seeds"]
    raw_opponents = grid["opponents"]
    raw_seats = grid["seats"]
    if not isinstance(raw_seeds, list) or not raw_seeds:
        raise AttributionError("grid.seeds: expected a nonempty list")
    if not isinstance(raw_opponents, list) or not raw_opponents:
        raise AttributionError("grid.opponents: expected a nonempty list")
    if not isinstance(raw_seats, list):
        raise AttributionError("grid.seats: expected [0, 1]")
    seeds = [_strict_int(item, f"grid.seeds[{index}]") for index, item in enumerate(raw_seeds)]
    opponents = [
        _nonempty_string(item, f"grid.opponents[{index}]")
        for index, item in enumerate(raw_opponents)
    ]
    seats = [_strict_int(item, f"grid.seats[{index}]") for index, item in enumerate(raw_seats)]
    if len(set(seeds)) != len(seeds):
        raise AttributionError("grid.seeds: duplicate seed")
    if len(set(opponents)) != len(opponents):
        raise AttributionError("grid.opponents: duplicate opponent")
    if seats != [0, 1]:
        raise AttributionError("grid.seats: both seats must be declared in canonical order [0, 1]")
    start = _strict_int(grid["trace_step_start"], "grid.trace_step_start")
    end = _strict_int(grid["trace_step_end"], "grid.trace_step_end")
    if start < 0 or end < start or end - start > 10_000:
        raise AttributionError("grid trace interval is invalid or unreasonably large")
    cells = [CellKey(opponent, seed, seat) for opponent in opponents for seed in seeds for seat in seats]
    steps = list(range(start, end + 1))
    normalized = {
        "seeds": seeds,
        "opponents": opponents,
        "seats": seats,
        "trace_step_start": start,
        "trace_step_end": end,
        "expected_cells": len(cells),
        "expected_trace_rows_per_build": len(cells) * len(steps),
    }
    return cells, steps, normalized


def _parse_policy(value: Any) -> dict[str, Any]:
    policy = _require_mapping(value, "policy")
    allowed = {
        "min_mean_own_delta",
        "min_mean_margin_delta",
        "max_result_regressions",
        "max_new_losses",
        "min_worst_cell_own_delta",
    }
    _exact_keys(policy, allowed, "policy")
    normalized = {
        "min_mean_own_delta": _finite(policy["min_mean_own_delta"], "policy.min_mean_own_delta"),
        "min_mean_margin_delta": _finite(policy["min_mean_margin_delta"], "policy.min_mean_margin_delta"),
        "max_result_regressions": _strict_int(
            policy["max_result_regressions"], "policy.max_result_regressions"
        ),
        "max_new_losses": _strict_int(policy["max_new_losses"], "policy.max_new_losses"),
        "min_worst_cell_own_delta": _finite(
            policy["min_worst_cell_own_delta"], "policy.min_worst_cell_own_delta"
        ),
    }
    if normalized["max_result_regressions"] < 0 or normalized["max_new_losses"] < 0:
        raise AttributionError("policy count limits must be nonnegative")
    return normalized


def _parse_games(rows: list[Any], expected: Sequence[CellKey], label: str) -> dict[CellKey, GameCell]:
    expected_set = set(expected)
    parsed: dict[CellKey, GameCell] = {}
    for index, raw in enumerate(rows):
        row = _require_mapping(raw, f"{label}[{index}]")
        _exact_keys(row, {"opponent", "seed", "candidate_seat", "status", "scores"}, f"{label}[{index}]")
        if row["status"] != "complete":
            raise AttributionError(f"{label}[{index}]: status must be complete")
        key = CellKey(
            _nonempty_string(row["opponent"], f"{label}[{index}].opponent"),
            _strict_int(row["seed"], f"{label}[{index}].seed"),
            _strict_int(row["candidate_seat"], f"{label}[{index}].candidate_seat"),
        )
        if key in parsed:
            raise AttributionError(f"{label}: duplicate cell {key}")
        scores = row["scores"]
        if not isinstance(scores, list) or len(scores) != 2:
            raise AttributionError(f"{label}[{index}].scores: expected two terminal scores")
        parsed[key] = GameCell(
            (_finite(scores[0], f"{label}[{index}].scores[0]"), _finite(scores[1], f"{label}[{index}].scores[1]"))
        )
    observed = set(parsed)
    if observed != expected_set:
        missing = [cell.as_dict() for cell in sorted(expected_set - observed)]
        extra = [cell.as_dict() for cell in sorted(observed - expected_set)]
        raise AttributionError(f"{label}: grid mismatch; missing={missing}, extra={extra}")
    return parsed


def _parse_trace(
    rows: list[Any], expected_cells: Sequence[CellKey], expected_steps: Sequence[int], label: str
) -> dict[tuple[CellKey, int], TraceStep]:
    expected_keys = {(cell, step) for cell in expected_cells for step in expected_steps}
    parsed: dict[tuple[CellKey, int], TraceStep] = {}
    allowed = {
        "opponent",
        "seed",
        "candidate_seat",
        "step",
        "status",
        "observation_sha256",
        "action",
        "diagnostics",
    }
    for index, raw in enumerate(rows):
        row = _require_mapping(raw, f"{label}[{index}]")
        unknown = sorted(set(row) - allowed)
        required = allowed - {"diagnostics"}
        missing = sorted(required - set(row))
        if unknown or missing:
            raise AttributionError(
                f"{label}[{index}]: key mismatch; missing={missing}, unknown={unknown}"
            )
        if row["status"] != "complete":
            raise AttributionError(f"{label}[{index}]: status must be complete")
        cell = CellKey(
            _nonempty_string(row["opponent"], f"{label}[{index}].opponent"),
            _strict_int(row["seed"], f"{label}[{index}].seed"),
            _strict_int(row["candidate_seat"], f"{label}[{index}].candidate_seat"),
        )
        step = _strict_int(row["step"], f"{label}[{index}].step")
        key = (cell, step)
        if key in parsed:
            raise AttributionError(f"{label}: duplicate trace row {cell} step {step}")
        observation_sha = _hex_digest(
            row["observation_sha256"], 64, f"{label}[{index}].observation_sha256"
        )
        action = row["action"]
        action_sha = _sha256(_canonical_bytes(action))
        diagnostics = row.get("diagnostics")
        if diagnostics is not None:
            _canonical_bytes(diagnostics)
        parsed[key] = TraceStep(observation_sha, action, action_sha, diagnostics)
    observed = set(parsed)
    if observed != expected_keys:
        missing_count = len(expected_keys - observed)
        extra_count = len(observed - expected_keys)
        sample_missing = [
            {**cell.as_dict(), "step": step}
            for cell, step in sorted(expected_keys - observed)[:8]
        ]
        sample_extra = [
            {**cell.as_dict(), "step": step}
            for cell, step in sorted(observed - expected_keys)[:8]
        ]
        raise AttributionError(
            f"{label}: trace grid mismatch; missing={missing_count} {sample_missing}, "
            f"extra={extra_count} {sample_extra}"
        )
    return parsed
