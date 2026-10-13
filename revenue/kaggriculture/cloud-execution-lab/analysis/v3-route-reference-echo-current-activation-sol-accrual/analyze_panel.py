# SPDX-License-Identifier: Apache-2.0
"""Fail-closed comparison for the route-reference-echo activation panel."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics

from panel_evidence import (
    OPERATION, EvidenceError, action_steps, activation_events, index, mean,
    outcome, scores, sign_tail,
)


def analyze(control, candidate):
    controls, candidates = index(control, "control"), index(candidate, "candidate")
    if set(controls) != set(candidates):
        raise EvidenceError("control/candidate schedules differ")
    rows = []
    for key in sorted(controls):
        base, repair = controls[key], candidates[key]
        base_actions = action_steps(base, "control", key)
        repair_actions = action_steps(repair, "candidate", key)
        if len(base_actions) != len(repair_actions):
            raise EvidenceError(f"action lengths differ {key}")
        first = next((i for i, pair in enumerate(zip(base_actions, repair_actions))
                      if pair[0] != pair[1]), None)
        own0, rival0, margin0 = scores(base, "control", key)
        own1, rival1, margin1 = scores(repair, "candidate", key)
        events = activation_events(repair, key)
        if base.get("candidate_agent_evidence") != []:
            raise EvidenceError(f"control emitted candidate evidence {key}")
        if (own0, rival0) != (own1, rival1) and first is None:
            raise EvidenceError(f"score changed without action change {key}")
        rows.append({
            "opponent": key[0], "seed": key[1], "seat": key[2],
            "activation_count": len(events), "activations": events,
            "action_changed": first is not None,
            "first_action_divergence_step": first,
            "control_own": own0, "candidate_own": own1,
            "own_delta": own1 - own0,
            "control_rival": rival0, "candidate_rival": rival1,
            "rival_delta": rival1 - rival0,
            "control_margin": margin0, "candidate_margin": margin1,
            "margin_delta": margin1 - margin0,
            "control_outcome": outcome(margin0),
            "candidate_outcome": outcome(margin1),
        })

    events = sum(row["activation_count"] for row in rows)
    activated = sum(row["activation_count"] > 0 for row in rows)
    action_cells = sum(row["action_changed"] for row in rows)
    score_cells = sum((row["own_delta"], row["rival_delta"]) != (0, 0) for row in rows)
    own = [row["own_delta"] for row in rows]
    rival = [row["rival_delta"] for row in rows]
    margins = [row["margin_delta"] for row in rows]
    positive, negative = sum(v > 0 for v in own), sum(v < 0 for v in own)
    transitions = Counter(f'{r["control_outcome"]}->{r["candidate_outcome"]}' for r in rows)
    new_losses = sum(r["control_outcome"] != "loss" and r["candidate_outcome"] == "loss" for r in rows)
    lost_wins = sum(r["control_outcome"] == "win" and r["candidate_outcome"] != "win" for r in rows)

    grouped, seeds = defaultdict(list), defaultdict(list)
    for row in rows:
        grouped[(row["opponent"], row["seat"])].append(row)
        seeds[row["seed"]].append(row)
    strata = {
        f"{opponent}/seat{seat}": {
            "cells": len(group),
            "activated_cells": sum(r["activation_count"] > 0 for r in group),
            "action_changed_cells": sum(r["action_changed"] for r in group),
            "mean_own_delta": mean(r["own_delta"] for r in group),
            "mean_margin_delta": mean(r["margin_delta"] for r in group),
            "minimum_own_delta": min(r["own_delta"] for r in group),
        }
        for (opponent, seat), group in sorted(grouped.items())
    }
    seed_effects = {
        str(seed): {
            "cells": len(group),
            "activated_cells": sum(r["activation_count"] > 0 for r in group),
            "own_delta_sum": sum(r["own_delta"] for r in group),
            "margin_delta_sum": sum(r["margin_delta"] for r in group),
        }
        for seed, group in sorted(seeds.items())
    }
    seed_values = [entry["own_delta_sum"] for entry in seed_effects.values()]
    seed_positive = sum(value > 0 for value in seed_values)
    seed_negative = sum(value < 0 for value in seed_values)
    gates = {
        "natural_normalization_activated": events > 0,
        "returned_action_activated": action_cells > 0,
        "score_changes_action_bound": True,
        "positive_mean_own": mean(own) > 0,
        "positive_mean_margin": mean(margins) > 0,
        "no_new_losses": new_losses == 0,
        "no_lost_wins": lost_wins == 0,
        "nonnegative_opponent_seat_mean_own": all(
            entry["mean_own_delta"] >= 0 for entry in strata.values()),
    }
    advance = all(gates[name] for name in (
        "positive_mean_own", "positive_mean_margin", "no_new_losses",
        "no_lost_wins", "nonnegative_opponent_seat_mean_own"))
    regressed = (mean(own) < 0 or mean(margins) < 0 or new_losses or lost_wins or
                 not gates["nonnegative_opponent_seat_mean_own"])
    verdict = ("NO_NATURAL_ACTIVATION" if not events else
               "STATE_ONLY_ACTIVATION" if not action_cells else
               "ADVANCE" if advance else "REGRESSION" if regressed else
               "MIXED_MORE_EVIDENCE")
    return {
        "schema_version": 1, "operation": OPERATION, "verdict": verdict,
        "promotion_authorized": False, "hosted_leaderboard_claim": False,
        "cells": len(rows),
        "activation": {
            "events": events, "activated_cells": activated,
            "action_changed_cells": action_cells, "score_changed_cells": score_cells,
            "removed_quantity": sum(e["removed_quantity"] for r in rows for e in r["activations"]),
        },
        "overall": {
            "mean_own_delta": mean(own), "median_own_delta": statistics.median(own),
            "mean_rival_delta": mean(rival), "mean_margin_delta": mean(margins),
            "minimum_own_delta": min(own), "maximum_own_delta": max(own),
            "positive_zero_negative_cells": [positive, len(own)-positive-negative, negative],
            "cell_sign_tail_descriptive_only": sign_tail(positive, negative),
            "new_losses": new_losses, "lost_wins": lost_wins,
            "outcome_transitions": dict(sorted(transitions.items())),
        },
        "seed_cluster": {
            "effects": seed_effects,
            "positive_zero_negative_seeds": [
                seed_positive, len(seed_values)-seed_positive-seed_negative, seed_negative],
            "sign_tail_descriptive_only": sign_tail(seed_positive, seed_negative),
        },
        "strata": strata, "gates": gates, "rows": rows,
    }


def markdown(report):
    activation, overall = report["activation"], report["overall"]
    return "\n".join([
        "# Route-reference echo current-activation panel", "",
        f"**Verdict: `{report['verdict']}`**", "",
        f"- Cells: {report['cells']}",
        f"- Natural events / activated cells: {activation['events']} / {activation['activated_cells']}",
        f"- Action-changed / score-changed cells: {activation['action_changed_cells']} / {activation['score_changed_cells']}",
        f"- Removed echo quantity: {activation['removed_quantity']}",
        f"- Mean own / rival / margin delta: {overall['mean_own_delta']:.3f} / {overall['mean_rival_delta']:.3f} / {overall['mean_margin_delta']:.3f}",
        f"- Positive / zero / negative cells: {overall['positive_zero_negative_cells']}",
        f"- New losses / lost wins: {overall['new_losses']} / {overall['lost_wins']}", "",
        "Offline official-interpreter evidence only; no promotion, provider mutation, Kaggle upload, or leaderboard claim.", "",
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(json.loads(args.control.read_text()), json.loads(args.candidate.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n")
    args.markdown.write_text(markdown(report))
    print(json.dumps({"verdict": report["verdict"], **report["activation"], **report["overall"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
