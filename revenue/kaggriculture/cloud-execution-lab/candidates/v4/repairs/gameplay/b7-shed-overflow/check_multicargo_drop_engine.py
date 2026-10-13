#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-pinned official-engine differential for B7 multi-cargo DROP custody."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
HERE = Path(__file__).resolve().parent
LAB = HERE.parents[4]
ENGINE = LAB / "reference" / "engine" / "kaggriculture.py"
HELPER = HERE / "multicargo_drop_guard.py"
CFG = {"boardSize": 10, "shedCapacity": 100}


class CheckError(RuntimeError):
    pass


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise CheckError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def assert_source():
    actual = git_blob_sha(ENGINE)
    if actual != ENGINE_BLOB:
        raise CheckError(f"engine drift: expected {ENGINE_BLOB}, got {actual}")
    return {"engine": actual, "helper": git_blob_sha(HELPER)}


def build(engine, player, room, inventories):
    farms = [engine._new_farm(10, 3000) for _ in range(2)]
    farm = farms[player]
    farm["farmer"] = [4, 4]
    farm["hands"] = [[4, 4] for _ in range(max(0, len(inventories) - 1))]
    private = engine._new_private()
    private["inventories"] = copy.deepcopy(inventories)
    private["shed"]["CARROT"] = 100 - room
    obs = {"player": player, "farms": farms, "private": private}
    return obs


def action_for(actor, actors, row):
    rows = [["PASS"] for _ in range(actors)]
    rows[actor] = row
    return {"farmer": rows[0], "hands": rows[1:], "market": []}


def execute(engine, obs, action):
    farm = copy.deepcopy(obs["farms"][obs["player"]])
    private = copy.deepcopy(obs["private"])
    rows = [action["farmer"], *action["hands"]]
    for actor, row in enumerate(rows):
        engine._apply_unit_action(farm, private, actor, row, 10, 10, 24, shed_capacity=100)
    return farm, private


def quantity(inventory):
    return sum(v for v in inventory.values() if type(v) is int and v > 0)


def check_cell(engine, helper, *, player, actor, room, inventory):
    actors = 2
    inventories = [{}, {}]
    inventories[actor] = dict(inventory)
    obs = build(engine, player, room, inventories)
    parent = action_for(actor, actors, ["DROP"])
    before = copy.deepcopy(parent)
    out = helper.transform(obs, parent, CFG, enabled=True)
    if parent != before:
        raise CheckError("helper mutated parent action")

    original_farm, original_private = execute(engine, obs, before)
    guarded_farm, guarded_private = execute(engine, obs, out)
    changed = out is not parent
    if changed:
        if guarded_farm != original_farm:
            raise CheckError(f"farm mismatch p{player} a{actor} room{room} {inventory}")
        if guarded_private["shed"] != original_private["shed"]:
            raise CheckError(f"shed mismatch p{player} a{actor} room{room} {inventory}")
        before_qty = quantity(original_private["inventories"][actor])
        after_qty = quantity(guarded_private["inventories"][actor])
        if after_qty <= before_qty:
            raise CheckError(f"changed cell did not retain cargo: {inventory}")
    return changed


