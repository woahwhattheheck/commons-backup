#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""V5-23 inventory-underflow crash probe on the pinned official engine."""
from __future__ import annotations

import ast
import hashlib
import json
import math
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
    module = types.ModuleType("_v5_market_underflow_pinned_engine")
    module.__file__ = str(engine_dir / "kaggriculture.py")
    module.resolve_episode_seed = lambda _env: 0
    exec(compile(tree, module.__file__, "exec"), module.__dict__)
    return module


def make_world(engine, *, step: int, money: float = 3000):
    farms = [engine._new_farm(10, money), engine._new_farm(10, money)]
    privates = [engine._new_private(), engine._new_private()]
    market = engine._new_market()
    town = engine._new_town()
    observations = [
        Struct(
            player=i,
            step=step,
            day=step // 24,
            hour=step % 24,
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
        townShopSellInterval=4,
        townCenterSellInterval=24,
        episodeSteps=720,
    )
    env = Struct(configuration=cfg, done=False, info={"seed": 0})
    return state, env


def expected_consumption(engine, item: str) -> int:
    center = 1 if item in engine.TOWN_CENTER_PRODUCTS else 0
    shops = 0
    for products in engine.SHOPS.values():
        if item in products:
            shops += 2 if len(products) == 1 else 1
    return center + shops


def town_boundary(engine, initial_inventory: int) -> dict:
    state, env = make_world(engine, step=0)
    market = state[0].observation.market
    market["inventory"] = {item: initial_inventory for item in engine.PRODUCTS}
    state[0].observation.town["unlocked_shops"] = sorted(engine.SHOPS)
    engine.interpreter(state, env)
    return {
        "initial_inventory": initial_inventory,
        "final_inventory": dict(market["inventory"]),
        "prices": dict(market["prices"]),
    }


def buy_beyond_zero(engine) -> dict:
    state, env = make_world(engine, step=97, money=1_000_000_000)
    market = state[0].observation.market
    market["inventory"]["WHEAT"] = 1
    engine._refresh_prices(market)
    before_money = state[0].observation.farms[0]["money"]
    state[0].action["market"] = [["BUY_PRODUCT", "WHEAT", 2]]
    engine.interpreter(state, env)
    return {
        "initial_inventory": 1,
        "final_inventory": market["inventory"]["WHEAT"],
        "units_bought": state[0].observation.private["shed"]["WHEAT"],
        "money_spent": before_money - state[0].observation.farms[0]["money"],
        "final_price": market["prices"]["WHEAT"],
    }


def run_probe() -> dict:
    engine = load_engine()
    town_runs = [town_boundary(engine, value) for value in (1, 0, -1)]
    buy_run = buy_beyond_zero(engine)
    expected = {item: expected_consumption(engine, item) for item in engine.PRODUCTS}
    checks = {
        "town_consumption_uses_signed_python_ints": all(
            all(type(value) is int for value in row["final_inventory"].values())
            for row in town_runs
        ),
        "town_consumption_matches_exact_decrements": all(
            row["final_inventory"][item] == row["initial_inventory"] - expected[item]
            for row in town_runs
            for item in engine.PRODUCTS
        ),
        "negative_inventory_is_reached_without_wrap": any(
            value < 0
            for row in town_runs
            for value in row["final_inventory"].values()
        ),
        "all_refreshed_prices_are_finite_positive_ints": all(
            type(price) is int and price >= 1 and math.isfinite(price)
            for row in town_runs
            for price in row["prices"].values()
        ),
        "buy_can_cross_zero_without_crash": (
            buy_run["final_inventory"] == -1
            and buy_run["units_bought"] == 2
            and buy_run["money_spent"] > 0
            and type(buy_run["final_price"]) is int
            and buy_run["final_price"] >= 1
        ),
    }
    return {
        "schema": "titan-v5/market-inventory-underflow/v1",
        "engine": {
            "git_blob": ENGINE_GIT_BLOB,
            "sha256": ENGINE_SHA256,
            "configuration_sha256": CONFIG_SHA256,
        },
        "hypothesis": "zero inventory underflows or crashes town pricing",
        "verdict": "FALSIFIED" if all(checks.values()) else "UNRESOLVED",
        "checks": checks,
        "expected_consumption": expected,
        "town_runs": town_runs,
        "buy_beyond_zero": buy_run,
        "runtime_change": False,
        "policy_change": False,
    }


if __name__ == "__main__":
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["verdict"] == "FALSIFIED" else 1)
