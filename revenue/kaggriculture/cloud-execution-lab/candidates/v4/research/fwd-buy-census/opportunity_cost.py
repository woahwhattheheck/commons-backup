# SPDX-License-Identifier: Apache-2.0
"""Offline, source-pinned FWD-BUY opportunity-cost experiments; not a policy.

Runs constructed day-3 trajectories through the full official interpreter.
No donor, runtime, census decoder, network, or gameplay function is substituted.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import random
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Callable

CALLBACKS = 0

ENGINE_BLOBS = {
    "kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
}


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        self[key] = value


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def load_engine(directory):
    """Execute precisely authenticated bytes, including the real seed helper."""
    raw = {name: (Path(directory) / name).read_bytes() for name in ENGINE_BLOBS}
    for name, expected in ENGINE_BLOBS.items():
        if git_blob(raw[name]) != expected:
            raise ValueError("official source mismatch: " + name)
    parsed = ast.parse(raw["utils.py"])
    helper = next(n for n in parsed.body
                  if isinstance(n, ast.FunctionDef) and n.name == "resolve_episode_seed")
    namespace = {"Any": Any, "Callable": Callable, "random": random}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "pinned_seed_helper", "exec"), namespace)
    names = ("kaggle_environments", "kaggle_environments.utils")
    previous = {name: sys.modules.get(name) for name in names}
    package = types.ModuleType(names[0])
    utils = types.ModuleType(names[1])
    utils.resolve_episode_seed = namespace["resolve_episode_seed"]
    try:
        sys.modules[names[0]], sys.modules[names[1]] = package, utils
        # The official module opens its JSON sibling while loading. Use a private
        # staging directory, not a second read from the original source directory.
        with tempfile.TemporaryDirectory(prefix="fwd-engine-") as tmp:
            for name, data in raw.items():
                (Path(tmp) / name).write_bytes(data)
            engine = types.ModuleType("fwd_pinned_engine")
            engine.__file__ = str(Path(tmp) / "kaggriculture.py")
            exec(compile(raw["kaggriculture.py"], engine.__file__, "exec"), engine.__dict__)
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
    return engine, {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()}


def action(farmer="PASS", hands=(), market=()):
    return {"farmer": [farmer], "hands": [[op] for op in hands],
            "market": copy.deepcopy(list(market))}


def fixture(engine, seat, *, cash=3000, wheat_inventory=10000, shops=0):
    if type(seat) is not int or seat not in (0, 1):
        raise ValueError("seat must be 0 or 1")
    cfg = Struct({k: v.get("default") if isinstance(v, dict) else v
                  for k, v in engine.specification["configuration"].items()})
    cfg.weedSpawnChance = 0
    farms = [engine._new_farm(10, cash), engine._new_farm(10, cash)]
    market = engine._new_market()
    market["inventory"]["WHEAT"] = wheat_inventory
    engine._refresh_prices(market)
    town = {"unlocked_shops": ["BAKERY"] * shops}
    state = [Struct(observation=Struct(player=i, step=90, day=3, hour=18,
                 farms=farms, market=market, town=town, private=engine._new_private()),
                 action=action(), status="ACTIVE", reward=0) for i in range(2)]
    return state, Struct(configuration=cfg, done=False, info={"seed": 9600803})


def plant(engine, yield_units):
    tile = engine._new_plant("CARROT", 0, 24)
    tile.update(yield_units=yield_units, consecutive_unwatered=0, watered_today=True)
    return tile


def tick(engine, state, env, seat, step, own_action):
    global CALLBACKS
    for s in state:
        s.observation.step = step
        s.observation.day, s.observation.hour = divmod(step, env.configuration.turnsPerDay)
        s.action = action()
    state[seat].action = copy.deepcopy(own_action)
    before = state[seat].observation.farms[seat]["money"]
    engine.interpreter(state, env)
    CALLBACKS += 1
    obs = state[seat].observation
    return {"step": step, "action": copy.deepcopy(own_action),
            "cash_delta": obs.farms[seat]["money"] - before,
            "cash": obs.farms[seat]["money"], "shed": copy.deepcopy(obs.private["shed"]),
            "inventories": copy.deepcopy(obs.private["inventories"]),
            "hands": copy.deepcopy(obs.farms[seat]["hands"])}


def physical(state, seat):
    """Both farms and private stocks, excluding cash and the shared market."""
    farms = copy.deepcopy(state[seat].observation.farms)
    for farm in farms:
        farm.pop("money")
    return {"farms": farms, "private": [copy.deepcopy(s.observation.private) for s in state]}


def finish(state, seat, trace):
    obs = state[seat].observation
    return {"cash": obs.farms[seat]["money"],
            "rival_cash": obs.farms[1-seat]["money"],
            "physical": physical(state, seat),
            "market_inventory": copy.deepcopy(obs.market["inventory"]), "trace": trace}


def headroom_pair(engine, *, seat=0, quantity=4, room=4, harvest=4,
                  wheat_inventory=10000, shops=1):
    """Same CARROT harvest and later outlet; equal delivered WHEAT, three arms.

    Fixtures stay in FWD's named days-0..3 regime: CARROT is mature on day 3.
    They are constructed states, not claims that any runtime produced them.
    """
    for name, value in (("quantity", quantity), ("room", room), ("harvest", harvest)):
        if type(value) is not int or value < 0:
            raise ValueError(name + " must be a nonnegative integer")
    if not quantity <= room <= 100 or harvest > 4:
        raise ValueError("require quantity <= room <= 100 and CARROT harvest <= 4")
    world = fixture(engine, seat, wheat_inventory=wheat_inventory, shops=shops)
    state, _ = world
    farm = state[seat].observation.farms[seat]
    x, y = farm["farmer"]
    farm["tiles"][y][x] = plant(engine, harvest)
    state[seat].observation.private["shed"]["CARROT"] = 100 - room
    result = {}
    for arm in ("early_hold", "jit", "early_unwind"):
        current, env = copy.deepcopy(world)
        trace = []
        for step in range(92, 98):
            orders = []
            if quantity and step == 92 and arm != "jit":
                orders = [["BUY_PRODUCT", "WHEAT", quantity]]
            if quantity and step == 95 and arm == "early_unwind":
                orders = [["SELL", "WHEAT", quantity]]
            if step == 96:
                orders = [["SELL", "CARROT", 100]]
            if quantity and step == 97 and arm != "early_hold":
                orders = [["BUY_PRODUCT", "WHEAT", quantity]]
            trace.append(tick(engine, current, env, seat, step,
                              action("HARVEST" if step == 92 else "PASS", market=orders)))
        result[arm] = finish(current, seat, trace)
    return result


def capital_pair(engine, *, seat=0, cash=26):
    """A $26 early WHEAT purchase may block the next callback's $1 HIRE.

    A common later DIG clears the unharvested annual crop, so final physical
    state is equal. This is a fixed-script opportunity, not optimal play.
    """
    world = fixture(engine, seat, cash=cash, shops=1)
    state, _ = world
    farm = state[seat].observation.farms[seat]
    farm["farmer"] = [4, 3]
    farm["tiles"][4][4] = plant(engine, 4)
    result = {}
    for arm in ("early_hold", "jit"):
        current, env = copy.deepcopy(world)
        trace = []
        for step in range(90, 98):
            orders = []
            if step == 90 and arm == "early_hold":
                orders = [["BUY_PRODUCT", "WHEAT", 1]]
            if step == 91:
                orders = [["HIRE"]]
            if step == 93:
                orders = [["SELL", "CARROT", 4]]
            if step == 94 and arm == "jit":
                orders = [["BUY_PRODUCT", "WHEAT", 1]]
            # EOD95 resets both farmers onto the crop at (4, 4).
            farmer = "DIG" if step == 96 else "PASS"
            hands = ("HARVEST",) if step == 92 else ("DROP",) if step == 93 else ()
            trace.append(tick(engine, current, env, seat, step,
                              action(farmer, hands, orders)))
        result[arm] = finish(current, seat, trace)
    return result


def summary(pair):
    base = pair["jit"]
    return {arm: {"cash": row["cash"], "delta_own": row["cash"]-base["cash"],
                  "delta_rival": row["rival_cash"]-base["rival_cash"],
                  "delta_margin": row["cash"]-base["cash"]-row["rival_cash"]+base["rival_cash"],
                  "same_final_physical": row["physical"] == base["physical"],
                  "cash_deltas_by_tick": [t["cash_delta"] for t in row["trace"]]}
            for arm, row in pair.items()}


def run_panel(engine):
    """Return ALL declared synthetic cells, including zero-effect controls."""
    rows = []
    for seat in (0, 1):
        for q in (1, 2, 4, 8, 20):
            for room in (q, q+4, 100):
                for harvest in (1, 2, 4):
                    for inventory in (9996, 10000, 10020):
                        for shops in (0, 1):
                            cfg = dict(seat=seat, quantity=q, room=room, harvest=harvest,
                                       wheat_inventory=inventory, shops=shops)
                            pair = headroom_pair(engine, **cfg)
                            expected_loss = min(harvest, room)-min(harvest, room-q)
                            observed_loss = (pair["jit"]["trace"][3]["shed"]["CARROT"]
                                             - pair["early_hold"]["trace"][3]["shed"]["CARROT"])
                            if observed_loss != expected_loss:
                                raise RuntimeError("headroom accounting mismatch: " + repr(cfg))
                            stats = summary(pair)
                            if not all(s["same_final_physical"] for s in stats.values()):
                                raise RuntimeError("unmatched final physical state: " + repr(cfg))
                            rows.append({"configuration": cfg, "lost_carrot": observed_loss,
                                         "arms": stats})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        engine, hashes = load_engine(args.engine_dir)
        rows = run_panel(engine)
        report = {"schema": "titan.fwd-opportunity-cost.v1", "engine_sha256": hashes,
                  "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "scope": "constructed day-3 full-interpreter trajectories; no donor/runtime/field gate",
                  "cells": len(rows), "headroom_cells": rows,
                  "headroom_witness": summary(headroom_pair(engine)),
                  "capital_witness": [summary(capital_pair(engine, seat=s)) for s in (0, 1)],
                  "capital_funded_control": [summary(capital_pair(engine, seat=s, cash=27)) for s in (0, 1)],
                  "limits": ["No natural engagement or win-rate claim", "No promotion or default change",
                             "Shared market inventory may differ; both farms/private stocks match",
                             "Known future actions are experiment labels, never policy inputs"]}
        report["full_interpreter_callbacks"] = CALLBACKS
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(json.dumps({"cells": len(rows), "headroom_witness": report["headroom_witness"],
                      "capital_witness": report["capital_witness"],
                      "capital_funded_control": report["capital_funded_control"]}, sort_keys=True))


if __name__ == "__main__":
    main()
