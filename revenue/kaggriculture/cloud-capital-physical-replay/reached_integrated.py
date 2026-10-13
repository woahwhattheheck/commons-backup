# SPDX-License-Identifier: Apache-2.0
"""Use the retained integrated actor with the existing complete-tail evaluator.

This adds an independent fork for one documented actor family, not a simulator,
selector or new production controller. The command consumes TRACE's native
JSONL and DELVE's original runtime closure in an isolated process.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import types
from typing import Any
from dataclasses import asdict

MAIN = "7015cc00acfa4922"
SHEEP = "dc76e4003029ac51"
CHECKPOINT = 226
ACTOR_SEED = 20260907


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def identity(path):
    raw = Path(path).read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "git_blob": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}


def fork_integrated(actor: Any):
    """Copy all actor state while sharing the three immutable source modules.

    Supported input is the pinned IntegratedSelectedAgent / PlanOverlay graph.
    The controller must be the SAME instance used by the production overlay and
    cap chooser. deepcopy preserves those aliases inside each independent fork.
    Unknown actor families are not silently reset or downgraded to Arlene-only.
    A source module is shared, never modified by this function.
    """
    production = actor.production
    if actor.controller is not production.agent or production.chooser.agent is not actor.controller:
        raise ValueError("Integrated actor has inconsistent controller references")
    modules = (production.A, production.K, production.chooser.K)
    if not all(isinstance(module, types.ModuleType) for module in modules):
        raise TypeError("Supply the documented module-backed integrated producer")
    memo = {id(module): module for module in modules}
    copied = deepcopy(actor, memo)
    if copied is actor or copied.controller is actor.controller or copied.production is production:
        raise ValueError("Actor fork is not independent")
    if copied.controller is not copied.production.agent or copied.production.chooser.agent is not copied.controller:
        raise ValueError("Actor fork lost controller aliases")
    return copied


def state_digest(actor):
    """Deterministic graph fingerprint for this execution receipt, not a checkpoint.

    Includes every instance field and shared-object topology; source modules and
    callables are named, not serialized. This cannot restore an actor by itself.
    """
    seen = {}

    def walk(value):
        if value is None or type(value) in (str, int, float, bool):
            return value
        if isinstance(value, types.ModuleType):
            return {"module": value.__name__, "file": getattr(value, "__file__", None)}
        if isinstance(value, (types.FunctionType, types.BuiltinFunctionType, type)):
            return {"callable": value.__module__ + "." + value.__qualname__}
        key = id(value)
        if key in seen:
            return {"ref": seen[key]}
        seen[key] = len(seen)
        if isinstance(value, dict):
            return {"dict": [[walk(k), walk(v)] for k, v in value.items()]}
        if isinstance(value, (list, tuple)):
            return {type(value).__name__: [walk(v) for v in value]}
        if isinstance(value, (set, frozenset)):
            return {type(value).__name__: [walk(v) for v in sorted(value, key=repr)]}
        if hasattr(value, "__dict__"):
            return {"class": type(value).__module__ + "." + type(value).__qualname__,
                    "state": walk(vars(value))}
        raise TypeError("Unsupported state fingerprint shape: " + type(value).__name__)

    return digest(walk(actor))


def restore_prefix(actor, rows, *, checkpoint=CHECKPOINT):
    """Consume already-normalized TRACE rows; no frame parser or engine call.

    Every input and expected action comes from the original ordered actor stream.
    No seed is derived from observations and no future row is used by the actor.
    The returned actor is before its checkpoint action, never a reset at that time.
    """
    if checkpoint < 0 or len(rows) <= checkpoint:
        raise ValueError("Missing checkpoint in saved actor input")
    original = digest(rows[:checkpoint + 1])
    chain = hashlib.sha256()
    for step in range(checkpoint):
        row = rows[step]
        if row["step"] != step or row["observation"]["step"] != step:
            raise ValueError("Saved prefix is not contiguous")
        if row["seat"] != row["observation"]["player"]:
            raise ValueError("Saved private observation has a different seat")
        action = actor.act(deepcopy(row["observation"]), deepcopy(row["configuration"]))
        if action != row["expected_action"]:
            raise ValueError(f"Original actor differs at decision {step}")
        chain.update(encoded({"step": step, "action": action}) + b"\n")
    row = rows[checkpoint]
    if row["step"] != checkpoint or row["observation"]["step"] != checkpoint:
        raise ValueError("Checkpoint clock differs")
    if row["seat"] != row["observation"]["player"]:
        raise ValueError("Checkpoint private observation has a different seat")
    if digest(rows[:checkpoint + 1]) != original:
        raise AssertionError("Saved input changed during prefix restoration")
    return deepcopy(row), {"matched_actions": checkpoint, "through_step": checkpoint - 1,
                           "action_prefix_sha256": chain.hexdigest(), "engine_calls": 0}


def consume_completed(report, date_directory):
    """Use DATE's unchanged ranker; no new pricing, simulation or selection rule."""
    directory = Path(date_directory)
    sys.path.insert(0, str(directory))
    import dated_scenarios
    import physical_outcomes
    DatedSelector = dated_scenarios.DatedSelector
    raw = report["replay"]
    cfg = report["validation"]["configuration"]
    observation = report["validation"]["input_row"]["observation"]
    selector = DatedSelector.from_completed_replay(raw, cfg, scenario_ids=tuple(raw["scenarios"]))
    selector([{"route_id": MAIN}, {"route_id": SHEEP}], observation)
    return {"comparison": selector.last_report,
            "sources": {"dated_scenarios.py": identity(dated_scenarios.__file__),
                        "physical_outcomes.py": identity(physical_outcomes.__file__)},
            "actor_calls": 0, "engine_calls": 0, "applied_to_live_actor": False}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(args):
    if os.environ.get("PYTHONHASHSEED") != str(ACTOR_SEED):
        raise ValueError("Use PYTHONHASHSEED=20260907 for the original actor process")
    source_map = json.loads((args.trace / "SOURCE-MAP.json").read_text())
    receipt = json.loads((args.trace / "candidate-inputs-receipt.json").read_text())
    raw = (args.trace / "candidate-inputs.jsonl.gz").read_bytes()
    decoded = gzip.decompress(raw)
    if hashlib.sha256(raw).hexdigest() != receipt["output_file_sha256"] or hashlib.sha256(decoded).hexdigest() != receipt["input_jsonl_sha256"]:
        raise ValueError("TRACE input bytes differ from their receipt")
    if identity(args.trace / "SOURCE-MAP.json")["sha256"] != receipt["source_map_sha256"]:
        raise ValueError("TRACE source map differs")
    bound = {}
    for key, record in source_map.items():
        if key.startswith("runtime/"):
            path = args.runtime / key.removeprefix("runtime/")
            bound[key] = identity(path)
            if bound[key]["sha256"] != record["sha256"]:
                raise ValueError("Original runtime input differs: " + key)
    dependencies = {"replay": (args.replay, "e299275048d241602541e3329631f169e4de7634"),
                    "oracle": (args.oracle, "49640c27862d3d132c828fbafc6a8b4957527736"),
                    "whole_actor_view": (args.tail, "bc1a74974ca06e9a6cd6408ba15e246baea75656")}
    pins = {name: identity(path) for name, (path, _) in dependencies.items()}
    for name in dependencies:
        if pins[name]["git_blob"] != dependencies[name][1]:
            raise ValueError("Use the documented " + name + " source")
    sys.path[:0] = [str(args.runtime / "cloud-integration-differentials"),
                    str(args.runtime / "cloud-execution-lab")]
    factory = load(args.runtime / "cloud-integration-differentials/funded_main.py", "rill_original_factory")
    oracle = load(args.oracle, "rill_reached_oracle")
    replay = load(args.replay, "rill_reached_replay")
    tail = load(args.tail, "rill_reached_whole_actor")
    evaluator = load(args.evaluator, "rill_reached_evaluator")
    engine, engine_hashes = evaluator.get_engine(args.engine, prepare=False)
    if engine_hashes != receipt["engine_sha256"]:
        raise ValueError("Engine does not match original source")
    random.seed(ACTOR_SEED)
    actor = factory.make_agent(funded=False)
    rows = [json.loads(line) for line in decoded.splitlines()]
    row, restoration = restore_prefix(actor, rows)
    obs, cfg = row["observation"], row["configuration"]
    if actor.controller.cur != MAIN:
        raise ValueError("This retained case is not the documented MAIN incumbent")
    before = state_digest(actor)
    observation_before = digest(obs)
    # Same public hypotheses as OSPREY's reached quote; additions are expressed
    # in T04's after-market EOD time (287), not first-active time (288).
    scenarios = {
        "observed_shops_continue_no_rival": oracle.Scenario(label="Current visible shops only; no future shops/rival flow supplied"),
        "hypothetical_yarn_288_no_rival": oracle.Scenario(new_shops={287: ("YARN_STORE",)},
            label="Hypothetical YARN buyer first visible at288, not known at226; no rival flow")}
    previous = json.loads(args.resume.read_text()) if args.resume else None
    reused = {}
    reuse_receipt = None
    if previous:
        old = previous["replay"]
        if (old["observation_sha256"] != digest(obs) or old["start_step"] != CHECKPOINT
                or old["end_step"] != int(cfg["episodeSteps"]) - 2
                or old["original_route"] != MAIN
                or previous["validation"]["runtime_closure"] != bound
                or previous["validation"]["source_pins"] != pins
                or old["scenarios"] != {k: json.loads(encoded(asdict(v))) for k, v in scenarios.items()}):
            raise ValueError("Resume report is not bound to these exact inputs")
        for case in old["cases"]:
            if case["status"] == "complete":
                key = (case["offered_route"], case["scenario_id"])
                if key in reused or key[0] not in (MAIN, SHEEP) or key[1] not in scenarios:
                    raise ValueError("Duplicate or foreign completed case")
                if case["program_sha256"] != digest(actor.controller.R[key[0]]):
                    raise ValueError("Saved program differs")
                reused[key] = case
        reuse_receipt = identity(args.resume)
    cases, newly_run, decisions, elapsed = [], 0, 0, 0.0
    facade = tail.SellRouteView(actor, cfg)
    def fork(view):
        return tail.SellRouteView(fork_integrated(view.scheduler), view.configuration)
    for route in (MAIN, SHEEP):
        for name, scenario in scenarios.items():
            if (route, name) in reused:
                cases.append(reused[route, name])
            elif newly_run < args.max_cases:
                one = replay.replay_routes(facade, (route,), obs, cfg, engine,
                    oracle.simulate_bundle, scenarios={name: scenario}, end_step=int(cfg["episodeSteps"]) - 2,
                    fork_controller=fork, limits=replay.ReplayLimits(seconds=args.seconds, decisions=493))
                cases.extend(one["cases"])
                newly_run += 1
                decisions += one["decisions_executed"]
                elapsed += one["wall_seconds"]
            else:
                cases.append({"offered_route": route, "scenario_id": name, "status": "incomplete",
                              "cash_gain": None, "rival_cash_delta": None, "market_rows": [],
                              "reason": "not_run_in_this_shard"})
    report = {"schema": "titan.integrated-reached-value.v1", "complete": all(c["status"] == "complete" for c in cases),
              "selection": None,
              "replay": {"schema": "titan.capital-physical-replay.v1",
                "complete": all(c["status"] == "complete" for c in cases),
                "observation_sha256": digest(obs), "start_step": CHECKPOINT,
                "end_step": int(cfg["episodeSteps"]) - 2, "original_route": MAIN,
                "scenarios": {name: asdict(v) for name, v in scenarios.items()}, "cases": cases,
                "decisions_executed": sum(len(c["market_rows"]) for c in cases), "wall_seconds": elapsed,
                "scope": "conditional own-state execution via existing T04 oracle; not paired rival trading",
                "selection": None},
              "attempt": {"new_cases": newly_run, "new_model_decisions": decisions, "new_tail_seconds": elapsed,
                          "reused_complete_cases": len(reused), "resume_report": reuse_receipt,
                          "driver": identity(__file__), "limit_seconds_per_case": args.seconds},
              "comparisons": []}
    by_key = {(c["offered_route"], c["scenario_id"]): c for c in cases}
    for name in scenarios:
        control, alternate = by_key[MAIN, name], by_key[SHEEP, name]
        complete = control["status"] == alternate["status"] == "complete"
        report["comparisons"].append({"scenario_id": name, "complete_pair": complete,
            "main_cash": control.get("final_cash"), "sheep_cash": alternate.get("final_cash"),
            "sheep_minus_main": alternate["final_cash"] - control["final_cash"] if complete else None,
            "rival_cash_delta": None})
    if state_digest(actor) != before or digest(obs) != observation_before:
        raise AssertionError("Original integrated actor or observation changed")
    report["validation"] = {"restoration": restoration, "source_pins": pins,
        "runtime_closure": bound, "engine_sha256": engine_hashes,
        "trace_receipt_sha256": identity(args.trace / "candidate-inputs-receipt.json")["sha256"],
        "checkpoint_input_sha256": digest(row), "actor_state_sha256": before,
        "original_actor_unchanged": True, "input_unchanged": True,
        "configuration": cfg, "input_row": row, "new_games": 0,
        "game_seeds_initialized": [], "source_environment_seed_provenance_only": 9965001,
        "origin": "DELVE9965001/p0 integrated funding-OFF, SELL-ON; original 226 prefix restored"}
    if args.date:
        report["consumer"] = consume_completed(report, args.date)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime", "trace", "replay", "oracle", "tail", "evaluator", "engine", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--resume", type=Path)
    p.add_argument("--date", type=Path)
    p.add_argument("--max-cases", type=int, default=4)
    args = p.parse_args()
    report = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded(report) + b"\n")
    print(json.dumps({"complete": report["complete"], "comparisons": report["comparisons"],
                      "restoration": report["validation"]["restoration"],
                      "tail_seconds": report["replay"]["wall_seconds"]}, indent=2))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
