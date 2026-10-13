#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""V5-24 fertilizer-maturation probe against the pinned official engine."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import types


ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
CONFIG_SHA256 = "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867"


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
    module = types.ModuleType("_v5_fertilizer_maturation_pinned_engine")
    module.__file__ = str(engine_dir / "kaggriculture.py")
    module.resolve_episode_seed = lambda _env: 0
    exec(compile(tree, module.__file__, "exec"), module.__dict__)
    return module


def run_case(engine, crop: str) -> dict:
    day = 7
    turns_per_day = 24
    farm = engine._new_farm(10, 3000)
    private = engine._new_private()
    farm["farmer"] = [1, 1]
    farm["tiles"][1][1] = engine._new_plant(crop, day, turns_per_day)
    private["inventories"][0]["FERTILIZER"] = 8
    tile = farm["tiles"][1][1]

    before = {
        "planted_day": tile["planted_day"],
        "max_lifespan_step": tile["max_lifespan_step"],
        "yield_units": tile["yield_units"],
    }

    for _ in range(4):
        engine._apply_unit_action(
            farm,
            private,
            0,
            ["FERTILIZE"],
            10,
            day,
            turns_per_day,
            100,
        )

    after_fertilize = {
        "planted_day": tile["planted_day"],
        "max_lifespan_step": tile["max_lifespan_step"],
        "yield_units": tile["yield_units"],
        "fertilized_until_day": tile["fertilized_until_day"],
        "fertilizer_remaining": private["inventories"][0].get("FERTILIZER", 0),
    }

    engine._apply_unit_action(
        farm,
        private,
        0,
        ["HARVEST"],
        10,
        day,
        turns_per_day,
        100,
    )

    after_harvest_tile = farm["tiles"][1][1]
    return {
        "crop": crop,
        "fertilizer_applied": 4,
        "before": before,
        "after_fertilize": after_fertilize,
        "same_day_harvest_units": private["inventories"][0].get(crop, 0),
        "same_day_tile_kind": (
            after_harvest_tile.get("kind")
            if isinstance(after_harvest_tile, dict)
            else after_harvest_tile
        ),
        "same_day_yield_units": (
            after_harvest_tile.get("yield_units")
            if isinstance(after_harvest_tile, dict)
            else None
        ),
    }


def run_probe() -> dict:
    engine = load_engine()
    cases = [run_case(engine, "CARROT"), run_case(engine, "TOMATO")]
    by_crop = {row["crop"]: row for row in cases}
    carrot = by_crop["CARROT"]
    tomato = by_crop["TOMATO"]

    checks = {
        "fertilizer_does_not_change_planted_day": all(
            row["before"]["planted_day"] == row["after_fertilize"]["planted_day"]
            for row in cases
        ),
        "fertilizer_does_not_change_lifespan_clock": all(
            row["before"]["max_lifespan_step"]
            == row["after_fertilize"]["max_lifespan_step"]
            for row in cases
        ),
        "fertilizer_does_not_create_yield": all(
            row["before"]["yield_units"] == row["after_fertilize"]["yield_units"]
            for row in cases
        ),
        "same_day_nonongoing_harvest_is_blocked": (
            carrot["same_day_harvest_units"] == 0
            and carrot["same_day_tile_kind"] == "PLANT"
            and carrot["same_day_yield_units"] == 1
        ),
        "same_day_ongoing_harvest_is_blocked": (
            tomato["same_day_harvest_units"] == 0
            and tomato["same_day_tile_kind"] == "PLANT"
            and tomato["same_day_yield_units"] == 0
        ),
        "same_day_fertilizer_window_does_not_stack": all(
            row["after_fertilize"]["fertilized_until_day"] == 9 for row in cases
        ),
        "repeated_fertilizer_is_consumed_without_extra_window": all(
            row["after_fertilize"]["fertilizer_remaining"] == 4 for row in cases
        ),
    }

    return {
        "schema": "titan-v5/fertilizer-maturation/v1",
        "engine": {
            "git_blob": ENGINE_GIT_BLOB,
            "sha256": ENGINE_SHA256,
            "configuration_sha256": CONFIG_SHA256,
        },
        "hypothesis": (
            "Repeated same-day FERTILIZE can reduce crop maturity below zero "
            "or create an instant/infinite harvest"
        ),
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
