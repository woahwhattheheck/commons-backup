"""Summarize matched ROOT-SIM-C full-game outputs from existing league jobs."""
from __future__ import annotations

import argparse
import gzip
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path


def load_results(roots):
    rows = []
    for root in roots:
        for path in sorted(root.rglob("result.json")):
            row = json.loads(path.read_text())
            row["result_path"] = str(path)
            row["trajectory_path"] = str(path.with_name("trajectory.jsonl.gz"))
            rows.append(row)
    return rows


def key(row):
    return row["opponent"], row["seed"], row["candidate_seat"]


def logical_complete(rows, label):
    grouped = defaultdict(list)
    for row in rows:
        grouped[key(row)].append(row)
    chosen, problems = {}, []
    for cell, attempts in grouped.items():
        complete = [row for row in attempts if row["status"] == "complete"]
        if len(complete) != 1:
            problems.append({"cell": cell, "complete_attempts": len(complete),
                             "statuses": [row["status"] for row in attempts]})
        elif complete:
            chosen[cell] = complete[0]
    if problems:
        raise SystemExit(f"{label} logical cell problems: {problems}")
    return chosen


def margin(row):
    seat = row["candidate_seat"]
    return row["scores"][seat] - row["scores"][1 - seat]


def own_cash(row):
    return row["scores"][row["candidate_seat"]]


def outcome(value):
    return "W" if value > 0 else "L" if value < 0 else "T"


def bootstrap_ci(values, rng, samples=20000):
    if not values:
        return None
    means = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(samples))
    return [means[int(.025 * samples)], means[int(.975 * samples)]]


def first_candidate_action_difference(current, historical):
    seat = current["candidate_seat"]
    with gzip.open(current["trajectory_path"], "rt") as left, gzip.open(historical["trajectory_path"], "rt") as right:
        for left_line, right_line in zip(left, right):
            a, b = json.loads(left_line), json.loads(right_line)
            current_action = a["state"][seat]["action"]
            historical_action = b["state"][seat]["action"]
            if current_action != historical_action:
                return {"transition": a["transition"], "current_action": current_action,
                        "historical_action": historical_action}
    return None


