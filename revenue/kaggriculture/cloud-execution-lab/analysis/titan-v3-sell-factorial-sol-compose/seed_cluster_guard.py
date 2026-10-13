#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Guard TITAN's four-arm SELL decision against hidden seed-cluster regressions."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

PARENT_OP = "titan-v3-sell-objective-certified-pressure-factorial-gate-20260910-01"
OP = "titan-v3-sell-seed-cluster-tail-guard-20260910-01"
ARMS = ("control", "own_value", "certified_pressure", "both")
SINGLES = ARMS[1:3]
VERDICTS = {
    "SELECT_BOTH": "both",
    "SELECT_OWN_VALUE": "own_value",
    "SELECT_CERTIFIED_PRESSURE": "certified_pressure",
    "NO_SAFE_ADVANCE": None,
    "INACTIVE": None,
}
RANK = {"loss": 0, "tie": 1, "win": 2}


class EvidenceError(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise EvidenceError(message)


def number(value, label):
    need(not isinstance(value, bool) and isinstance(value, (int, float)), f"{label} must be numeric")
    value = float(value)
    need(math.isfinite(value), f"{label} must be finite")
    return value


def integer(value, label):
    need(type(value) is int and value >= 0, f"{label} must be a nonnegative integer")
    return value


def summary(values, label):
    data = [number(value, label) for value in values]
    need(data, f"{label} is empty")
    total = math.fsum(data)
    mean = number(total / len(data), f"{label} mean")
    ordered = sorted(data)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else number(
        (ordered[mid - 1] + ordered[mid]) / 2, f"{label} median"
    )
    return {
        "count": len(data), "mean": mean, "median": median,
        "min": min(data), "max": max(data), "total": number(total, f"{label} total"),
        "positive": sum(v > 0 for v in data), "zero": sum(v == 0 for v in data),
        "negative": sum(v < 0 for v in data),
    }


def load(path):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, f"duplicate JSON key {key!r}")
            out[key] = value
        return out

    def bad_constant(value):
        raise EvidenceError(f"non-finite JSON constant {value}")

    try:
        raw = Path(path).read_bytes()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=bad_constant)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot load parent report: {exc}") from exc
    need(isinstance(value, dict), "parent report root must be an object")
    return value, hashlib.sha256(raw).hexdigest()


def semantic_sha(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError) as exc:
        raise EvidenceError("parent report is not canonical finite JSON") from exc
    return hashlib.sha256(raw).hexdigest()


def outcome(own, rival):
    return "win" if own > rival else "loss" if own < rival else "tie"


def validate(report):
    need(report.get("schema_version") == 1, "unsupported parent schema")
    need(report.get("operation") == PARENT_OP, "parent operation mismatch")
    need(report.get("arms") == list(ARMS), "parent arm ordering mismatch")

    sel = report.get("selection")
    need(isinstance(sel, dict), "parent selection must be an object")
    verdict = sel.get("verdict")
    need(verdict in VERDICTS, "unsupported parent verdict")
    selected = sel.get("selected_arm")
    need(selected == VERDICTS[verdict], "parent verdict/arm mismatch")
    eligible = sel.get("eligible_against_control")
    need(isinstance(eligible, dict) and set(eligible) == set(ARMS[1:]), "malformed eligibility map")
    need(all(type(v) is bool for v in eligible.values()), "eligibility values must be boolean")
    need(selected is None or eligible[selected], "parent selected an ineligible arm")
    composition = sel.get("composition_nondominated")
    need(type(composition) is bool and composition == (selected == "both"), "parent composition mismatch")
    need(sel.get("promotion_authorized") is False, "parent must not authorize promotion")
    need(sel.get("hosted_leaderboard_claim") is False, "parent must not claim hosted evidence")

    grid = report.get("grid")
    need(isinstance(grid, dict), "parent grid must be an object")
    opponents, seeds = grid.get("opponents"), grid.get("seeds")
    need(isinstance(opponents, list) and opponents and all(isinstance(x, str) and x for x in opponents), "bad opponents")
    need(len(opponents) == len(set(opponents)), "duplicate opponents")
    need(isinstance(seeds, list) and len(seeds) >= 2, "at least two independent seeds are required")
    seeds = [integer(seed, "seed") for seed in seeds]
    need(len(seeds) == len(set(seeds)), "duplicate seeds")
    need(grid.get("both_seats") is True, "both seats are required")
    expected = {(opp, seed, seat) for opp in opponents for seed in seeds for seat in (0, 1)}
    need(grid.get("cells_per_arm") == len(expected), "cells_per_arm mismatch")
    need(grid.get("total_games") == len(expected) * 4, "total_games mismatch")

    raw_cells = report.get("cells")
    need(isinstance(raw_cells, list) and len(raw_cells) == len(expected), "incomplete parent cell grid")
    seen, cells = set(), []
    for raw in raw_cells:
        need(isinstance(raw, dict), "cell must be an object")
        key = (raw.get("opponent"), raw.get("seed"), raw.get("candidate_seat"))
        need(key in expected, f"unexpected cell {key}")
        need(key not in seen, f"duplicate cell {key}")
        seen.add(key)
        arm_rows = raw.get("arms")
        need(isinstance(arm_rows, dict) and set(arm_rows) == set(ARMS), f"bad arm set {key}")
        states = {}
        for arm in ARMS:
            row = arm_rows[arm]
            need(isinstance(row, dict), f"bad state {key}/{arm}")
            own = number(row.get("own_cash"), f"{key}/{arm} own")
            rival = number(row.get("rival_cash"), f"{key}/{arm} rival")
            margin = number(row.get("margin"), f"{key}/{arm} margin")
            need(margin == number(own - rival, f"{key}/{arm} recomputed margin"), f"detached margin {key}/{arm}")
            need(row.get("outcome") == outcome(own, rival), f"detached outcome {key}/{arm}")
            states[arm] = {"own": own, "rival": rival, "margin": margin, "outcome": row["outcome"]}
        cells.append({"opponent": key[0], "seed": key[1], "seat": key[2], "arms": states})
    need(seen == expected, "parent cell grid mismatch")
    return sel, eligible, opponents, seeds, sorted(cells, key=lambda c: (c["seed"], c["opponent"], c["seat"]))


