#!/usr/bin/env python3
"""Test moving one already-planned crop into an earlier free worker window."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import statistics

import analyze_traces as common


EARLY = ((284, 10, ["PLANT", "WHEAT"]), (285, 10, ["WATER"]))


def validate_reached_predicate(actions, observations, seat):
    for step in (284, 285):
        obs = observations[(step, seat)]
        farm = obs["farms"][seat]
        position = farm["hands"][10]
        if (position != [8, 0] or farm["tiles"][0][8] is not None or
                actions[step][seat]["hands"][10] != ["PASS"] or
                obs["private"]["seeds"].get("WHEAT", 0) <= 0):
            raise ValueError(f"early free-window predicate failed at {step}")
    later = observations[(304, seat)]["farms"][seat]
    if (later["hands"][5] != [8, 0] or
            actions[304][seat]["hands"][5] != ["PLANT", "WHEAT"] or
            actions[305][seat]["hands"][5] != ["WATER"]):
        raise ValueError("later same-tile plant/water pair is absent")


def analyze(path, engine, evaluator):
    seed, seat = common.trace_identity(path)
    actions, observations = common.read_trace(path)
    validate_reached_predicate(actions, observations, seat)
    baseline = common.replay(engine, evaluator, actions, seed, seat)
    changed = copy.deepcopy(actions)
    for step, hand, request in EARLY:
        changed[step][seat]["hands"][hand] = request
    trial = common.replay(engine, evaluator, changed, seed, seat)
    return {
        "trace": str(path), "seed": seed, "seat": seat,
        "baseline_cash": baseline["cash"], "trial_cash": trial["cash"],
        "terminal_cash_delta": trial["cash"] - baseline["cash"],
        "rival_cash_delta": trial["rival_cash"] - baseline["rival_cash"],
        "terminal_seed_state_preserved": (
            baseline["final_private"]["seeds"] == trial["final_private"]["seeds"]
        ),
        "changed_requests": [
            {"step": step, "hand_index": hand, "before": ["PASS"], "after": request}
            for step, hand, request in EARLY
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("traces", nargs="+", type=Path)
    args = parser.parse_args()
    root = args.archive_root.resolve()
    evaluator = common.load(root / "checks/reference/evaluator/evaluate.py",
                            "early_plant_evaluator")
    engine, hashes = evaluator.get_engine(
        args.engine_dir.resolve(), root / "checks/reference/evaluator/loader.py")
    games = [analyze(path, engine, evaluator) for path in args.traces]
    values = [game["terminal_cash_delta"] for game in games]
    result = {
        "classification": "deliberate engine-valid fixed-action counterfactuals",
        "engine_ref": evaluator.ENGINE_REF, "engine_sha256": hashes,
        "games": games,
        "summary": {
            "n": len(values), "positive": sum(v > 0 for v in values),
            "zero": sum(v == 0 for v in values),
            "negative": sum(v < 0 for v in values),
            "mean": statistics.mean(values), "median": statistics.median(values),
            "minimum": min(values), "maximum": max(values),
            "terminal_seed_state_preserved": all(
                game["terminal_seed_state_preserved"] for game in games),
        },
        "decision": "send opportunity to complete-route owner; reject standalone transform",
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
