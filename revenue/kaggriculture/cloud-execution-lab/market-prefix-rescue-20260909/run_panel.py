#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run paired exact-engine games for the market-prefix rescue candidate."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EVALUATOR_PATH = ROOT / "reference/evaluator/evaluate.py"
LOADER_PATH = ROOT / "reference/evaluator/loader.py"
ENGINE_DIR = ROOT / "reference/engine"
BASELINE_PATH = ROOT / "main.py"
CANDIDATE_PATH = HERE / "candidate.py"
ARLENE_PATH = ROOT / "reference/next-panel/vendor/arlene.py"
SOURCE_CONTRACT = HERE / "source_contract.json"
DIAGNOSTIC_KEY = "__titan_market_prefix_rescue__"
OPERATION = "op:titan-v3-market-prefix-rescue-20260909-01"
DEFAULT_SEEDS = (2609099601, 2609099602, 2609099603, 2609099604)


def import_file(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_source_contract():
    contract = json.loads(SOURCE_CONTRACT.read_text(encoding="utf-8"))
    failures = []
    actual = {}
    for relative, expected in contract["git_blobs"].items():
        path = (HERE / relative).resolve(strict=True)
        digest = git_blob_sha1(path)
        actual[relative] = digest
        if digest != expected:
            failures.append({"path": relative, "expected": expected, "actual": digest})
    if failures:
        raise AssertionError(f"source contract drift: {failures}")
    return contract, actual


def _clean_action(response, *, candidate_seat: bool, step: int):
    action = response.get("action")
    if not isinstance(action, dict):
        raise TypeError("worker action is not an object")
    clean = deepcopy(action)
    diagnostic = clean.pop(DIAGNOSTIC_KEY, None)
    if diagnostic is not None and not candidate_seat:
        raise ValueError("diagnostic marker emitted by non-candidate seat")
    if diagnostic is not None:
        if (not isinstance(diagnostic, dict) or diagnostic.get("changed") is not True
                or int(diagnostic.get("step", -1)) != step):
            raise ValueError("malformed candidate diagnostic marker")
    return clean, diagnostic


def play(evaluator, engine, specs, seed, candidate_seat, *, rng_seed,
         action_timeout, startup_timeout, game_timeout):
    cfg = evaluator.Struct({
        key: value.get("default") if isinstance(value, dict) else value
        for key, value in engine.specification["configuration"].items()
    })
    cfg.seed = seed
    env = evaluator.Struct(configuration=cfg, done=False, info={})
    state = [
        evaluator.Struct(observation=evaluator.Struct(), action={}, status="ACTIVE", reward=0)
        for _ in range(2)
    ]
    started = time.perf_counter()
    initial_cpu = time.process_time()
    actors = []
    trace = hashlib.sha256()
    events = []
    event_count = 0
    result = {
        "seed": seed,
        "candidate_seat": candidate_seat,
        "status": "failed",
        "scores": None,
        "failure": None,
        "steps": 0,
        "episode_steps": cfg.episodeSteps,
        "daily_bank": [],
        "candidate_event_count": 0,
        "candidate_events": events,
    }
    try:
        engine.interpreter(state, env)
        if cfg.get("seed") is not None:
            raise ValueError("environment seed leaked to agents")
        for seat, spec in enumerate(specs):
            actor = evaluator.Actor(
                spec,
                ENGINE_DIR,
                LOADER_PATH,
                rng_seed + (seat != candidate_seat),
                startup_timeout,
            )
            actors.append(actor)
            if actor.ready.get("kind") != "ready":
                result["failure"] = {"seat": seat, "step": 0, "phase": "startup", **actor.ready}
                return result
        for step in range(cfg.episodeSteps):
            actions = []
            for seat, actor in enumerate(actors):
                remaining = game_timeout - (time.perf_counter() - started)
                if remaining <= 0:
                    result["failure"] = {"kind": "game_timeout", "seat": None, "step": step}
                    return result
                state[seat].observation.step = step
                state[seat].observation.remainingOverageTime = 0
                response = actor.act(
                    state[seat].observation,
                    cfg,
                    min(action_timeout, remaining),
                )
                if response.get("kind") != "action":
                    result["failure"] = {"seat": seat, "step": step, "phase": "action", **response}
                    return result
                clean, diagnostic = _clean_action(
                    response,
                    candidate_seat=(seat == candidate_seat),
                    step=step,
                )
                if diagnostic is not None:
                    event_count += 1
                    if len(events) < 128:
                        events.append(diagnostic)
                actions.append(clean)
            for seat in range(2):
                state[seat].action = actions[seat]
            engine.interpreter(state, env)
            result["steps"] += 1
            bank = [float(state[0].observation.farms[index]["money"]) for index in range(2)]
            trace.update(evaluator.encoded({"step": step, "actions": actions, "bank": bank}))
            done = all(item.status == "DONE" for item in state)
            if (step + 1) % cfg.turnsPerDay == 0 or done:
                result["daily_bank"].append({"step": step, "bank": bank})
            if done:
                scores = [item.reward for item in state]
                if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in scores):
                    raise ValueError("nonfinite or missing terminal score")
                result.update(status="complete", scores=scores)
                env.done = True
                return result
        result["failure"] = {"kind": "incomplete", "seat": None, "step": result["steps"]}
    except Exception as exc:  # Fail closed while retaining a compact witness.
        result["failure"] = {
            "kind": "runner_error",
            "seat": None,
            "step": result["steps"],
            "error": f"{type(exc).__name__}: {exc}"[:1000],
        }
    finally:
        for actor in actors:
            actor.close()
        result["actors"] = [actor.report() for actor in actors]
        result["wall_seconds"] = time.perf_counter() - started
        result["driver_cpu_seconds"] = time.process_time() - initial_cpu
        result["bank_snapshot"] = [
            float(state[0].observation.get("farms", [{"money": 0}] * 2)[index]["money"])
            for index in range(2)
        ]
        trace.update(evaluator.encoded([item.observation for item in state]))
        result["trace_sha256"] = trace.hexdigest()
        result["candidate_event_count"] = event_count
        result["candidate_events_truncated"] = max(0, event_count - len(events))
    return result


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        temporary = stream.name
    os.replace(temporary, path)


