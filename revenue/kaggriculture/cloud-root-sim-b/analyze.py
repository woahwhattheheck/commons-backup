#!/usr/bin/env python3
"""Aggregate ROOT-SIM-B results without exposing private trajectories."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


T95 = {30: 2.042272456, 31: 2.039513446}


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    low, high = math.floor(index), math.ceil(index)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - index) + ordered[high] * (index - low)


def interval(values: list[float]) -> dict:
    mean = statistics.mean(values)
    if len(values) < 2:
        return {"n": len(values), "mean": mean, "ci95": [mean, mean]}
    critical = T95.get(len(values) - 1, 1.96)
    half = critical * statistics.stdev(values) / math.sqrt(len(values))
    return {"n": len(values), "mean": mean, "ci95": [mean - half, mean + half]}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    repo, run = args.repo.resolve(), args.run.resolve()
    roots = {
        "current": [run / "cal-current", run / "full-current"],
        "historical": [run / "cal-historical", run / "full-historical"],
    }
    rows, failures = [], []
    for controller, paths in roots.items():
        for root in paths:
            for path in root.glob("*/result.json"):
                game = json.loads(path.read_text())
                row = {"controller": controller, "path": str(path), **game}
                if game.get("status") != "complete":
                    failures.append(row)
                    continue
                seat = game["candidate_seat"]
                row.update(
                    candidate_cash=game["scores"][seat],
                    opponent_cash=game["scores"][1 - seat],
                    margin=game["scores"][seat] - game["scores"][1 - seat],
                )
                rows.append(row)

    recovery_rows = []
    for controller in roots:
        recovery = run / f"recovery-{controller}"
        for path in recovery.glob("*/result.json"):
            game = json.loads(path.read_text())
            seat = game["candidate_seat"]
            recovery_rows.append({
                "controller": controller,
                "path": str(path),
                **game,
                "candidate_cash": game["scores"][seat],
                "opponent_cash": game["scores"][1 - seat],
                "margin": game["scores"][seat] - game["scores"][1 - seat],
            })

    by_controller = {}
    paired = {}
    paired_seats = defaultdict(list)
    for row in rows:
        paired_seats[(row["controller"], row["opponent"], row["seed"])].append(row["margin"])
    seed_margins = {key: statistics.mean(values) for key, values in paired_seats.items()}
    for controller in roots:
        games = [row for row in rows if row["controller"] == controller]
        strata = {}
        for opponent in ("apex", "arlene", "euler"):
            selected = [row for row in games if row["opponent"] == opponent]
            candidate_calls, candidate_rpcs = [], []
            for row in selected:
                actor = row["actors"][row["candidate_seat"]]
                candidate_calls.extend(actor["call_seconds"])
                candidate_rpcs.extend(actor["rpc_seconds"])
            strata[opponent] = {
                "games": len(selected),
                "wins": sum(row["margin"] > 0 for row in selected),
                "draws": sum(row["margin"] == 0 for row in selected),
                "losses": sum(row["margin"] < 0 for row in selected),
                "mean_candidate_cash": statistics.mean(row["candidate_cash"] for row in selected),
                "mean_margin": statistics.mean(row["margin"] for row in selected),
                "wall_seconds": {
                    "mean": statistics.mean(row["wall_seconds"] for row in selected),
                    "p95": percentile([row["wall_seconds"] for row in selected], .95),
                    "max": max(row["wall_seconds"] for row in selected),
                },
                "candidate_call_seconds": {
                    "p95": percentile(candidate_calls, .95),
                    "p99": percentile(candidate_calls, .99),
                    "max": max(candidate_calls),
                },
                "candidate_rpc_seconds": {
                    "p95": percentile(candidate_rpcs, .95),
                    "p99": percentile(candidate_rpcs, .99),
                    "max": max(candidate_rpcs),
                },
            }
        by_controller[controller] = {
            "games": len(games),
            "wins": sum(row["margin"] > 0 for row in games),
            "draws": sum(row["margin"] == 0 for row in games),
            "losses": sum(row["margin"] < 0 for row in games),
            "complete_720_captures": sum(
                row.get("episode_steps") == 720
                and row.get("steps") == 719
                and row.get("recorded_transitions") == 720
                for row in games
            ),
            "strata": strata,
        }

    per_opponent_deltas = {}
    per_seed_overall = defaultdict(list)
    for opponent in ("apex", "arlene", "euler"):
        deltas = []
        for seed in range(1909081501, 1909081533):
            keys = [(controller, opponent, seed) for controller in roots]
            if all(key in seed_margins and len(paired_seats[key]) == 2 for key in keys):
                delta = seed_margins[("current", opponent, seed)] - seed_margins[("historical", opponent, seed)]
                deltas.append(delta)
                per_seed_overall[seed].append(delta)
        per_opponent_deltas[opponent] = interval(deltas)
    paired = {
        "unit": "seed; mirrored seats averaged before controller subtraction",
        "by_opponent": per_opponent_deltas,
        "opponent_stratified_overall": interval([
            statistics.mean(per_seed_overall[seed]) for seed in sorted(per_seed_overall)
            if len(per_seed_overall[seed]) == 3
        ]),
    }

    original_by_cell = {
        (row["controller"], row["opponent"], row["seed"], row["candidate_seat"]): row
        for row in rows
    }
    recovery_by_cell = {
        (row["controller"], row["opponent"], row["seed"], row["candidate_seat"]): row
        for row in recovery_rows
    }
    recovered_keys = [
        (row["controller"], row["opponent"], row["seed"], row["candidate_seat"])
        for row in failures
    ]
    sensitivity_rows = rows + [recovery_by_cell[key] for key in recovered_keys]
    sensitivity_seed = defaultdict(list)
    for row in sensitivity_rows:
        sensitivity_seed[(row["controller"], row["opponent"], row["seed"])].append(row["margin"])
    sensitivity_deltas = {}
    sensitivity_overall = defaultdict(list)
    for opponent in ("apex", "arlene", "euler"):
        values = []
        for seed in range(1909081501, 1909081533):
            delta = (statistics.mean(sensitivity_seed[("current", opponent, seed)])
                     - statistics.mean(sensitivity_seed[("historical", opponent, seed)]))
            values.append(delta)
            sensitivity_overall[seed].append(delta)
        sensitivity_deltas[opponent] = interval(values)
    paired_counterpart_checks = []
    for key, recovered in recovery_by_cell.items():
        original = original_by_cell.get(key)
        if original is not None:
            paired_counterpart_checks.append({
                "controller": key[0], "opponent": key[1], "seed": key[2], "seat": key[3],
                "original_scores": original["scores"], "recovery_scores": recovered["scores"],
                "scores_identical": original["scores"] == recovered["scores"],
            })
    recovery_sensitivity = {
        "use": "diagnostic only; failed original attempts remain failures",
        "games": len(recovery_rows),
        "all_complete_720": all(
            row["status"] == "complete" and row["recorded_transitions"] == 720
            for row in recovery_rows
        ),
        "replaced_failed_cells_for_sensitivity": len(recovered_keys),
        "paired_counterpart_checks": paired_counterpart_checks,
        "by_opponent": sensitivity_deltas,
        "opponent_stratified_overall": interval([
            statistics.mean(sensitivity_overall[seed]) for seed in sorted(sensitivity_overall)
        ]),
    }

    losses = sorted(
        ({key: row[key] for key in ("controller", "opponent", "seed", "candidate_seat",
                                     "candidate_cash", "opponent_cash", "margin", "cell_id")}
         for row in rows if row["margin"] < 0),
        key=lambda row: row["margin"],
    )
    versions = {
        "repo_commit": __import__("subprocess").check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "current_archive": sha256(repo / "revenue/kaggriculture/cloud-execution-lab/exports/titan-current.tar.gz"),
        "historical_archive": sha256(repo / "revenue/kaggriculture/cloud-execution-lab/exports/historical/titan-7b58fa06da778b1519b81d509d28dff3481b3bbcc7a2d656e8bdfe4a22540524.tar.gz"),
        "evaluator": sha256(repo / "revenue/kaggriculture/cloud-eval/evaluate.py"),
        "loader": sha256(repo / "revenue/kaggriculture/20260907-offline-agent/evaluate.py"),
        "driver": sha256(repo / "revenue/kaggriculture/cloud-ultra-league/run_league.py"),
        "apex_source_entrypoint": sha256(repo / "revenue/kaggriculture/cloud-execution-lab/reference/apex/main.py"),
        "apex_prebuilt_binary": sha256(repo / "revenue/kaggriculture/cloud-execution-lab/reference/apex/agent.so"),
        "arlene": sha256(repo / "revenue/kaggriculture/cloud-execution-lab/reference/next-panel/vendor/arlene.py"),
        "euler": sha256(repo / "revenue/kaggriculture/20260907-offline-agent/main.py"),
    }
    summary = {
        "operation": "titan-root-sim-b-20260908-1345",
        "seed_range": [1909081501, 1909081532],
        "scheduled_games": 384,
        "recorded_results": len(rows) + len(failures),
        "complete_games": len(rows),
        "failures": [{
            "controller": row["controller"],
            "opponent": row["opponent"],
            "seed": row["seed"],
            "candidate_seat": row["candidate_seat"],
            "cell_id": row["cell_id"],
            "failure_seat": row["failure"].get("seat"),
            "step": row["failure"].get("step"),
            "phase": row["failure"].get("phase"),
            "kind": row["failure"].get("kind"),
            "exchange_seconds": row["failure"].get("rpc_failure", {}).get("transport", {}).get("exchange_seconds"),
            "request_encoded_seconds": row["failure"].get("rpc_failure", {}).get("transport", {}).get("request_encoded_seconds"),
            "request_bytes_written": row["failure"].get("rpc_failure", {}).get("transport", {}).get("request_bytes_written"),
        } for row in failures],
        "controllers": by_controller,
        "paired_controller_margin_delta": paired,
        "recovery_sensitivity": recovery_sensitivity,
        "losses": losses,
        "versions": versions,
    }
    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
