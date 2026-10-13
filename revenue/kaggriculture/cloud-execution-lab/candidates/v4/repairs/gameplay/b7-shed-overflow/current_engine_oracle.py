#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-pinned current-engine oracle for the preserved B7 shed-overflow guard.

This is evidence tooling only.  It does not wire B7 into titan_runtime, change a
feature default, run an evaluator, or mutate gameplay state outside local copies.

The B7 theorem is deliberately narrow: for an actor adjacent to the shed carrying
exactly one positive product, a DROP that would overflow the remaining shed room
may be replaced by PLACE(product, room), or PASS when room is zero.  The official
engine then produces the same shed contents while retaining only the units that
DROP would have destroyed.  Earlier actors are resolved in engine order, so the
oracle also covers prior product PLACE/DROP and the donor's conservative PICKUP /
ambiguous-PLACE fail-closed boundaries.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

HELPER_BLOB = "a27da659884c0f9a9594cbd9332b5edb4d7f3307"
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
RUNTIME_BLOB = "b952c9c228ecbde592bf3d2df01638677abb0d24"

HELPER_REL = Path(
    "revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/gameplay/"
    "b7-shed-overflow/legacy/b7_shed_room_guard.py"
)
ENGINE_REL = Path(
    "revenue/kaggriculture/cloud-execution-lab/reference/engine/kaggriculture.py"
)
RUNTIME_REL = Path("revenue/kaggriculture/cloud-execution-lab/titan_runtime.py")

STANDARD_CONFIG = {
    "boardSize": 10,
    "turnsPerDay": 24,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}


class OracleError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def repo_root(start: Path) -> Path:
    for parent in (start, *start.parents):
        if (parent / HELPER_REL).is_file() and (parent / ENGINE_REL).is_file():
            return parent
    raise OracleError("repository root not found")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise OracleError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_pins(root: Path) -> dict[str, str]:
    expected = {
        HELPER_REL: HELPER_BLOB,
        ENGINE_REL: ENGINE_BLOB,
        RUNTIME_REL: RUNTIME_BLOB,
    }
    got: dict[str, str] = {}
    for rel, want in expected.items():
        path = root / rel
        data = path.read_bytes()
        actual = git_blob_sha(data)
        got[str(rel)] = actual
        if actual != want:
            raise OracleError(f"source drift for {rel}: expected {want}, got {actual}")

    runtime = (root / RUNTIME_REL).read_text(encoding="utf-8")
    feed = "returned = self._feed_stock_selected(obs, cfg or {}, returned)"
    capital = "returned = self._early_capital_selected(obs, cfg or {}, returned)"
    finish = "self.quadrant.finish(obs, returned)"
    if runtime.count(feed) != 1 or runtime.count(capital) != 1 or runtime.count(finish) != 1:
        raise OracleError("current runtime selected-action hook anchors drifted")
    if not (runtime.index(feed) < runtime.index(capital) < runtime.index(finish)):
        raise OracleError("current runtime final selected-action order drifted")
    return got


def selected_row(action: dict[str, Any], actor: int):
    return action["farmer"] if actor == 0 else action["hands"][actor - 1]


def set_selected_row(action: dict[str, Any], actor: int, row: list[Any]) -> None:
    if actor == 0:
        action["farmer"] = row
    else:
        action["hands"][actor - 1] = row


def build_observation(engine, *, player: int, actors: int, room: int,
                      inventories: list[dict[str, int]], capacity: int = 100):
    if not (0 <= room <= capacity):
        raise OracleError("invalid room")
    farms = [engine._new_farm(10, 3000) for _ in range(2)]
    farm = farms[player]
    farm["farmer"] = [4, 4]
    farm["hands"] = [[4, 4] for _ in range(max(0, actors - 1))]
    private = engine._new_private()
    private["inventories"] = copy.deepcopy(inventories)
    private["shed"]["CARROT"] = capacity - room
    return {
        "step": 240,
        "player": player,
        "farms": farms,
        "private": private,
        "market": engine._new_market(),
        "town": engine._new_town(),
        "day": 10,
        "hour": 0,
    }


