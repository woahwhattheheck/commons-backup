#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""V5-19 ground-state DROP probe against the pinned official engine."""
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
    module = types.ModuleType("_v5_ground_drop_pinned_engine")
    module.__file__ = str(engine_dir / "kaggriculture.py")
    module.resolve_episode_seed = lambda _env: 0
    exec(compile(tree, module.__file__, "exec"), module.__dict__)
    return module


def make_world(engine, *, position: tuple[int, int], step: int):
    farms = [engine._new_farm(10, 3000), engine._new_farm(10, 3000)]
    farms[0]["farmer"] = list(position)
    privates = [engine._new_private(), engine._new_private()]
    privates[0]["inventories"][0]["FERTILIZER"] = 500
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
        episodeSteps=720,
    )
    env = Struct(configuration=cfg, done=False, info={"seed": 0})
    return state, env


def run_case(engine, name: str, position: tuple[int, int], step: int) -> dict:
    state, env = make_world(engine, position=position, step=step)
    before_tile = state[0].observation.farms[0]["tiles"][position[1]][position[0]]
    state[0].action["farmer"] = ["DROP", "FERTILIZER", 500, *position]
    engine.interpreter(state, env)
    farm = state[0].observation.farms[0]
    private = state[0].observation.private
    after_position = tuple(farm["farmer"])
    after_tile = farm["tiles"][after_position[1]][after_position[0]]
    return {
        "case": name,
        "position_before": list(position),
        "position_after": list(after_position),
        "tile_before": before_tile,
        "tile_after": after_tile,
        "inventory_after": private["inventories"][0].get("FERTILIZER", 0),
        "shed_after": private["shed"]["FERTILIZER"],
    }


def run_probe() -> dict:
    engine = load_engine()
    cases = [
        run_case(engine, "empty_non_shed_midday", (1, 1), 97),
        run_case(engine, "locked_non_shed_midday", (9, 9), 97),
        run_case(engine, "locked_shed_access_midday", (5, 4), 97),
        run_case(engine, "empty_non_shed_end_of_day", (1, 1), 119),
    ]
    by_name = {row["case"]: row for row in cases}
    empty = by_name["empty_non_shed_midday"]
    locked = by_name["locked_non_shed_midday"]
    shed_access = by_name["locked_shed_access_midday"]
    eod = by_name["empty_non_shed_end_of_day"]
    checks = {
        "empty_tile_drop_is_noop": (
            empty["tile_after"] is None
            and empty["inventory_after"] == 500
            and empty["shed_after"] == 0
        ),
        "ordinary_locked_tile_drop_is_noop": (
            locked["tile_after"] == "LOCKED"
            and locked["inventory_after"] == 500
            and locked["shed_after"] == 0
        ),
        "locked_shed_access_deposits_only_to_shed": (
            shed_access["tile_after"] == "LOCKED"
            and shed_access["inventory_after"] == 0
            and shed_access["shed_after"] == 100
        ),
        "shed_overflow_is_discarded": (
            shed_access["inventory_after"] + shed_access["shed_after"] == 100
        ),
        "eod_routes_inventory_to_capped_shed_not_ground": (
            eod["tile_after"] is None
            and eod["inventory_after"] == 0
            and eod["shed_after"] == 100
        ),
    }
    return {
        "schema": "titan-v5/ground-drop-persistence/v1",
        "engine": {
            "git_blob": ENGINE_GIT_BLOB,
            "sha256": ENGINE_SHA256,
            "configuration_sha256": CONFIG_SHA256,
        },
        "hypothesis": "DROP can persist inventory on farm tiles outside shed capacity",
        "verdict": "FALSIFIED" if all(checks.values()) else "UNRESOLVED",
        "checks": checks,
        "cases": cases,
        "runtime_change": False,
        "policy_change": False,
    }


if __name__ == "__main__":
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["verdict"] == "FALSIFIED" else 1)
