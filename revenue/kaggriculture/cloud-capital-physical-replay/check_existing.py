# SPDX-License-Identifier: Apache-2.0
"""Run the real existing Arlene/T04/engine join on a retained own observation."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from physical_replay import ReplayLimits, replay_routes


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def blob(path):
    b = Path(path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()


def run(source_root, oracle_path, engine_root, observation_path, end_step=260):
    source_root, engine_root = Path(source_root), Path(engine_root)
    arlene_path = source_root / "cloud-frontier-policy/next-panel/vendor/arlene.py"
    arlene_bytes = arlene_path.read_bytes()
    if hashlib.sha256(arlene_bytes).hexdigest() != "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4":
        raise ValueError("Expected the documented original Arlene source")
    if blob(oracle_path) != "49640c27862d3d132c828fbafc6a8b4957527736":
        raise ValueError("Expected the documented existing T04 oracle")
    evaluator = load(source_root / "cloud-eval/evaluate.py", "rill_eval")
    engine, engine_hashes = evaluator.get_engine(engine_root)
    oracle = load(oracle_path, "rill_oracle")
    arlene = load(arlene_path, "rill_arlene")
    document = json.loads(Path(observation_path).read_text())
    obs = document.get("observation", document)
    configuration = {k: v.get("default") if isinstance(v, dict) else v
                     for k, v in engine.specification["configuration"].items()}
    configuration["seed"] = None
    original = arlene.Agent()
    original_state = deepcopy(original.__dict__)
    obs_before = deepcopy(obs)
    scenarios = {"observed_shops_only": oracle.Scenario()}
    report = replay_routes(original, [arlene.MAIN, "dc76e4003029ac51"], obs,
                           configuration, engine, oracle.simulate_bundle,
                           scenarios=scenarios, end_step=end_step,
                           limits=ReplayLimits(seconds=30))
    if not report["complete"]:
        raise AssertionError([(c["status"], c.get("reason")) for c in report["cases"]])
    comparisons = []
    for case in report["cases"]:
        independent = deepcopy(original)
        independent.cur = case["offered_route"]
        expected = oracle.simulate_bundle(engine, obs, configuration, independent.act,
                                          end_step=end_step, scenario=scenarios[case["scenario_id"]],
                                          record_actions=True)
        if case["result"] != expected:
            raise AssertionError("Delegated physical outcome changed")
        comparisons.append({"route": case["offered_route"],
                            "all_delegated_fields_match": True,
                            "cash_gain": case["cash_gain"],
                            "final_cash": case["final_cash"],
                            "decision_count": len(case["active_routes"]),
                            "minimum_after_market_cash": case["minimum_after_market_cash"]})
    if original.__dict__ != original_state or obs != obs_before:
        raise AssertionError("Live producer or input observation was changed")
    report["validation"] = {
        "comparisons": comparisons, "original_controller_unchanged": True,
        "observation_unchanged": True, "engine_sha256": engine_hashes,
        "oracle_git_blob": blob(oracle_path), "arlene_git_blob": blob(arlene_path),
        "observation_file_sha256": hashlib.sha256(Path(observation_path).read_bytes()).hexdigest(),
        "input": "existing T10 decision121 own observation; not HAZEL226 or a new full game",
    }
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source-root", required=True)
    p.add_argument("--oracle", required=True)
    p.add_argument("--engine-root", required=True)
    p.add_argument("--observation", required=True)
    p.add_argument("--end-step", type=int, default=260)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    report = run(args.source_root, args.oracle, args.engine_root, args.observation, args.end_step)
    Path(args.output).write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps(report["validation"], indent=2))