def execute_units(engine, observation: dict[str, Any], action: dict[str, Any],
                  capacity: int = 100):
    player = observation["player"]
    farm = copy.deepcopy(observation["farms"][player])
    private = copy.deepcopy(observation["private"])
    commands = [action["farmer"], *action["hands"]]
    for actor, command in enumerate(commands):
        engine._apply_unit_action(
            farm, private, actor, command,
            10, observation.get("day", 10), 24,
            shed_capacity=capacity,
        )
    return farm, private


def assert_guarded_equivalence(engine, original_obs, original_action, transformed,
                               actor: int, item: str, qty: int, room: int) -> None:
    original_farm, original_private = execute_units(engine, original_obs, original_action)
    guarded_farm, guarded_private = execute_units(engine, original_obs, transformed)

    if original_farm != guarded_farm:
        raise OracleError("guard changed farm/position/tile state")
    if original_private["shed"] != guarded_private["shed"]:
        raise OracleError("guard changed shed result")

    original_inv = original_private["inventories"][actor]
    guarded_inv = guarded_private["inventories"][actor]
    if item in original_inv:
        raise OracleError("official DROP unexpectedly retained overflow cargo")
    expected = qty - room
    if expected <= 0:
        raise OracleError("guarded-equivalence called for non-overflow case")
    if guarded_inv.get(item) != expected:
        raise OracleError(
            f"guard retained {guarded_inv.get(item)!r} {item}, expected {expected}"
        )
    other_original = [copy.deepcopy(x) for x in original_private["inventories"]]
    other_guarded = [copy.deepcopy(x) for x in guarded_private["inventories"]]
    other_original[actor].pop(item, None)
    other_guarded[actor].pop(item, None)
    if other_original != other_guarded:
        raise OracleError("guard changed inventory state outside preserved overflow")


def run_matrix(helper, engine) -> dict[str, Any]:
    total = changed = unchanged = 0
    by_seat = {"0": 0, "1": 0}
    by_actor = {"0": 0, "1": 0}
    products = ("MILK", "WOOL")

    for player in (0, 1):
        for actor in (0, 1):
            for room in (0, 1, 2, 5):
                for qty in (1, 2, 3, 6):
                    for item in products:
                        total += 1
                        inventories = [{}, {}]
                        inventories[actor] = {item: qty}
                        obs = build_observation(
                            engine, player=player, actors=2, room=room,
                            inventories=inventories,
                        )
                        action = {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}
                        set_selected_row(action, actor, ["DROP"])
                        before = copy.deepcopy(action)
                        transformed = helper.transform(
                            obs, action, STANDARD_CONFIG, enabled=True
                        )
                        if action != before:
                            raise OracleError("helper mutated parent action in place")

                        if qty > room:
                            changed += 1
                            by_seat[str(player)] += 1
                            by_actor[str(actor)] += 1
                            want = ["PASS"] if room == 0 else ["PLACE", item, room]
                            if selected_row(transformed, actor) != want:
                                raise OracleError(
                                    f"wrong replacement p{player}/a{actor}/room{room}/qty{qty}: "
                                    f"{selected_row(transformed, actor)!r} != {want!r}"
                                )
                            assert_guarded_equivalence(
                                engine, obs, before, transformed, actor, item, qty, room
                            )
                        else:
                            unchanged += 1
                            if transformed is not action:
                                raise OracleError("non-overflow path lost exact action identity")
                            if execute_units(engine, obs, before) != execute_units(engine, obs, transformed):
                                raise OracleError("non-overflow path changed engine outcome")

    return {
        "cells": total,
        "changed_cells": changed,
        "unchanged_cells": unchanged,
        "changed_by_seat": by_seat,
        "changed_by_actor": by_actor,
    }


