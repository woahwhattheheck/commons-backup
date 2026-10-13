#!/usr/bin/env python3
"""Validate and summarize raw paired wide-field reports without dropping failures."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verdict(own: float, rival: float) -> str:
    return "W" if own > rival else "L" if own < rival else "T"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    cfg = json.loads(args.config.read_text())
    entries = [x.split("=", 1)[0] for x in cfg["opponents"]]
    seeds = list(range(cfg["seeds"]["first"], cfg["seeds"]["last"] + 1))
    rows, reports, errors = [], [], []
    for arm in cfg["arms"]:
        for path in sorted((args.input / "raw" / arm).glob("*.json")):
            report = json.loads(path.read_text())
            reports.append({"arm": arm, "path": str(path), "sha256": digest(path)})
            for game in report.get("games", []):
                row = {"arm": arm, **game}
                scores, seat = game.get("scores"), game["candidate_seat"]
                if game.get("status") == "complete" and scores:
                    row["own_cash"] = scores[seat]
                    row["rival_cash"] = scores[1 - seat]
                    row["verdict"] = verdict(row["own_cash"], row["rival_cash"])
                else:
                    errors.append(row)
                rows.append(row)
    expected = {(arm, seed, seat, opp) for arm in cfg["arms"] for seed in seeds
                for seat in (0, 1) for opp in entries}
    all_rows = rows
    key_of = lambda r: (r["arm"], r["seed"], r["candidate_seat"], r["opponent"])
    unexpected = sorted({key_of(r) for r in all_rows} - expected)
    rows = [r for r in all_rows if key_of(r) in expected]
    errors = [r for r in errors if key_of(r) in expected]
    observed = {key_of(r) for r in rows}
    duplicates = len(rows) - len(observed)
    missing = sorted(expected - observed)
    control = cfg["control"]
    by_key = {(r["arm"], r["seed"], r["candidate_seat"], r["opponent"]): r for r in rows}
    summary = {}
    for arm in cfg["arms"]:
        arm_rows = [r for r in rows if r["arm"] == arm and "verdict" in r]
        item = {v: sum(r["verdict"] == v for r in arm_rows) for v in ("W", "T", "L")}
        item["completed"] = len(arm_rows)
        item["failed"] = sum(r["arm"] == arm for r in errors)
        item["mean_own_cash"] = statistics.fmean(r["own_cash"] for r in arm_rows) if arm_rows else None
        item["mean_rival_cash"] = statistics.fmean(r["rival_cash"] for r in arm_rows) if arm_rows else None
        max_calls = [r["actors"][r["candidate_seat"]]["max_call_seconds"] for r in arm_rows]
        item["max_candidate_call_seconds"] = max(max_calls, default=None)
        by_opponent = {}
        mirror = {}
        for opponent in entries:
            ors = [r for r in arm_rows if r["opponent"] == opponent]
            by_opponent[opponent] = {
                **{v: sum(r["verdict"] == v for r in ors) for v in ("W", "T", "L")},
                "completed": len(ors),
                "mean_own_cash": statistics.fmean(r["own_cash"] for r in ors) if ors else None,
                "mean_rival_cash": statistics.fmean(r["rival_cash"] for r in ors) if ors else None,
            }
            exact = 0
            compared = 0
            for seed in seeds:
                pair = [r for r in ors if r["seed"] == seed]
                if len(pair) != 2:
                    continue
                compared += 1
                exact += (pair[0]["own_cash"] == pair[1]["own_cash"] and
                          pair[0]["rival_cash"] == pair[1]["rival_cash"])
            mirror[opponent] = {"exact_mirrors": exact, "seat_pairs": compared}
        item["by_opponent"] = by_opponent
        item["mirror_dependence"] = mirror
        if arm != control:
            deltas = []
            flips = defaultdict(int)
            for r in arm_rows:
                key = (control, r["seed"], r["candidate_seat"], r["opponent"])
                base = by_key.get(key)
                if not base or "verdict" not in base:
                    continue
                d = {"seed": r["seed"], "seat": r["candidate_seat"], "opponent": r["opponent"],
                     "d_own": r["own_cash"] - base["own_cash"],
                     "d_rival": r["rival_cash"] - base["rival_cash"],
                     "d_margin": (r["own_cash"] - r["rival_cash"]) -
                                 (base["own_cash"] - base["rival_cash"]),
                     "control_verdict": base["verdict"], "arm_verdict": r["verdict"]}
                deltas.append(d)
                if d["control_verdict"] != d["arm_verdict"]:
                    flips[d["control_verdict"] + "->" + d["arm_verdict"]] += 1
            item["paired"] = {"count": len(deltas),
                              "mean_d_own": statistics.fmean(d["d_own"] for d in deltas) if deltas else None,
                              "mean_d_rival": statistics.fmean(d["d_rival"] for d in deltas) if deltas else None,
                              "mean_d_margin": statistics.fmean(d["d_margin"] for d in deltas) if deltas else None,
                              "flips": dict(flips),
                              "by_opponent": {
                                  opponent: {
                                      "count": len(ds := [d for d in deltas if d["opponent"] == opponent]),
                                      "mean_d_own": statistics.fmean(d["d_own"] for d in ds) if ds else None,
                                      "mean_d_rival": statistics.fmean(d["d_rival"] for d in ds) if ds else None,
                                      "mean_d_margin": statistics.fmean(d["d_margin"] for d in ds) if ds else None,
                                  } for opponent in entries
                              },
                              "rows": deltas}
        summary[arm] = item
    loss_dir = args.output / "loss-traces"
    loss_dir.mkdir(parents=True, exist_ok=True)
    for r in rows:
        if r.get("verdict") == "L" or r.get("status") != "complete":
            name = f"{r['arm']}-{r['seed']}-{r['candidate_seat']}-{r['opponent']}.json"
            (loss_dir / name).write_text(json.dumps(r, indent=2) + "\n")
    result = {"schema": "titan.widefield.v1",
              "complete": not missing and not unexpected and not duplicates and not errors,
              "expected_games": len(expected), "observed_games": len(rows),
              "missing": missing, "unexpected": unexpected,
              "duplicate_count": duplicates, "errors": errors,
              "lineage_note": "lonespear18-greedy and lonespear18-scipy are modes of one source lineage",
              "source_lineage_count": len(set(cfg.get("lineages", {}).values())),
              "reports": reports, "summary": summary}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "summary"}, indent=2))
    for arm, item in summary.items():
        print(arm, item["W"], item["T"], item["L"], "failed", item["failed"],
              "mean own/rival", item["mean_own_cash"], item["mean_rival_cash"])
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
