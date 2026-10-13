#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound BARNPIPE PLACE -> FEED -> CARE chaining oracle.

Research only. The canonical interpreter applies a player's farmer and hands in
actor order against one shared mutable farm. This oracle proves a later actor can
service an animal that an earlier co-located actor placed in the same callback,
and that a four-actor chain can BUILD -> PLACE -> FEED -> CARE on an empty tile.
It also executes the exact animal daily-refresh function to prove placement-day
FEED+CARE banks one pending care bonus for the first later production day.

No action transform/controller/runtime wiring lives here.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import types
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
UNIT_CHAINING = HERE / "unit_phase_chaining.py"
UNIT_CHAINING_GIT_BLOB = "4f3be59d7f29024bda355933c61ebf3cad49037d"
ANIMAL_ORDER = ("GOOSE", "COW", "SHEEP")


def _git_blob(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def _load_upc_module(path: Path = UNIT_CHAINING):
    """Authenticate then execute the captured canonical chaining bytes exactly once."""
    raw = path.read_bytes()
    actual = _git_blob(raw)
    if actual != UNIT_CHAINING_GIT_BLOB:
        raise RuntimeError(
            f"unit-phase-chaining drift: expected git blob {UNIT_CHAINING_GIT_BLOB}, got {actual}"
        )
    namespace: dict[str, Any] = {
        "__name__": "_barnpipe_authenticated_unit_phase_chaining",
        "__file__": str(path),
        "__package__": None,
    }
    exec(compile(raw, str(path), "exec"), namespace, namespace)
    return types.SimpleNamespace(**namespace)


upc = _load_upc_module()
ENGINE_GIT_BLOB = upc.ENGINE_GIT_BLOB
ENGINE = upc.ENGINE


def load_namespace(source: str) -> dict[str, Any]:
    """Load only exact source helpers used by BARNPIPE witnesses."""
    ns = upc.load_unit_namespace(source)
    tree = ast.parse(source)
    daily = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_daily_refresh_animals"),
        None,
    )
    if daily is None:
        raise AssertionError("_daily_refresh_animals missing")
    module = ast.fix_missing_locations(ast.Module(body=[daily], type_ignores=[]))
    exec(compile(module, "<canonical-kaggriculture-animal-refresh>", "exec"), ns, ns)
    return ns


def _farm(actors: int, tile0: Any, *, positions: list[tuple[int, int]] | None = None,
          tile1: Any = None) -> dict[str, Any]:
    if type(actors) is not int or actors < 1:
        raise ValueError("actors must be a positive int")
    positions = positions or [(0, 0)] * actors
    if len(positions) != actors:
        raise ValueError("positions/actors mismatch")
    return {
        "money": 3000.0,
        "tiles": [
            [copy.deepcopy(tile0), copy.deepcopy(tile1), "LOCKED", "LOCKED"],
            [None, None, "LOCKED", "LOCKED"],
            ["LOCKED", "LOCKED", "LOCKED", "LOCKED"],
            ["LOCKED", "LOCKED", "LOCKED", "LOCKED"],
        ],
        "farmer": list(positions[0]),
        "hands": [list(p) for p in positions[1:]],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }


def _private(ns: dict[str, Any], inventories: list[dict[str, int]]) -> dict[str, Any]:
    carry = [
        "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
        "EGG", "MILK", "WOOL", "FERTILIZER", *ns["ANIMALS"].keys(),
    ]
    return {
        "shed": {item: 0 for item in dict.fromkeys(carry)},
        "seeds": {crop: 0 for crop in ns["CROPS"]},
        "inventories": copy.deepcopy(inventories),
    }


def _apply_rows(ns: dict[str, Any], farm: dict[str, Any], private: dict[str, Any],
                rows: list[list[Any]], *, day: int = 0) -> None:
    if len(rows) != 1 + len(farm["hands"]):
        raise ValueError("row/actor mismatch")
    apply = ns["_apply_unit_action"]
    for actor, row in enumerate(rows):
        apply(farm, private, actor, row, 4, day, 24, 100)


def _tile(tile: Any) -> Any:
    if not isinstance(tile, dict):
        return tile
    keys = (
        "kind", "animal", "placed_day", "yield_units", "consecutive_unfed",
        "fed_today", "cared_today", "fertilizer_available", "pending_care_bonus",
    )
    return {key: tile[key] for key in keys if key in tile}


def _summary(farm: dict[str, Any], private: dict[str, Any]) -> dict[str, Any]:
    return {
        "tile_0_0": _tile(farm["tiles"][0][0]),
        "tile_1_0": _tile(farm["tiles"][0][1]),
        "inventories": copy.deepcopy(private["inventories"]),
    }


def _opposite_structure(structure: str) -> str:
    return "PASTURE" if structure == "COOP" else "COOP"


def _service_pipeline(ns: dict[str, Any], animal: str) -> dict[str, Any]:
    structure = ns["ANIMALS"][animal]["structure"]
    initial = {"kind": structure}

    farm = _farm(3, initial)
    private = _private(ns, [{animal: 1}, {"WHEAT": 1}, {}])
    _apply_rows(ns, farm, private, [["PLACE", animal], ["FEED"], ["CARE"]])
    forward = _summary(farm, private)

    farm = _farm(3, initial)
    private = _private(ns, [{"WHEAT": 1}, {animal: 1}, {}])
    _apply_rows(ns, farm, private, [["FEED"], ["PLACE", animal], ["CARE"]])
    feed_before_place = _summary(farm, private)

    farm = _farm(3, initial)
    private = _private(ns, [{}, {animal: 1}, {"WHEAT": 1}])
    _apply_rows(ns, farm, private, [["CARE"], ["PLACE", animal], ["FEED"]])
    care_before_place = _summary(farm, private)

    return {
        "structure": structure,
        "forward": forward,
        "feed_before_place": feed_before_place,
        "care_before_place": care_before_place,
    }


