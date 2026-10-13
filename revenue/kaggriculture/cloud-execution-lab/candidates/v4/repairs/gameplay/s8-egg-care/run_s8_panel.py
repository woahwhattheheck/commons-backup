#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the independent S8 native-shadow and reachable-service field panel.

The complete plan is persisted before any game executes. Native shadow is not a
fitness comparison. Positive fixture deltas are not native/hosted strength claims.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

import materialize_s8_field as materialize
import run_s8_field as field

REGIMES = {"native_shadow": ("off", "spread_or_discard"),
           "grower": ("off", "donor", "spread_or_discard"),
           "disposal": ("off", "donor", "spread", "discard", "spread_or_discard")}


def pair(base, candidate):
    for key in ("seed", "seat", "configuration_overrides", "configuration", "opponent", "engine_sha256", "kind"):
        if base[key] != candidate[key]:
            raise ValueError("Noncomparable field pair: " + key)
    if any(row["status"] != "complete" or row["steps"] != 719 for row in (base, candidate)):
        return {"complete": False, "seed": base["seed"], "seat": base["seat"]}
    seat = base["seat"]
    if type(seat) is not int or seat not in (0, 1):
        raise ValueError("Invalid seat")
    for row in (base, candidate):
        scores = row["scores"]
        if not isinstance(scores, list) or len(scores) != 2 or any(
                type(n) not in (int, float) or not math.isfinite(n) for n in scores):
            raise ValueError("Invalid completed-game cash scores")
        receipt = row["helper"]
        if (not isinstance(receipt, dict) or receipt.get("calls") != 719
                or type(receipt.get("transformed_actions")) is not int
                or not 0 <= receipt["transformed_actions"] <= 719):
            raise ValueError("Invalid completed-game helper receipt")
    own = candidate["scores"][seat] - base["scores"][seat]
    rival = candidate["scores"][1-seat] - base["scores"][1-seat]
    before, after = base["census"]["effects"], candidate["census"]["effects"]
    return {"complete": True, "seed": base["seed"], "seat": seat,
            "delta_own": own, "delta_rival": rival, "delta_margin": own-rival,
            "same_action_trace": base["action_sha256"] == candidate["action_sha256"],
            "same_world_trace": base["world_sha256"] == candidate["world_sha256"],
            "helper_proposals": candidate["helper"]["transformed_actions"],
            "first_proposal_step": candidate["helper"]["first_change_step"],
            "effects_delta": {key: after.get(key, 0)-before.get(key, 0)
                              for key in sorted(set(before) | set(after))}}


def run(archive, sources, output, seeds):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    plan = {"schema": "titan.s8.henhouse.plan.v1", "seeds": seeds,
            "seed_status": "predeclared for this panel; no global holdout claim",
            "cells": [{"kind": kind, "mode": mode, "seed": seed, "seat": seat}
                      for kind, modes in REGIMES.items() for mode in modes
                      for seed in seeds for seat in (0, 1)],
            "configuration_overrides": {"disposal": {"startingMoney": 10000}},
            "runner_source_sha256": {name: field.sha256(Path(__file__).parent / name)
                                     for name in ("run_s8_field.py", "run_s8_panel.py", "reachable_goose.py", "materialize_s8_field.py")},
            "source_git_blobs": materialize.PINS,
            "helper_sha256": materialize.GENERATED_SHA256,
            "reference_archive_sha256": materialize.ARCHIVE_SHA256}
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    games, packages, runtimes = [], {}, {}
    for kind, modes in REGIMES.items():
        for mode in modes:
            label = kind + "-" + mode
            root = output / "packages" / label
            report = output / "telemetry" / (label + ".json")
            manifest = materialize.build(archive, sources, root, report, kind=kind, mode=mode)
            hashes = field.package_hashes(root)
            digest = hashlib.sha256(field.encoded(hashes)).hexdigest()
            packages[label] = {"manifest": manifest, "files": hashes, "package_sha256": digest}
            runtimes[(kind, mode)] = (root, report, digest)
    (output / "packages.json").write_text(json.dumps(packages, indent=2) + "\n")
    index = {}
    for cell in plan["cells"]:
        kind, mode, seed, seat = (cell[k] for k in ("kind", "mode", "seed", "seat"))
        root, report, digest = runtimes[(kind, mode)]
        report.unlink(missing_ok=True)
        name = f"{kind}-{mode}-{seed}-{seat}"
        game = field.play(root, seed, seat, output / "games" / name,
                          entry=str(root / "henhouse_entry.py"),
                          configuration=plan["configuration_overrides"].get(kind, {}),
                          expected_package_sha256=digest)
        game.update(kind=kind, mode=mode)
        if report.exists():
            game["helper"] = json.loads(report.read_text())
        else:
            game["helper"] = None
        if game["status"] == "complete" and (game["helper"] is None or game["helper"]["calls"] != 719):
            game.update(status="failed", failure={"kind": "missing_or_incomplete_helper_receipt"})
        (output / "games" / name / "game.json").write_text(json.dumps(game, indent=2) + "\n")
        games.append(game); index[(kind, mode, seed, seat)] = game
        print(json.dumps({**cell, "status": game["status"], "scores": game["scores"],
                          "proposals": None if game["helper"] is None else game["helper"]["transformed_actions"]}), flush=True)
    comparisons = {}
    for kind, modes in REGIMES.items():
        for mode in modes[1:]:
            rows = [pair(index[(kind, "off", seed, seat)], index[(kind, mode, seed, seat)])
                    for seed in seeds for seat in (0, 1)]
            valid = [r for r in rows if r["complete"]]
            # Seats share environment seeds; do not treat mirrored seats as IID.
            blocks = [statistics.mean(r["delta_margin"] for r in valid if r["seed"] == seed)
                      for seed in seeds if sum(r["seed"] == seed for r in valid) == 2]
            comparisons[kind + ":" + mode] = {
                "fitness_comparison": kind != "native_shadow",
                "native_promotion_evidence": False,
                "planned_pairs": len(rows), "completed_pairs": len(valid),
                "seed_block_count": len(blocks),
                "mean_seed_block_delta_margin": statistics.mean(blocks) if blocks else None,
                "min_seed_block_delta_margin": min(blocks) if blocks else None,
                "max_seed_block_delta_margin": max(blocks) if blocks else None,
                "engaged_pairs": sum(r["helper_proposals"] > 0 for r in valid),
                "rows": rows}
    result = {"schema": "titan.s8.henhouse.panel.v1", "plan_sha256": field.sha256(output / "plan.json"),
              "planned_games": len(plan["cells"]), "completed_games": sum(g["status"] == "complete" for g in games),
              "comparisons": comparisons,
              "limits": ["Native mode returns unchanged native actions and measures proposals only.",
                         "Fixture modes are legal constructed service regimes, not TITAN strategies.",
                         "Disposal fixture uses explicitly paired startingMoney10000.",
                         "No hosted score, global holdout, native activation or general strength claim."]}
    (output / "panel.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sources", type=Path, default=Path(__file__).parent)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", default="1,17,101,2027,6607,104729")
    args = parser.parse_args()
    seeds = [int(x) for x in args.seeds.split(",")]
    if not seeds or len(seeds) != len(set(seeds)):
        parser.error("Seeds must be a nonempty distinct list")
    result = run(args.archive, args.sources, args.output, seeds)
    return int(result["completed_games"] != result["planned_games"])


if __name__ == "__main__":
    raise SystemExit(main())