def cluster(rows, eligible, seed, opponent_name=None):
    own, margin, lost = [], [], 0
    for cell in rows:
        both = cell["arms"]["both"]
        singles = [cell["arms"][arm] for arm in eligible]
        own.append(number(both["own"] - max(row["own"] for row in singles), "own regret"))
        margin.append(number(both["margin"] - max(row["margin"] for row in singles), "margin regret"))
        lost += RANK[both["outcome"]] < max(RANK[row["outcome"]] for row in singles)
    own_s, margin_s = summary(own, "own regret"), summary(margin, "margin regret")
    out = {
        "seed": seed, "cells": len(rows),
        "own_cash_regret_vs_best_singleton": own_s,
        "margin_regret_vs_best_singleton": margin_s,
        "lost_singleton_outcome_cells": lost,
        "nondominated": own_s["mean"] >= 0 and margin_s["mean"] >= 0 and lost == 0,
    }
    if opponent_name is not None:
        out["opponent"] = opponent_name
    return out


def singleton_rank(cells, arm):
    own = [cell["arms"][arm]["own"] - cell["arms"]["control"]["own"] for cell in cells]
    margin = [cell["arms"][arm]["margin"] - cell["arms"]["control"]["margin"] for cell in cells]
    own_s, margin_s = summary(own, f"{arm} own delta"), summary(margin, f"{arm} margin delta")
    return own_s["mean"], margin_s["mean"], -own_s["negative"]