def summarize(games):
    by_key = {}
    for game in games:
        key = (game["opponent"], game["seed"], game["candidate_seat"])
        by_key.setdefault(key, {})[game["variant"]] = game
    pairs = []
    for key in sorted(by_key):
        variants = by_key[key]
        if set(variants) != {"baseline", "candidate"}:
            raise AssertionError(f"incomplete variant pair: {key}: {sorted(variants)}")
        baseline = variants["baseline"]
        candidate = variants["candidate"]
        if baseline["status"] != "complete" or candidate["status"] != "complete":
            raise AssertionError(f"failed game in pair: {key}")
        seat = key[2]
        base_own = float(baseline["scores"][seat])
        base_rival = float(baseline["scores"][1 - seat])
        cand_own = float(candidate["scores"][seat])
        cand_rival = float(candidate["scores"][1 - seat])
        events = int(candidate["candidate_event_count"])
        trace_diverged = baseline["trace_sha256"] != candidate["trace_sha256"]
        if not events and (trace_diverged or baseline["scores"] != candidate["scores"]):
            raise AssertionError(f"zero-activation candidate diverged from baseline: {key}")
        if events and not trace_diverged:
            raise AssertionError(f"activated candidate retained identical trace: {key}")
        pairs.append({
            "opponent": key[0],
            "seed": key[1],
            "candidate_seat": seat,
            "activation_events": events,
            "trace_diverged": trace_diverged,
            "baseline_scores": baseline["scores"],
            "candidate_scores": candidate["scores"],
            "own_delta": cand_own - base_own,
            "rival_delta": cand_rival - base_rival,
            "margin_delta": (cand_own - cand_rival) - (base_own - base_rival),
            "baseline_margin": base_own - base_rival,
            "candidate_margin": cand_own - cand_rival,
        })
    deltas = [row["margin_delta"] for row in pairs]
    own = [row["own_delta"] for row in pairs]
    activated = [row for row in pairs if row["activation_events"]]
    activated_deltas = [row["margin_delta"] for row in activated]
    return {
        "paired_cells": len(pairs),
        "activation_cells": len(activated),
        "activation_events": sum(row["activation_events"] for row in pairs),
        "trace_divergence_cells": sum(row["trace_diverged"] for row in pairs),
        "mean_own_delta": statistics.mean(own) if own else None,
        "mean_margin_delta": statistics.mean(deltas) if deltas else None,
        "median_margin_delta": statistics.median(deltas) if deltas else None,
        "positive_margin_cells": sum(value > 0 for value in deltas),
        "zero_margin_cells": sum(value == 0 for value in deltas),
        "negative_margin_cells": sum(value < 0 for value in deltas),
        "activated_mean_margin_delta": statistics.mean(activated_deltas) if activated_deltas else None,
        "activated_worst_margin_delta": min(activated_deltas) if activated_deltas else None,
        "pairs": pairs,
    }


def markdown(report):
    summary = report.get("summary") or {}
    lines = [
        "# TITAN market-prefix rescue paired panel",
        "",
        f"- Operation: `{report['operation']}`",
        f"- Status: **{report['status']}**",
        f"- Engine ref: `{report['engine']['ref']}`",
        f"- Baseline source: `{report['baseline']['sha256']}`",
        f"- Candidate source: `{report['candidate']['sha256']}`",
        f"- Completed games: {sum(game['status'] == 'complete' for game in report['games'])}/{len(report['games'])}",
        f"- Paired cells: {summary.get('paired_cells')}",
        f"- Activation cells/events: {summary.get('activation_cells')}/{summary.get('activation_events')}",
        f"- Mean own delta: {summary.get('mean_own_delta')}",
        f"- Mean margin delta: {summary.get('mean_margin_delta')}",
        f"- Activated mean/worst margin delta: {summary.get('activated_mean_margin_delta')} / {summary.get('activated_worst_margin_delta')}",
        "",
        "This is an offline exact-engine development screen, not hosted Kaggle scoring or a promotion claim.",
    ]
    return "\n".join(lines) + "\n"


