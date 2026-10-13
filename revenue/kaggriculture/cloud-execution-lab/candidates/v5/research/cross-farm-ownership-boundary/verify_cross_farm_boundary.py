#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Executable V5-25 probe against the pinned Kaggriculture engine.

The framework seed helper is the only shim.  Every transition exercised by the
probe is compiled unchanged from the pinned engine source.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import types


ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
CONFIG_SHA256 = "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867"


class Struct(dict):
    """Small attribute-access mapping matching Kaggle's observation objects."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    __setattr__ = dict.__setitem__


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def locate_engine() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "reference" / "engine"
        if (candidate / "kaggriculture.py").is_file():
            return candidate
    raise RuntimeError("pinned reference/engine directory not found")


def load_engine(engine_dir: Path | None = None):
    engine_dir = engine_dir or locate_engine()
    source = (engine_dir / "kaggriculture.py").read_bytes()
    config = (engine_dir / "kaggriculture.json").read_bytes()
    if git_blob_sha1(source) != ENGINE_GIT_BLOB:
        raise ValueError("official engine git-blob mismatch")
    if hashlib.sha256(source).hexdigest() != ENGINE_SHA256:
        raise ValueError("official engine sha256 mismatch")
    if hashlib.sha256(config).hexdigest() != CONFIG_SHA256:
        raise ValueError("official configuration sha256 mismatch")

    tree = ast.parse(source)
    framework_imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "kaggle_environments.utils"
    ]
    if len(framework_imports) != 1:
        raise ValueError("unexpected framework import shape")
    tree.body.remove(framework_imports[0])

    module = types.ModuleType("_v5_cross_farm_pinned_engine")
    module.__file__ = str(engine_dir / "kaggriculture.py")
    module.resolve_episode_seed = lambda _env: 0
    exec(compile(tree, module.__file__, "exec"), module.__dict__)
    return module


def mature_carrot(engine):
    tile = engine._new_plant("CARROT", 0, 24)
    tile["yield_units"] = 3
    tile["max_lifespan_step"] = -1
    return tile


def make_world(engine, attacker_tile=None, target_tile=None):
    farms = [engine._new_farm(10, 3000), engine._new_farm(10, 3000)]
    privates = [engine._new_private(), engine._new_private()]
    farms[0]["farmer"] = [4, 4]
    farms[0]["tiles"][4][4] = attacker_tile
    farms[1]["tiles"][1][1] = target_tile
    market = engine._new_market()
    town = engine._new_town()
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
    cfg.update(boardSize=10, turnsPerDay=24, shedCapacity=100,
               weedSpawnChance=0.0, episodeSteps=720)
    env = Struct(configuration=cfg, done=False, info={"seed": 0})
    return state, env


def apply_turn(engine, action, *, attacker_tile=None, target_tile=None):
    state, env = make_world(engine, attacker_tile, target_tile)
    state[0].action["farmer"] = action
    before = deepcopy(state[0].observation.farms)
    engine.interpreter(state, env)
    return state, before


def run_probe(engine_dir: Path | None = None) -> dict:
    engine = load_engine(engine_dir)

    target = mature_carrot(engine)
    state, before = apply_turn(
        engine, ["HARVEST", 1, 1], attacker_tile=None, target_tile=deepcopy(target)
    )
    harvest_target_unchanged = state[0].observation.farms[1]["tiles"][1][1] == target
    harvest_gained_nothing = not state[0].observation.private["inventories"][0]
    harvest_attacker_unchanged = state[0].observation.farms[0] == before[0]

    state, before = apply_turn(
        engine, ["CLEAR", 1, 1], attacker_tile={"kind": "WEED"},
        target_tile=deepcopy(target)
    )
    clear_is_unknown_noop = state[0].observation.farms == before

    state, _before = apply_turn(
        engine, ["DIG", 1, 1], attacker_tile={"kind": "WEED"},
        target_tile=deepcopy(target)
    )
    dig_only_local = (
        state[0].observation.farms[0]["tiles"][4][4] is None
        and state[0].observation.farms[1]["tiles"][1][1] == target
    )

    own = mature_carrot(engine)
    state, _before = apply_turn(
        engine, ["HARVEST", 1, 1], attacker_tile=deepcopy(own),
        target_tile=deepcopy(target)
    )
    harvest_extra_coordinates_ignored = (
        state[0].observation.private["inventories"][0] == {"CARROT": 3}
        and state[0].observation.farms[1]["tiles"][1][1] == target
    )

    checks = {
        "harvest_target_unchanged": harvest_target_unchanged,
        "harvest_gained_nothing": harvest_gained_nothing,
        "harvest_attacker_unchanged": harvest_attacker_unchanged,
        "clear_is_unknown_noop": clear_is_unknown_noop,
        "dig_only_mutates_acting_farm": dig_only_local,
        "harvest_coordinate_tail_is_ignored": harvest_extra_coordinates_ignored,
    }
    return {
        "schema": "titan-v5/cross-farm-ownership-boundary/v1",
        "engine": {
            "git_blob": ENGINE_GIT_BLOB,
            "sha256": ENGINE_SHA256,
            "configuration_sha256": CONFIG_SHA256,
        },
        "hypothesis": "an actor can HARVEST or clear a rival farm by supplying coordinates",
        "verdict": "FALSIFIED" if all(checks.values()) else "UNRESOLVED",
        "checks": checks,
        "runtime_change": False,
        "policy_change": False,
    }


if __name__ == "__main__":
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["verdict"] == "FALSIFIED" else 1)