def run_order_boundaries(helper, engine) -> dict[str, Any]:
    passed: list[str] = []

    # Prior product PLACE consumes two of three free slots, so the later DROP
    # must be rewritten against one remaining slot.
    obs = build_observation(
        engine, player=0, actors=2, room=3,
        inventories=[{"EGG": 2}, {"MILK": 5}],
    )
    action = {"farmer": ["PLACE", "EGG", 2], "hands": [["DROP"]], "market": []}
    out = helper.transform(obs, action, STANDARD_CONFIG, enabled=True)
    if out["hands"][0] != ["PLACE", "MILK", 1]:
        raise OracleError("prior PLACE room accounting failed")
    of, op = execute_units(engine, obs, action)
    gf, gp = execute_units(engine, obs, out)
    if of != gf or op["shed"] != gp["shed"] or gp["inventories"][1].get("MILK") != 4:
        raise OracleError("prior PLACE official-engine differential failed")
    passed.append("prior_product_place")

    # Prior DROP has the same room effect, but deletes the first actor's cargo in
    # both worlds; B7 must still guard only the later actor.
    obs = build_observation(
        engine, player=1, actors=2, room=3,
        inventories=[{"EGG": 2}, {"MILK": 5}],
    )
    action = {"farmer": ["DROP"], "hands": [["DROP"]], "market": []}
    out = helper.transform(obs, action, STANDARD_CONFIG, enabled=True)
    if out["farmer"] != ["DROP"] or out["hands"][0] != ["PLACE", "MILK", 1]:
        raise OracleError("prior DROP room accounting failed")
    of, op = execute_units(engine, obs, action)
    gf, gp = execute_units(engine, obs, out)
    if of != gf or op["shed"] != gp["shed"] or gp["inventories"][1].get("MILK") != 4:
        raise OracleError("prior DROP official-engine differential failed")
    passed.append("prior_drop")

    # A prior PICKUP changes room dynamically. The donor intentionally refuses
    # to approximate it when a later DROP would otherwise be guarded.
    obs = build_observation(
        engine, player=0, actors=2, room=3,
        inventories=[{}, {"MILK": 5}],
    )
    obs["private"]["shed"]["WHEAT"] = 1
    action = {"farmer": ["PICKUP", "WHEAT", 1], "hands": [["DROP"]], "market": []}
    out = helper.transform(obs, action, STANDARD_CONFIG, enabled=True)
    if out is not action:
        raise OracleError("prior PICKUP boundary did not fail exact-parent closed")
    passed.append("prior_pickup_fail_closed")

    # Animal/unknown PLACE can target a structure rather than the shed and is
    # therefore deliberately ambiguous for this capacity-only guard.
    obs = build_observation(
        engine, player=1, actors=2, room=1,
        inventories=[{"GOOSE": 1}, {"MILK": 5}],
    )
    action = {"farmer": ["PLACE", "GOOSE"], "hands": [["DROP"]], "market": []}
    out = helper.transform(obs, action, STANDARD_CONFIG, enabled=True)
    if out is not action:
        raise OracleError("ambiguous animal PLACE did not fail exact-parent closed")
    passed.append("ambiguous_place_fail_closed")

    # Disabled mode is the key-OFF identity theorem required before any wiring.
    obs = build_observation(
        engine, player=0, actors=1, room=0, inventories=[{"MILK": 5}],
    )
    action = {"farmer": ["DROP"], "hands": [], "market": []}
    if helper.transform(obs, action, STANDARD_CONFIG, enabled=False) is not action:
        raise OracleError("disabled B7 lost exact action identity")
    passed.append("disabled_identity")

    return {"passed": passed, "count": len(passed)}


def run() -> dict[str, Any]:
    root = repo_root(Path(__file__).resolve())
    pins = assert_pins(root)
    helper = load_module("_b7_guard_oracle", root / HELPER_REL)
    engine = load_module("_b7_engine_oracle", root / ENGINE_REL)
    matrix = run_matrix(helper, engine)
    boundaries = run_order_boundaries(helper, engine)
    return {
        "status": "PASS",
        "scope": "source-pinned B7 current-engine differential; evidence only; unwired",
        "pins": pins,
        "matrix": matrix,
        "boundaries": boundaries,
        "runtime_hook": (
            "compatible only as a final selected unit-action guard after "
            "_feed_stock_selected and _early_capital_selected; no hook is installed here"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = run()
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