def actor_timings(rows):
    calls, rpcs = [], []
    for row in rows:
        actor = row["actors"][row["candidate_seat"]]
        calls.extend(actor.get("call_seconds", []))
        rpcs.extend(actor.get("rpc_seconds", []))
    def stats(values):
        ordered = sorted(values)
        return {"count": len(values), "mean": statistics.mean(values),
                "p95": ordered[int(.95 * (len(ordered) - 1))],
                "p99": ordered[int(.99 * (len(ordered) - 1))], "max": max(values)}
    return {"call_seconds": stats(calls), "rpc_seconds": stats(rpcs)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, action="append", required=True)
    parser.add_argument("--historical", type=Path, action="append", required=True)
    parser.add_argument("--failed-state", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    current = logical_complete(load_results(args.current), "current")
    historical = logical_complete(load_results(args.historical), "historical")
    expected = {(opponent, seed, seat) for opponent in ("apex", "arlene", "euler")
                for seed in range(1909081601, 1909081633) for seat in (0, 1)}
    if set(current) != expected or set(historical) != expected:
        raise SystemExit(f"grid mismatch current={len(current)} historical={len(historical)} expected={len(expected)}")

    rng = random.Random(20260908)
    strata = {}
    for opponent in ("apex", "arlene", "euler"):
        crows = [current[cell] for cell in sorted(current) if cell[0] == opponent]
        hrows = [historical[cell] for cell in sorted(historical) if cell[0] == opponent]
        seed_deltas, seed_cash_deltas = [], []
        for seed in range(1909081601, 1909081633):
            cells = [(opponent, seed, seat) for seat in (0, 1)]
            seed_deltas.append(statistics.mean(margin(current[cell]) - margin(historical[cell]) for cell in cells))
            seed_cash_deltas.append(statistics.mean(own_cash(current[cell]) - own_cash(historical[cell]) for cell in cells))
        strata[opponent] = {
            "games_per_controller": len(crows),
            "current_wdl": {x: sum(outcome(margin(row)) == x for row in crows) for x in "WTL"},
            "historical_wdl": {x: sum(outcome(margin(row)) == x for row in hrows) for x in "WTL"},
            "current_mean_own_cash": statistics.mean(map(own_cash, crows)),
            "historical_mean_own_cash": statistics.mean(map(own_cash, hrows)),
            "current_mean_margin": statistics.mean(map(margin, crows)),
            "historical_mean_margin": statistics.mean(map(margin, hrows)),
            "mean_paired_margin_delta": statistics.mean(seed_deltas),
            "seed_paired_margin_delta_bootstrap_95": bootstrap_ci(seed_deltas, rng),
            "mean_paired_own_cash_delta": statistics.mean(seed_cash_deltas),
            "seed_paired_own_cash_delta_bootstrap_95": bootstrap_ci(seed_cash_deltas, rng),
        }

    paired = []
    for cell in sorted(expected):
        c, h = current[cell], historical[cell]
        paired.append({"opponent": cell[0], "seed": cell[1], "seat": cell[2],
                       "current_scores": c["scores"], "historical_scores": h["scores"],
                       "current_margin": margin(c), "historical_margin": margin(h),
                       "margin_delta": margin(c) - margin(h),
                       "own_cash_delta": own_cash(c) - own_cash(h)})
    seed_deltas = [statistics.mean(row["margin_delta"] for row in paired if row["seed"] == seed)
                   for seed in range(1909081601, 1909081633)]
    seed_cash_deltas = [statistics.mean(row["own_cash_delta"] for row in paired if row["seed"] == seed)
                        for seed in range(1909081601, 1909081633)]
    losses = sorted((row for row in current.values() if margin(row) < 0), key=margin)
    cases = []
    for row in losses[:12]:
        cell = key(row)
        cases.append({"opponent": cell[0], "seed": cell[1], "seat": cell[2],
                      "current_scores": row["scores"], "current_margin": margin(row),
                      "historical_scores": historical[cell]["scores"],
                      "historical_margin": margin(historical[cell]),
                      "first_candidate_action_difference": first_candidate_action_difference(row, historical[cell])})
    setup_failures = []
    for path in args.failed_state:
        state = json.loads(path.read_text())
        for row in state["finished_cells"]:
            if row["status"] == "complete":
                continue
            failure = row.get("failure") or {}
            transport = (failure.get("rpc_failure") or {}).get("transport") or {}
            setup_failures.append({
                "state": str(path), "id": row["id"], "seed": row["seed"],
                "seat": row["seat"], "opponent": row["opponent"],
                "kind": failure.get("kind"), "phase": failure.get("phase"),
                "failed_actor_seat": failure.get("seat"), "step": failure.get("step"),
                "timeout_seconds": transport.get("timeout_seconds"),
                "exchange_seconds": transport.get("exchange_seconds"),
                "response_bytes_read": transport.get("response_bytes_read"),
            })
    report = {
        "operation": "titan-root-sim-c-20260908-1345",
        "logical_completed_games": len(current) + len(historical),
        "logical_errors_or_timeouts": 0,
        "completed_action_rounds": sum(row["steps"] for row in [*current.values(), *historical.values()]),
        "controllers": {"current": 192, "historical_v1": 192},
        "grid": {"seeds": [1909081601, 1909081632], "opponents": ["apex", "arlene", "euler"],
                 "seats": [0, 1], "episode_steps": 720},
        "overall": {
            "current_wdl": {x: sum(outcome(margin(row)) == x for row in current.values()) for x in "WTL"},
            "historical_wdl": {x: sum(outcome(margin(row)) == x for row in historical.values()) for x in "WTL"},
            "current_mean_own_cash": statistics.mean(map(own_cash, current.values())),
            "historical_mean_own_cash": statistics.mean(map(own_cash, historical.values())),
            "mean_paired_margin_delta": statistics.mean(seed_deltas),
            "seed_paired_margin_delta_bootstrap_95": bootstrap_ci(seed_deltas, rng),
            "mean_paired_own_cash_delta": statistics.mean(seed_cash_deltas),
            "seed_paired_own_cash_delta_bootstrap_95": bootstrap_ci(seed_cash_deltas, rng),
        },
        "strata": strata,
        "current_candidate_timings": actor_timings(list(current.values())),
        "historical_candidate_timings": actor_timings(list(historical.values())),
        "retained_failed_attempts": setup_failures,
        "worst_current_losses": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"logical_completed_games": report["logical_completed_games"],
                      "overall": report["overall"], "strata": strata,
                      "retained_failed_attempts": len(setup_failures)}, indent=2))


if __name__ == "__main__":
    main()
