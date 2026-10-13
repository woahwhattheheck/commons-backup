#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Paired terminal-score comparison and causally aligned first-action attribution."""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from attribution_common import AttributionError, CellKey, GameCell, TraceStep


def _result(cell: GameCell, seat: int) -> str:
    own = cell.scores[seat]
    rival = cell.scores[1 - seat]
    if own > rival:
        return "W"
    if own < rival:
        return "L"
    return "T"


def _score_view(cell: GameCell, seat: int) -> tuple[float, float, float]:
    own = cell.scores[seat]
    rival = cell.scores[1 - seat]
    return own, rival, own - rival


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _json_diff(before: Any, after: Any, prefix: str = "") -> list[dict[str, Any]]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        rows: list[dict[str, Any]] = []
        keys = sorted(set(before) | set(after))
        for key in keys:
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in before:
                rows.append({"path": path, "before": {"missing": True}, "after": after[key]})
            elif key not in after:
                rows.append({"path": path, "before": before[key], "after": {"missing": True}})
            else:
                rows.extend(_json_diff(before[key], after[key], path))
        return rows
    if isinstance(before, list) and isinstance(after, list):
        if before == after:
            return []
        return [{"path": prefix or "$", "before": before, "after": after}]
    if type(before) is type(after) and before == after:
        return []
    return [{"path": prefix or "$", "before": before, "after": after}]


def _action_category(before: Any, after: Any) -> tuple[str, list[str]]:
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return "whole_action", ["$"]
    missing = object()
    changed = [
        key
        for key in sorted(set(before) | set(after))
        if before.get(key, missing) != after.get(key, missing)
    ]
    changed_set = set(changed)
    if changed_set == {"market"}:
        return "market_only", changed
    if changed_set == {"hands"}:
        return "hands_only", changed
    if changed_set == {"farmer"}:
        return "farmer_only", changed
    if changed_set and changed_set <= {"farmer", "hands"}:
        return "unit_actions", changed
    return "mixed" if changed else "identical", changed


def _first_sequence_difference(before: Any, after: Any) -> dict[str, Any] | None:
    if not isinstance(before, list) or not isinstance(after, list):
        return None
    limit = max(len(before), len(after))
    for index in range(limit):
        left = before[index] if index < len(before) else {"missing": True}
        right = after[index] if index < len(after) else {"missing": True}
        if left != right:
            return {"index": index, "before": left, "after": right}
    return None


def _diagnostic_diff(before: Any, after: Any) -> list[dict[str, Any]]:
    if before is None and after is None:
        return []
    rows = _json_diff(before, after)
    # Diagnostics can be large; the causal receipt needs changed keys, not a log dump.
    return rows[:32]


