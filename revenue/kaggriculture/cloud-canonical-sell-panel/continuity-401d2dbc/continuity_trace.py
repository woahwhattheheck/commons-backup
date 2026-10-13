#!/usr/bin/env python3
"""One official-engine game retaining actions plus child/RPC timing per call."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluator", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    placement = parser.add_argument("--candidate-seat", type=int, choices=(0, 1))
    placement.required = True
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    E = load(args.evaluator.resolve(), "continuity_evaluator")
    engine, hashes = E.get_engine(args.engine_dir.resolve())
    candidate, control = str(args.candidate.resolve()), str(args.control.resolve())
    specs = [candidate, control] if args.candidate_seat == 0 else [control, candidate]
    cfg = E.Struct({k: v.get("default") if isinstance(v, dict) else v
                    for k, v in engine.specification["configuration"].items()})
    cfg.seed = args.seed
    env = E.Struct(configuration=cfg, done=False, info={})
    state = [E.Struct(observation=E.Struct(), action={}, status="ACTIVE", reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    actors, rows, trace = [], [], hashlib.sha256()
    started = time.perf_counter()
    try:
        for seat, spec in enumerate(specs):
            actor = E.Actor(spec, args.engine_dir, E.LOADER,
                            20260907 + (seat != args.candidate_seat), 10.0)
            assert actor.ready["kind"] == "ready", actor.ready
            actors.append(actor)
        for step in range(cfg.episodeSteps):
            actions, calls = [], []
            for seat, actor in enumerate(actors):
                state[seat].observation.step = step
                state[seat].observation.remainingOverageTime = 0
                rpc_started = time.perf_counter()
                response = actor.act(state[seat].observation, cfg, 1.0)
                rpc_seconds = time.perf_counter() - rpc_started
                assert response["kind"] == "action", response
                actions.append(response["action"])
                calls.append({"child_seconds": response["call_seconds"],
                              "child_cpu_seconds": response["call_cpu_seconds"],
                              "rpc_seconds": rpc_seconds})
            for seat in range(2):
                state[seat].action = actions[seat]
            engine.interpreter(state, env)
            bank = [float(state[0].observation.farms[i]["money"]) for i in range(2)]
            trace.update(E.encoded({"step": step, "actions": actions, "bank": bank}))
            rows.append({"step": step, "actions": actions, "bank": bank, "calls": calls})
            if all(item.status == "DONE" for item in state):
                break
        scores = [item.reward for item in state]
        trace.update(E.encoded([item.observation for item in state]))
        for actor in actors:
            actor.close()
        payload = {
            "seed": args.seed, "candidate_seat": args.candidate_seat,
            "scores": scores, "steps": len(rows), "trace_sha256": trace.hexdigest(),
            "engine_ref": E.ENGINE_REF, "engine_sha256": hashes,
            "candidate_entry_sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
            "control_entry_sha256": hashlib.sha256(args.control.read_bytes()).hexdigest(),
            "wall_seconds": time.perf_counter() - started,
            "actors": [actor.report() for actor in actors], "trace": rows,
        }
    finally:
        for actor in actors:
            actor.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=1) + "\n")
    print(json.dumps({k: payload[k] for k in
                      ("seed", "candidate_seat", "scores", "steps", "trace_sha256", "wall_seconds")}, indent=2))


if __name__ == "__main__":
    main()
