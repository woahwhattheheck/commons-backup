#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""V5-22 same-tick harvest probe against the pinned official engine."""
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
    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "kaggle_environments.utils"
    ]
    if len(imports) != 1:
        raise ValueError("unexpected framework import shape")
    tree.body.remove(imports[0])
    module = types.ModuleType("_v5_double_harvest_pinned_engine")
    module.__file__ = str(engine_dir / "kaggriculture.py")
    module.resolve_episode_seed = lambda _env: 0
    exec(compile(tree, module.__file__, "exec"), module.__dict__)
    return module


def mature_carrot(engine):
    tile = engine._new_plant("CARROT", 0, 24)
    tile["yield_units"] = 3
    tile["max_lifespan_step"] = -1
    return tile


def make_world(engine):
    farms = [engine._new_farm(10, 3000), engine._new_farm(10, 3000)]
    farms[0]["farmer"] = [4, 4]
    farms[0]["hands"] = [[4, 4], [4, 4]]
    farms[0]["tiles"][4][4] = mature_carrot(engine)
    privates = [engine._new_private(), engine._new_private()]
    privates[0]["inventories"] = [{}, {}, {}]
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
    cfg.update(
        boardSize=10,
        turnsPerDay=24,
        shedCapacity=100,
        weedSpawnChance=0.0,
        episodeSteps=720,
    )
    env = Struct(configuration=cfg, done=False, info={"seed": 0})
    return state, env


def run_order(engine, winner: int) -> dict:
    state, env = make_world(engine)
    actions = [["PASS"], ["PASS"], ["PASS"]]
    actions[winner] = ["HARVEST", 4, 4]
    # Every other actor also attempts the same harvest later in the same turn.
    for index in range(winner + 1, 3):
        actions[index] = ["HARVEST", 4, 4]
    state[0].action = {
        "farmer": actions[0],
        "hands": actions[1:],
        "market": [],
    }
    rival_before = deepcopy(state[0].observation.farms[1])
    engine.interpreter(state, env)
    inventories = state[0].observation.private["inventories"]
    tile_after = state[0].observation.farms[0]["tiles"][4][4]
    return {
        "requested_first_actor": winner,
        "inventories": inventories,
        "total_carrots": sum(inv.get("CARROT", 0) for inv in inventories),
        "tile_yield_after": 0 if tile_after is None else tile_after["yield_units"],
        "rival_unchanged": state[0].observation.farms[1] == rival_before,
    }


def run_probe(engine_dir: Path | None = None) -> dict:
    engine = load_engine(engine_dir)
    runs = [run_order(engine, winner) for winner in range(3)]
    checks = {
        "yield_conserved_once_per_turn": all(run["total_carrots"] == 3 for run in runs),
        "tile_depleted_once": all(run["tile_yield_after"] == 0 for run in runs),
        "first_executed_actor_wins": all(
            run["inventories"][run["requested_first_actor"]] == {"CARROT": 3}
            for run in runs
        ),
        "later_same_tick_harvests_are_noops": all(
            all(
                not inventory
                for index, inventory in enumerate(run["inventories"])
                if index != run["requested_first_actor"]
            )
            for run in runs
        ),
        "rival_farm_unchanged": all(run["rival_unchanged"] for run in runs),
    }
    return {
        "schema": "titan-v5/double-harvest-sequencing/v1",
        "engine": {
            "git_blob": ENGINE_GIT_BLOB,
            "sha256": ENGINE_SHA256,
            "configuration_sha256": CONFIG_SHA256,
        },
        "hypothesis": "multiple actors can duplicate one tile's yield in a single tick",
        "verdict": "FALSIFIED" if all(checks.values()) else "UNRESOLVED",
        "checks": checks,
        "runs": runs,
        "runtime_change": False,
        "policy_change": False,
    }


if __name__ == "__main__":
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["verdict"] == "FALSIFIED" else 1)