def run(args):
    contract, source_blobs = verify_source_contract()
    evaluator = import_file(EVALUATOR_PATH, "titan_market_prefix_rescue_evaluator")
    if evaluator.ENGINE_REF != contract["engine_ref"]:
        raise AssertionError("evaluator engine ref drift")
    engine, engine_hashes = evaluator.get_engine(ENGINE_DIR, LOADER_PATH)
    baseline_spec = str(BASELINE_PATH.resolve()) + "::agent"
    candidate_spec = str(CANDIDATE_PATH.resolve()) + "::instrumented_agent"
    opponents = {"exact_public_arlene": str(ARLENE_PATH.resolve()) + "::agent"}
    started = time.time()
    report = {
        "schema_version": 1,
        "operation": OPERATION,
        "status": "running",
        "runner_head": args.runner_head,
        "base_commit": contract["base_commit"],
        "source_contract_sha256": sha256(SOURCE_CONTRACT),
        "source_git_blobs": source_blobs,
        "engine": {"ref": evaluator.ENGINE_REF, "sha256": engine_hashes},
        "evaluator": {"path": str(EVALUATOR_PATH), "sha256": sha256(EVALUATOR_PATH)},
        "loader": {"path": str(LOADER_PATH), "sha256": sha256(LOADER_PATH)},
        "baseline": {"entrypoint": baseline_spec, "sha256": sha256(BASELINE_PATH)},
        "candidate": {
            "entrypoint": candidate_spec,
            "sha256": sha256(CANDIDATE_PATH),
            "transform_sha256": sha256(HERE / "market_prefix_rescue.py"),
        },
        "opponents": {name: {"entrypoint": spec, "sha256": sha256(ARLENE_PATH)} for name, spec in opponents.items()},
        "seeds": args.seeds,
        "agent_rng_seed": args.rng_seed,
        "limits": {
            "action_timeout_seconds": args.action_timeout,
            "startup_timeout_seconds": args.startup_timeout,
            "game_timeout_seconds": args.game_timeout,
        },
        "method": "Pinned official interpreter; fresh process per agent per game; baseline and candidate paired against the same opponent in both seats; diagnostic marker stripped before interpreter execution.",
        "games": [],
        "summary": None,
        "wall_seconds": 0.0,
    }
    atomic_json(args.output, report)
    for variant, tested in (("baseline", baseline_spec), ("candidate", candidate_spec)):
        for opponent, rival in opponents.items():
            for seed in args.seeds:
                for seat in (0, 1):
                    pair = [tested, rival] if seat == 0 else [rival, tested]
                    game = play(
                        evaluator,
                        engine,
                        pair,
                        seed,
                        seat,
                        rng_seed=args.rng_seed,
                        action_timeout=args.action_timeout,
                        startup_timeout=args.startup_timeout,
                        game_timeout=args.game_timeout,
                    )
                    game.update(variant=variant, opponent=opponent)
                    report["games"].append(game)
                    report["wall_seconds"] = time.time() - started
                    atomic_json(args.output, report)
                    print(json.dumps({
                        "variant": variant,
                        "opponent": opponent,
                        "seed": seed,
                        "candidate_seat": seat,
                        "status": game["status"],
                        "scores": game["scores"],
                        "events": game["candidate_event_count"],
                        "failure": game["failure"],
                    }, sort_keys=True), flush=True)
                    if game["status"] != "complete":
                        report["status"] = "failed"
                        atomic_json(args.output, report)
                        raise RuntimeError(f"game failed: {variant}/{opponent}/{seed}/seat{seat}")
    report["summary"] = summarize(report["games"])
    report["status"] = "complete"
    report["wall_seconds"] = time.time() - started
    atomic_json(args.output, report)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print("MARKET_PREFIX_RESCUE_SUMMARY " + json.dumps(report["summary"], sort_keys=True), flush=True)
    return report


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--seeds", default=",".join(map(str, DEFAULT_SEEDS)))
    value.add_argument("--rng-seed", type=int, default=20260909)
    value.add_argument("--action-timeout", type=float, default=1.0)
    value.add_argument("--startup-timeout", type=float, default=10.0)
    value.add_argument("--game-timeout", type=float, default=120.0)
    value.add_argument("--runner-head", default=None)
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--markdown", type=Path, required=True)
    return value


def main():
    args = parser().parse_args()
    try:
        args.seeds = [int(item.strip()) for item in args.seeds.split(",") if item.strip()]
        if not args.seeds or len(args.seeds) != len(set(args.seeds)):
            raise ValueError
    except ValueError:
        raise SystemExit("--seeds requires distinct comma-separated integers")
    if any(not math.isfinite(value) or value <= 0 for value in
           (args.action_timeout, args.startup_timeout, args.game_timeout)):
        raise SystemExit("timeouts must be finite and positive")
    run(args)


if __name__ == "__main__":
    main()
