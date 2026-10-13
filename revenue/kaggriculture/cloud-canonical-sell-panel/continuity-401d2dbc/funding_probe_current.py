#!/usr/bin/env python3
"""Reach current DEFAULT funding through main.agent with the control isolated."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


def load(path, name):
    sys.path.insert(0, str(path.parent))
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
    parser.add_argument("--seed", type=int, default=9922023)
    parser.add_argument("--candidate-seat", type=int, choices=(0, 1), default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    E = load(args.evaluator.resolve(), "funding_continuity_evaluator")
    engine, hashes = E.get_engine(args.engine_dir.resolve())
    candidate = load(args.candidate.resolve(), "current_canonical_entry")
    cfg = E.Struct({k: v.get("default") if isinstance(v, dict) else v
                    for k, v in engine.specification["configuration"].items()})
    cfg.seed = args.seed
    env = E.Struct(configuration=cfg, done=False, info={})
    state = [E.Struct(observation=E.Struct(), action={}, status="ACTIVE", reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    rival_seat = 1 - args.candidate_seat
    rival = E.Actor(str(args.control.resolve()), args.engine_dir, E.LOADER, 20260908, 10.0)
    assert rival.ready["kind"] == "ready", rival.ready
    hook_calls, reached, wrapped = [], None, False
    try:
        for step in range(cfg.episodeSteps):
            actions = [None, None]
            for seat in range(2):
                state[seat].observation.step = step
                state[seat].observation.remainingOverageTime = 0
                if seat == args.candidate_seat:
                    before = copy.deepcopy(state[seat].observation)
                    started = time.perf_counter()
                    actions[seat] = candidate.agent(before, cfg)
                    call_seconds = time.perf_counter() - started
                    instance = candidate._INSTANCE
                    if not wrapped and instance.ready:
                        original = instance.funding_module.select_seed_queue

                        def counted(*positional, **keywords):
                            hook_calls.append(step)
                            return original(*positional, **keywords)

                        instance.funding_module.select_seed_queue = counted
                        wrapped = True
                    if instance.diagnostics.get("seed_funding") is not None:
                        reached = {
                            "step": step,
                            "hook_calls_this_entry": sum(value == step for value in hook_calls),
                            "call_seconds": call_seconds,
                            "selected": instance.selected,
                            "returned": actions[seat],
                            "diagnostics": copy.deepcopy(instance.diagnostics),
                        }
                        break
                else:
                    response = rival.act(state[seat].observation, cfg, 1.0)
                    assert response["kind"] == "action", response
                    actions[seat] = response["action"]
            if reached is not None:
                break
            for seat in range(2):
                state[seat].action = actions[seat]
            engine.interpreter(state, env)
    finally:
        rival.close()
    payload = {
        "purpose": "stopped activation probe; excluded from game outcomes",
        "seed": args.seed, "candidate_seat": args.candidate_seat,
        "candidate_entry_sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
        "config": json.loads((args.candidate.parent / "TITAN-CONFIG.json").read_text()),
        "config_sha256": hashlib.sha256((args.candidate.parent / "TITAN-CONFIG.json").read_bytes()).hexdigest(),
        "engine_ref": E.ENGINE_REF, "engine_sha256": hashes,
        "total_hook_calls_before_stop": len(hook_calls), "reached": reached,
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    assert reached is not None and reached["hook_calls_this_entry"] == len(hook_calls) == 1


if __name__ == "__main__":
    main()
