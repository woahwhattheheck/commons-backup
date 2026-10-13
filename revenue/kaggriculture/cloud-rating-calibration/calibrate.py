"""Grouped head-to-head strength calibration for TITAN game receipts.

This module is deliberately an offline result consumer.  It never imports an
agent or engine and cannot launch games.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ELO_PER_LOG_ODDS = 400.0 / math.log(10.0)
EXPECTED_CANDIDATE = {
    "candidate_archive_sha256": "95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153",
    "candidate_runtime_sha256": "9e5e4eb6fe66d2516365f96ad9e2366d07c446b6c70e5cada28602ae46c3a1b8",
}
EXPECTED_OPPONENT = {
    "arlene": {
        "baseline_archive_sha256": "7dcb73bb0d8bc6d0d003b107fcb47c93f9e77c4d8c64d39fec8bd54d406bb407",
        "baseline_candidate_sha256": "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4",
        "opponent_runtime_sha256": "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4",
    },
    "frozen_sell": {
        "opponent_runtime_sha256": "ca810092542eed9d862466df71ef6ee723170a54d5ad5764babd3d4a727202ae",
    },
    "apex": {
        "opponent_runtime_sha256": "1f7cd5fb8a16585936d2562a3667f85bb6661688718ef58f73006de66148354a",
    },
}


def _quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("quantile requires observations")
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _outcome(row: dict[str, Any]) -> tuple[str, float]:
    if "candidate_cash" in row and "baseline_cash" in row:
        candidate = float(row["candidate_cash"])
        baseline = float(row["baseline_cash"])
        return ("W", 1.0) if candidate > baseline else (("L", 0.0) if candidate < baseline else ("T", 0.5))
    value = str(row.get("result", "")).upper()
    if value not in {"W", "T", "L"}:
        raise ValueError("each row needs cash fields or result W/T/L")
    return value, {"W": 1.0, "T": 0.5, "L": 0.0}[value]


def validate_games(games: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[Any, list[dict[str, Any]]]]:
    rows = [dict(row) for row in games]
    if not rows:
        raise ValueError("games is empty")
    grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[Any, int]] = set()
    for row in rows:
        if row.get("error") not in (None, ""):
            raise ValueError(f"failed game cannot be scored: {row.get('error')}")
        if "seed" not in row or "seat" not in row:
            raise ValueError("each game needs seed and seat")
        seat = int(row["seat"])
        if seat not in (0, 1):
            raise ValueError(f"invalid seat {seat}")
        key = (row["seed"], seat)
        if key in seen:
            raise ValueError(f"duplicate seed/seat {key}")
        seen.add(key)
        row["seat"] = seat
        row["result"], row["points"] = _outcome(row)
        grouped[row["seed"]].append(row)
    bad = {seed: sorted(row["seat"] for row in group) for seed, group in grouped.items()
           if sorted(row["seat"] for row in group) != [0, 1]}
    if bad:
        raise ValueError(f"every seed must contain both seats exactly once: {bad}")
    return rows, dict(grouped)


def _penalized_strength(rows: Iterable[dict[str, Any]]) -> tuple[float, float, float]:
    materialized = list(rows)
    # A half pseudo-observation at each boundary prevents infinite estimates.
    probability = (sum(float(row["points"]) for row in materialized) + 0.5) / (len(materialized) + 1.0)
    log_odds = math.log(probability / (1.0 - probability))
    return probability, log_odds, ELO_PER_LOG_ODDS * log_odds


def _rank_at(score: float, anchors: list[dict[str, Any]]) -> float:
    ordered = sorted((float(row["score"]), float(row["rank"])) for row in anchors)
    if not ordered[0][0] <= score <= ordered[-1][0]:
        raise ValueError("score interval requires rank extrapolation")
    for (left_score, left_rank), (right_score, right_rank) in zip(ordered, ordered[1:]):
        if left_score <= score <= right_score:
            if left_score == right_score:
                return min(left_rank, right_rank)
            weight = (score - left_score) / (right_score - left_score)
            return left_rank + weight * (right_rank - left_rank)
    return ordered[-1][1]


def rank_interval(score_interval: list[float], snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {"identified": False, "reason": "no contemporaneous cross-sectional rank snapshot"}
    anchors = list(snapshot.get("anchors", []))
    if len(anchors) < 3:
        return {"identified": False, "reason": "fewer than three cross-sectional score/rank anchors"}
    observed = {str(row.get("observed_at", snapshot.get("observed_at", ""))) for row in anchors}
    if len(observed) != 1 or "" in observed:
        return {"identified": False, "reason": "rank anchors are not from one timestamp"}
    ordered = sorted((float(row["score"]), float(row["rank"])) for row in anchors)
    if len({score for score, _ in ordered}) < 3:
        return {"identified": False, "reason": "fewer than three distinct anchor scores"}
    if any(right_rank > left_rank for (_, left_rank), (_, right_rank) in zip(ordered, ordered[1:])):
        return {"identified": False, "reason": "rank is not monotone non-increasing with score"}
    try:
        values = [_rank_at(float(score_interval[0]), anchors), _rank_at(float(score_interval[1]), anchors)]
    except ValueError as exc:
        return {"identified": False, "reason": str(exc)}
    return {
        "identified": True,
        "observed_at": next(iter(observed)),
        "interval": [max(1, math.floor(min(values))), max(1, math.ceil(max(values)))],
        "method": "piecewise-linear interpolation; no extrapolation",
    }


def calibrate(payload: dict[str, Any], *, iterations: int = 100_000, bootstrap_seed: int = 20260908) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    source = payload.get("source", {})
    family = source.get("opponent_family", "arlene")
    if family not in EXPECTED_OPPONENT:
        raise ValueError(f"unrecognized opponent family {family!r}")
    expected_source = {**EXPECTED_CANDIDATE, **EXPECTED_OPPONENT[family]}
    # The original Arlene input used the older baseline_runtime field name.
    if family == "arlene" and "opponent_runtime_sha256" not in source:
        source = {**source, "opponent_runtime_sha256": source.get("baseline_runtime_sha256")}
    mismatches = {key: {"expected": expected, "actual": source.get(key)}
                  for key, expected in expected_source.items() if source.get(key) != expected}
    if mismatches:
        raise ValueError(f"source identity mismatch: {mismatches}")
    rows, grouped = validate_games(payload["games"])
    if payload.get("schema") == "titan.calibration.input.v1":
        for row in rows:
            if row.get("candidate_runtime_sha256") != source["candidate_runtime_sha256"]:
                raise ValueError("per-game candidate runtime hash mismatch")
            opponent_hash = row.get("opponent_runtime_sha256", row.get("baseline_runtime_sha256"))
            if opponent_hash != source["opponent_runtime_sha256"]:
                raise ValueError("per-game opponent runtime hash mismatch")
    seeds = sorted(grouped, key=str)
    rng = random.Random(bootstrap_seed)
    elo_draws: list[float] = []
    margin_draws: list[float] = []
    outcome_draws = {key: [] for key in ("W", "T", "L")}
    for _ in range(iterations):
        sampled = [rng.choice(seeds) for _ in seeds]
        draw_rows = [row for seed in sampled for row in grouped[seed]]
        elo_draws.append(_penalized_strength(draw_rows)[2])
        draw_counts = Counter(row["result"] for row in draw_rows)
        for key in outcome_draws:
            outcome_draws[key].append(draw_counts[key] / len(draw_rows))
        if all("candidate_cash" in row and "baseline_cash" in row for row in draw_rows):
            margin_draws.append(sum(float(row["candidate_cash"]) - float(row["baseline_cash"]) for row in draw_rows) / len(draw_rows))

    probability, log_odds, elo_proxy = _penalized_strength(rows)
    counts = Counter(row["result"] for row in rows)
    raw_score = sum(float(row["points"]) for row in rows) / len(rows)
    elo_interval = [_quantile(elo_draws, 0.025), _quantile(elo_draws, 0.975)]
    anchor = dict(payload["baseline_anchor"]) if payload.get("baseline_anchor") else None
    score_interval = None
    anchored_point = None
    if anchor:
        anchor_low = float(anchor["score_low"] if "score_low" in anchor else anchor["score"])
        anchor_high = float(anchor["score_high"] if "score_high" in anchor else anchor["score"])
        if anchor_low > anchor_high:
            raise ValueError("baseline score band is reversed")
        score_interval = [anchor_low + elo_interval[0], anchor_high + elo_interval[1]]
        anchored_point = float(anchor.get("score", (anchor_low + anchor_high) / 2.0)) + elo_proxy
    by_seat = {}
    for seat in (0, 1):
        seat_rows = [row for row in rows if row["seat"] == seat]
        seat_counts = Counter(row["result"] for row in seat_rows)
        by_seat[str(seat)] = {k: seat_counts[k] for k in ("W", "T", "L")}

    result: dict[str, Any] = {
        "model": {
            "name": "paired Bradley-Terry empirical proxy",
            "ties": "half win",
            "penalty": "0.5 pseudo-point over one pseudo-game",
            "uncertainty": "percentile bootstrap resampling whole seed clusters; both seats retained",
            "iterations": iterations,
            "bootstrap_seed": bootstrap_seed,
            "limitations": [
                "not the undocumented Kaggle backend update formula",
                "conditional on this one baseline matchup",
                "does not remove matchup nontransitivity or opponent-population shift",
            ],
        },
        "sample": {
            "seed_clusters": len(seeds), "games": len(rows),
            "W": counts["W"], "T": counts["T"], "L": counts["L"],
            "by_seat": by_seat,
        },
        "source": source,
        "fit": {
            "raw_score_fraction": raw_score,
            "penalized_score_probability": probability,
            "log_odds": log_odds,
            "elo_scale_proxy": elo_proxy,
            "elo_scale_proxy_95pct_cluster_bootstrap": elo_interval,
            "candidate_score_odds": math.exp(log_odds),
            "opponent_score_odds": math.exp(-log_odds),
        },
        "expected_match_outcome": {
            key: {
                "empirical_probability": counts[key] / len(rows),
                "95pct_seed_cluster_bootstrap": [_quantile(outcome_draws[key], 0.025), _quantile(outcome_draws[key], 0.975)],
            } for key in ("W", "T", "L")
        },
        "baseline_anchor": anchor,
        "anchored_score_proxy_point": anchored_point,
        "anchored_score_proxy_sensitivity_band": score_interval,
        "rank": rank_interval(score_interval, payload.get("rank_snapshot")) if score_interval else
                {"identified": False, "reason": "opponent has no hosted score anchor"},
    }
    if margin_draws:
        margins = [float(row["candidate_cash"]) - float(row["baseline_cash"]) for row in rows]
        result["cash_margin"] = {
            "mean": sum(margins) / len(margins),
            "95pct_cluster_bootstrap": [_quantile(margin_draws, 0.025), _quantile(margin_draws, 0.975)],
            "note": "descriptive only; Kaggle ranks terminal win/tie/loss rather than coin margin",
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260908)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text())
    report = calibrate(payload, iterations=args.iterations, bootstrap_seed=args.bootstrap_seed)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
