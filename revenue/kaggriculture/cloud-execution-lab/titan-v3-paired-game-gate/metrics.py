# SPDX-License-Identifier: Apache-2.0
"""Paired cash/result metrics and explicit promotion checks."""
from __future__ import annotations

from collections import defaultdict
import statistics
from typing import Any, Iterable, Mapping, Sequence

from gate_common import CellKey, Game, GateError, finite_number


def _mean(values: Sequence[float], *, label: str) -> float:
    try:
        result = statistics.fmean(values)
    except (OverflowError, ValueError) as exc:
        raise GateError(f"{label}: derived mean is not finite") from exc
    return finite_number(result, label=label)


def _median(values: Sequence[float], *, label: str) -> float:
    try:
        result = statistics.median(values)
    except (OverflowError, ValueError) as exc:
        raise GateError(f"{label}: derived median is not finite") from exc
    return finite_number(result, label=label)


def _summary(values: Sequence[float], *, label: str) -> dict[str, float | int]:
    return {
        "n": len(values),
        "mean": _mean(values, label=f"{label}.mean"),
        "median": _median(values, label=f"{label}.median"),
        "min": min(values), "max": max(values),
        "positive": sum(value > 0 for value in values),
        "zero": sum(value == 0 for value in values),
        "negative": sum(value < 0 for value in values),
    }


def _rank(result: str) -> int:
    return {"L": 0, "T": 1, "W": 2}[result]


def _counts(results: Iterable[str]) -> dict[str, int]:
    out = {"W": 0, "T": 0, "L": 0}
    for result in results:
        out[result] += 1
    return out


def analyze(baseline: Mapping[CellKey, Game], candidate: Mapping[CellKey, Game]) -> dict[str, Any]:
    keys = sorted(baseline)
    cells, regressions, improvements = [], [], []
    own_deltas, margin_deltas = [], []
    pair_values: dict[tuple[str, int], list[float]] = defaultdict(list)
    opponent_values: dict[str, list[float]] = defaultdict(list)
    seat_values: dict[int, list[float]] = defaultdict(list)
    baseline_win_regressions = new_losses = 0

    for key in keys:
        base, cand = baseline[key], candidate[key]
        cell_label = f"cell {key.as_list()}"
        baseline_margin = finite_number(base.own - base.rival, label=f"{cell_label} baseline_margin")
        candidate_margin = finite_number(cand.own - cand.rival, label=f"{cell_label} candidate_margin")
        own_delta = finite_number(cand.own - base.own, label=f"{cell_label} own_delta")
        rival_delta = finite_number(cand.rival - base.rival, label=f"{cell_label} rival_delta")
        margin_delta = finite_number(
            candidate_margin - baseline_margin,
            label=f"{cell_label} margin_delta",
        )
        own_deltas.append(own_delta)
        margin_deltas.append(margin_delta)
        pair_values[(key.opponent, key.seed)].append(own_delta)
        opponent_values[key.opponent].append(own_delta)
        seat_values[key.seat].append(own_delta)
        baseline_result = "W" if baseline_margin > 0 else ("T" if baseline_margin == 0 else "L")
        candidate_result = "W" if candidate_margin > 0 else ("T" if candidate_margin == 0 else "L")
        record = {
            "key": key.as_list(), "baseline_result": baseline_result,
            "candidate_result": candidate_result, "baseline_margin": baseline_margin,
            "candidate_margin": candidate_margin, "own_delta": own_delta,
        }
        if _rank(candidate_result) < _rank(baseline_result):
            regressions.append(record)
            baseline_win_regressions += baseline_result == "W"
            new_losses += candidate_result == "L" and baseline_result != "L"
        elif _rank(candidate_result) > _rank(baseline_result):
            improvements.append(record)
        cells.append({
            "key": key.as_list(), "baseline_scores": list(base.scores),
            "candidate_scores": list(cand.scores), "baseline_result": baseline_result,
            "candidate_result": candidate_result, "own_delta": own_delta,
            "rival_delta": rival_delta, "margin_delta": margin_delta,
        })

    pairs, pair_means = [], []
    for (opponent, seed), values in sorted(pair_values.items()):
        if len(values) != 2:
            raise GateError(f"internal pair cardinality error for {[opponent, seed]}: {len(values)}")
        value = _mean(values, label=f"pair {[opponent, seed]} seat_mean_own_delta")
        pair_means.append(value)
        pairs.append({
            "opponent": opponent, "seed": seed,
            "seat_mean_own_delta": value, "seat_deltas": values,
        })
    per_opponent = {
        key: _summary(value, label=f"opponent {key!r} own_delta")
        for key, value in sorted(opponent_values.items())
    }
    per_seat = {
        str(key): _summary(value, label=f"seat {key} own_delta")
        for key, value in sorted(seat_values.items())
    }
    baseline_results = [cell["baseline_result"] for cell in cells]
    candidate_results = [cell["candidate_result"] for cell in cells]
    aggregate = {
        "cells": len(cells), "pairs": len(pairs),
        "own_delta": _summary(own_deltas, label="aggregate own_delta"),
        "margin_delta": _summary(margin_deltas, label="aggregate margin_delta"),
        "positive_cell_fraction": sum(value > 0 for value in own_deltas) / len(own_deltas),
        "nonnegative_cell_fraction": sum(value >= 0 for value in own_deltas) / len(own_deltas),
        "positive_pair_fraction": sum(value > 0 for value in pair_means) / len(pair_means),
        "nonnegative_pair_fraction": sum(value >= 0 for value in pair_means) / len(pair_means),
        "changed_cells": sum(baseline[key].scores != candidate[key].scores for key in keys),
        "baseline_results": _counts(baseline_results),
        "candidate_results": _counts(candidate_results),
        "result_regressions": len(regressions), "result_improvements": len(improvements),
        "baseline_win_regressions": baseline_win_regressions, "new_losses": new_losses,
        "negative_opponent_strata": sum(value["mean"] < 0 for value in per_opponent.values()),
        "negative_seat_strata": sum(value["mean"] < 0 for value in per_seat.values()),
    }
    return {
        "cells": cells, "pairs": pairs, "aggregate": aggregate,
        "per_opponent": per_opponent, "per_seat": per_seat,
        "result_regression_cells": regressions, "result_improvement_cells": improvements,
    }


