# SPDX-License-Identifier: Apache-2.0
"""Consume RILL's retained four-case report without running a simulator or game."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time

from dated_scenarios import DatedSelector

REPLAY_SHA256 = "22276ac78fc06c99fe6e58e878eed24d9f526b68616c3183f1a48e6ddd1f278c"
ARLENE_SHA256 = "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4"
HAZEL_BLOB = "00abee3c99641eb0ab1729fd80e6f9a5c783f373"
MECHANICS_BLOB = "044a4f9c0a4a44dde10ada57563238bcaf82075d"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blob(path):
    data = Path(path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(replay_path, arlene_path, hazel_path, mechanics_path):
    if digest(replay_path) != REPLAY_SHA256 or digest(arlene_path) != ARLENE_SHA256:
        raise ValueError("Use the exact retained report and original controller source")
    if blob(hazel_path) != HAZEL_BLOB or blob(mechanics_path) != MECHANICS_BLOB:
        raise ValueError("Use the documented existing HAZEL/mechanics sources")
    replay = json.loads(Path(replay_path).read_bytes())
    observation = replay["experiment"]["conditional_observation_226"]
    configuration = {"episodeSteps": 720}
    scenario_ids = ("brunch_future", "yarn_at288")
    arlene = load("completed_arlene", arlene_path)
    hazel = load("completed_hazel", hazel_path)
    mechanics = load("completed_mechanics", mechanics_path)
    # This fresh instance tests the route-selection interface only. The retained
    # replay's progressed controller state is not reconstructed or called here.
    controller = arlene.Agent()
    offers = [hazel.quote_program(key, controller.R[key], observation, configuration, mechanics)
              for key in (hazel.MAIN, hazel.SHEEP)]
    original = deepcopy((observation, controller.__dict__, replay))
    selector = DatedSelector.from_completed_replay(replay, configuration, scenario_ids=scenario_ids)
    outer = hazel.choose_before_action(controller, observation, configuration, mechanics, selector=selector)
    comparison = deepcopy(selector.last_report)
    assert comparison is not None, "existing callback seam did not invoke selector"
    assert comparison["selected"] == controller.cur == hazel.MAIN
    assert comparison["candidates"][hazel.SHEEP]["worst_paired_gain"] == -10903
    assert (observation, controller.__dict__, replay) == original
    differences = {item["name"]: item["routes"][hazel.SHEEP]["final_executed_cash"]
                   - item["routes"][hazel.MAIN]["final_executed_cash"]
                   for item in comparison["scenarios"]}
    assert differences == {"brunch_future": -10903, "yarn_at288": 8574}
    assert all(row["minimum_after_market_cash"] == 23
               for item in comparison["scenarios"] for row in item["routes"].values())
    negative = []
    for mode in ("incomplete", "missing_case", "drop_negative_future", "nonterminal", "wrong_observation"):
        report = deepcopy(replay)
        obs = deepcopy(observation)
        if mode == "incomplete": report["complete"] = False
        elif mode == "missing_case": report["cases"].pop()
        elif mode == "drop_negative_future":
            del report["scenarios"]["brunch_future"]
            report["cases"] = [c for c in report["cases"] if c["scenario_id"] == "yarn_at288"]
        elif mode == "nonterminal": report["end_step"] = 287
        else: obs["farms"][int(obs["player"])]["money"] += 1
        candidate = DatedSelector.from_completed_replay(report, configuration, scenario_ids=scenario_ids)
        assert candidate(offers, obs) == hazel.MAIN
        assert candidate.last_report["reason"] == "execution_report_invalid"
        negative.append({"case": mode, "reason": candidate.last_report["invalid_input"]})
    # Positive-only is an explicitly changed hypothetical bank, NOT a statement
    # that this future was known at226, and not used in the two-column decision.
    positive = deepcopy(replay)
    positive["scenarios"] = {"yarn_at288": positive["scenarios"]["yarn_at288"]}
    positive["cases"] = [c for c in positive["cases"] if c["scenario_id"] == "yarn_at288"]
    positive_selector = DatedSelector.from_completed_replay(positive, configuration,
                                                          scenario_ids=("yarn_at288",))
    assert positive_selector(offers, observation) == hazel.SHEEP
    elapsed = []
    for _ in range(50):
        before = time.perf_counter()
        selector(offers, observation)
        elapsed.append((time.perf_counter() - before) * 1000)
    return {
        "schema": "date.completed-physical-consumer-check.v1",
        "scope": "retained_conditional_report_consumption_not_new_simulation_or_game",
        "pins": {"replay_sha256": REPLAY_SHA256, "arlene_sha256": ARLENE_SHA256,
                 "hazel_blob": HAZEL_BLOB, "mechanics_blob": MECHANICS_BLOB,
                 "dated_selector_sha256": digest(Path(__file__).with_name("dated_scenarios.py")),
                 "input_bridge_sha256": digest(Path(__file__).with_name("physical_outcomes.py"))},
        "comparison": comparison, "paired_cash_differences": differences,
        "outer_choice": outer["after"], "existing_selector_seam_calls": 1,
        "reconciled_recorded_market_queues": sum(len(c["market_rows"]) for c in replay["cases"]),
        "negative_controls": negative,
        "explicit_positive_only_control": {"selected": positive_selector.last_report["selected"],
            "worst_paired_gain": positive_selector.last_report["candidates"][hazel.SHEEP]["worst_paired_gain"],
            "scope": "hypothetical_changed_bank_not_a_known_future"},
        "benchmark": {"iterations": 50, "median_ms": statistics.median(elapsed), "max_ms": max(elapsed),
            "scope": "existing_report_validation_and_ranking_only_no_imports_quoting_or_simulation"},
        "new_simulator_calls": 0, "new_game_seeds": [], "new_games": 0, "parent_action_calls": 0,
        "limits": ["RILL's own-state conditional model, not interactive rival trading or real HAZEL226 states.",
                   "Minimum is after whole queues plus initial cash, not an intra-queue trough or full-fill certificate.",
                   "Source-seam binding uses a fresh test instance, not reconstruction of the progressed source controller.",
                   "No calibrated scenario probability, win utility, default change or whole-agent timing claim."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("replay", "arlene", "hazel", "mechanics", "output"):
        parser.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args()
    result = run(args.replay, args.arlene, args.hazel, args.mechanics)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: result[key] for key in ("paired_cash_differences", "negative_controls", "benchmark",
                     "reconciled_recorded_market_queues", "new_simulator_calls")}, indent=2))
