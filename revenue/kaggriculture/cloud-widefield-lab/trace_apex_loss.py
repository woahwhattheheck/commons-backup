#!/usr/bin/env python3
"""Replay one development failure through the exact isolated evaluator contract.

This is diagnostic instrumentation, not another policy or a held evaluation.  It
retains every authored action and call timing, plus end-of-day cash, production,
inventory and shared-market state.  Its trace digest is computed identically to
cloud-eval/evaluate.py so a replay can be tied back to the accepted result.
"""

from __future__ import annotations

import argparse
import copy
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("widefield_exact_evaluator", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot import evaluator {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def nonzero(mapping):
    return {str(k): int(v) for k, v in mapping.items() if v}


def farm_snapshot(farm, private, capacity):
    tiles = Counter()
    ready = Counter()
    planted = Counter()
    placed = Counter()
    structures = Counter()
    for row in farm.get("tiles", []):
        for tile in row:
            if not isinstance(tile, dict):
                tiles[str(tile)] += 1
                continue
            if tile.get("crop"):
                crop = str(tile["crop"])
                planted[crop] += 1
                ready[crop] += int(tile.get("yield_units", 0))
            if tile.get("animal"):
                animal = str(tile["animal"])
                placed[animal] += 1
                ready[animal] += int(tile.get("yield_units", 0))
            if tile.get("structure"):
                structures[str(tile["structure"])] += 1
            tiles[str(tile.get("state", "occupied"))] += 1
    shed = nonzero(private.get("shed", {}))
    carried = Counter()
    inventories = []
    for inv in private.get("inventories", []):
        inventories.append(nonzero(inv))
        carried.update({str(k): int(v) for k, v in inv.items() if v})
    shed_units = sum(shed.values())
    return {
        "money": float(farm["money"]),
        "shed": shed,
        "shed_units": shed_units,
        "shed_room": int(capacity) - shed_units,
        "carried": dict(carried),
        "inventories": inventories,
        "carried_units": sum(carried.values()),
        "hands": len(farm.get("hands", [])),
        "unlocked": copy.deepcopy(farm.get("unlocked", farm.get("quadrants"))),
        "tile_states": dict(tiles),
        "crops": dict(planted),
        "animals": dict(placed),
        "structures": dict(structures),
        "ready_yield": dict(ready),
    }


def snapshot(state, cfg):
    market = state[0].observation.get("market", {})
    return {
        "farms": [farm_snapshot(state[0].observation.farms[i],
                                state[i].observation.private,
                                cfg.shedCapacity) for i in range(2)],
        "market_inventory": nonzero(market.get("inventory", {})),
        "market_prices": {str(k): float(v) for k, v in market.get("prices", {}).items()},
    }


def play(evaluator, engine, cache, loader, candidate, opponent, seed, candidate_seat):
    cfg = evaluator.Struct({key: value.get("default") if isinstance(value, dict) else value
                            for key, value in engine.specification["configuration"].items()})
    cfg.seed = int(seed)
    env = evaluator.Struct(configuration=cfg, done=False, info={})
    state = [evaluator.Struct(observation=evaluator.Struct(), action={}, status="ACTIVE", reward=0)
             for _ in range(2)]
    engine.interpreter(state, env)
    if cfg.get("seed") is not None:
        raise ValueError("environment seed unexpectedly exposed")
    specs = [candidate, opponent] if candidate_seat == 0 else [opponent, candidate]
    actors = []
    trace = hashlib.sha256()
    steps = []
    daily = []
    failure = None
    started = time.perf_counter()
    try:
        for seat, agent_spec in enumerate(specs):
            actor = evaluator.Actor(agent_spec, cache, loader,
                                    20260907 + (seat != candidate_seat))
            actors.append(actor)
            if actor.ready.get("kind") != "ready":
                failure = {"seat": seat, "step": 0, "phase": "startup", **actor.ready}
                break
        for step in range(cfg.episodeSteps):
            if failure:
                break
            before = snapshot(state, cfg)
            actions = []
            timings = []
            for seat, actor in enumerate(actors):
                state[seat].observation.step = step
                state[seat].observation.remainingOverageTime = 0
                rpc_started = time.perf_counter()
                response = actor.act(state[seat].observation, cfg, 1.0)
                rpc_seconds = time.perf_counter() - rpc_started
                if response.get("kind") != "action":
                    failure = {"seat": seat, "step": step, "phase": "action", **response}
                    break
                actions.append(response["action"])
                timings.append({
                    "seat": seat,
                    "role": "candidate" if seat == candidate_seat else "opponent",
                    "call_seconds": response["call_seconds"],
                    "call_cpu_seconds": response["call_cpu_seconds"],
                    "rpc_seconds": rpc_seconds,
                })
            if failure:
                break
            for seat in range(2):
                state[seat].action = actions[seat]
            engine.interpreter(state, env)
            after = snapshot(state, cfg)
            bank = [float(state[0].observation.farms[i]["money"]) for i in range(2)]
            trace.update(evaluator.encoded({"step": step, "actions": actions, "bank": bank}))
            row = {"step": step, "day": step // int(cfg.turnsPerDay),
                   "hour": step % int(cfg.turnsPerDay), "actions": actions,
                   "timings": timings, "bank": bank,
                   "before": before, "after": after}
            steps.append(row)
            done = all(s.status == "DONE" for s in state)
            if (step + 1) % int(cfg.turnsPerDay) == 0 or done:
                daily.append(copy.deepcopy(row))
            if done:
                env.done = True
                break
    finally:
        for actor in actors:
            actor.close()
    trace.update(evaluator.encoded([s.observation for s in state]))
    scores = [s.reward for s in state] if not failure else None
    return {
        "seed": int(seed), "candidate_seat": int(candidate_seat),
        "candidate": evaluator.fingerprint(candidate),
        "opponent": evaluator.fingerprint(opponent),
        "status": "failed" if failure else "complete", "failure": failure,
        "scores": scores, "steps_completed": len(steps),
        "trace_sha256": trace.hexdigest(), "actions_and_timing": steps,
        "daily_trajectory": daily,
        "actors": [actor.report() for actor in actors],
        "wall_seconds": time.perf_counter() - started,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluator", type=Path, required=True)
    ap.add_argument("--engine-dir", type=Path, required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--opponent", required=True)
    ap.add_argument("--seed", type=int, default=9921001)
    ap.add_argument("--seat", type=int, choices=(0, 1), default=0)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    evaluator = load_module(args.evaluator.resolve())
    engine, hashes = evaluator.get_engine(args.engine_dir, evaluator.LOADER)
    result = play(evaluator, engine, args.engine_dir, evaluator.LOADER,
                  str(Path(args.candidate).resolve()), str(Path(args.opponent).resolve()),
                  args.seed, args.seat)
    report = {
        "schema": "titan.widefield.loss-trace.v1",
        "purpose": "development-case diagnosis; not held evidence",
        "engine_ref": evaluator.ENGINE_REF,
        "engine_sha256": hashes,
        "games": [result],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in
                      ("seed", "candidate_seat", "status", "scores", "failure",
                       "steps_completed", "trace_sha256", "wall_seconds")}, sort_keys=True))
    return 1 if result["status"] != "complete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