def evaluate_policy(metrics: Mapping[str, Any], policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    aggregate, checks = metrics["aggregate"], []

    def check(name: str, actual: float | int, op: str, threshold: float | int) -> None:
        passed = actual >= threshold if op == ">=" else actual <= threshold
        checks.append({"name": name, "actual": actual, "op": op, "threshold": threshold, "pass": passed})

    check("mean_own_delta", aggregate["own_delta"]["mean"], ">=", policy["min_mean_own_delta"])
    check("median_own_delta", aggregate["own_delta"]["median"], ">=", policy["min_median_own_delta"])
    check("mean_margin_delta", aggregate["margin_delta"]["mean"], ">=", policy["min_mean_margin_delta"])
    check("positive_cell_fraction", aggregate["positive_cell_fraction"], ">=", policy["min_positive_cell_fraction"])
    check("positive_pair_fraction", aggregate["positive_pair_fraction"], ">=", policy["min_positive_pair_fraction"])
    for name in (
        "result_regressions", "baseline_win_regressions", "new_losses",
        "negative_opponent_strata", "negative_seat_strata",
    ):
        check(name, aggregate[name], "<=", policy[f"max_{name}"])
    if policy["min_worst_cell_own_delta"] is not None:
        check("worst_cell_own_delta", aggregate["own_delta"]["min"], ">=", policy["min_worst_cell_own_delta"])
    changed = aggregate["changed_cells"]
    checks.append({
        "name": "any_score_change", "actual": changed,
        "op": "> 0" if policy["require_any_change"] else ">= 0",
        "threshold": 0, "pass": changed > 0 if policy["require_any_change"] else True,
    })
    return checks
