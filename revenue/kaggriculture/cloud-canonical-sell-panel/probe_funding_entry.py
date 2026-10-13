#!/usr/bin/env python3
"""Stop at the first funding-hook call reached through canonical main.agent."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    __setattr__ = dict.__setitem__


def load(path: Path, name: str):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--evaluator", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=9922005)
    parser.add_argument("--seed-status", default="already consumed in PR10005 economic-stress work")
    parser.add_argument("--seat", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    evaluator = load(args.evaluator.resolve(), "funding_probe_evaluator")
    engine, engine_hashes = evaluator.get_engine(args.engine_dir.resolve())
    candidate = load(args.candidate.resolve(), "canonical_entry")
    control = load(args.control.resolve(), "frozen_control_entry")

    cfg = Struct({k: v.get("default") if isinstance(v, dict) else v
                  for k, v in engine.specification["configuration"].items()})
    cfg.seed = args.seed
    env = Struct(configuration=cfg, done=False, info={})
    state = [Struct(observation=Struct(), action={}, status="ACTIVE", reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    calls = []
    wrapped = False
    original = None
    reached = None

    for step in range(cfg.episodeSteps):
        actions = [None, None]
        for player in range(2):
            state[player].observation.step = step
            state[player].observation.remainingOverageTime = 0
            if player == args.seat:
                before = copy.deepcopy(state[player].observation)
                actions[player] = candidate.agent(before, cfg)
                instance = candidate._INSTANCE
                if not wrapped and instance.ready:
                    original = instance.funding_module.select_seed_queue

                    def counted(*positional, **keywords):
                        calls.append({"step": step})
                        return original(*positional, **keywords)

                    instance.funding_module.select_seed_queue = counted
                    wrapped = True
                if instance.diagnostics.get("seed_funding") is not None:
                    this_step_calls = sum(item["step"] == step for item in calls)
                    reached = {
                        "step": step,
                        "hook_calls_this_entry": this_step_calls,
                        "observation_sha256": hashlib.sha256(canonical(before)).hexdigest(),
                        "selected": instance.selected,
                        "returned": actions[player],
                        "diagnostics": copy.deepcopy(instance.diagnostics),
                    }
                    break
            else:
                actions[player] = control.agent(copy.deepcopy(state[player].observation), cfg)
        if reached is not None:
            break
        for player in range(2):
            state[player].action = actions[player]
        engine.interpreter(state, env)
        if all(item.status == "DONE" for item in state):
            break

    payload = {
        "purpose": "activation-only; not a panel game or outcome",
        "source_seed_status": args.seed_status,
        "seed": args.seed,
        "candidate_seat": args.seat,
        "entrypoint": str(args.candidate.resolve()),
        "config": json.loads((args.candidate.parent / "TITAN-CONFIG.json").read_text()),
        "config_sha256": hashlib.sha256((args.candidate.parent / "TITAN-CONFIG.json").read_bytes()).hexdigest(),
        "engine_ref": evaluator.ENGINE_REF,
        "engine_sha256": engine_hashes,
        "reached": reached,
        "total_hook_calls_before_stop": len(calls),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    if reached is None or reached["hook_calls_this_entry"] != 1:
        raise SystemExit("Funding hook was not observed exactly once through the production entry")


if __name__ == "__main__":
    main()