def _policy_check(metrics: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    checks = (
        ("mean_own_delta", ">=", policy["min_mean_own_delta"]),
        ("mean_margin_delta", ">=", policy["min_mean_margin_delta"]),
        ("result_regressions", "<=", policy["max_result_regressions"]),
        ("new_losses", "<=", policy["max_new_losses"]),
        ("worst_cell_own_delta", ">=", policy["min_worst_cell_own_delta"]),
    )
    for field, operator, threshold in checks:
        observed = metrics[field]
        passed = observed >= threshold if operator == ">=" else observed <= threshold
        if not passed:
            failures.append(
                {"field": field, "operator": operator, "threshold": threshold, "observed": observed}
            )
    return ("PASS" if not failures else "REGRESSION"), failures


def _compare_scores(
    before_name: str,
    after_name: str,
    before: Mapping[CellKey, GameCell],
    after: Mapping[CellKey, GameCell],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    own_deltas: list[float] = []
    margin_deltas: list[float] = []
    result_regressions = 0
    result_improvements = 0
    new_losses = 0
    rank = {"L": 0, "T": 1, "W": 2}
    for key in sorted(before):
        left = before[key]
        right = after[key]
        left_own, left_rival, left_margin = _score_view(left, key.seat)
        right_own, right_rival, right_margin = _score_view(right, key.seat)
        left_result = _result(left, key.seat)
        right_result = _result(right, key.seat)
        own_delta = right_own - left_own
        rival_delta = right_rival - left_rival
        margin_delta = right_margin - left_margin
        own_deltas.append(own_delta)
        margin_deltas.append(margin_delta)
        if rank[right_result] < rank[left_result]:
            result_regressions += 1
        if rank[right_result] > rank[left_result]:
            result_improvements += 1
        if right_result == "L" and left_result != "L":
            new_losses += 1
        rows.append(
            {
                **key.as_dict(),
                "before_scores": list(left.scores),
                "after_scores": list(right.scores),
                "before_result": left_result,
                "after_result": right_result,
                "own_delta": own_delta,
                "rival_delta": rival_delta,
                "margin_delta": margin_delta,
            }
        )
    metrics = {
        "cells": len(rows),
        "mean_own_delta": _mean(own_deltas),
        "mean_margin_delta": _mean(margin_deltas),
        "worst_cell_own_delta": min(own_deltas),
        "best_cell_own_delta": max(own_deltas),
        "result_regressions": result_regressions,
        "result_improvements": result_improvements,
        "new_losses": new_losses,
    }
    verdict, failures = _policy_check(metrics, policy)
    worst = sorted(rows, key=lambda item: (item["own_delta"], item["margin_delta"], item["opponent"], item["seed"], item["candidate_seat"]))[:10]
    return {
        "before": before_name,
        "after": after_name,
        "verdict": verdict,
        "policy_failures": failures,
        "metrics": metrics,
        "worst_cells": worst,
    }


def _trace_attribution(
    before_name: str,
    after_name: str,
    before_games: Mapping[CellKey, GameCell],
    after_games: Mapping[CellKey, GameCell],
    before_trace: Mapping[tuple[CellKey, int], TraceStep],
    after_trace: Mapping[tuple[CellKey, int], TraceStep],
    cells: Sequence[CellKey],
    steps: Sequence[int],
) -> dict[str, Any]:
    divergences: list[dict[str, Any]] = []
    observation_drift: list[dict[str, Any]] = []
    unexplained_score_changes: list[dict[str, Any]] = []
    category_counts: Counter[str] = Counter()
    step_counts: Counter[int] = Counter()
    opponent_counts: Counter[str] = Counter()
    seat_counts: Counter[int] = Counter()

    for cell in sorted(cells):
        first: dict[str, Any] | None = None
        for step in steps:
            left = before_trace[(cell, step)]
            right = after_trace[(cell, step)]
            if left.observation_sha256 != right.observation_sha256:
                observation_drift.append(
                    {
                        **cell.as_dict(),
                        "step": step,
                        "before_observation_sha256": left.observation_sha256,
                        "after_observation_sha256": right.observation_sha256,
                    }
                )
                break
            if left.action_sha256 != right.action_sha256:
                category, changed_keys = _action_category(left.action, right.action)
                market_diff = None
                hands_diff = None
                if isinstance(left.action, Mapping) and isinstance(right.action, Mapping):
                    market_diff = _first_sequence_difference(left.action.get("market"), right.action.get("market"))
                    hands_diff = _first_sequence_difference(left.action.get("hands"), right.action.get("hands"))
                first = {
                    **cell.as_dict(),
                    "step": step,
                    "category": category,
                    "changed_top_level_keys": changed_keys,
                    "observation_sha256": left.observation_sha256,
                    "before_action_sha256": left.action_sha256,
                    "after_action_sha256": right.action_sha256,
                    "market_first_difference": market_diff,
                    "hands_first_difference": hands_diff,
                    "diagnostic_changes": _diagnostic_diff(left.diagnostics, right.diagnostics),
                }
                divergences.append(first)
                category_counts[category] += 1
                step_counts[step] += 1
                opponent_counts[cell.opponent] += 1
                seat_counts[cell.seat] += 1
                break

        score_changed = before_games[cell].scores != after_games[cell].scores
        if score_changed and first is None and not any(
            item["opponent"] == cell.opponent
            and item["seed"] == cell.seed
            and item["candidate_seat"] == cell.seat
            for item in observation_drift
        ):
            unexplained_score_changes.append(
                {
                    **cell.as_dict(),
                    "before_scores": list(before_games[cell].scores),
                    "after_scores": list(after_games[cell].scores),
                }
            )

    if observation_drift:
        sample = observation_drift[:8]
        raise AttributionError(
            f"{before_name}->{after_name}: observation drift precedes any action difference: {sample}"
        )
    if unexplained_score_changes:
        raise AttributionError(
            f"{before_name}->{after_name}: terminal scores changed without an action divergence: "
            f"{unexplained_score_changes[:8]}"
        )

    earliest_step = min((item["step"] for item in divergences), default=None)
    return {
        "cells_with_action_divergence": len(divergences),
        "cells_without_action_divergence": len(cells) - len(divergences),
        "earliest_divergence_step": earliest_step,
        "category_counts": dict(sorted(category_counts.items())),
        "first_divergence_step_counts": {
            str(key): value for key, value in sorted(step_counts.items())
        },
        "opponent_counts": dict(sorted(opponent_counts.items())),
        "seat_counts": {str(key): value for key, value in sorted(seat_counts.items())},
        "cells": divergences,
    }
