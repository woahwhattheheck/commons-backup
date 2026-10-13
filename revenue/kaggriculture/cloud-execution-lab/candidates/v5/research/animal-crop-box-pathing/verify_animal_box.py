#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""V5-26 crop-box animal-pathing probe on the pinned official engine."""
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
CENTER = (2, 2)


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
    module = types.ModuleType("_v5_animal_box_pinned_engine")
    module.__file__ = str(engine_dir / "kaggriculture.py")
    module.resolve_episode_seed = lambda _env: 0
    exec(compile(tree, module.__file__, "exec"), module.__dict__)
    return module


def make_world(engine, *, ring: bool, step: int = 95, fed: bool = True):
    farms = [engine._new_farm(10, 3000), engine._new_farm(10, 3000)]
    privates = [engine._new_private(), engine._new_private()]
    farm = farms[0]
    cx, cy = CENTER
    goose = engine._new_animal("GOOSE", 0)
    goose["fed_today"] = fed
    farm["tiles"][cy][cx] = goose
    if ring:
        for y in range(cy - 1, cy + 2):
            for x in range(cx - 1, cx + 2):
                if (x, y) == CENTER:
                    continue
                crop = engine._new_plant("WHEAT", 3, 24)
                crop["watered_today"] = True
                crop["consecutive_unwatered"] = 0
                farm["tiles"][y][x] = crop
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
    return state, Struct(configuration=cfg, done=False, info={"seed": 0})


def animal_locations(farm):
    return [
        [x, y]
        for y, row in enumerate(farm["tiles"])
        for x, tile in enumerate(row)
        if isinstance(tile, dict) and "animal" in tile
    ]


def production_boundary(engine, *, ring: bool) -> dict:
    state, env = make_world(engine, ring=ring)
    farm = state[0].observation.farms[0]
    engine.interpreter(state, env)
    center = farm["tiles"][CENTER[1]][CENTER[0]]
    return {
        "ring": ring,
        "animal_locations": animal_locations(farm),
        "center_animal": center.get("animal"),
        "center_yield_units": center.get("yield_units"),
        "center_fields": sorted(center),
    }


def harvest_fixed_center(engine) -> dict:
    state, env = make_world(engine, ring=True)
    farm = state[0].observation.farms[0]
    engine.interpreter(state, env)
    state[0].observation.step = 96
    state[0].observation.day = 4
    state[0].observation.hour = 0
    farm["farmer"] = list(CENTER)
    state[0].action["farmer"] = ["HARVEST"]
    engine.interpreter(state, env)
    center = farm["tiles"][CENTER[1]][CENTER[0]]
    return {
        "animal_locations": animal_locations(farm),
        "center_yield_units": center["yield_units"],
        "farmer_inventory": dict(state[0].observation.private["inventories"][0]),
    }


def unfed_escape(engine) -> dict:
    state, env = make_world(engine, ring=True, step=23, fed=False)
    farm = state[0].observation.farms[0]
    engine.interpreter(state, env)
    state[0].observation.step = 47
    state[0].observation.day = 1
    state[0].observation.hour = 23
    engine.interpreter(state, env)
    center = farm["tiles"][CENTER[1]][CENTER[0]]
    return {
        "animal_locations": animal_locations(farm),
        "center_tile": deepcopy(center),
    }


def run_probe() -> dict:
    engine = load_engine()
    boxed = production_boundary(engine, ring=True)
    open_field = production_boundary(engine, ring=False)
    harvested = harvest_fixed_center(engine)
    escaped = unfed_escape(engine)
    checks = {
        "boxed_goose_stays_on_center_tile": boxed["animal_locations"] == [[2, 2]],
        "open_goose_also_stays_on_center_tile": open_field["animal_locations"] == [[2, 2]],
        "crop_ring_does_not_change_animal_state": (
            {k: v for k, v in boxed.items() if k != "ring"}
            == {k: v for k, v in open_field.items() if k != "ring"}
        ),
        "production_occurs_without_animal_movement": boxed["center_yield_units"] == 1,
        "fixed_center_harvest_collects_one_egg": (
            harvested["animal_locations"] == [[2, 2]]
            and harvested["center_yield_units"] == 0
            and harvested["farmer_inventory"] == {"EGG": 1}
        ),
        "starved_animal_escapes_without_relocation": (
            escaped["animal_locations"] == []
            and escaped["center_tile"] == {"kind": "COOP"}
        ),
    }
    return {
        "schema": "titan-v5/animal-crop-box-pathing/v1",
        "engine": {
            "git_blob": ENGINE_GIT_BLOB,
            "sha256": ENGINE_SHA256,
            "configuration_sha256": CONFIG_SHA256,
        },
        "hypothesis": "a crop ring uniquely confines an otherwise wandering Goose",
        "verdict": "FALSIFIED" if all(checks.values()) else "UNRESOLVED",
        "checks": checks,
        "boxed": boxed,
        "open_field": open_field,
        "harvested": harvested,
        "unfed_escape": escaped,
        "runtime_change": False,
        "policy_change": False,
    }


if __name__ == "__main__":
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["verdict"] == "FALSIFIED" else 1)
