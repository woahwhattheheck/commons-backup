#!/usr/bin/env python3
"""Causal land-timing counterfactuals over retained official-engine traces."""
from __future__ import annotations

import argparse
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import re


LAND_ORDER = ("NE", "SW", "SE")
LAND_PRICES = (1000, 2000, 4000)
MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1),
         "EAST": (1, 0), "WEST": (-1, 0)}


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def trace_identity(path: Path):
    match = re.search(r"-(\d+)\.(?:trace\.)?json\.gz$", path.name)
    seat_match = re.search(r"-([01])\.trace\.json\.gz$", path.name)
    if not match or not seat_match:
        raise ValueError(f"cannot recover seed/seat from {path.name}")
    stem = path.name[:seat_match.start()]
    seed_match = re.search(r"-(\d+)-(?:sell|cok-v10)$", stem)
    if not seed_match:
        raise ValueError(f"cannot recover seed from {path.name}")
    return int(seed_match.group(1)), int(seat_match.group(1))


def read_trace(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows = json.load(stream)
    if len(rows) != 1438:
        raise ValueError(f"expected 1438 seat rows in {path}, got {len(rows)}")
    by_step = {}
    observations = {}
    for row in rows:
        step, seat = int(row["step"]), int(row["seat"])
        by_step.setdefault(step, {})[seat] = copy.deepcopy(row["response"]["action"])
        # Consumer-history traces retain reached observations for the candidate
        # seat only; the fixed opponent rows intentionally contain actions and
        # timings but no observation payload.
        if "observation" in row:
            observations[(step, seat)] = row["observation"]
    actions = [[by_step[step][0], by_step[step][1]] for step in range(719)]
    return actions, observations


def quadrant(x, y, size):
    half = size // 2
    return ("S" if y >= half else "N") + ("E" if x >= half else "W")


def crossing_steps(observations, seat, next_quadrant, board_size):
    crossings = []
    for step in range(719):
        obs = observations[(step, seat)]
        farm = obs["farms"][seat]
        action = obs.get("_candidate_action")
        if action is None:
            continue
        units = [action.get("farmer", ["PASS"]), *action.get("hands", [])]
        positions = [farm["farmer"], *farm["hands"]]
        for position, unit in zip(positions, units):
            if not unit or unit[0] not in MOVES:
                continue
            dx, dy = MOVES[unit[0]]
            x, y = int(position[0]) + dx, int(position[1]) + dy
            if 0 <= x < board_size and 0 <= y < board_size:
                if quadrant(x, y, board_size) == next_quadrant:
                    crossings.append(step)
                    break
    return crossings


def replay(engine, evaluator, actions, seed, seat, *, add_step=None,
           remove_step=None):
    cfg = evaluator.Struct({
        key: value.get("default") if isinstance(value, dict) else value
        for key, value in engine.specification["configuration"].items()
    })
    cfg.seed = seed
    env = evaluator.Struct(configuration=cfg, done=False, info={})
    state = [evaluator.Struct(observation=evaluator.Struct(), action={},
                              status="ACTIVE", reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    banks, lands = [], []
    for step, pair in enumerate(actions):
        for cell in state:
            cell.observation.step = step
        turn = copy.deepcopy(pair)
        market = turn[seat].setdefault("market", [])
        if step == add_step:
            market.append(["BUY_LAND"])
        if step == remove_step:
            removed = False
            for index, order in enumerate(market):
                if not removed and order and order[0] == "BUY_LAND":
                    market[index] = []
                    removed = True
        state[0].action, state[1].action = turn
        engine.interpreter(state, env)
        banks.append(float(state[seat].observation.farms[seat]["money"]))
        lands.append(len(state[seat].observation.farms[seat]["unlocked_quadrants"]))
        if all(cell.status == "DONE" for cell in state):
            break
    return {
        "cash": float(state[seat].reward),
        "rival_cash": float(state[1-seat].reward),
        "banks": banks,
        "lands": lands,
        "status": [cell.status for cell in state],
        "final_private": copy.deepcopy(state[seat].observation.private),
    }


def safe_steps(actions, banks, seat, start, stop, cost, maximum, *, suffix=False):
    accepted = []
    for step in range(start, stop):
        market = actions[step][seat].get("market", [])
        if len(market) >= maximum:
            continue
        horizon = banks[step:] if suffix else banks[step:stop]
        if horizon and min(horizon) >= cost:
            accepted.append(step)
    return accepted


def analyze(path, engine, evaluator):
    seed, seat = trace_identity(path)
    actions, observations = read_trace(path)
    missing = [step for step in range(719)
               if (step, seat) not in observations]
    if missing:
        raise ValueError(
            f"candidate seat {seat} lacks reached observations at {missing[:5]}"
        )
    for step in range(719):
        observations[(step, seat)]["_candidate_action"] = actions[step][seat]
    baseline = replay(engine, evaluator, actions, seed, seat)
    if baseline["status"] != ["DONE", "DONE"]:
        raise ValueError(f"incomplete retained trace: {path}")
    land_steps = [step for step, pair in enumerate(actions)
                  if any(order and order[0] == "BUY_LAND"
                         for order in pair[seat].get("market", []))]
    maximum = 10
    shifted = []
    previous = 0
    for index, target in enumerate(land_steps):
        cost = LAND_PRICES[index]
        eligible = safe_steps(actions, baseline["banks"], seat, previous,
                              target, cost, maximum)
        if eligible:
            step = eligible[0]
            trial = replay(engine, evaluator, actions, seed, seat,
                           add_step=step, remove_step=target)
            shifted.append({"purchase_number": index + 1, "cost": cost,
                            "baseline_step": target, "earliest_safe_step": step,
                            "turns_earlier": target-step,
                            "terminal_cash_delta": trial["cash"]-baseline["cash"],
                            "rival_cash_delta": trial["rival_cash"]-baseline["rival_cash"],
                            "purchase_executed": trial["lands"][-1] == baseline["lands"][-1]})
        previous = target + 1

    extra = None
    if len(land_steps) < len(LAND_PRICES):
        cost = LAND_PRICES[len(land_steps)]
        start = land_steps[-1] + 1 if land_steps else 0
        eligible = safe_steps(actions, baseline["banks"], seat, start, 719,
                              cost, maximum, suffix=True)
        if eligible:
            next_quadrant = LAND_ORDER[len(land_steps)]
            crossings = crossing_steps(observations, seat, next_quadrant, 10)
            candidates = {eligible[0]}
            for crossing in crossings:
                before = [step for step in eligible if step < crossing]
                if before:
                    candidates.add(before[-1])
            trials = []
            for step in sorted(candidates):
                trial = replay(engine, evaluator, actions, seed, seat, add_step=step)
                trials.append({"step": step,
                               "terminal_cash_delta": trial["cash"]-baseline["cash"],
                               "rival_cash_delta": trial["rival_cash"]-baseline["rival_cash"],
                               "purchase_executed": trial["lands"][-1] == baseline["lands"][-1]+1})
            extra = {"purchase_number": len(land_steps)+1, "cost": cost,
                     "next_quadrant": next_quadrant,
                     "eligible_steps": len(eligible),
                     "crossing_steps": crossings,
                     "tested": trials,
                     "best": max(trials, key=lambda row: row["terminal_cash_delta"])}
    return {
        "trace": str(path), "seed": seed, "seat": seat,
        "baseline_cash": baseline["cash"],
        "baseline_rival_cash": baseline["rival_cash"],
        "land_steps": land_steps, "shifted_existing": shifted,
        "extra_land": extra,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("traces", nargs="+", type=Path)
    args = parser.parse_args()
    root = args.archive_root.resolve()
    evaluator = load(root / "checks/reference/evaluator/evaluate.py",
                     "early_capital_evaluator")
    engine, hashes = evaluator.get_engine(
        args.engine_dir.resolve(), root / "checks/reference/evaluator/loader.py")
    games = [analyze(path, engine, evaluator) for path in args.traces]
    result = {
        "method": "retained authored-action counterfactual through official engine",
        "engine_ref": evaluator.ENGINE_REF,
        "engine_sha256": hashes,
        "games": games,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
