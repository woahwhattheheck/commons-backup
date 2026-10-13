#!/usr/bin/env python3
"""Combine source-frozen evaluator reports with tie-aware paired outcomes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    games = []
    inputs = []
    for path in args.inputs:
        report = json.loads(path.read_text())
        games.extend(report["games"])
        inputs.append({"path": str(path), "sha256": sha(path), "progress": report.get("progress")})
    valid = [g for g in games if g["status"] == "complete"]
    margins = [g["scores"][g["candidate_seat"]] - g["scores"][1-g["candidate_seat"]] for g in valid]
    pairs = []
    for seed in sorted({g["seed"] for g in games}):
        rows = sorted((g for g in valid if g["seed"] == seed), key=lambda g: g["candidate_seat"])
        pairs.append({"seed": seed, "games": len(rows),
                      "seat_results": [("W" if m > 0 else "L" if m < 0 else "T")
                                       for m in [r["scores"][r["candidate_seat"]] - r["scores"][1-r["candidate_seat"]] for r in rows]],
                      "margins": [r["scores"][r["candidate_seat"]] - r["scores"][1-r["candidate_seat"]] for r in rows]})
    actor_stats = [a for g in games for a in g.get("actors", [])]
    payload = {
        "inputs": inputs,
        "scheduled_games": len(games),
        "completed_games": len(valid),
        "failed_games": len(games) - len(valid),
        "wins": sum(m > 0 for m in margins),
        "ties": sum(m == 0 for m in margins),
        "losses": sum(m < 0 for m in margins),
        "tie_aware_score": (sum(m > 0 for m in margins) + 0.5 * sum(m == 0 for m in margins)) / len(margins) if margins else None,
        "mean_margin": statistics.mean(margins) if margins else None,
        "median_margin": statistics.median(margins) if margins else None,
        "max_agent_call_seconds": max((a.get("max_call_seconds", 0) for a in actor_stats), default=0),
        "max_rpc_seconds": max((a.get("max_rpc_seconds", 0) for a in actor_stats), default=0),
        "peak_actor_rss_kib": max((a.get("peak_rss_kib", 0) for a in actor_stats), default=0),
        "timeout_or_error_games": sum(g["status"] != "complete" for g in games),
        "pairs": pairs,
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
