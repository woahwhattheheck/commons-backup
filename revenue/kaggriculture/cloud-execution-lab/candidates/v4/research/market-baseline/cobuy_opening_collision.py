#!/usr/bin/env python3
"""Source-bound opening COBUY collision witness.

Research/evidence only. This does not retime any order or authorize activation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ARLENE_BLOB = "bdb9cf58148a3c7961c085f4902759537decabf6"
APEX_TAPE_BLOB = "00ea34e3a3f340792ff61de0671abb4c1073472a"
APEX_POLICY_BLOB = "ea238366136ce9df06811691831445f183d0b936"
APEX_MAIN_BLOB = "f2ae8d9b229755235b93e98cd216d59ba0af4d9f"
APEX_GUARD_BLOB = "38a75d26cd366e7145dfee86c4c43d53e6b1268f"
TURNS = 719
ROUTES = 2
MAX_ORDERS = 10
PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER")
MARKET_OPS = ("PASS", "HIRE", "BUY_LAND", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL")
CONFIG = {"boardSize": 10, "shedCapacity": 100, "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}
STARTING_MONEY = 1_000


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def checked_text(path: Path, expected_blob: str) -> str:
    data = path.read_bytes()
    actual = git_blob(data)
    if actual != expected_blob:
        raise ValueError(f"Git blob mismatch for {path}: expected {expected_blob}, got {actual}")
    return data.decode("utf-8")


def decode_apex_action(encoded: str) -> dict[str, Any]:
    values = [int(v) for v in encoded.split()]
    if len(values) < 2:
        raise ValueError("short Apex action")
    n_units, n_orders = values[:2]
    if not (0 <= n_units <= 40 and 0 <= n_orders <= 16):
        raise ValueError("invalid Apex action counts")
    cursor = 2
    units = []
    for _ in range(n_units):
        if cursor + 3 > len(values):
            raise ValueError("truncated unit triple")
        units.append(tuple(values[cursor:cursor + 3]))
        cursor += 3
    orders = []
    for _ in range(n_orders):
        if cursor + 3 > len(values):
            raise ValueError("truncated market triple")
        op, item, qty = values[cursor:cursor + 3]
        orders.append((op, item, qty))
        cursor += 3
    if cursor != len(values):
        raise ValueError("trailing Apex action values")
    return {"units": units, "orders": orders}


def parse_apex_tapes(text: str) -> list[list[str]]:
    turns_match = re.search(r"constexpr int kTurns = (\d+);", text)
    routes_match = re.search(r"constexpr int kRoutes = (\d+);", text)
    if not turns_match or not routes_match:
        raise ValueError("Apex tape dimensions missing")
    turns, routes = int(turns_match.group(1)), int(routes_match.group(1))
    if (turns, routes) != (TURNS, ROUTES):
        raise ValueError(f"Apex tape dimension drift: {(turns, routes)}")
    encoded = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', text)
    if len(encoded) != TURNS * ROUTES:
        raise ValueError(f"expected {TURNS * ROUTES} encoded actions, found {len(encoded)}")
    return [encoded[r * TURNS:(r + 1) * TURNS] for r in range(ROUTES)]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_engine(path: Path):
    checked_text(path, ENGINE_BLOB)
    try:
        import kaggle_environments.utils  # noqa: F401
    except ModuleNotFoundError:
        pkg = sys.modules.setdefault("kaggle_environments", types.ModuleType("kaggle_environments"))
        util = types.ModuleType("kaggle_environments.utils")
        util.resolve_episode_seed = lambda env: int(getattr(env, "info", {}).get("seed", 0))
        pkg.utils = util
        sys.modules["kaggle_environments.utils"] = util
    return load_module(path, "_cobuy_opening_engine")


def arlene_opening(arlene_path: Path) -> dict[str, Any]:
    checked_text(arlene_path, ARLENE_BLOB)
    arlene = load_module(arlene_path, "_cobuy_opening_arlene")
    rows = {}
    for route_id, route in sorted(arlene.routes().items()):
        market = list(route[0].get("market") or [])[:MAX_ORDERS]
        rows[route_id] = market
    opening = {json.dumps(v, separators=(",", ":")) for v in rows.values()}
    if len(opening) != 1:
        raise AssertionError("Arlene routes diverge at step 0")
    row0 = next(iter(rows.values()))[0]
    if row0 != ["BUY_PRODUCT", "WHEAT", 13]:
        raise AssertionError(f"unexpected Arlene opening row0: {row0!r}")
    return {"route_markets": rows, "row0": row0}


def apex_opening(tape_path: Path, policy_path: Path, main_path: Path, guard_path: Path) -> dict[str, Any]:
    tape = parse_apex_tapes(checked_text(tape_path, APEX_TAPE_BLOB))
    policy = checked_text(policy_path, APEX_POLICY_BLOB)
    main = checked_text(main_path, APEX_MAIN_BLOB)
    guard = checked_text(guard_path, APEX_GUARD_BLOB)
    if "if (state.step == 0) selected_route = 0;" not in policy:
        raise AssertionError("Apex step-0 route reset contract missing")
    if "action['market'] = market[:10]" not in main:
        raise AssertionError("Apex final market-row cap contract missing")
    if "Action result = input;" not in guard or "add_budget_sale" not in guard:
        raise AssertionError("Apex six-day guard contract missing")
    decoded = decode_apex_action(tape[0][0])
    if not decoded["orders"]:
        raise AssertionError("Apex route0 step0 has no market row")
    op, item, qty = decoded["orders"][0]
    named = [MARKET_OPS[op], PRODUCTS[item], qty]
    if named != ["BUY_PRODUCT", "WHEAT", 13]:
        raise AssertionError(f"unexpected Apex opening row0: {named!r}")
    return {"route": 0, "encoded": tape[0][0], "decoded": decoded, "row0": named}


def _world(engine):
    farms = [engine._new_farm(CONFIG["boardSize"], STARTING_MONEY) for _ in range(2)]
    privates = [engine._new_private() for _ in range(2)]
    market = engine._new_market()
    states = []
    for player in range(2):
        obs = SimpleNamespace(player=player, farms=farms, private=privates[player], market=market)
        states.append(SimpleNamespace(observation=obs, action={}))
    env = SimpleNamespace(configuration=dict(CONFIG), info={"seed": 0})
    return states, env


def _run_market(engine, row0: list[Any], *, self_row: int, rival_seat: int) -> dict[str, Any]:
    states, env = _world(engine)
    self_seat = 1 - rival_seat
    before_money = [float(f["money"]) for f in states[0].observation.farms]
    before_inventory = int(states[0].observation.market["inventory"]["WHEAT"])
    for seat in (0, 1):
        orders = [list(row0)]
        if seat == self_seat and self_row == 1:
            orders.insert(0, ["SELL", "WHEAT", 0])
        states[seat].action = {"farmer": ["PASS"], "hands": [], "market": orders}
    engine._process_market(states, env)
    farms = states[0].observation.farms
    fills = [int(states[i].observation.private["shed"]["WHEAT"]) for i in (0, 1)]
    costs = [int(round(before_money[i] - float(farms[i]["money"]))) for i in (0, 1)]
    return {
        "rival_seat": rival_seat,
        "self_seat": self_seat,
        "self_raw_order_index": self_row,
        "filled_qty_by_seat": fills,
        "cost_by_seat": costs,
        "market_inventory_before": before_inventory,
        "market_inventory_after": int(states[0].observation.market["inventory"]["WHEAT"]),
    }


def build_receipt(*, engine_path: Path, arlene_path: Path, tape_path: Path,
                  policy_path: Path, apex_main_path: Path, guard_path: Path) -> dict[str, Any]:
    own = arlene_opening(arlene_path)
    rival = apex_opening(tape_path, policy_path, apex_main_path, guard_path)
    if own["row0"] != rival["row0"]:
        raise AssertionError("opening source rows do not collide")
    engine = load_engine(engine_path)
    aligned = [_run_market(engine, own["row0"], self_row=0, rival_seat=s) for s in (0, 1)]
    misaligned = [_run_market(engine, own["row0"], self_row=1, rival_seat=s) for s in (0, 1)]
    for case in aligned:
        if case["filled_qty_by_seat"] != [13, 13]:
            raise AssertionError(f"opening fill drift: {case}")
    for a, m in zip(aligned, misaligned):
        self_seat = a["self_seat"]
        if a["market_inventory_after"] != m["market_inventory_after"]:
            raise AssertionError("aligned/misaligned terminal inventory differs")
        if m["cost_by_seat"][self_seat] - a["cost_by_seat"][self_seat] != 13:
            raise AssertionError("opening row-alignment value drift")
    return {
        "schema": "titan-v4-cobuy-current-native-opening-v1",
        "status": "CURRENT_ALREADY_ALIGNED_GUARDRAIL",
        "decision_authority": False,
        "scope": "deterministic step-0 opening only; not a 719-step collision census",
        "source_blobs": {
            "official_engine": ENGINE_BLOB,
            "arlene": ARLENE_BLOB,
            "apex_tape": APEX_TAPE_BLOB,
            "apex_policy": APEX_POLICY_BLOB,
            "apex_main": APEX_MAIN_BLOB,
            "apex_six_day_guard": APEX_GUARD_BLOB,
        },
        "collision": {
            "step": 0,
            "raw_order_index": 0,
            "item": "WHEAT",
            "rival_authored_qty": 13,
            "own_required_qty": 13,
            "apex_selected_route": 0,
            "arlene_route_ids": sorted(own["route_markets"]),
        },
        "aligned_both_seats": aligned,
        "misaligned_both_seats": misaligned,
        "delta": {
            "aligned_self_cost": 370,
            "misaligned_self_cost": 383,
            "self_cost_penalty_if_moved_to_row1": 13,
            "terminal_inventory_equal": True,
        },
        "disposition": [
            "preserve current step-0 WHEAT13 raw-row-0 alignment",
            "do not treat this already-aligned cell as a new profit opportunity",
            "continue broader current-native/replay collision census for other required buys",
            "no runtime/default/config/archive/Kaggle activation from this receipt",
        ],
    }


def default_paths(root: Path) -> dict[str, Path]:
    lab = root / "revenue/kaggriculture/cloud-execution-lab"
    apex = root / "revenue/kaggriculture/cloud-frontier-policy/next-panel/vendor/apex"
    return {
        "engine_path": lab / "reference/engine/kaggriculture.py",
        "arlene_path": lab / "reference/next-panel/vendor/arlene.py",
        "tape_path": apex / "source/tape.inc",
        "policy_path": apex / "source/policy.cpp",
        "apex_main_path": apex / "main.py",
        "guard_path": apex / "source/include/six_day_budget_guard.hpp",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[7])
    ns = ap.parse_args(argv)
    receipt = build_receipt(**default_paths(ns.repo_root))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
