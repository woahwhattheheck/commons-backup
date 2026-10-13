# SPDX-License-Identifier: Apache-2.0
"""Check recursive event-prefix reuse against six already-saved physical worlds.

This command restores the existing DELVE226 integrated actor, executes one new
multi-world conditional model, and compares every complete case with immutable
RILL/ADMISSION saved outputs. It runs no games and initializes no game seed.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys
from time import perf_counter

from check_prefix_reuse import blob, load, setup

HERE = Path(__file__).resolve().parent
VISIBLE = (288, 360, 432, 504, 576)


def identity(path):
    path = Path(path)
    body = path.read_bytes()
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            "git_blob": hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest()}


def verify_manifest(root, name):
    root = Path(root).resolve()
    manifest = json.loads((root / name).read_text(encoding="utf-8"))
    for member, expected in manifest.items():
        path = (root / member).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Manifest member escapes package: " + member)
        got = identity(path)
        if got["bytes"] != expected["bytes"] or got["sha256"] != expected["sha256"]:
            raise ValueError("Manifest member differs: " + member)
        if "git_blob" in expected and got["git_blob"] != expected["git_blob"]:
            raise ValueError("Manifest Git blob differs: " + member)
    return len(manifest)


def scenario_from_doc(oracle, document):
    return oracle.Scenario(**{
        key: ({int(step): value for step, value in values.items()}
              if key != "label" else values)
        for key, values in document.items()
    })


def restore_actor(c):
    root = c.root
    runtime = root / "original-runtime/revenue/kaggriculture"
    sys.path[:0] = [str(runtime / "cloud-integration-differentials"),
                    str(runtime / "cloud-execution-lab")]
    restore = load("prism_tree_restore", root / "work/revenue/kaggriculture/cloud-capital-physical-replay/reached_integrated.py")
    tail = load("prism_tree_tail", root / "titan-joint-sell-tail-value-evidence-20260907/source/sell_tail_value.py")
    factory = load("prism_tree_factory", runtime / "cloud-integration-differentials/funded_main.py")
    random.seed(restore.ACTOR_SEED)
    actor = factory.make_agent(funded=False)
    raw = gzip.decompress((root / "TITAN-TRACE-DELVE-control-inputs/candidate-inputs.jsonl.gz").read_bytes())
    rows = [json.loads(line) for line in raw.splitlines()]
    row, receipt = restore.restore_prefix(actor, rows)
    facade = tail.SellRouteView(actor, row["configuration"])

    def fork(view):
        return tail.SellRouteView(restore.fork_integrated(view.scheduler), view.configuration)

    return restore, actor, facade, fork, row, receipt


def saved_inputs(c, arrival_root):
    scenarios = {}
    expected = {}
    original = c.reference["replay"]
    for scenario_id in ("observed_shops_continue_no_rival", "hypothetical_yarn_288_no_rival"):
        scenarios[scenario_id] = scenario_from_doc(c.oracle, original["scenarios"][scenario_id])
    for case in original["cases"]:
        expected[(case["offered_route"], case["scenario_id"])] = case

    arrival_root = Path(arrival_root).resolve()
    later = arrival_root / "results/later-arrivals"
    for visible in VISIBLE[1:]:
        scenario_id = f"hypothetical_yarn_{visible}_no_rival"
        docs = []
        for path in sorted(later.glob(f"yarn-{visible}-*.json.gz")):
            payload = json.loads(gzip.decompress(path.read_bytes()))
            docs.append(payload["scenario"])
            case = payload["replay"]["cases"][0]
            expected[(case["offered_route"], case["scenario_id"])] = case
        if len(docs) != 2 or docs[0] != docs[1]:
            raise ValueError(f"Saved scenario {visible} is missing or inconsistent")
        scenarios[scenario_id] = scenario_from_doc(c.oracle, docs[0])
    return scenarios, expected


def normalized(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def run(rill_root, arrival_root, seconds):
    verified = {
        "rill_manifest_members": verify_manifest(rill_root, "SHA256-MANIFEST.json"),
        "arrival_manifest_members": verify_manifest(arrival_root, "MANIFEST.json"),
    }
    c = setup(rill_root)
    restore, actor, facade, fork, row, restoration = restore_actor(c)
    scenarios, expected = saved_inputs(c, arrival_root)
    route_ids = (restore.MAIN, restore.SHEEP)
    if len(expected) != len(route_ids) * len(scenarios):
        raise ValueError("Saved case bank is incomplete")
    actor_before = restore.state_digest(actor)
    row_before = deepcopy(row)
    segment_calls = []

    def observed_simulate(*args, **kwargs):
        begun = perf_counter()
        start_step = int(args[1]["step"])
        segment = c.oracle.simulate_bundle(*args, **kwargs)
        record = {
            "start_step": start_step,
            "end_step": int(kwargs["end_step"]),
            "scenario_label": kwargs["scenario"].label,
            "wall_seconds": perf_counter() - begun,
        }
        segment_calls.append(record)
        print("SEGMENT " + json.dumps(record, sort_keys=True), flush=True)
        return segment

    result = c.current.replay_routes(
        facade, route_ids, row["observation"], row["configuration"],
        c.engine, observed_simulate, scenarios=scenarios, end_step=718,
        fork_controller=fork, limits=c.current.ReplayLimits(seconds=seconds, decisions=5916),
        reuse_scenario_prefixes=True)
    comparisons = []
    for case in result["cases"]:
        key = case["offered_route"], case["scenario_id"]
        comparisons.append({
            "offered_route": key[0], "scenario_id": key[1],
            "status": case["status"], "final_cash": case.get("final_cash"),
            "same_complete_case": normalized(case) == expected[key],
        })
    meta = result.get("prefix_reuse", {})
    invariants = {
        "complete": result["complete"],
        "all_saved_cases_equal": all(item["same_complete_case"] for item in comparisons),
        "decisions_executed_expected_3866": result["decisions_executed"] == 3866,
        "reused_decisions_expected_2050": meta.get("reused_decisions") == 2050,
        "branch_steps_exact": meta.get("branch_steps") == [287, 359, 431, 503, 575],
        "prefixes_computed_expected_10": meta.get("prefixes_computed") == 10,
        "actor_unchanged": restore.state_digest(actor) == actor_before,
        "input_unchanged": row == row_before,
    }
    output = {
        "schema": "titan.event-prefix-tree-validation.v1",
        "scope": "six existing conditional own-state worlds; no games, seeds, rival utility or policy selection",
        "verified_inputs": verified,
        "source": {
            "candidate": identity(HERE / "physical_replay.py"),
            "flat_prefix_reference": identity(Path(rill_root).resolve().parent / "osprey/source/physical_replay.py")
                if (Path(rill_root).resolve().parent / "osprey/source/physical_replay.py").exists() else None,
            "engine_sha256": c.engine_hashes,
        },
        "restoration": restoration,
        "scenario_order": list(scenarios),
        "comparisons": comparisons,
        "invariants": invariants,
        "new_full_games": 0,
        "game_seeds_initialized": [],
        "selection": None,
        "segment_calls": segment_calls,
        "replay": result,
    }
    if not all(invariants.values()):
        output["validation_failed"] = True
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rill-evidence", type=Path, required=True)
    parser.add_argument("--arrival-evidence", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=240.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a fresh output file")
    result = run(args.rill_evidence, args.arrival_evidence, args.seconds)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "invariants": result["invariants"],
        "decisions_executed": result["replay"]["decisions_executed"],
        "wall_seconds": result["replay"]["wall_seconds"],
        "prefix_reuse": result["replay"]["prefix_reuse"],
        "comparisons": result["comparisons"],
    }, indent=2, allow_nan=False))
    return int(bool(result.get("validation_failed")))


if __name__ == "__main__":
    raise SystemExit(main())
