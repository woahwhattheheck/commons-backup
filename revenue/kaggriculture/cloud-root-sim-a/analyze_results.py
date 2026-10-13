"""Aggregate the fixed ROOT-SIM-A bank without publishing raw trajectories."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path


CONTROLLERS = ("current499989ab", "historical7b58")
OPPONENTS = ("apex", "arlene", "euler")
SEEDS = tuple(range(1909081401, 1909081433))


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low, fraction = int(position), position % 1
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def bootstrap_mean_ci(values: list[float], rng: random.Random) -> list[float]:
    draws = [statistics.fmean(rng.choice(values) for _ in values) for _ in range(20000)]
    return [percentile(draws, 0.025), percentile(draws, 0.975)]


def canonical_path(root: Path, controller: str, opponent: str, seed: int, seat: int) -> Path:
    if seed == 1909081401 and opponent != "apex":
        phase, suffix = "calibration", ""
    elif seed <= 1909081402 and opponent == "apex":
        phase, suffix = "setup-fixed-apex", "-setup-fixed"
    elif seed == 1909081402:
        phase, suffix = "calibration-rest", ""
    elif controller == "current499989ab" and seed == 1909081426 and opponent in {"arlene", "euler"}:
        phase, suffix = "low-concurrency-fixed", "-low-concurrency-fixed"
    else:
        phase, suffix = "remaining", ""
    return root / "results" / phase / controller / f"{opponent}-{seed}-s{seat}{suffix}" / "result.json"


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, repo = args.job_root.resolve(), args.repo.resolve()
    games: dict[tuple, dict] = {}
    for controller in CONTROLLERS:
        for opponent in OPPONENTS:
            for seed in SEEDS:
                for seat in (0, 1):
                    path = canonical_path(root, controller, opponent, seed, seat)
                    if not path.is_file():
                        raise SystemExit(f"missing canonical result: {path}")
                    game = read(path)
                    expected = (seed, seat, opponent, "complete", 719, 720)
                    actual = (game.get("seed"), game.get("candidate_seat"), game.get("opponent"),
                              game.get("status"), game.get("steps"), game.get("episode_steps"))
                    if actual != expected:
                        raise SystemExit(f"invalid canonical result {path}: {actual}")
                    games[controller, opponent, seed, seat] = game

    rng = random.Random(1909081401)
    summary: dict = {"controllers": {}, "paired_controller_delta": {}}
    for controller in CONTROLLERS:
        controller_rows = []
        for opponent in OPPONENTS:
            rows = [games[controller, opponent, seed, seat] for seed in SEEDS for seat in (0, 1)]
            margins, outcomes, cash = [], Counter(), []
            for game in rows:
                seat = game["candidate_seat"]
                own, rival = game["scores"][seat], game["scores"][1 - seat]
                margins.append(own - rival)
                cash.append(own)
                outcomes["W" if own > rival else "L" if own < rival else "D"] += 1
            paired = [sum(games[controller, opponent, seed, seat]["scores"][seat]
                          - games[controller, opponent, seed, seat]["scores"][1 - seat]
                          for seat in (0, 1)) for seed in SEEDS]
            summary["controllers"].setdefault(controller, {"opponents": {}})["opponents"][opponent] = {
                "games": len(rows), "wdl": dict(outcomes), "final_cash_mean": statistics.fmean(cash),
                "margin_mean_per_game": statistics.fmean(margins),
                "paired_margin_mean_per_seed": statistics.fmean(paired),
                "paired_margin_95pct_seed_bootstrap_ci": bootstrap_mean_ci(paired, rng),
            }
            controller_rows.extend(rows)
        calls, rpcs, walls = [], [], []
        for game in controller_rows:
            actor = game["actors"][game["candidate_seat"]]
            calls.extend(actor["call_seconds"])
            rpcs.extend(actor["rpc_seconds"])
            walls.append(game["wall_seconds"])
        summary["controllers"][controller]["all_opponents"] = {
            "games": len(controller_rows), "errors_or_timeouts": 0,
            "action_calls": len(calls),
            "call_seconds": {"median": statistics.median(calls), "p95": percentile(calls, .95),
                             "p99": percentile(calls, .99), "max": max(calls)},
            "rpc_seconds": {"median": statistics.median(rpcs), "p95": percentile(rpcs, .95),
                            "p99": percentile(rpcs, .99), "max": max(rpcs)},
            "game_wall_seconds": {"median": statistics.median(walls), "p95": percentile(walls, .95),
                                  "max": max(walls)},
        }

    overall_by_seed = defaultdict(list)
    for opponent in OPPONENTS:
        deltas = []
        for seed in SEEDS:
            values = {}
            for controller in CONTROLLERS:
                values[controller] = sum(
                    games[controller, opponent, seed, seat]["scores"][seat]
                    - games[controller, opponent, seed, seat]["scores"][1 - seat]
                    for seat in (0, 1))
            delta = values["current499989ab"] - values["historical7b58"]
            deltas.append(delta)
            overall_by_seed[seed].append(delta)
        summary["paired_controller_delta"][opponent] = {
            "seed_count": len(deltas), "paired_margin_delta_mean": statistics.fmean(deltas),
            "95pct_seed_bootstrap_ci": bootstrap_mean_ci(deltas, rng),
            "min": min(deltas), "max": max(deltas),
        }
    overall = [statistics.fmean(overall_by_seed[seed]) for seed in SEEDS]
    summary["paired_controller_delta"]["stratified_overall"] = {
        "seed_count": len(overall), "opponents_per_seed": len(OPPONENTS),
        "mean_paired_margin_delta": statistics.fmean(overall),
        "95pct_seed_bootstrap_ci": bootstrap_mean_ci(overall, rng),
    }

    setup_failures = []
    for path in sorted((root / "results").glob("*/*/*/result.json")):
        game = read(path)
        if game.get("status") != "complete":
            setup_failures.append({"controller": path.parts[-3], "cell_id": game.get("cell_id"),
                                   "kind": game.get("failure", {}).get("kind"),
                                   "step": game.get("failure", {}).get("step")})
    report = {
        "operation": "titan-root-sim-a-20260908-1345", "schema_version": 1,
        "versions": {
            "commons_commit": "9ab11ca5a5d130e20ba1a87d339a1044c27fa507",
            "current_archive_sha256": "499989ab907331d4c0c990af2ab3703e6731dc83078964aca8563ea5a069e48e",
            "current_archive_bytes": 313471,
            "current_runtime_files": 83,
            "current_tar_file_members_including_SOURCE_json": 84,
            "historical_archive_sha256": "7b58fa06da778b1519b81d509d28dff3481b3bbcc7a2d656e8bdfe4a22540524",
            "historical_archive_bytes": 286356,
            "historical_runtime_files": 77,
            "historical_tar_file_members_including_SOURCE_json": 78,
            "engine_ref": "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c",
            "evaluator_sha256": file_sha(repo / "revenue/kaggriculture/cloud-eval/evaluate.py"),
            "loader_sha256": file_sha(repo / "revenue/kaggriculture/20260907-offline-agent/evaluate.py"),
            "league_sha256": file_sha(repo / "revenue/kaggriculture/cloud-ultra-league/run_league.py"),
            "apex_source_sha256": file_sha(root / "opponents/apex/main.py"),
            "apex_binary_sha256": file_sha(root / "opponents/apex/agent.so"),
            "used_job_config_sha256": {
                name: file_sha(root / "configs" / (name + ".json")) for name in (
                    "calibration-current499989ab", "calibration-historical7b58",
                    "setup-fixed-apex-current499989ab", "setup-fixed-apex-historical7b58",
                    "calibration-rest-current499989ab", "calibration-rest-historical7b58",
                    "remaining-current499989ab", "remaining-historical7b58",
                    "low-concurrency-fixed-current499989ab",
                )
            },
        },
        "canonical_full_games": len(games), "setup_failures_retained_excluded_from_wdl": setup_failures,
        "summary": summary,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
