#!/usr/bin/env python3
"""Emit aggregate W/D/L, timing, and paired effects from private league results."""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path


def percentile(values, q):
    values = sorted(values)
    pos = (len(values) - 1) * q
    low, high = math.floor(pos), math.ceil(pos)
    return values[low] if low == high else values[low] * (high-pos) + values[high] * (pos-low)


def bootstrap(values, samples=50000):
    rng, n = random.Random(20260908), len(values)
    means = [sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(samples)]
    return [percentile(means, .025), percentile(means, .975)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("result_root", type=Path)
    args = parser.parse_args()
    rows = {}
    started = list(args.result_root.glob("**/STARTED.json"))
    for path in args.result_root.glob("**/result.json"):
        row = json.loads(path.read_text())
        controller = "historical" if row.get("cell_id", "").startswith("historical-") else "current"
        key = (controller, row.get("seed"), row.get("candidate_seat"), row.get("opponent"))
        if row.get("status") == "complete":
            rows[key] = row
    strata = {}
    for controller in ("current", "historical"):
        for opponent in ("apex", "arlene", "euler"):
            group = [v for (c, _, _, o), v in rows.items() if c == controller and o == opponent]
            wdl, cash, margins, wall, calls, rpc = [0, 0, 0], [], [], [], [], []
            for row in group:
                seat = row["candidate_seat"]
                own, rival = row["scores"][seat], row["scores"][1-seat]
                wdl[0 if own > rival else 2 if own < rival else 1] += 1
                cash.append(own); margins.append(own-rival); wall.append(row["wall_seconds"])
                calls += row["actors"][seat]["call_seconds"]
                rpc += row["actors"][seat]["rpc_seconds"]
            strata[f"{controller}:{opponent}"] = {
                "games": len(group), "wdl": wdl, "mean_final_cash": statistics.fmean(cash),
                "mean_margin": statistics.fmean(margins),
                "wall_median_p95_max": [statistics.median(wall), percentile(wall, .95), max(wall)],
                "call_p99_max": [percentile(calls, .99), max(calls)],
                "rpc_p99_max": [percentile(rpc, .99), max(rpc)]}
    effects = {}
    for opponent in ("apex", "arlene", "euler"):
        by_seed = defaultdict(list)
        for seed in range(1909081701, 1909081733):
            for seat in (0, 1):
                current = rows[("current", seed, seat, opponent)]
                historical = rows[("historical", seed, seat, opponent)]
                cm = current["scores"][seat] - current["scores"][1-seat]
                hm = historical["scores"][seat] - historical["scores"][1-seat]
                by_seed[seed].append(cm-hm)
        values = [statistics.fmean(pair) for pair in by_seed.values()]
        effects[opponent] = {"seed_units": len(values), "mean": statistics.fmean(values),
                             "median": statistics.median(values), "bootstrap_95_ci": bootstrap(values),
                             "min": min(values), "max": max(values)}
    print(json.dumps({"started_attempts": len(started), "complete_identities": len(rows),
                      "strata": strata, "seed_level_paired_margin_delta": effects},
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
