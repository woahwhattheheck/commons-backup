#!/usr/bin/env python3
"""Source-bound oracle for Kaggriculture same-callback unit-phase chaining.

Research only. This module never changes a returned action. It authenticates the
canonical engine, proves the interpreter's actor execution order structurally,
then executes only the exact source `_apply_unit_action` implementation in small
constructed worlds to isolate state changes that an earlier actor can expose to a
later co-located actor during the same callback.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
HERE = Path(__file__).resolve().parent
LAB = HERE.parents[3] if len(HERE.parents) >= 4 else HERE
ENGINE = LAB / "reference" / "engine" / "kaggriculture.py"

_ASSIGNMENTS = {"CROPS", "ANIMALS", "FARMER_MOVES"}
_FUNCTIONS = {
    "_quadrant_of",
    "_shed_access_tiles",
    "_is_shed_adjacent",
    "_farmer_position",
    "_set_farmer_position",
    "_farmer_inventory",
    "_inv_add",
    "_inv_take",
    "_new_plant",
    "_new_animal",
    "_apply_unit_action",
}


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def read_engine(path: Path = ENGINE, expected_blob: str = ENGINE_GIT_BLOB) -> str:
    data = path.read_bytes()
    got = git_blob(data)
    if got != expected_blob:
        raise RuntimeError(f"engine drift: {got} != {expected_blob}")
    return data.decode("utf-8")


def _call_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _contains_apply_call(node: ast.AST, actor_kind: str) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call) or _call_name(child) != "_apply_unit_action":
            continue
        if len(child.args) < 3:
            continue
        actor = child.args[2]
        if actor_kind == "farmer" and isinstance(actor, ast.Constant) and actor.value == 0:
            return True
        if actor_kind == "hand" and isinstance(actor, ast.BinOp):
            if (
                isinstance(actor.left, ast.Name)
                and actor.left.id == "h_idx"
                and isinstance(actor.op, ast.Add)
                and isinstance(actor.right, ast.Constant)
                and actor.right.value == 1
            ):
                return True
    return False


def assert_interpreter_contract(source: str) -> dict[str, Any]:
    """Prove the exact source still executes farmer -> hands -> market.

    This intentionally checks structure, not line numbers, and also pins the
    atomic PLANT preflight that happens before any unit mutation.
    """
    tree = ast.parse(source)
    interpreter = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "interpreter"),
        None,
    )
    if interpreter is None:
        raise AssertionError("interpreter missing")

    player_loop = None
    for stmt in interpreter.body:
        if not isinstance(stmt, ast.For):
            continue
        target_names = {n.id for n in ast.walk(stmt.target) if isinstance(n, ast.Name)}
        if {"i", "s"}.issubset(target_names) and any(
            isinstance(n, ast.Name) and n.id == "state" for n in ast.walk(stmt.iter)
        ):
            player_loop = stmt
            break
    if player_loop is None:
        raise AssertionError("player unit loop missing")

    farmer_stmt_index = None
    hand_stmt_index = None
    for idx, stmt in enumerate(player_loop.body):
        if farmer_stmt_index is None and _contains_apply_call(stmt, "farmer"):
            farmer_stmt_index = idx
        if isinstance(stmt, ast.For):
            target_names = {n.id for n in ast.walk(stmt.target) if isinstance(n, ast.Name)}
            if "h_idx" in target_names and _contains_apply_call(stmt, "hand"):
                hand_stmt_index = idx
                if not (
                    isinstance(stmt.iter, ast.Call)
                    and isinstance(stmt.iter.func, ast.Name)
                    and stmt.iter.func.id == "enumerate"
                    and len(stmt.iter.args) == 1
                    and isinstance(stmt.iter.args[0], ast.Name)
                    and stmt.iter.args[0].id == "hands_actions"
                ):
                    raise AssertionError("hand execution order drift")
    if farmer_stmt_index is None or hand_stmt_index is None:
        raise AssertionError("unit application calls missing")
    if farmer_stmt_index >= hand_stmt_index:
        raise AssertionError("farmer must execute before hands")

    player_loop_index = interpreter.body.index(player_loop)
    market_indexes = [
        idx
        for idx, stmt in enumerate(interpreter.body)
        if any(
            isinstance(n, ast.Call) and _call_name(n) == "_process_market"
            for n in ast.walk(stmt)
        )
    ]
    if not market_indexes or min(market_indexes) <= player_loop_index:
        raise AssertionError("unit-before-market phase order drift")

    required_anchors = (
        "unit_actions = [farmer_action, *hands_actions]",
        "blocked = {crop for crop, n in plant_demand.items() if n > seeds.get(crop, 0)}",
        'return ["PASS"]',
    )
    for anchor in required_anchors:
        if anchor not in source:
            raise AssertionError(f"atomic PLANT preflight drift: missing {anchor}")

    return {
        "farmer_statement_index": farmer_stmt_index,
        "hands_statement_index": hand_stmt_index,
        "market_after_player_loop": True,
        "atomic_plant_preflight_pinned": True,
    }


def load_unit_namespace(source: str) -> dict[str, Any]:
    """Compile only exact engine constants/helpers needed by `_apply_unit_action`."""
    tree = ast.parse(source)
    selected: list[ast.stmt] = []
    found_assignments: set[str] = set()
    found_functions: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            names = set()
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
            keep = names & _ASSIGNMENTS
            if keep:
                selected.append(node)
                found_assignments.update(keep)
        elif isinstance(node, ast.FunctionDef) and node.name in _FUNCTIONS:
            selected.append(node)
            found_functions.add(node.name)
    missing = (_ASSIGNMENTS - found_assignments) | (_FUNCTIONS - found_functions)
    if missing:
        raise AssertionError(f"required engine subset missing: {sorted(missing)}")
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    ns: dict[str, Any] = {}
    exec(compile(module, "<canonical-kaggriculture-unit-subset>", "exec"), ns, ns)
    return ns


def atomic_plant_filter(unit_actions: list[list[Any]], seeds: dict[str, int]) -> list[list[Any]]:
    """Exact mirror of the source-pinned atomic PLANT preflight."""
    demand: dict[str, int] = {}
    for action in unit_actions:
        if isinstance(action, list) and len(action) >= 2 and action[0] == "PLANT":
            crop = action[1]
            demand[crop] = demand.get(crop, 0) + 1
    blocked = {crop for crop, n in demand.items() if n > seeds.get(crop, 0)}
    return [
        ["PASS"]
        if isinstance(action, list) and len(action) >= 2 and action[0] == "PLANT" and action[1] in blocked
        else action
        for action in unit_actions
    ]


def _blank_private(ns: dict[str, Any], *, seeds: dict[str, int] | None = None,
                   inv0: dict[str, int] | None = None, inv1: dict[str, int] | None = None) -> dict[str, Any]:
    crop_names = ns["CROPS"].keys()
    product_and_animals = [
        "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
        "EGG", "MILK", "WOOL", "FERTILIZER", *ns["ANIMALS"].keys(),
    ]
    private = {
        "shed": {item: 0 for item in dict.fromkeys(product_and_animals)},
        "seeds": {crop: 0 for crop in crop_names},
        "inventories": [dict(inv0 or {}), dict(inv1 or {})],
    }
    if seeds:
        private["seeds"].update(seeds)
    return private


def _farm(tile0: Any, *, pos0=(0, 0), pos1=(0, 0), tile1: Any = None) -> dict[str, Any]:
    return {
        "money": 3000.0,
        "tiles": [
            [copy.deepcopy(tile0), copy.deepcopy(tile1), "LOCKED", "LOCKED"],
            [None, None, "LOCKED", "LOCKED"],
            ["LOCKED", "LOCKED", "LOCKED", "LOCKED"],
            ["LOCKED", "LOCKED", "LOCKED", "LOCKED"],
        ],
        "farmer": list(pos0),
        "hands": [list(pos1)],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }


def _apply_pair(ns: dict[str, Any], farm: dict[str, Any], private: dict[str, Any],
                first: list[Any], second: list[Any], *, day: int = 0) -> None:
    apply = ns["_apply_unit_action"]
    apply(farm, private, 0, first, 4, day, 24, 100)
    apply(farm, private, 1, second, 4, day, 24, 100)


def _tile_summary(tile: Any) -> Any:
    if not isinstance(tile, dict):
        return tile
    keys = (
        "kind", "crop", "animal", "planted_day", "yield_units",
        "fertilized_until_day", "watered_today", "pending_care_bonus",
    )
    return {k: tile[k] for k in keys if k in tile}


def _world_summary(farm: dict[str, Any], private: dict[str, Any]) -> dict[str, Any]:
    return {
        "tile_0_0": _tile_summary(farm["tiles"][0][0]),
        "tile_1_0": _tile_summary(farm["tiles"][0][1]),
        "inventories": copy.deepcopy(private["inventories"]),
        "seeds": copy.deepcopy(private["seeds"]),
    }


def _plant(crop: str, *, planted_day: int, yield_units: int, watered_today: bool = False,
           fertilized_until_day: int = -1) -> dict[str, Any]:
    return {
        "kind": "PLANT",
        "crop": crop,
        "planted_day": planted_day,
        "watered_today": watered_today,
        "consecutive_unwatered": 0,
        "yield_units": yield_units,
        "max_lifespan_step": 10_000,
        "fertilized_until_day": fertilized_until_day,
    }


def run_witnesses(source: str) -> dict[str, Any]:
    contract = assert_interpreter_contract(source)
    ns = load_unit_namespace(source)
    witnesses: dict[str, Any] = {}

    farm = _farm({"kind": "WEED"})
    private = _blank_private(ns, seeds={"WHEAT": 1})
    actions = atomic_plant_filter([["DIG"], ["PLANT", "WHEAT"]], private["seeds"])
    _apply_pair(ns, farm, private, actions[0], actions[1])
    forward = _world_summary(farm, private)
    farm = _farm({"kind": "WEED"})
    private = _blank_private(ns, seeds={"WHEAT": 1})
    actions = atomic_plant_filter([["PLANT", "WHEAT"], ["DIG"]], private["seeds"])
    _apply_pair(ns, farm, private, actions[0], actions[1])
    reverse = _world_summary(farm, private)
    witnesses["dig_then_plant"] = {"forward": forward, "reverse": reverse}

    source_plant = _plant("WHEAT", planted_day=0, yield_units=3, watered_today=True)
    farm = _farm(source_plant)
    private = _blank_private(ns, seeds={"WHEAT": 1})
    actions = atomic_plant_filter([["HARVEST"], ["PLANT", "WHEAT"]], private["seeds"])
    _apply_pair(ns, farm, private, actions[0], actions[1], day=4)
    forward = _world_summary(farm, private)
    farm = _farm(source_plant)
    private = _blank_private(ns, seeds={"WHEAT": 1})
    actions = atomic_plant_filter([["PLANT", "WHEAT"], ["HARVEST"]], private["seeds"])
    _apply_pair(ns, farm, private, actions[0], actions[1], day=4)
    reverse = _world_summary(farm, private)
    witnesses["harvest_then_plant"] = {"forward": forward, "reverse": reverse}

    source_plant = _plant("WHEAT", planted_day=0, yield_units=1)
    farm = _farm(source_plant)
    private = _blank_private(ns, inv0={"FERTILIZER": 1})
    _apply_pair(ns, farm, private, ["FERTILIZE"], ["WATER"], day=3)
    forward = _world_summary(farm, private)
    farm = _farm(source_plant)
    private = _blank_private(ns, inv1={"FERTILIZER": 1})
    _apply_pair(ns, farm, private, ["WATER"], ["FERTILIZE"], day=3)
    reverse = _world_summary(farm, private)
    witnesses["fertilize_then_water"] = {"forward": forward, "reverse": reverse}

    farm = _farm(None)
    private = _blank_private(ns, inv1={"GOOSE": 1})
    _apply_pair(ns, farm, private, ["BUILD_COOP"], ["PLACE", "GOOSE"], day=0)
    forward = _world_summary(farm, private)
    farm = _farm(None)
    private = _blank_private(ns, inv0={"GOOSE": 1})
    _apply_pair(ns, farm, private, ["PLACE", "GOOSE"], ["BUILD_COOP"], day=0)
    reverse = _world_summary(farm, private)
    witnesses["build_then_place"] = {"forward": forward, "reverse": reverse}

    farm = _farm({"kind": "WEED"}, pos0=(0, 0), pos1=(1, 0), tile1={"kind": "WEED"})
    private = _blank_private(ns, seeds={"WHEAT": 1})
    actions = atomic_plant_filter([["DIG"], ["PLANT", "WHEAT"]], private["seeds"])
    _apply_pair(ns, farm, private, actions[0], actions[1])
    witnesses["distinct_tile_control"] = _world_summary(farm, private)

    witnesses["atomic_seed_control"] = {
        "requested": [["PLANT", "WHEAT"], ["PLANT", "WHEAT"]],
        "seeds": {"WHEAT": 1},
        "filtered": atomic_plant_filter(
            [["PLANT", "WHEAT"], ["PLANT", "WHEAT"]], {"WHEAT": 1}
        ),
    }

    return {
        "schema": "titan-v4-unit-phase-chaining/v1",
        "engine_git_blob": ENGINE_GIT_BLOB,
        "interpreter_contract": contract,
        "witnesses": witnesses,
        "disposition": "SOURCE_MECHANISM_CONFIRMED_CURRENT_NATIVE_ECONOMICS_UNASSESSED",
        "policy_boundary": {
            "same_callback_market_credit": False,
            "cross_actor_inventory_transfer": False,
            "requires_actor_order": True,
            "requires_shared_tile_for_tile_enabling_chains": True,
            "atomic_plant_collateral_still_applies": True,
        },
    }


def report(path: Path = ENGINE) -> dict[str, Any]:
    source = read_engine(path)
    return run_witnesses(source)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()
    payload = report()
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
