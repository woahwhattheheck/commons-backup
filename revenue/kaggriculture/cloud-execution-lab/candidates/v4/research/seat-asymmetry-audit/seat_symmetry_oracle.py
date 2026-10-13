# SPDX-License-Identifier: Apache-2.0
"""Source-pinned seat-symmetry falsifier for the official Kaggriculture engine.

This is offline research tooling for the one canonical V4. It never mutates a
playing agent, publication artifact, default, or Kaggle submission.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
import types
from pathlib import Path

ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
DEFAULT_ENGINE = Path(__file__).resolve().parents[4] / "reference" / "engine" / "kaggriculture.py"


class Struct(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    __setattr__ = dict.__setitem__


def _load_engine(path: Path):
    """Authenticate one engine byte buffer and execute that exact buffer."""
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != ENGINE_SHA256:
        raise ValueError(f"official engine identity mismatch: {actual}")
    package = types.ModuleType("kaggle_environments")
    utils = types.ModuleType("kaggle_environments.utils")

    def _no_seed_resolution(_env):
        raise RuntimeError("seat symmetry oracle must not initialize an episode")

    utils.resolve_episode_seed = _no_seed_resolution
    old_pkg = sys.modules.get("kaggle_environments")
    old_utils = sys.modules.get("kaggle_environments.utils")
    sys.modules["kaggle_environments"] = package
    sys.modules["kaggle_environments.utils"] = utils
    try:
        module = types.ModuleType("_seat_symmetry_engine")
        module.__file__ = str(path)
        module.__package__ = ""
        code = compile(raw, str(path), "exec", dont_inherit=True)
        exec(code, module.__dict__, module.__dict__)
        return module
    finally:
        if old_pkg is None:
            sys.modules.pop("kaggle_environments", None)
        else:
            sys.modules["kaggle_environments"] = old_pkg
        if old_utils is None:
            sys.modules.pop("kaggle_environments.utils", None)
        else:
            sys.modules["kaggle_environments.utils"] = old_utils


def _config(**overrides):
    cfg = Struct(boardSize=10, startingMoney=100_000, maxMarketOrdersPerTurn=10,
                 farmHandCostMult=1, shedCapacity=100, turnsPerDay=24,
                 weedSpawnChance=0.005, townShopSellInterval=4,
                 townCenterSellInterval=24, townShopUnlockInterval=3,
                 episodeSteps=720)
    cfg.update(overrides)
    return cfg


def _fresh_state(engine, *, seed=1, weed=0.005, step=0, money=100_000):
    farms = [engine._new_farm(10, money) for _ in range(2)]
    privates = [engine._new_private() for _ in range(2)]
    for private in privates:
        for item in engine.PRODUCTS:
            private["shed"][item] = 4
        for animal in engine.ANIMALS:
            private["shed"][animal] = 1
        for crop in engine.CROPS:
            private["seeds"][crop] = 12
    market = engine._new_market()
    town = engine._new_town()
    observations = [Struct(farms=farms, market=market, town=town, day=step // 24,
                           hour=step % 24, step=step, player=seat,
                           private=privates[seat]) for seat in range(2)]
    state = [Struct(observation=observations[seat], action={}, status="ACTIVE", reward=0)
             for seat in range(2)]
    env = Struct(configuration=_config(weedSpawnChance=weed), done=False,
                 info={"seed": seed})
    return state, env


def _seat_snapshot(state, seat):
    obs = state[seat].observation
    return {"farm": copy.deepcopy(obs.farms[seat]),
            "private": copy.deepcopy(obs.private)}


def _assert_swapped(run_ab, run_ba):
    left = [_seat_snapshot(run_ab, 0), _seat_snapshot(run_ab, 1)]
    right = [_seat_snapshot(run_ba, 1), _seat_snapshot(run_ba, 0)]
    if left != right:
        raise AssertionError("seat-swapped private/farm outcomes diverged")
    if run_ab[0].observation.market != run_ba[0].observation.market:
        raise AssertionError("seat-swapped shared market diverged")
    if run_ab[0].observation.town != run_ba[0].observation.town:
        raise AssertionError("seat-swapped shared town diverged")


def _random_order(rng, engine):
    item = rng.choice(engine.PRODUCTS)
    choices = [["HIRE"], ["BUY_LAND"], ["SELL", item, rng.randint(1, 4)],
               ["BUY_PRODUCT", rng.choice(["WHEAT", "FERTILIZER"]), rng.randint(1, 4)],
               ["BUY_SEED", rng.choice(sorted(engine.CROPS)), rng.randint(1, 4)],
               ["BUY_ANIMAL", rng.choice(sorted(engine.ANIMALS)), rng.randint(1, 2)], []]
    return copy.deepcopy(rng.choice(choices))


def market_swap_trials(engine, *, trials=128, seed=99117):
    rng = random.Random(seed)
    engaged = 0
    for index in range(trials):
        q_a = [_random_order(rng, engine) for _ in range(rng.randint(1, 8))]
        q_b = [_random_order(rng, engine) for _ in range(rng.randint(1, 8))]
        state_ab, env_ab = _fresh_state(engine, seed=index + 10)
        state_ba, env_ba = _fresh_state(engine, seed=index + 10)
        if index % 4 == 0:
            state_ab[0].observation.market["inventory"]["FERTILIZER"] = 1_000_000
            state_ba[0].observation.market["inventory"]["FERTILIZER"] = 1_000_000
            engine._refresh_prices(state_ab[0].observation.market)
            engine._refresh_prices(state_ba[0].observation.market)
        state_ab[0].action = {"market": copy.deepcopy(q_a)}
        state_ab[1].action = {"market": copy.deepcopy(q_b)}
        state_ba[0].action = {"market": copy.deepcopy(q_b)}
        state_ba[1].action = {"market": copy.deepcopy(q_a)}
        before_ab = copy.deepcopy(state_ab[0].observation.market)
        engine._process_market(state_ab, env_ab)
        engine._process_market(state_ba, env_ba)
        _assert_swapped(state_ab, state_ba)
        if state_ab[0].observation.market != before_ab:
            engaged += 1
    if engaged == 0:
        raise AssertionError("market-symmetry trials never engaged shared market state")
    return {"trials": trials, "engaged_market_trials": engaged}


def full_step_swap_trials(engine, *, trials=64, seed=5501):
    rng = random.Random(seed)
    for index in range(trials):
        step = rng.randrange(0, 23)
        state_ab, env_ab = _fresh_state(engine, seed=index + 100, weed=0.0, step=step)
        state_ba, env_ba = _fresh_state(engine, seed=index + 100, weed=0.0, step=step)
        q_a = [_random_order(rng, engine) for _ in range(rng.randint(0, 5))]
        q_b = [_random_order(rng, engine) for _ in range(rng.randint(0, 5))]
        state_ab[0].action = {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(q_a)}
        state_ab[1].action = {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(q_b)}
        state_ba[0].action = {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(q_b)}
        state_ba[1].action = {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(q_a)}
        engine.interpreter(state_ab, env_ab)
        engine.interpreter(state_ba, env_ba)
        _assert_swapped(state_ab, state_ba)
    return {"trials": trials}


def weed_stream_witness(engine, *, search_seeds=64):
    for seed in range(search_seeds):
        state, env = _fresh_state(engine, seed=seed, weed=0.5, step=23)
        for seat in (0, 1):
            state[seat].action = {"farmer": ["PASS"], "hands": [], "market": []}
        engine.interpreter(state, env)
        farm0 = state[0].observation.farms[0]["tiles"]
        farm1 = state[0].observation.farms[1]["tiles"]
        if farm0 != farm1:
            return {"seed": seed, "different": True}
    raise AssertionError("no seat-indexed weed-stream witness found")


def weed_off_eod_control(engine):
    state, env = _fresh_state(engine, seed=7, weed=0.0, step=23)
    for seat in (0, 1):
        state[seat].action = {"farmer": ["PASS"], "hands": [], "market": []}
    engine.interpreter(state, env)
    if state[0].observation.farms[0] != state[0].observation.farms[1]:
        raise AssertionError("weed-off symmetric EOD control diverged")
    return {"symmetric": True}


def run(engine_path: Path, *, market_trials=128, step_trials=64):
    engine = _load_engine(engine_path)
    return {"schema": "titan-v4-seat-symmetry-oracle/v1",
            "engine_sha256": ENGINE_SHA256,
            "market": market_swap_trials(engine, trials=market_trials),
            "non_eod_full_interpreter": full_step_swap_trials(engine, trials=step_trials),
            "weed_off_eod": weed_off_eod_control(engine),
            "weed_stream_witness": weed_stream_witness(engine),
            "interpretation": {"market_seat_order_causal": False,
                               "eod_weed_rng_is_seat_indexed": True,
                               "promotion_decision": "NOT_ASSESSED"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=DEFAULT_ENGINE)
    parser.add_argument("--market-trials", type=int, default=128)
    parser.add_argument("--step-trials", type=int, default=64)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.market_trials <= 0 or args.step_trials <= 0:
        parser.error("trial counts must be positive")
    report = run(args.engine, market_trials=args.market_trials, step_trials=args.step_trials)
    text = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