def _build_pipeline(ns: dict[str, Any], animal: str) -> dict[str, Any]:
    structure = ns["ANIMALS"][animal]["structure"]
    build = "BUILD_COOP" if structure == "COOP" else "BUILD_PASTURE"

    farm = _farm(4, None)
    private = _private(ns, [{}, {animal: 1}, {"WHEAT": 1}, {}])
    _apply_rows(ns, farm, private, [[build], ["PLACE", animal], ["FEED"], ["CARE"]])
    forward = _summary(farm, private)

    farm = _farm(4, None)
    private = _private(ns, [{animal: 1}, {}, {"WHEAT": 1}, {}])
    _apply_rows(ns, farm, private, [["PLACE", animal], [build], ["FEED"], ["CARE"]])
    place_before_build = _summary(farm, private)

    return {
        "structure": structure,
        "build": build,
        "forward": forward,
        "place_before_build": place_before_build,
    }


def _custody_controls(ns: dict[str, Any], animal: str) -> dict[str, Any]:
    structure = ns["ANIMALS"][animal]["structure"]

    farm = _farm(3, {"kind": structure})
    private = _private(ns, [{animal: 1}, {}, {"WHEAT": 1}])
    _apply_rows(ns, farm, private, [["PASS"], ["PLACE", animal], ["FEED"]])
    wrong_animal_actor = _summary(farm, private)

    farm = _farm(3, {"kind": structure})
    private = _private(ns, [{animal: 1, "WHEAT": 1}, {}, {}])
    _apply_rows(ns, farm, private, [["PLACE", animal], ["FEED"], ["CARE"]])
    wrong_wheat_actor = _summary(farm, private)

    farm = _farm(3, {"kind": _opposite_structure(structure)})
    private = _private(ns, [{animal: 1}, {"WHEAT": 1}, {}])
    _apply_rows(ns, farm, private, [["PLACE", animal], ["FEED"], ["CARE"]])
    wrong_structure = _summary(farm, private)

    positions = [(0, 0), (1, 0), (1, 0)]
    farm = _farm(3, {"kind": structure}, positions=positions, tile1={"kind": structure})
    private = _private(ns, [{animal: 1}, {"WHEAT": 1}, {}])
    _apply_rows(ns, farm, private, [["PLACE", animal], ["FEED"], ["CARE"]])
    distinct_tile = _summary(farm, private)

    return {
        "wrong_animal_actor": wrong_animal_actor,
        "wrong_wheat_actor": wrong_wheat_actor,
        "wrong_structure": wrong_structure,
        "distinct_tile": distinct_tile,
    }


def _eod_bonus(ns: dict[str, Any], animal: str) -> dict[str, Any]:
    """Prove placement-day service banks exactly one bonus for first production."""
    structure = ns["ANIMALS"][animal]["structure"]
    first_yield_day = ns["ANIMALS"][animal]["first_yield_day"]

    def run(care_on_placement_day: bool) -> dict[str, Any]:
        farm = _farm(3, {"kind": structure})
        private = _private(ns, [{animal: 1}, {"WHEAT": 1}, {}])
        third = ["CARE"] if care_on_placement_day else ["PASS"]
        _apply_rows(ns, farm, private, [["PLACE", animal], ["FEED"], third], day=0)
        before_eod0 = _summary(farm, private)
        ns["_daily_refresh_animals"](farm, 0)
        after_eod0 = _summary(farm, private)

        private["inventories"][1]["WHEAT"] = first_yield_day - 1
        for day in range(1, first_yield_day):
            _apply_rows(ns, farm, private, [["PASS"], ["FEED"], ["PASS"]], day=day)
            ns["_daily_refresh_animals"](farm, day)
        first_production = _summary(farm, private)
        return {
            "before_placement_eod": before_eod0,
            "after_placement_eod": after_eod0,
            "first_production": first_production,
        }

    return {
        "first_yield_day": first_yield_day,
        "with_placement_day_care": run(True),
        "without_placement_day_care": run(False),
    }


def run_witnesses(source: str) -> dict[str, Any]:
    contract = upc.assert_interpreter_contract(source)
    ns = load_namespace(source)
    animals: dict[str, Any] = {}
    for animal in ANIMAL_ORDER:
        if animal not in ns["ANIMALS"]:
            raise AssertionError(f"animal domain drift: missing {animal}")
        animals[animal] = {
            "place_feed_care": _service_pipeline(ns, animal),
            "build_place_feed_care": _build_pipeline(ns, animal),
            "custody_controls": _custody_controls(ns, animal),
            "eod_bonus": _eod_bonus(ns, animal),
        }
    return {
        "schema": "titan-v4-barnpipe-place-service/v1",
        "engine_git_blob": ENGINE_GIT_BLOB,
        "unit_phase_chaining_git_blob": UNIT_CHAINING_GIT_BLOB,
        "interpreter_contract": contract,
        "animals": animals,
        "disposition": "SOURCE_MECHANISM_CONFIRMED_CURRENT_NATIVE_ECONOMICS_UNASSESSED",
        "policy_boundary": {
            "research_only": True,
            "requires_actor_order": True,
            "requires_shared_tile": True,
            "cross_actor_inventory_transfer": False,
            "placement_day_production_claimed": False,
            "runtime_activation_authority": False,
        },
    }


def report(path: Path = ENGINE) -> dict[str, Any]:
    source = upc.read_engine(path)
    return run_witnesses(source)


def main() -> int:
    print(json.dumps(report(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
