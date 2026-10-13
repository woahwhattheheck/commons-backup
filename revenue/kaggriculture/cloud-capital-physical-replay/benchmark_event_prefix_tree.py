# SPDX-License-Identifier: Apache-2.0
"""Alternating flat-prefix and recursive-tree timings on unchanged native T04."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
from statistics import median
import time

from check_prefix_reuse import blob, load, setup
from test_prefix_reuse import Controller


def run(rill_root, flat_source, repetitions=7):
    c = setup(rill_root)
    flat = load("prism_event_flat_reference", flat_source)
    obs = deepcopy(c.obs)
    obs.update(step=22, day=0, hour=22)
    cfg = deepcopy(c.cfg)
    cfg["episodeSteps"] = 80
    actor = Controller(switch=23)
    scenarios = {"none": c.oracle.Scenario(label="none")}
    for step in (24, 36, 48, 60):
        scenarios[f"at-{step}"] = c.oracle.Scenario(
            new_shops={step: ("YARN_STORE",)}, label=f"first event {step}")
    rows = []
    reference = None
    for repetition in range(repetitions):
        order = (("flat", flat), ("tree", c.current))
        if repetition % 2:
            order = tuple(reversed(order))
        for name, module in order:
            started = time.perf_counter()
            report = module.replay_routes(
                actor, ("main", "other"), obs, cfg, c.engine,
                c.oracle.simulate_bundle, scenarios=scenarios, end_step=70,
                limits=module.ReplayLimits(seconds=30, decisions=2000),
                reuse_scenario_prefixes=True)
            elapsed = time.perf_counter() - started
            if not report["complete"]:
                raise AssertionError(report)
            if reference is None:
                reference = deepcopy(report["cases"])
            if report["cases"] != reference:
                raise AssertionError("Flat/tree case output differs")
            rows.append({
                "repetition": repetition, "implementation": name,
                "wall_seconds": elapsed,
                "reported_wall_seconds": report["wall_seconds"],
                "decisions_executed": report["decisions_executed"],
                "same_all_case_fields": True,
                "prefix_reuse": report["prefix_reuse"],
            })
    if actor.calls != 0:
        raise AssertionError("Live controller was called")
    medians = {name: median(row["wall_seconds"] for row in rows
                            if row["implementation"] == name)
               for name in ("flat", "tree")}
    return {
        "schema": "titan.event-prefix-tree-benchmark.v1",
        "scope": "constructed 22-70 native T04 workload; two scripted routes x five declared worlds; not game strength or whole-agent latency",
        "sources": {
            "candidate_blob": blob(Path(__file__).with_name("physical_replay.py")),
            "flat_reference_blob": blob(flat_source),
            "engine_sha256": c.engine_hashes,
        },
        "repetitions": repetitions,
        "median_wall_seconds": medians,
        "median_reduction_fraction": 1 - medians["tree"] / medians["flat"],
        "decision_counts": {
            name: sorted({row["decisions_executed"] for row in rows
                          if row["implementation"] == name})
            for name in ("flat", "tree")
        },
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rill-evidence", type=Path, required=True)
    parser.add_argument("--flat-source", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a fresh output file")
    result = run(args.rill_evidence, args.flat_source, args.repetitions)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "median_wall_seconds": result["median_wall_seconds"],
        "median_reduction_fraction": result["median_reduction_fraction"],
        "decision_counts": result["decision_counts"],
    }, indent=2))


if __name__ == "__main__":
    main()
