"""Known-policy falsification of treating fixed tapes as live opponents.

Uses the package's existing process-isolated Actor and pinned official engine.
No network, Kaggle API, new policy, Actions dispatch, or runtime change.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
from tape_integrity import FrozenTape, MarketRecorder, ReplayError, TapeAudit, encoded

SOURCE_MANIFEST = "e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2"
PINNED_ARCHIVE = "b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9"
ENGINE_PIN = "3c202c7ee921da239356789e266b694635103fc4"
EVALUATOR_PIN = "e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c"


def authenticate(root: Path) -> dict:
    source = root / "SOURCE.json"
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_MANIFEST:
        raise ReplayError("source manifest is not the declared b567 native package")
    mapping = json.loads(source.read_text())["runtime"]
    for name, row in mapping.items():
        path = root / name
        if not path.is_file():
            raise ReplayError(f"missing package member: {name}")
        data = path.read_bytes()
        if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ReplayError(f"changed package member: {name}")
    evaluator = root / "checks/reference/evaluator/evaluate.py"
    if hashlib.sha256(evaluator.read_bytes()).hexdigest() != EVALUATOR_PIN:
        raise ReplayError("evaluator byte pin changed")
    return {"archive_sha256": PINNED_ARCHIVE, "source_manifest_sha256": SOURCE_MANIFEST,
            "authenticated_runtime_members": len(mapping), "engine_blob": ENGINE_PIN,
            "main_sha256": mapping["main.py"]["sha256"],
            "config_sha256": mapping["TITAN-CONFIG.json"]["sha256"],
            "evaluator_sha256": EVALUATOR_PIN}


def import_evaluator(root: Path):
    path = root / "checks/reference/evaluator/evaluate.py"
    spec = importlib.util.spec_from_file_location("tape_probe_existing_evaluator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def play(ev, root: Path, specs: list, seed: int, target_seat: int, *, reference=None,
         audit_seats=(), record=False, game_timeout=120.0) -> dict:
    cache, loader = root / "checks/reference/engine", root / "checks/reference/evaluator/loader.py"
    engine, _ = ev.get_engine(cache, loader)
    cfg = ev.Struct({key: value.get("default") if isinstance(value, dict) else value
                     for key, value in engine.specification["configuration"].items()})
    cfg.seed = seed
    env = ev.Struct(configuration=cfg, done=False, info={})
    state = [ev.Struct(observation=ev.Struct(), action={}, status="ACTIVE", reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    if cfg.get("seed") is not None:
        raise ReplayError("private environment seed would be exposed to an agent")
    binding = {"engine_blob": ENGINE_PIN, "configuration": dict(cfg), "seed": seed,
               "policy_rng_seeds": [9000 + int(s != target_seat) for s in range(2)]}
    tapes, actors, audits = {}, {}, {}
    result = {"seed": seed, "target_seat": target_seat, "status": "failed", "scores": None,
              "callbacks": 0, "failure": None, "binding": binding, "frames": [],
              "surplus_hand_callbacks": [0, 0], "raw_over_cap_callbacks": [0, 0]}
    trace, start = hashlib.sha256(), time.perf_counter()
    try:
        for seat, agent in enumerate(specs):
            if agent == "TAPE":
                if reference is None or reference.get("status") != "complete":
                    raise ReplayError("TAPE requires a complete reference game")
                tapes[seat] = FrozenTape(reference["frames"], seat,
                                         expected_binding=reference["binding"], actual_binding=binding)
            else:
                actors[seat] = ev.Actor(agent, cache, loader, 9000 + int(seat != target_seat))
                if actors[seat].ready.get("kind") != "ready":
                    raise ReplayError(f"worker not ready: seat {seat}, {actors[seat].ready}")
        for seat in audit_seats:
            if seat not in tapes:
                raise ReplayError("audit seat must be an actual tape consumer")
            audits[seat] = TapeAudit(seat)
        for step in range(cfg.episodeSteps):
            for s in state:
                s.observation.step = step
                s.observation.remainingOverageTime = 0
            before = deepcopy([s.observation for s in state])
            actions = []
            for seat in range(2):
                if seat in tapes:
                    action = tapes[seat].action(step)
                else:
                    remaining = game_timeout - (time.perf_counter() - start)
                    if remaining <= 0:
                        raise ReplayError(f"game deadline at step {step}")
                    response = actors[seat].act(state[seat].observation, cfg, min(1.0, remaining))
                    if response.get("kind") != "action":
                        raise ReplayError(f"worker failure seat {seat} step {step}: {response}")
                    action = response["action"]
                encoded(action)
                actions.append(deepcopy(action))
                hands, market = action.get("hands", []), action.get("market", [])
                if isinstance(hands, list) and len(hands) > len(state[seat].observation.farms[seat]["hands"]):
                    result["surplus_hand_callbacks"][seat] += 1
                if isinstance(market, list) and len(market) > max(1, int(cfg.maxMarketOrdersPerTurn)):
                    result["raw_over_cap_callbacks"][seat] += 1
            for seat in range(2):
                state[seat].action = actions[seat]
            with MarketRecorder(engine, state) as recorder:
                engine.interpreter(state, env)
            frame = {"step": step, "before": before, "actions": actions,
                     "after": deepcopy([s.observation for s in state]),
                     "receipts": recorder.receipts, "status": [s.status for s in state],
                     "rewards": [s.reward for s in state]}
            trace.update(encoded(frame) + b"\n")
            for seat, audit in audits.items():
                audit.observe(reference["frames"][step], frame)
            if record:
                result["frames"].append(frame)
            result["callbacks"] += 1
            if all(s.status == "DONE" for s in state):
                for tape in tapes.values():
                    tape.finish()
                scores = [s.reward for s in state]
                if any(type(s) not in (int, float) or not math.isfinite(s) for s in scores):
                    raise ReplayError("nonfinite terminal reward")
                result.update(status="complete", scores=scores, margin=scores[target_seat] - scores[1 - target_seat])
                env.done = True
                break
        if result["status"] != "complete":
            raise ReplayError("official interpreter never reached DONE")
    except Exception as exc:
        result["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        for actor in actors.values():
            actor.close()
        result["actors"] = {str(seat): actor.report() for seat, actor in actors.items()}
        result["wall_seconds"] = time.perf_counter() - start
        result["trace_sha256"] = trace.hexdigest()
        result["audits"] = {str(seat): audit.report() for seat, audit in audits.items()}
    return result


def require_complete(game, arm):
    if game["status"] != "complete":
        raise ReplayError(f"{arm} incomplete: {game['failure']}")


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n")


def panel(root: Path, output: Path, seeds: list[int], seats: list[int]) -> dict:
    source, ev = authenticate(root), import_evaluator(root)
    native = str(root / "main.py") + "::agent"
    results = {"schema": "titan-replay-probe/1", "source": source, "python": sys.version,
               "parent_optimized": bool(sys.flags.optimize), "worker_optimized": False,
               "scope": "Controlled known-policy native-vs-native falsification; NOT top-30 replay data or a ladder strength result.",
               "inner_runtime_deadline_fallbacks": "NOT_INSTRUMENTED; worker completion is not zero-fallback proof", "cells": []}
    here = Path(__file__).resolve().parent
    results["audit_source_sha256"] = hashlib.sha256((here/"tape_integrity.py").read_bytes()).hexdigest()
    results["probe_source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    for seed in seeds:
        for target in seats:
            label, cell_dir = f"seed-{seed}-seat-{target}", output / f"seed-{seed}-seat-{target}"
            cell_dir.mkdir(exist_ok=True)
            specs = [native, native]
            specs[target] = "official_starter"
            ref = play(ev, root, specs, seed, target, record=True)
            write_json(cell_dir / "reference-summary.json", {k: v for k, v in ref.items() if k != "frames"})
            require_complete(ref, "reference")
            corpus_bytes = encoded(ref)
            (cell_dir / "reference.json.gz").write_bytes(gzip.compress(corpus_bytes, compresslevel=1, mtime=0))
            print(json.dumps({"cell": label, "arm": "reference", "scores": ref["scores"]}), flush=True)
            control = play(ev, root, ["TAPE", "TAPE"], seed, target, reference=ref, audit_seats=(0, 1))
            write_json(cell_dir / "control.json", control)
            require_complete(control, "dual-tape control")
            if control["trace_sha256"] != ref["trace_sha256"]:
                raise ReplayError("dual-tape control does not reproduce the complete original trajectory")
            if any(a["changed_callbacks"] for a in control["audits"].values()):
                raise ReplayError("reference control audit reports drift")
            specs = ["TAPE", "TAPE"]
            specs[target] = native
            replay = play(ev, root, specs, seed, target, reference=ref, audit_seats=(1 - target,))
            write_json(cell_dir / "replay.json", replay)
            require_complete(replay, "native-vs-tape")
            print(json.dumps({"cell": label, "arm": "replay", "scores": replay["scores"],
                              "audit": replay["audits"][str(1 - target)]["changed_callbacks"]}), flush=True)
            live = play(ev, root, [native, native], seed, target)
            write_json(cell_dir / "live.json", live)
            require_complete(live, "native-vs-live-native")
            delta = replay["margin"] - live["margin"]
            row = {"seed": seed, "target_seat": target, "reference_scores": ref["scores"],
                   "control_trace_exact": True, "reference_trace_sha256": ref["trace_sha256"],
                   "reference_corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
                   "replay_scores": replay["scores"], "live_scores": live["scores"],
                   "replay_margin": replay["margin"], "live_margin": live["margin"],
                   "replay_minus_live_margin": delta,
                   "win_class_changed": (replay["margin"] > 0) - (replay["margin"] < 0) !=
                                        (live["margin"] > 0) - (live["margin"] < 0),
                   "callbacks_per_arm": [g["callbacks"] for g in (ref, control, replay, live)],
                   "audit": replay["audits"][str(1 - target)],
                   "surplus_hand_callbacks_by_arm": {n: g["surplus_hand_callbacks"] for n, g in
                       (("reference", ref), ("control", control), ("replay", replay), ("live", live))},
                   "trace_sha256_by_arm": {n: g["trace_sha256"] for n, g in
                       (("reference", ref), ("control", control), ("replay", replay), ("live", live))}}
            results["cells"].append(row)
            write_json(output / "RESULTS.json", results)
            print(json.dumps({"cell": label, "arm": "live", "scores": live["scores"],
                              "replay_minus_live_margin": delta}), flush=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", default="9922023,9922999")
    parser.add_argument("--seats", default="0,1")
    args = parser.parse_args()
    try:
        seeds = [int(x.strip()) for x in args.seeds.split(",")]
        seats = [int(x.strip()) for x in args.seats.split(",")]
        if not seeds or len(seeds) != len(set(seeds)):
            raise ReplayError("nonempty distinct seeds required")
        if not seats or len(seats) != len(set(seats)) or any(s not in (0, 1) for s in seats):
            raise ReplayError("distinct seats from 0,1 required")
        panel(args.native.resolve(), args.output.resolve(), seeds, seats)
    except (ReplayError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