def run_matrix(engine, helper):
    cells = changed = 0
    by_seat = {"0": 0, "1": 0}
    by_actor = {"0": 0, "1": 0}
    for player in (0, 1):
        for actor in (0, 1):
            for room in (0, 1, 2, 3):
                for first_qty in (1, 2, 3, 5):
                    for tail in (("WOOL", 2), ("GOOSE", 1)):
                        inventory = {"MILK": first_qty, tail[0]: tail[1]}
                        cells += 1
                        did_change = check_cell(
                            engine, helper, player=player, actor=actor,
                            room=room, inventory=inventory,
                        )
                        expected = room == 0 or (first_qty >= room and first_qty + tail[1] > room)
                        if did_change != expected:
                            raise CheckError(
                                f"admission mismatch p{player} a{actor} room{room} inventory={inventory}: "
                                f"changed={did_change} expected={expected}"
                            )
                        if did_change:
                            changed += 1
                            by_seat[str(player)] += 1
                            by_actor[str(actor)] += 1

    # room==0 is exact even when an animal is first: PASS leaves an already-full
    # shed identical while avoiding DROP's unconditional inventory deletion.
    for player in (0, 1):
        cells += 1
        if not check_cell(
            engine, helper, player=player, actor=0, room=0,
            inventory={"GOOSE": 1, "MILK": 3},
        ):
            raise CheckError("full-shed animal-first cell was not admitted")
        changed += 1
        by_seat[str(player)] += 1
        by_actor["0"] += 1

    # With room available, animal-first PLACE would be structurally ambiguous.
    for player in (0, 1):
        cells += 1
        if check_cell(
            engine, helper, player=player, actor=0, room=2,
            inventory={"GOOSE": 5, "MILK": 3},
        ):
            raise CheckError("animal-first partial-room cell did not fail closed")

    return {
        "cells": cells,
        "changed_cells": changed,
        "changed_by_seat": by_seat,
        "changed_by_actor": by_actor,
    }


def run_order_cases(engine, helper):
    passed = []

    # Prior PLACE consumes 2/3 free slots; later first item saturates final slot.
    obs = build(engine, 0, 3, [{"EGG": 2}, {"MILK": 1, "WOOL": 4}])
    parent = {"farmer": ["PLACE", "EGG", 2], "hands": [["DROP"]], "market": []}
    out = helper.transform(obs, parent, CFG, enabled=True)
    if out["hands"][0] != ["PLACE", "MILK", 1]:
        raise CheckError("prior PLACE room accounting failed")
    of, op = execute(engine, obs, parent)
    gf, gp = execute(engine, obs, out)
    if of != gf or op["shed"] != gp["shed"] or gp["inventories"][1] != {"WOOL": 4}:
        raise CheckError("prior PLACE exact-engine differential failed")
    passed.append("prior_product_place")

    # Prior DROP consumes 2/3 free slots but is itself not overflowing.
    obs = build(engine, 1, 3, [{"EGG": 2}, {"MILK": 1, "WOOL": 4}])
    parent = {"farmer": ["DROP"], "hands": [["DROP"]], "market": []}
    out = helper.transform(obs, parent, CFG, enabled=True)
    if out["farmer"] != ["DROP"] or out["hands"][0] != ["PLACE", "MILK", 1]:
        raise CheckError("prior DROP room accounting failed")
    of, op = execute(engine, obs, parent)
    gf, gp = execute(engine, obs, out)
    if of != gf or op["shed"] != gp["shed"] or gp["inventories"][1] != {"WOOL": 4}:
        raise CheckError("prior DROP exact-engine differential failed")
    passed.append("prior_drop")

    # Prior PICKUP can increase room, so stale capacity must never be used.
    obs = build(engine, 0, 2, [{}, {"MILK": 5, "WOOL": 2}])
    parent = {"farmer": ["PICKUP", "CARROT", 1], "hands": [["DROP"]], "market": []}
    if helper.transform(obs, parent, CFG, enabled=True) is not parent:
        raise CheckError("prior PICKUP did not fail closed")
    passed.append("prior_pickup_fail_closed")

    # DROP would need to deposit across two product keys; one PLACE cannot be
    # state-equivalent, so identity is mandatory.
    obs = build(engine, 0, 3, [{"MILK": 1, "WOOL": 5}, {}])
    parent = {"farmer": ["DROP"], "hands": [["PASS"]], "market": []}
    if helper.transform(obs, parent, CFG, enabled=True) is not parent:
        raise CheckError("multi-key spanning DROP did not fail closed")
    passed.append("spanning_drop_fail_closed")

    return passed


def run():
    pins = assert_source()
    engine = load("_b7_engine", ENGINE)
    helper = load("_b7_multicargo", HELPER)
    return {
        "status": "PASS",
        "scope": "official-engine B7 multi-cargo DROP custody differential; default-OFF; unwired",
        "pins": pins,
        "matrix": run_matrix(engine, helper),
        "order_cases": run_order_cases(engine, helper),
    }


def main() -> int:
    print(json.dumps(run(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
