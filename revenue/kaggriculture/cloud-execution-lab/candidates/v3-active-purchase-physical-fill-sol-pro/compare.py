# SPDX-License-Identifier: Apache-2.0
"""Bind paired control/candidate reports and issue a seed-clustered verdict."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any

EXPECTED_SEEDS = [
    539131249, 1834999074, 2609097301, 2609097302,
    2609097303, 2609097304, 2611092201, 2611092207,
]
EXPECTED_OPPONENTS = {"arlene", "v1"}
EXPECTED_EPISODE_STEPS = 720


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"report is not an object: {path}")
    return value


def _cell_key(game: dict[str, Any]) -> tuple[str, int, int]:
    return str(game["opponent"]), int(game["seed"]), int(game["candidate_seat"])


def _index(report: dict[str, Any], label: str) -> dict[tuple[str, int, int], dict[str, Any]]:
    if report.get("progress", {}).get("state") != "complete":
        raise RuntimeError(f"{label} report is not terminal-complete")
    games = report.get("games")
    if not isinstance(games, list):
        raise RuntimeError(f"{label} games missing")
    result: dict[tuple[str, int, int], dict[str, Any]] = {}
    for game in games:
        if not isinstance(game, dict):
            raise RuntimeError(f"{label} contains a non-object game")
        key = _cell_key(game)
        if key in result:
            raise RuntimeError(f"duplicate {label} cell: {key}")
        if game.get("status") != "complete" or game.get("failure") is not None:
            raise RuntimeError(f"incomplete {label} cell: {key}: {game.get('failure')}")
        if int(game.get("episode_steps", -1)) != EXPECTED_EPISODE_STEPS:
            raise RuntimeError(f"episode length drift in {label} cell: {key}")
        if int(game.get("steps", -1)) != int(game.get("episode_steps", -2)) - 1:
            raise RuntimeError(f"lifecycle mismatch in {label} cell: {key}")
        if int(game.get("tested_action_count", -1)) != int(game["steps"]):
            raise RuntimeError(f"tested action count mismatch in {label} cell: {key}")
        digest = game.get("tested_action_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise RuntimeError(f"tested action digest missing in {label} cell: {key}")
        scores = game.get("scores")
        if not (
            isinstance(scores, list) and len(scores) == 2 and
            all(isinstance(x, (int, float)) and math.isfinite(x) for x in scores)
        ):
            raise RuntimeError(f"invalid scores in {label} cell: {key}")
        result[key] = game
    return result


def _sign_tail(positive: int, nonzero: int) -> float:
    if nonzero <= 0:
        return 1.0
    # One-sided exact Binomial(n, 0.5): P[X >= positive].
    numerator = sum(math.comb(nonzero, k) for k in range(positive, nonzero + 1))
    return numerator / (2 ** nonzero)


def compare(
    control_path: Path,
    candidate_path: Path,
    *,
    materialization_path: Path | None = None,
    evaluator_receipt_path: Path | None = None,
) -> dict[str, Any]:
    control = _load(control_path)
    candidate = _load(candidate_path)
    for field in (
        "engine_ref", "engine_sha256", "loader_sha256", "evaluator_sha256",
        "seeds", "agent_rng_seed", "candidate",
    ):
        if control.get(field) != candidate.get(field):
            raise RuntimeError(f"arm provenance mismatch: {field}")
    if control.get("opponents") != candidate.get("opponents"):
        raise RuntimeError("opponent provenance mismatch")
    if control.get("seeds") != EXPECTED_SEEDS:
        raise RuntimeError("independent seed set drift")
    if set(control.get("opponents", {})) != EXPECTED_OPPONENTS:
        raise RuntimeError("opponent panel drift")
    materialization_sha256 = None
    if materialization_path is not None:
        materialization = _load(materialization_path)
        if materialization.get("operation") != "TITAN-V3-ACTIVE-PURCHASE-PHYSICAL-FILL-20260910-01":
            raise RuntimeError("materialization operation drift")
        if materialization.get("candidate", {}).get("changed_members") != ["scheduler.py"]:
            raise RuntimeError("materialization factor drift")
        materialization_sha256 = hashlib.sha256(materialization_path.read_bytes()).hexdigest()
    evaluator_receipt_sha256 = None
    if evaluator_receipt_path is not None:
        evaluator_receipt = _load(evaluator_receipt_path)
        if evaluator_receipt.get("source_git_blob") != "077feb2208b6e0c1727835eb4f8089709bf67f3b":
            raise RuntimeError("evaluator source identity drift")
        if evaluator_receipt.get("generated_sha256") != control.get("evaluator_sha256"):
            raise RuntimeError("generated evaluator/report binding drift")
        evaluator_receipt_sha256 = hashlib.sha256(evaluator_receipt_path.read_bytes()).hexdigest()
    a = _index(control, "control")
    b = _index(candidate, "candidate")
    if set(a) != set(b):
        raise RuntimeError("control/candidate cell set mismatch")
    expected = len(control.get("seeds", [])) * len(control.get("opponents", {})) * 2
    if len(a) != expected:
        raise RuntimeError(f"panel cardinality mismatch: expected {expected}, got {len(a)}")
    cells = []
    for key in sorted(a):
        ca, cb = a[key], b[key]
        seat = key[2]
        own_a, rival_a = float(ca["scores"][seat]), float(ca["scores"][1 - seat])
        own_b, rival_b = float(cb["scores"][seat]), float(cb["scores"][1 - seat])
        action_changed = ca["tested_action_sha256"] != cb["tested_action_sha256"]
        trace_changed = ca.get("trace_sha256") != cb.get("trace_sha256")
        own_delta = own_b - own_a
        rival_delta = rival_b - rival_a
        margin_delta = (own_b - rival_b) - (own_a - rival_a)
        if not action_changed and (trace_changed or own_delta or rival_delta):
            raise RuntimeError(f"closed-loop changed without tested action divergence: {key}")
        cells.append({
            "opponent": key[0], "seed": key[1], "seat": seat,
            "action_changed": action_changed, "trace_changed": trace_changed,
            "control_own": own_a, "candidate_own": own_b, "own_delta": own_delta,
            "control_rival": rival_a, "candidate_rival": rival_b, "rival_delta": rival_delta,
            "margin_delta": margin_delta,
            "control_outcome": (own_a > rival_a) - (own_a < rival_a),
            "candidate_outcome": (own_b > rival_b) - (own_b < rival_b),
        })
    activated = [row for row in cells if row["action_changed"]]
    own = [row["own_delta"] for row in activated]
    margin = [row["margin_delta"] for row in activated]
    strata: dict[str, dict[str, float | int]] = {}
    for opponent in sorted({row["opponent"] for row in cells}):
        for seat in (0, 1):
            rows = [row for row in activated if row["opponent"] == opponent and row["seat"] == seat]
            strata[f"{opponent}/seat{seat}"] = {
                "activated": len(rows),
                "mean_own_delta": statistics.mean([r["own_delta"] for r in rows]) if rows else 0.0,
                "mean_margin_delta": statistics.mean([r["margin_delta"] for r in rows]) if rows else 0.0,
            }
    clusters = []
    for seed in sorted({row["seed"] for row in cells}):
        rows = [row for row in activated if row["seed"] == seed]
        clusters.append({
            "seed": seed,
            "activated": len(rows),
            "own_delta": sum(row["own_delta"] for row in rows),
            "margin_delta": sum(row["margin_delta"] for row in rows),
        })
    nonzero_clusters = [c for c in clusters if c["own_delta"] != 0]
    positive_clusters = sum(c["own_delta"] > 0 for c in nonzero_clusters)
    negative_clusters = sum(c["own_delta"] < 0 for c in nonzero_clusters)
    new_losses = sum(row["control_outcome"] >= 0 and row["candidate_outcome"] < 0 for row in cells)
    lost_wins = sum(row["control_outcome"] > 0 and row["candidate_outcome"] <= 0 for row in cells)
    gained_wins = sum(row["control_outcome"] <= 0 and row["candidate_outcome"] > 0 for row in cells)
    if not activated:
        verdict = "INACTIVE"
    elif any(delta < 0 for delta in own) or new_losses or lost_wins:
        verdict = "REJECT"
    else:
        global_safe = (
            statistics.mean(own) > 0 and statistics.median(own) >= 0 and
            statistics.mean(margin) >= 0 and
            all(float(v["mean_own_delta"]) >= 0 for v in strata.values())
        )
        clustered = (
            negative_clusters == 0 and positive_clusters >= 6 and
            _sign_tail(positive_clusters, len(nonzero_clusters)) <= 0.05
        )
        verdict = "ADVANCE" if global_safe and clustered else "MORE_EVIDENCE"
    result = {
        "schema_version": 1,
        "operation": "TITAN-V3-ACTIVE-PURCHASE-PHYSICAL-FILL-20260910-01",
        "control_report_sha256": hashlib.sha256(control_path.read_bytes()).hexdigest(),
        "candidate_report_sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        "materialization_receipt_sha256": materialization_sha256,
        "evaluator_receipt_sha256": evaluator_receipt_sha256,
        "scheduled_cells_per_arm": expected,
        "complete_cells_per_arm": len(cells),
        "activated_cells": len(activated),
        "changed_score_cells": sum(
            bool(row["own_delta"] or row["rival_delta"]) for row in cells
        ),
        "mean_own_delta_activated": statistics.mean(own) if own else 0.0,
        "median_own_delta_activated": statistics.median(own) if own else 0.0,
        "minimum_own_delta_activated": min(own) if own else 0.0,
        "mean_margin_delta_activated": statistics.mean(margin) if margin else 0.0,
        "new_losses": new_losses,
        "lost_wins": lost_wins,
        "gained_wins": gained_wins,
        "independent_seed_clusters": {
            "positive": positive_clusters,
            "negative": negative_clusters,
            "zero_or_inactive": len(clusters) - len(nonzero_clusters),
            "one_sided_sign_tail": _sign_tail(positive_clusters, len(nonzero_clusters)),
            "clusters": clusters,
        },
        "strata": strata,
        "verdict": verdict,
        "cells": cells,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--materialization", type=Path)
    parser.add_argument("--evaluator-receipt", type=Path)
    args = parser.parse_args()
    result = compare(
        args.control, args.candidate,
        materialization_path=args.materialization,
        evaluator_receipt_path=args.evaluator_receipt,
    )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "complete_cells_per_arm", "activated_cells", "mean_own_delta_activated",
        "mean_margin_delta_activated", "new_losses", "lost_wins", "verdict"
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
