# SPDX-License-Identifier: Apache-2.0
"""Construct terminal-objective cases using the unchanged official interpreter.

Only deterministic one-action fixture states are executed. No agent, full game,
held seed, provider call, or hidden-state policy is run. Existing source files
are supplied locally; absent files are reported before loading the evaluator.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

from terminal_utility import build_table, solve_terminal

ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
ENGINE_HASHES = {
    "kaggriculture.py": "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e",
    "utils.py": "537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b",
    "kaggriculture.json": "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867",
}
SOLVER_BLOB = "3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute_case(ev, engine, *, player_index, lead, step, extra_scenario=False):
    first = ["SELL", "WHEAT", 2]
    second = ["SELL", "MILK", 2]
    plans = {"delayed": [[], first, second],
             "wheat_first": [first, second], "milk_first": [second, first]}
    scenarios = {
        "wheat17": {"market": [["SELL", "WHEAT", 17], []], "shed": {"WHEAT": 17, "MILK": 0}},
        "milk2_wheat3": {"market": [["SELL", "MILK", 2], ["SELL", "WHEAT", 3]],
                         "shed": {"WHEAT": 3, "MILK": 2}},
    }
    if extra_scenario:
        scenarios["wheat20"] = {"market": [["SELL", "WHEAT", 20]], "shed": {"WHEAT": 20}}
    document = {"plan_ids": list(plans), "scenario_ids": list(scenarios),
                "baseline": "delayed", "receipts": [],
                "source": {"engine_ref": ENGINE_REF, "engine_sha256": ENGINE_HASHES["kaggriculture.py"],
                           "kind": "constructed_one_action_official_interpreter",
                           "player_index": player_index, "step": step, "initial_cash_lead": lead,
                           "initial_common_cash": 100000, "own_shed": {"WHEAT": 2, "MILK": 2},
                           "market_inventory_each": 10000, "plans": plans, "scenarios": scenarios}}
    for plan_id, queue in plans.items():
        for scenario_id, rival in scenarios.items():
            cfg = ev.Struct({k: v.get("default") if isinstance(v, dict) else v
                             for k, v in engine.specification["configuration"].items()})
            cfg.seed = 0  # Initialization of a manufactured state, not a played game seed.
            env = ev.Struct(configuration=cfg, done=False, info={})
            state = [ev.Struct(observation=ev.Struct(), action={}, status="ACTIVE", reward=0)
                     for _ in range(2)]
            engine.interpreter(state, env)
            for actor in state:
                actor.observation.step = step
                actor.observation.day = step // cfg.turnsPerDay
                actor.observation.hour = step % cfg.turnsPerDay
                actor.observation.private["shed"] = {"WHEAT": 2, "MILK": 2}
            state[1-player_index].observation.private["shed"] = copy.deepcopy(rival["shed"])
            farms = state[0].observation.farms
            farms[player_index]["money"] = 100000 + lead
            farms[1-player_index]["money"] = 100000
            own_action = {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(queue)}
            rival_action = {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(rival["market"])}
            state[player_index].action = own_action
            state[1-player_index].action = rival_action
            public_state_hash = digest(state[player_index].observation)
            before = [farms[i]["money"] for i in (player_index, 1-player_index)]
            engine.interpreter(state, env)
            cash = [farms[i]["money"] for i in (player_index, 1-player_index)]
            done = all(s.status == "DONE" for s in state)
            rewards = [state[i].reward for i in (player_index, 1-player_index)] if done else None
            if done:
                assert rewards == cash
            assert done == (step >= cfg.episodeSteps - 2)
            document["receipts"].append({
                "plan": plan_id, "scenario": scenario_id,
                "own_cash": cash[0], "rival_cash": cash[1], "done": done,
                "plan_sha256": digest(own_action),
                "scenario_sha256": digest({"action": rival_action, "initial_private": rival["shed"]}),
                "public_state_sha256": public_state_hash,
                "step": step, "cash_before": before, "official_rewards": rewards,
                "statuses": [s.status for s in state],
                "own_action": own_action, "rival_action": rival_action,
                "remaining_shed": [copy.deepcopy(state[i].observation.private["shed"])
                                   for i in (player_index, 1-player_index)],
            })
    return document


def run(engine_dir, engine_loader, solver_file):
    for name, expected in ENGINE_HASHES.items():
        if hashlib.sha256((engine_dir / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Local engine source differs: " + name)
    solver_bytes = solver_file.read_bytes()
    solver_blob = hashlib.sha1(b"blob " + str(len(solver_bytes)).encode() + b"\0" + solver_bytes).hexdigest()
    if solver_blob != SOLVER_BLOB:
        raise ValueError("Local T15 solver differs from the recorded consumer pin.")
    ev = load(engine_loader, "terminal_case_evaluator")
    engine, hashes = ev.get_engine(engine_dir)
    solver = load(solver_file, "terminal_case_t15_solver")
    cases = []
    for player_index in (0, 1):
        for lead, step, label in ((30, 718, "recover_from_losses"), (35, 718, "protect_all_wins"),
                                  (33, 718, "varying_baseline"), (30, 717, "not_terminal"),
                                  (30, 718, "omitted_rival_supply")):
            document = execute_case(ev, engine, player_index=player_index, lead=lead, step=step,
                                    extra_scenario=label == "omitted_rival_supply")
            table = build_table(document)
            absolute = solve_terminal(table, solver.solve_table)
            relative = solve_terminal(table, solver.solve_table, objective="baseline_relative")
            margin = solver.solve_table(table["cash_margin_deltas"])
            if label == "recover_from_losses":
                assert margin["weights"] == ["0", "2/3", "1/3"]
                assert absolute["weights"] == ["0", "1/2", "1/2"]
                assert absolute["worst_expected_win_points"] == "1/2"
                assert table["win_points"] == [["0", "0"], ["1", "0"], ["0", "1"]]
            elif label == "protect_all_wins":
                assert absolute["weights"] == ["1", "0", "0"]
                assert absolute["worst_expected_win_points"] == "1"
            elif label == "varying_baseline":
                assert absolute["status"] == "absolute_matrix_solver_needed"
                assert absolute["solver_called"] is False
            elif label == "omitted_rival_supply":
                assert absolute["weights"] == ["1", "0", "0"]
                assert absolute["worst_expected_win_points"] == "0"
            else:
                assert table["terminal"] is False and table["win_points"] is None
                assert absolute["solver_called"] is False
            cases.append({"name": label, "player_index": player_index, "document": document,
                          "table": table, "absolute_solution": absolute,
                          "relative_solution": relative, "cash_margin_solution": margin})
    return {"engine_ref": ENGINE_REF, "engine_hashes": hashes,
            "solver_blob": solver_blob, "solver_sha256": hashlib.sha256(solver_bytes).hexdigest(),
            "loader_sha256": hashlib.sha256(engine_loader.read_bytes()).hexdigest(),
            "case_count": len(cases), "official_action_transitions": sum(len(c["document"]["receipts"]) for c in cases),
            "initializations": sum(len(c["document"]["receipts"]) for c in cases),
            "new_full_games": 0, "cases": cases}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--engine-dir", type=Path, required=True)
    p.add_argument("--engine-loader", type=Path, required=True, help="Existing cloud evaluator's evaluate.py.")
    p.add_argument("--solver-file", type=Path, required=True, help="Existing pinned T15 solver.py.")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = run(a.engine_dir, a.engine_loader, a.solver_file)
    a.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}))