def assess(parent, *, byte_sha256=None, git_head=None):
    need(isinstance(parent, dict), "parent report must be an object")
    sel, eligible_map, opponents, seeds, cells = validate(parent)
    eligible = [arm for arm in SINGLES if eligible_map[arm]]
    if eligible:
        seed_rows = [cluster([c for c in cells if c["seed"] == seed], eligible, seed) for seed in seeds]
        pair_rows = [
            cluster([c for c in cells if c["seed"] == seed and c["opponent"] == opp], eligible, seed, opp)
            for opp in sorted(opponents) for seed in sorted(seeds)
        ]
        seed_own = summary((row["own_cash_regret_vs_best_singleton"]["mean"] for row in seed_rows), "seed own regret")
        seed_margin = summary((row["margin_regret_vs_best_singleton"]["mean"] for row in seed_rows), "seed margin regret")
        pair_own = summary((row["own_cash_regret_vs_best_singleton"]["mean"] for row in pair_rows), "opponent-seed own regret")
        pair_margin = summary((row["margin_regret_vs_best_singleton"]["mean"] for row in pair_rows), "opponent-seed margin regret")
        tail = {
            "applicable": True, "independent_unit": "seed", "paired_unit": "opponent|seed",
            "eligible_singletons": eligible, "seed_clusters": seed_rows,
            "opponent_seed_clusters": pair_rows,
            "summary": {
                "seed_clusters": len(seed_rows), "opponent_seed_clusters": len(pair_rows),
                "seed_own_regret": seed_own, "seed_margin_regret": seed_margin,
                "opponent_seed_own_regret": pair_own, "opponent_seed_margin_regret": pair_margin,
                "negative_seed_clusters": sum(not row["nondominated"] for row in seed_rows),
                "negative_opponent_seed_clusters": sum(not row["nondominated"] for row in pair_rows),
                "lost_singleton_outcome_cells": sum(row["lost_singleton_outcome_cells"] for row in seed_rows),
            },
        }
        tail["nondominated"] = not (
            tail["summary"]["negative_seed_clusters"]
            or tail["summary"]["negative_opponent_seed_clusters"]
        )
    else:
        tail = {
            "applicable": False, "independent_unit": "seed", "paired_unit": "opponent|seed",
            "eligible_singletons": [], "seed_clusters": [], "opponent_seed_clusters": [],
            "summary": None, "nondominated": True,
        }

    guarded = {
        "verdict": sel["verdict"], "selected_arm": sel["selected_arm"],
        "eligible_against_control": dict(eligible_map),
        "composition_nondominated": sel["composition_nondominated"],
        "parent_verdict": sel["verdict"], "parent_selected_arm": sel["selected_arm"],
        "seed_cluster_guard_applied": sel["selected_arm"] == "both" and bool(eligible),
        "seed_cluster_nondominated": tail["nondominated"], "downgrade_reason": None,
        "promotion_authorized": False, "hosted_leaderboard_claim": False,
    }
    if guarded["selected_arm"] == "both" and tail["applicable"] and not tail["nondominated"]:
        chosen = max(eligible, key=lambda arm: singleton_rank(cells, arm))
        guarded.update({
            "selected_arm": chosen,
            "verdict": "SELECT_OWN_VALUE" if chosen == "own_value" else "SELECT_CERTIFIED_PRESSURE",
            "composition_nondominated": False,
            "downgrade_reason": "NEGATIVE_SEED_OR_OPPONENT_SEED_CLUSTER_REGRET",
        })

    return {
        "schema_version": 1, "operation": OP, "git_head": git_head,
        "parent_gate": {"operation": PARENT_OP, "semantic_sha256": semantic_sha(parent),
                        "byte_sha256": byte_sha256, "git_head": parent.get("git_head")},
        "grid": {"opponents": opponents, "seeds": seeds, "cells_per_arm": len(cells),
                 "independent_unit": "seed", "independent_clusters": len(seeds),
                 "mirrored_seats_collapsed": True, "opponents_collapsed_within_seed": True},
        "seed_cluster_tail": tail, "selection": guarded,
    }


def markdown(report):
    s, tail = report["selection"], report["seed_cluster_tail"]
    lines = ["# TITAN V3 seed-cluster tail guard", "",
             f"- Parent verdict: **{s['parent_verdict']}**", f"- Guarded verdict: **{s['verdict']}**",
             f"- Selected arm: **{s['selected_arm'] or 'none'}**",
             f"- Cluster nondominated: **{s['seed_cluster_nondominated']}**",
             f"- Downgrade reason: **{s['downgrade_reason'] or 'none'}**", ""]
    if tail["applicable"]:
        lines += ["| Seed | Mean own regret | Mean margin regret | Pass |", "|---:|---:|---:|:---:|"]
        for row in tail["seed_clusters"]:
            lines.append(f"| {row['seed']} | {row['own_cash_regret_vs_best_singleton']['mean']:.3f} | "
                         f"{row['margin_regret_vs_best_singleton']['mean']:.3f} | "
                         f"{'yes' if row['nondominated'] else 'no'} |")
    lines += ["", "Mirrored seats are paired inside opponent × seed, then opponents are collapsed "
              "inside each seed. This guard never authorizes promotion or a hosted leaderboard claim."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--head")
    args = parser.parse_args()
    parent, byte_sha = load(args.input)
    report = assess(parent, byte_sha256=byte_sha, git_head=args.head)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    args.markdown.write_text(markdown(report))
    print(json.dumps({"verdict": report["selection"]["verdict"],
                      "selected_arm": report["selection"]["selected_arm"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
