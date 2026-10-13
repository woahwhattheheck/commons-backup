"""Pinned official-engine MW2 probe; measurement only, never a production policy.

Usage: python seat_market_probe.py --engine-dir PATH --cases 2048 --output receipt.json
PATH must contain kaggriculture.py, kaggriculture.json and the pinned utils.py.
Only synthetic initialization/market/EOD microstates are used; no game bank is read.
"""
from __future__ import annotations

import argparse
import ast
import builtins
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from typing import Any, Callable

PINS = {
    "kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
}


class ProbeError(ValueError):
    """Missing, untrusted, or contradictory probe evidence."""


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def load_engine(directory: Path) -> tuple[ModuleType, dict]:
    """Execute the whole pinned engine, adapting only its external seed import.

    The resolver itself is AST-extracted unchanged from the pinned utils.py.
    No installed kaggle_environments package or global sys.modules edits are used.
    Engine JSON is served from captured verified bytes, not re-read after checking.
    """
    directory = Path(directory).resolve()
    captured = {}
    for name, expected in PINS.items():
        data = (directory / name).read_bytes()
        if git_blob(data) != expected:
            raise ProbeError("source pin mismatch: " + name)
        captured[name] = data
    parsed = ast.parse(captured["utils.py"], filename="pinned/utils.py")
    defs = [n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name == "resolve_episode_seed"]
    if len(defs) != 1:
        raise ProbeError("ambiguous seed resolver")
    scope = {"Any": Any, "Callable": Callable, "random": random}
    exec(compile(ast.Module(body=defs, type_ignores=[]), "pinned/utils.py", "exec"), scope)
    shim = ModuleType("kaggle_environments.utils")
    shim.resolve_episode_seed = scope["resolve_episode_seed"]
    native_import = builtins.__import__
    native_open = builtins.open

    def import_adapter(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "kaggle_environments.utils" and level == 0:
            return shim
        return native_import(name, globals, locals, fromlist, level)

    def open_adapter(file, mode="r", *args, **kwargs):
        # The only import-time engine file read is its verified specification.
        if Path(file).resolve() == directory / "kaggriculture.json" and mode == "r":
            import io
            return io.StringIO(captured["kaggriculture.json"].decode("utf-8"))
        return native_open(file, mode, *args, **kwargs)

    module = ModuleType("titan_pinned_seat_engine")
    module.__file__ = str(directory / "kaggriculture.py")
    module.__dict__["__builtins__"] = dict(vars(builtins), __import__=import_adapter, open=open_adapter)
    exec(compile(captured["kaggriculture.py"], module.__file__, "exec"), module.__dict__)
    sources = {name: {"git_blob": git_blob(data), "bytes": len(data),
                      "sha256": hashlib.sha256(data).hexdigest()} for name, data in captured.items()}
    return module, sources


def initialize(engine, seed: int = 17, **overrides):
    defaults = {k: v.get("default") if isinstance(v, dict) else v
                for k, v in engine.specification["configuration"].items()}
    defaults.update(seed=seed)
    defaults.update(overrides)
    env = SimpleNamespace(configuration=SimpleNamespace(**defaults), info={}, done=False)
    state = [SimpleNamespace(observation=SimpleNamespace(step=0),
                             action={"market": [["BUY_SEED", "WHEAT", 1]]},
                             status="ACTIVE", reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    for s in state:
        s.action = {"farmer": ["PASS"], "hands": [], "market": []}
    return state, env


def snapshot(state, reverse=False):
    farms = copy.deepcopy(state[0].observation.farms)
    private = [copy.deepcopy(s.observation.private) for s in state]
    if reverse:
        farms.reverse()
        private.reverse()
    return {"market": copy.deepcopy(state[0].observation.market), "farms": farms, "private": private}


def swapped(state):
    """Exchange complete logical arms, retaining correct observation.player IDs."""
    out = copy.deepcopy(state)
    out[0].observation.farms.reverse()
    out[0].observation.private, out[1].observation.private = out[1].observation.private, out[0].observation.private
    out[0].action, out[1].action = out[1].action, out[0].action
    return out


def market_pair(engine, state, env):
    direct = copy.deepcopy(state)
    reverse = swapped(state)
    engine._process_market(direct, copy.deepcopy(env))
    engine._process_market(reverse, copy.deepcopy(env))
    a, b = snapshot(direct), snapshot(reverse, reverse=True)
    if canonical(a) != canonical(b):
        raise ProbeError("market player-swap counterexample")
    return a


def synthetic_case(engine, rng, index):
    state, env = initialize(engine, seed=17)
    # Include default cap plus specified nonstandard raw-prefix clamp controls.
    env.configuration.maxMarketOrdersPerTurn = [10, 1, 2, 0, -1][index % 5]
    for item in engine.PRODUCTS:
        state[0].observation.market["inventory"][item] = 10000 + rng.choice([-3000, -450, -1, 0, 1, 450, 3000, 100000])
    engine._refresh_prices(state[0].observation.market)
    for seat, s in enumerate(state):
        farm, private = s.observation.farms[seat], s.observation.private
        farm["money"] = float(rng.choice([0, 1, 10, 50, 500, 3000, 100000]))
        for _ in range(rng.randrange(101)):
            private["shed"][rng.choice(engine.PRODUCTS)] += 1
        for crop in engine.CROPS:
            private["seeds"][crop] = rng.randrange(6)
        for _ in range(rng.randrange(4)):
            # Authored valid own-hand/private surfaces without consuming a market slot.
            farm["hands"].append(engine._spawn_hand(farm, 10))
            private["inventories"].append({})
        farm["hires_today"] = len(farm["hands"])
        s.action["hands"] = [["PASS"] for _ in farm["hands"]]
        rows = []
        for _ in range(rng.randrange(13)):
            op = rng.choice(["SELL", "SELL", "BUY_PRODUCT", "BUY_ANIMAL", "BUY_SEED", "HIRE", "BUY_LAND", "EMPTY", "BAD"])
            if op == "EMPTY":
                rows.append(rng.choice([[], None, "inert"]))
            elif op == "BAD":
                rows.append(rng.choice([["SELL"], ["UNKNOWN", "WHEAT", 1], ["SELL", "WHEAT", 0], ["SELL", "WHEAT", "bad"]]))
            elif op in ("HIRE", "BUY_LAND"):
                rows.append([op])
            else:
                items = list(engine.CROPS) if op == "BUY_SEED" else list(engine.ANIMALS) if op == "BUY_ANIMAL" else engine.PRODUCTS
                rows.append([op, rng.choice(items), rng.choice([1, 2, 10, 50, 100])])
        s.action["market"] = rows
    return state, env


def timing_control(engine, trailing=False, reverse=False):
    state, env = initialize(engine)
    for s in state:
        s.observation.private["shed"]["WOOL"] = 50
        s.action["market"] = [["SELL", "WOOL", 50]]
    if trailing:
        state[1].action["market"].insert(0, [])
    if reverse:
        state = swapped(state)
    engine._process_market(state, env)
    gains = [int(f["money"] - 3000) for f in state[0].observation.farms]
    return gains[::-1] if reverse else gains


def eod_control(engine, seed=0):
    """A boundary witness, NOT a claim of full-game seat exchangeability."""
    state, env = initialize(engine, seed)
    before = copy.deepcopy(state)
    engine._end_of_day(state, env, 0)
    weeds = [[[x, y] for y, row in enumerate(f["tiles"]) for x, tile in enumerate(row)
              if isinstance(tile, dict) and tile.get("kind") == "WEED"] for f in state[0].observation.farms]
    return {"seed": seed, "identical_initial_farms": before[0].observation.farms[0] == before[0].observation.farms[1],
            "weed_tiles_by_seat": weeds, "different_farm_outcomes": weeds[0] != weeds[1]}


def run_probe(engine, sources, cases=2048):
    if type(cases) is not int or not 1 <= cases <= 100000:
        raise ProbeError("cases must be an integer in [1, 100000]")
    initial = []
    for seed in (0, 1, 17, 231):
        state, env = initialize(engine, seed)
        ids = [s.observation.player for s in state]
        if ids != [0, 1] or any(s.observation.private["seeds"]["WHEAT"] for s in state):
            raise ProbeError("initialization seat/action boundary failed")
        initial.append({"seed": seed, "observed_players_before_action": ids, "input_seed_scrubbed": env.configuration.seed is None})
    rng = random.Random(12655)
    transcript = hashlib.sha256()
    operations = set()
    for index in range(cases):
        state, env = synthetic_case(engine, rng, index)
        for s in state:
            for row in s.action["market"]:
                if isinstance(row, list) and row and isinstance(row[0], str):
                    operations.add(row[0])
        result = market_pair(engine, state, env)
        transcript.update(canonical({"index": index, "result": result}))
    sync = timing_control(engine)
    delayed = timing_control(engine, trailing=True)
    sync_swap = timing_control(engine, reverse=True)
    delayed_swap = timing_control(engine, trailing=True, reverse=True)
    if sync != sync_swap or delayed != delayed_swap or sync[0] != sync[1] or delayed[0] <= delayed[1]:
        raise ProbeError("raw-slot/seat discriminator failed")
    eod = next((w for seed in range(64) if (w := eod_control(engine, seed))["different_farm_outcomes"]), None)
    if eod is None:
        raise ProbeError("missing full-episode symmetry countercontrol")
    result = {"schema": "titan-v4-seat-market-probe-v1", "scope": "synthetic official-engine microstates; no full games or promotion",
              "sources": sources, "initialization": initial,
              "market_player_swap": {"cases": cases, "mismatches": 0, "generator_seed": 12655,
                                     "raw_caps": [10, 1, 2, 0, -1], "authored_operations": sorted(operations),
                                     "result_stream_sha256": transcript.hexdigest()},
              "raw_slot_control": {"item": "WOOL", "units_each": 50, "same_raw_slot_cash_gains": sync,
                                   "second_logical_arm_delayed_one_slot_cash_gains": delayed,
                                   "same_results_after_player_swap": True},
              "full_episode_symmetry_countercontrol": eod,
              "nonclaims": ["Kaggle assignment control or prediction", "empirical hosted seat distribution",
                            "rival current-action observability", "full-game seat symmetry", "positive paired margin or feature promotion"]}
    result["receipt_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--cases", type=int, default=2048)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output is not None and args.output.resolve() in {(args.engine_dir / name).resolve() for name in PINS}:
            raise ProbeError("output must not overwrite a pinned source")
        engine, sources = load_engine(args.engine_dir)
        output = canonical(run_probe(engine, sources, args.cases))
        if args.output is not None:
            with tempfile.NamedTemporaryFile(dir=args.output.parent, prefix=".seat-receipt-", delete=False) as tmp:
                temp_name = tmp.name
                try:
                    tmp.write(output)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                except BaseException:
                    Path(temp_name).unlink(missing_ok=True)
                    raise
            try:
                os.replace(temp_name, args.output)
            finally:
                Path(temp_name).unlink(missing_ok=True)
        sys.stdout.buffer.write(output)
        return 0
    except (OSError, ValueError, SyntaxError) as exc:
        print("seat probe: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
