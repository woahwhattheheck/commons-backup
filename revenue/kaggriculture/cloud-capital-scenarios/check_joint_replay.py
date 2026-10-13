# SPDX-License-Identifier: Apache-2.0
"""Consume JOINT's eight saved SELL-tail cases without an actor or simulator.

The referenced cases start from PRISM's retained step577 observation and use
explicit own-state scenarios, not actual future opponent actions. New runtime
execution here is input validation and ranking only.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

if os.environ.get("DATE_RUNTIME_ROOT"):
    sys.path.insert(0, os.environ["DATE_RUNTIME_ROOT"])

import dated_scenarios
import physical_outcomes
from dated_scenarios import DatedSelector

REPORT_SHA256 = "e71c0519fba8968fa25e554b4b1321256648b0c8438663146cd8b6ea370d917f"
INPUT_SHA256 = "fb9c5b388ee21dd9cb541e036b311723a056de4c132c360195a42b2dab6abbfb"
SCENARIOS = (
    "known_shops_no_external_flow", "external_milk_one_per_step",
    "external_wheat_one_per_step", "external_strawberry_one_per_step",
)
EXPECTED = dict(zip(SCENARIOS, (-1760, -2356, -1651, -1297)))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_pinned(path: Path, expected: str):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"Source identity mismatch: {path.name}")
    return json.loads(data)


def evaluate(replay, observation, config, offers):
    selector = DatedSelector.from_completed_replay(replay, config, scenario_ids=SCENARIOS)
    selected = selector(offers, observation)
    return selected, selector.last_report


def run(report_path: Path, input_path: Path) -> dict:
    joint = read_pinned(report_path, REPORT_SHA256)
    original_input = read_pinned(input_path, INPUT_SHA256)
    if joint["validation"]["input_file"]["sha256"] != INPUT_SHA256:
        raise ValueError("JOINT report names another player input")
    observation = original_input["observation"]
    replay = joint["replay"]
    config = joint["validation"]["configuration"]
    incumbent, alternative = joint["incumbent"], "7015cc00acfa4922"
    offers = [{"route_id": incumbent}, {"route_id": alternative}]
    before = deepcopy((joint, original_input, config, offers))
    chosen, explicit = evaluate(replay, observation, config, offers)
    if chosen != incumbent or explicit["reason"] != "no_covered_improvement":
        raise AssertionError("Explicit original-input comparison changed")
    deltas = {row["name"]: row["routes"][alternative]["final_executed_cash"]
              - row["routes"][incumbent]["final_executed_cash"]
              for row in explicit["scenarios"]}
    if deltas != EXPECTED:
        raise AssertionError("Retained paired values disagree")
    independent_deltas = {c["scenario_id"]: c["terminal_own_cash_delta"]
                          for c in joint["comparisons"] if c["route"] == alternative}
    if deltas != independent_deltas:
        raise AssertionError("DATE disagrees with JOINT's existing paired results")
    omitted = {k: v for k, v in config.items() if k != "episodeSteps"}
    configurations = {"explicit_original": config, "omitted_horizon": omitted,
                      "minimal_explicit": {"episodeSteps": 720}, "default_empty": {}}
    comparisons = {}
    for name, cfg in configurations.items():
        started = time.perf_counter()
        _, result = evaluate(replay, observation, cfg, offers)
        comparisons[name] = {"equals_explicit": result == explicit,
                             "comparison": result,
                             "validation_seconds": time.perf_counter() - started}
    faults = []
    for name in ("missing_case", "removed_scenario", "short_horizon", "foreign_observation", "cash_delta"):
        changed, obs = deepcopy(replay), deepcopy(observation)
        if name == "missing_case":
            changed["cases"].pop()
        elif name == "removed_scenario":
            del changed["scenarios"][SCENARIOS[1]]
            changed["cases"] = [c for c in changed["cases"] if c["scenario_id"] != SCENARIOS[1]]
        elif name == "short_horizon":
            changed["end_step"] -= 1
        elif name == "foreign_observation":
            obs["farms"][int(obs["player"])]["money"] += 1
        else:
            changed["cases"][0]["market_rows"][0]["cash_delta"] += 1
        expected_choice, expected = evaluate(changed, obs, {"episodeSteps": 720}, offers)
        choice, actual = evaluate(changed, obs, {}, offers)
        faults.append({"name": name, "explicit_reason": expected.get("invalid_input"),
                       "default_reason": actual.get("invalid_input"),
                       "preserves_explicit_result": actual == expected,
                       "retains_incumbent": choice == expected_choice == incumbent})
    if (joint, original_input, config, offers) != before:
        raise AssertionError("Original source inputs were modified")
    success = all(c["equals_explicit"] for c in comparisons.values()) and all(
        f["preserves_explicit_result"] and f["retains_incumbent"] for f in faults)
    return {
        "schema": "date.joint-default-horizon-check.v1", "success": success,
        "inputs": {"joint_report_sha256": REPORT_SHA256, "prism_input_sha256": INPUT_SHA256},
        "runtime": {"dated_scenarios_sha256": file_hash(Path(dated_scenarios.__file__)),
                    "physical_outcomes_sha256": file_hash(Path(physical_outcomes.__file__))},
        "scenario_deltas": deltas, "comparisons": comparisons, "fault_controls": faults,
        "retained_route_scenario_cases": len(replay["cases"]),
        "retained_market_queue_rows": sum(len(c["market_rows"]) for c in replay["cases"]),
        "input_unchanged": True, "new_simulator_calls": 0, "new_parent_calls": 0,
        "new_games": 0, "new_seeds": [],
        "limits": [
            "Consumes JOINT's conditional full-SELL outcomes; no rerun or new game evidence.",
            "Initial step577 input is retained PRISM data; future flows remain explicit hypotheses.",
            "Empty config tests default horizon interpretation, not reconstruction with a different configuration.",
            "Own cash is not rival margin or win probability; no canonical TITAN release is changed.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.report, args.input)
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "success", "scenario_deltas", "retained_route_scenario_cases", "retained_market_queue_rows",
        "new_simulator_calls", "new_games")}, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
