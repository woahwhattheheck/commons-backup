#!/usr/bin/env python3
"""Verify retained replay identity and summarize land counterfactuals."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import statistics


FILES = {
    "SELL": ("retained-first4.json.gz", "retained-next12.json.gz"),
    "COK": ("retained-first4-cok.json.gz", "retained-next12-cok.json.gz"),
}


def load_games(root: Path, names):
    games = []
    for name in names:
        with gzip.open(root / name, "rt", encoding="utf-8") as stream:
            document = json.load(stream)
        if document["engine_ref"] != "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c":
            raise ValueError(f"wrong engine pin in {name}")
        games.extend(document["games"])
    return games


def verify_baseline(game):
    trace = Path(game["trace"])
    sidecar = trace.with_name(trace.name.replace(".trace.json.gz", ".json"))
    source = json.loads(sidecar.read_text())
    seat = int(game["seat"])
    expected = source["scores"]
    actual = [None, None]
    actual[seat] = game["baseline_cash"]
    actual[1-seat] = game["baseline_rival_cash"]
    if (source["status"] != "complete" or source["steps"] != 719 or
            actual != expected):
        raise ValueError(f"baseline replay mismatch for {trace}")


def stats(values):
    return {
        "n": len(values),
        "positive": sum(value > 0 for value in values),
        "zero": sum(value == 0 for value in values),
        "negative": sum(value < 0 for value in values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def fixed_step(games, step):
    values = []
    for game in games:
        row = next((row for row in game["extra_land"]["tested"]
                    if row["step"] == step), None)
        if row is None:
            raise ValueError(f"step {step} absent from {game['trace']}")
        if not row["purchase_executed"]:
            raise ValueError(f"land purchase failed in {game['trace']}")
        values.append(row["terminal_cash_delta"])
    return stats(values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parent)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.root / "summary.json"
    families, all_games = {}, []
    for family, names in FILES.items():
        games = load_games(args.root, names)
        if len(games) != 32:
            raise ValueError(f"expected 32 {family} traces, got {len(games)}")
        for game in games:
            verify_baseline(game)
        shifts = [row["terminal_cash_delta"] for game in games
                  for row in game["shifted_existing"]]
        best = [game["extra_land"]["best"]["terminal_cash_delta"]
                for game in games]
        families[family] = {
            "baseline_replays_verified": len(games),
            "earlier_existing_land": stats(shifts),
            "third_land_step266": fixed_step(games, 266),
            "hindsight_best_tested_timing": stats(best),
        }
        all_games.extend(games)
    result = {
        "classification": "deliberate engine-valid fixed-action counterfactuals; not natural occurrences",
        "controller": "submitted 7b58fa06da778b1519b81d509d28dff3481b3bbcc7a2d656e8bdfe4a22540524",
        "engine": "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c / package 1.32.7",
        "families": families,
        "combined": {
            "baseline_replays_verified": len(all_games),
            "third_land_step266": fixed_step(all_games, 266),
            "hindsight_best_tested_timing": stats([
                game["extra_land"]["best"]["terminal_cash_delta"]
                for game in all_games
            ]),
        },
        "decision": "reject unconditional early third-land purchase; require a prospective public-state payback certificate",
    }
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
