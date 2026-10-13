#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""V5-21 physical shop-blockade probe against the pinned official engine."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import types


ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
CONFIG_SHA256 = "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867"


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    __setattr__ = dict.__setitem__


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def load_engine():
    engine_dir = next(
        (
            parent / "reference" / "engine"
            for parent in Path(__file__).resolve().parents
            if (parent / "reference" / "engine" / "kaggriculture.py").is_file()
        ),
        None,
    )
    if engine_dir is None:
        raise RuntimeError("pinned reference/engine directory not found")
    source = (engine_dir / "kaggriculture.py").read_bytes()
    config = (engine_dir / "kaggriculture.json").read_bytes()
    if git_blob_sha1(source) != ENGINE_GIT_BLOB:
        raise ValueError("official engine git-blob mismatch")
    if hashlib.sha256(source).hexdigest() != ENGINE_SHA256:
        raise ValueError("official engine sha256 mismatch")
    if hashlib.sha256(config).hexdigest() != CONFIG_SHA256:
        raise ValueError("official configuration sha256 mismatch")
    tree = ast.parse(source)
    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "kaggle_environments.utils"
    ]
    if len(imports) != 1:
        raise ValueError("unexpected framework import shape")
    tree.body.remove(imports[0])
    module = types.ModuleType("_v5_shop_blockade_pinned_engine")
    module.__file__ = str(engine_dir / "kaggriculture.py")
    module.resolve_episode_seed = lambda _env: 0
    exec(compile(tree, module.__file__, "exec"), module.__dict__)
    return module


def make_world(engine, actor_seat: int):
    farms = [engine._new_farm(10, 3000), engine._new_farm(10, 3000)]
    privates = [engine._new_private(), engine._new_private()]
    blocker_seat = 1 - actor_seat
    # Maximal same-coordinate occupancy on the other farm. The coordinate is
    # deliberately the shed-access coordinate used by every starting farmer.
    farms[blocker_seat]["farmer"] = [4, 4]
    farms[blocker_seat]["hands"] = [[4, 4] for _ in range(10)]
    market = engine._new_market()
    town = {"unlocked_shops": ["BAKERY"]}
    observations = [
        Struct(
            player=i,
            step=97,
            day=4,
            hour=1,
            farms=farms,
            private=privates[i],
            market=market,
            town=town,
        )
        for i in range(2)
    ]
    state = [
        Struct(
            observation=observations[i],
            action={"farmer": ["PASS"], "hands": [], "market": []},
            status="ACTIVE",
            reward=0,
        )
        for i in range(2)
    ]
    cfg = Struct(
        {
            key: value.get("default") if isinstance(value, dict) else value
            for key, value in engine.specification["configuration"].items()
        }
    )
    cfg.update(
        boardSize=10,
        turnsPerDay=24,
        shedCapacity=100,
        weedSpawnChance=0.0,
        episodeSteps=720,
    )
    env = Struct(configuration=cfg, done=False, info={"seed": 0})
    return state, env, blocker_seat


def buy_probe(engine, seat: int) -> dict:
    state, env, blocker = make_world(engine, seat)
    before_money = state[0].observation.farms[seat]["money"]
    state[seat].action["market"] = [
        ["BUY_SEED", "CARROT", 1],
        ["BUY_PRODUCT", "WHEAT", 1],
    ]
    engine.interpreter(state, env)
    private = state[seat].observation.private
    return {
        "seat": seat,
        "blocker_seat": blocker,
        "blocker_actor_count": 11,
        "carrot_seeds_bought": private["seeds"]["CARROT"],
        "wheat_bought": private["shed"]["WHEAT"],
        "money_spent": before_money - state[0].observation.farms[seat]["money"],
    }


def sell_probe(engine, seat: int) -> dict:
    state, env, blocker = make_world(engine, seat)
    state[seat].observation.private["shed"]["CARROT"] = 1
    before_money = state[0].observation.farms[seat]["money"]
    state[seat].action["market"] = [["SELL", "CARROT", 1]]
    engine.interpreter(state, env)
    private = state[seat].observation.private
    return {
        "seat": seat,
        "blocker_seat": blocker,
        "blocker_actor_count": 11,
        "carrots_after": private["shed"]["CARROT"],
        "money_gained": state[0].observation.farms[seat]["money"] - before_money,
    }


def run_probe() -> dict:
    engine = load_engine()
    buys = [buy_probe(engine, seat) for seat in (0, 1)]
    sells = [sell_probe(engine, seat) for seat in (0, 1)]
    checks = {
        "buy_seed_works_both_seats": all(row["carrot_seeds_bought"] == 1 for row in buys),
        "buy_product_works_both_seats": all(row["wheat_bought"] == 1 for row in buys),
        "buy_spends_positive_cash": all(row["money_spent"] > 0 for row in buys),
        "sell_works_both_seats": all(
            row["carrots_after"] == 0 and row["money_gained"] > 0 for row in sells
        ),
        "opponent_blocker_panel_present": all(
            row["blocker_actor_count"] == 11 for row in buys + sells
        ),
    }
    return {
        "schema": "titan-v5/shop-blockade-collision/v1",
        "engine": {
            "git_blob": ENGINE_GIT_BLOB,
            "sha256": ENGINE_SHA256,
            "configuration_sha256": CONFIG_SHA256,
        },
        "hypothesis": "opponent workers can physically block market or shop access",
        "verdict": "FALSIFIED" if all(checks.values()) else "UNRESOLVED",
        "checks": checks,
        "buy_runs": buys,
        "sell_runs": sells,
        "runtime_change": False,
        "policy_change": False,
    }


if __name__ == "__main__":
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["verdict"] == "FALSIFIED" else 1)
