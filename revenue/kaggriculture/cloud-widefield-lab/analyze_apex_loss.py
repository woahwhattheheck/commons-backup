#!/usr/bin/env python3
"""Summarize the retained Apex 9921001 diagnostic replays and experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load_game(path):
    return json.loads(Path(path).read_text())["games"][0]


def cash(game, seat=0):
    scores = game["scores"]
    return {"own_cash": scores[seat], "rival_cash": scores[1-seat],
            "margin": scores[seat] - scores[1-seat]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diagnosis", type=Path, required=True)
    ap.add_argument("--integrated-report", type=Path, required=True)
    ap.add_argument("--counterfactual", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    names = ["frozen-sell", "committed-envelope", "integrated-pr9997"]
    paths = {n: (args.diagnosis / f"{n}-fullstate.json"
                 if (args.diagnosis / f"{n}-fullstate.json").exists()
                 else args.diagnosis / f"{n}.json") for n in names}
    games = {n: load_game(p) for n, p in paths.items()}
    baseline = games["frozen-sell"]
    selected_days = (8, 9, 10, 13, 15, 16, 19, 21, 25, 27, 28, 29)
    trajectory = []
    for day in selected_days:
        row = baseline["daily_trajectory"][day]
        farms = row["after"]["farms"]
        market = row["after"]
        trajectory.append({
            "day": day, "step": row["step"],
            "cash": [farms[0]["money"], farms[1]["money"]],
            "margin": farms[0]["money"] - farms[1]["money"],
            "shed_room": [farms[0]["shed_room"], farms[1]["shed_room"]],
            "animals": [farms[0]["animals"], farms[1]["animals"]],
            "ready_yield_units": [sum(farms[0]["ready_yield"].values()),
                                  sum(farms[1]["ready_yield"].values())],
            "market_inventory": {k: market["market_inventory"].get(k, 0)
                                 for k in ("EGG", "WOOL", "MILK", "WHEAT")},
            "market_prices": {k: market["market_prices"].get(k)
                              for k in ("EGG", "WOOL", "MILK", "WHEAT")},
        })
    step226 = baseline["actions_and_timing"][226]
    step406 = baseline["actions_and_timing"][406]
    experiments = {}
    for path in sorted(args.counterfactual.glob("apex-9921001-*.json")):
        report = json.loads(path.read_text())
        values = []
        for game in report.get("games", []):
            if game.get("status") == "complete":
                values.append(cash(game, game["candidate_seat"]))
        experiments[path.stem] = {
            "games": len(report.get("games", [])), "completed": len(values),
            "cash": values, "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    report = {
        "schema": "titan.widefield.apex-loss-diagnosis.v1",
        "case": {"seed": 9921001, "opponent": "Apex", "independent_cases": 1,
                 "seat_records": 2, "seed_kind": "development"},
        "exact_arms": {n: {**cash(g), "trace_sha256": g["trace_sha256"],
                            "source": str(paths[n])} for n, g in games.items()},
        "trajectory": trajectory,
        "earliest_realized_production_divergence": {
            "step": 226, "day": 9, "before_cash": [
                step226["before"]["farms"][0]["money"],
                step226["before"]["farms"][1]["money"]],
            "market_prices": {k: step226["before"]["market_prices"][k]
                              for k in ("EGG", "WOOL", "MILK")},
            "actions": step226["actions"],
            "note": "step217 differing sheep quantities were unaffordable/no-op; animal counts first diverge after step226",
        },
        "cash_crossover": {"step": 406, "before_cash": [
                                step406["before"]["farms"][0]["money"],
                                step406["before"]["farms"][1]["money"]],
                            "after_cash": step406["bank"],
                            "actions": step406["actions"],
                            "market_prices": {k: step406["before"]["market_prices"][k]
                                              for k in ("EGG", "WOOL", "MILK")}},
        "capacity_finding": {
            "minimum_candidate_end_of_day_shed_room": min(
                r["after"]["farms"][0]["shed_room"] for r in baseline["daily_trajectory"]),
            "minimum_apex_end_of_day_shed_room": min(
                r["after"]["farms"][1]["shed_room"] for r in baseline["daily_trajectory"]),
            "end_of_day_overflow_observed": False,
            "note": "capacity becomes tight but does not bind this loss: every EOD carried inventory drops to zero and neither shed reaches 100",
        },
        "counterfactuals": experiments,
        "conclusion": {
            "bottleneck": "capital-and-route-coherent animal ROI, not SELL capacity",
            "evidence": "the parent funds 3 geese while wool is 3.7x egg price at first realized split; Apex funds 3 sheep and repeatedly monetizes scarcer wool",
            "narrow_substitution_result": "all tested goose-only substitutions remain losses and worsen margin; do not promote",
            "next_actionable_hypothesis": "choose the animal lot jointly with the same-turn hire/fertilizer budget and bind the producer route to the chosen product; retest as a producer-owned change, not a SELL/integration overlay",
        },
        "limitations": [
            "The two seat records are exact mirrors of one independent failure case.",
            "Changed actions can change shared market state and later opponent actions; counterfactual cash is whole-game evidence, not a ceteris-paribus unit price claim.",
            "Recorded market inventories/prices do not prove full RNG-state equivalence.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    recorded = {
        "trace_scope": "daily cash plus instrumented actions/market/capacity; SEDGE path counters absent",
        "provenance": {n: str(paths[n]) for n in names},
        "control": "frozen-sell", "candidate": "committed-envelope and integrated-pr9997",
        "rows": [{"arm": n, "seed": 9921001, "seat": 0, "opponent": "apex",
                  **cash(g), "trace_sha256": g["trace_sha256"]}
                 for n, g in games.items()],
    }
    recorded_path = args.output.with_name("apex-9921001-recorded-input.json")
    recorded_path.write_text(json.dumps(recorded, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"exact_arms": report["exact_arms"],
                      "capacity": report["capacity_finding"],
                      "counterfactuals": {k: v["cash"] for k, v in experiments.items()}},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
