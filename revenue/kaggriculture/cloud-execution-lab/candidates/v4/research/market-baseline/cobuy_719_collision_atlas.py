#!/usr/bin/env python3
"""Fail-closed 719-step authored COBUY collision atlas.

Research/evidence only. This extends the existing COBUY family without retiming
orders or claiming current-rival private-action visibility.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

COBUY_HELPER_BLOB = "c965ec1411aa5f6cff790be771504e2d43a2fd7d"
SCHEMA = "titan-v4-cobuy-719-authored-collision-atlas/v1"
BUYABLE = ("WHEAT", "FERTILIZER")
EXPECTED_APEX_GUARD_INTERVAL = 72
APEX_TERMINAL_STRIP_STEP = 718
OPENING_RECEIPT_BLOB = "b85fff2dd56dc319fc3b915bcd2a3d04b39186a2"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _load_verified_source_module(path: Path, expected_blob: str, name: str) -> ModuleType:
    """Read, authenticate, compile, and execute one immutable byte snapshot."""
    data = path.read_bytes()
    actual = git_blob(data)
    if actual != expected_blob:
        raise ValueError(f"Git blob mismatch for {path}: {actual} != {expected_blob}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"non-UTF-8 verified source: {path}") from exc
    module = ModuleType(name)
    module.__file__ = str(path)
    code = compile(text, f"{path}@gitblob:{actual}", "exec")
    exec(code, module.__dict__)
    return module


# The sibling helper defines the reviewed tape codec/source identities used by
# the opening COBUY theorem. Execute one exact reviewed snapshot rather than a
# normal import so decoder/constants cannot drift behind the evidence receipt.
_HELPER = _load_verified_source_module(
    Path(__file__).with_name("cobuy_opening_collision.py"),
    COBUY_HELPER_BLOB,
    "_cobuy_opening_collision_verified",
)
APEX_GUARD_BLOB = _HELPER.APEX_GUARD_BLOB
APEX_MAIN_BLOB = _HELPER.APEX_MAIN_BLOB
APEX_POLICY_BLOB = _HELPER.APEX_POLICY_BLOB
APEX_TAPE_BLOB = _HELPER.APEX_TAPE_BLOB
ARLENE_BLOB = _HELPER.ARLENE_BLOB
ENGINE_BLOB = _HELPER.ENGINE_BLOB
MARKET_OPS = _HELPER.MARKET_OPS
MAX_ORDERS = _HELPER.MAX_ORDERS
PRODUCTS = _HELPER.PRODUCTS
TURNS = _HELPER.TURNS
checked_text = _HELPER.checked_text
decode_apex_action = _HELPER.decode_apex_action
parse_apex_tapes = _HELPER.parse_apex_tapes


def _require_blob(path: Path, expected: str, label: str) -> bytes:
    data = path.read_bytes()
    actual = git_blob(data)
    if actual != expected:
        raise ValueError(f"{label} Git blob mismatch: {actual} != {expected}")
    return data


def _buy_row(raw: Any) -> tuple[str, int] | None:
    if not isinstance(raw, list) or len(raw) < 3:
        return None
    if raw[0] != "BUY_PRODUCT" or raw[1] not in BUYABLE:
        return None
    qty = raw[2]
    if type(qty) is not int or qty <= 0:
        return None
    return str(raw[1]), qty


def _arlene_row_stable(market: list[Any], row: int) -> bool:
    """clamp_sells may delete an earlier SELL and shift every later row."""
    return not any(
        isinstance(raw, list) and raw and raw[0] == "SELL"
        for raw in market[:row]
    )


def load_arlene(path: Path) -> ModuleType:
    module = _load_verified_source_module(path, ARLENE_BLOB, "_cobuy_719_arlene")
    for name in ("routes", "MAX_ORDERS", "FINAL_EXECUTABLE_STEP"):
        if not hasattr(module, name):
            raise ValueError(f"Arlene source missing {name}")
    if module.MAX_ORDERS != MAX_ORDERS:
        raise ValueError(f"Arlene MAX_ORDERS drift: {module.MAX_ORDERS!r}")
    if type(module.FINAL_EXECUTABLE_STEP) is not int:
        raise ValueError("Arlene FINAL_EXECUTABLE_STEP must be a plain int")
    return module


def arlene_route_pulses(module: ModuleType) -> dict[str, list[dict[str, Any]]]:
    routes = module.routes()
    if not isinstance(routes, dict) or not routes:
        raise ValueError("Arlene routes() must return a nonempty dict")
    stop = min(TURNS, module.FINAL_EXECUTABLE_STEP + 1)
    out: dict[str, list[dict[str, Any]]] = {}
    for route_id in sorted(routes):
        route = routes[route_id]
        if not isinstance(route, list) or len(route) < stop:
            raise ValueError(f"Arlene route {route_id!r} is too short")
        pulses: list[dict[str, Any]] = []
        for step in range(stop):
            action = route[step]
            if not isinstance(action, dict):
                continue
            market = action.get("market")
            if not isinstance(market, list):
                continue
            capped = market[:MAX_ORDERS]
            for row, raw in enumerate(capped):
                parsed = _buy_row(raw)
                if parsed is None:
                    continue
                item, qty = parsed
                pulses.append({
                    "route": str(route_id),
                    "step": step,
                    "row": row,
                    "item": item,
                    "qty": qty,
                    "raw_index_stable": _arlene_row_stable(capped, row),
                })
        out[str(route_id)] = pulses
    return out


def _invariant_pulses(per_route: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Exact stable (step,row,item,qty) intersection across every route."""
    route_ids = sorted(per_route)
    if not route_ids:
        return []
    key_sets = [
        {
            (p["step"], p["row"], p["item"], p["qty"])
            for p in per_route[route_id]
            if p["raw_index_stable"]
        }
        for route_id in route_ids
    ]
    shared = set.intersection(*key_sets)
    return [
        {"step": step, "row": row, "item": item, "qty": qty}
        for step, row, item, qty in sorted(shared)
    ]


def _decode_apex_market(encoded: str) -> list[list[Any]]:
    """Mirror Apex _unpack_action before its final Python market[:10] cap."""
    decoded = decode_apex_action(encoded)
    out: list[list[Any]] = []
    for op_idx, item_idx, qty in decoded["orders"]:
        if not (0 <= op_idx < len(MARKET_OPS)):
            continue
        op = MARKET_OPS[op_idx]
        if op == "PASS":
            continue
        if op in ("HIRE", "BUY_LAND"):
            out.append([op])
            continue
        if not (0 <= item_idx < len(PRODUCTS)):
            out.append(["OTHER", item_idx, qty])
            continue
        out.append([op, PRODUCTS[item_idx], qty])
    return out


def apex_route_pulses(
    tape_text: str,
    *,
    native_verified_opening: bool,
    guard_interval: int = EXPECTED_APEX_GUARD_INTERVAL,
) -> dict[str, list[dict[str, Any]]]:
    if type(guard_interval) is not int or guard_interval <= 0:
        raise ValueError("Apex guard interval must be a positive plain int")
    tapes = parse_apex_tapes(tape_text)
    out: dict[str, list[dict[str, Any]]] = {}
    for route_index, route in enumerate(tapes):
        pulses: list[dict[str, Any]] = []
        for step, encoded in enumerate(route):
            market = _decode_apex_market(encoded)[:MAX_ORDERS]
            for row, raw in enumerate(market):
                parsed = _buy_row(raw)
                if parsed is None:
                    continue
                item, qty = parsed
                guard_boundary = step % guard_interval == 0
                terminal_stripped = step == APEX_TERMINAL_STRIP_STEP
                opening_exception = step == 0 and native_verified_opening
                pulses.append({
                    "route": str(route_index),
                    "step": step,
                    "row": row,
                    "item": item,
                    "qty": qty,
                    "raw_index_stable": (
                        not terminal_stripped
                        and (not guard_boundary or opening_exception)
                    ),
                    "guard_boundary": guard_boundary,
                    "terminal_stripped": terminal_stripped,
                })
        out[str(route_index)] = pulses
    return out


def _pair_collisions(
    own_pulses: list[dict[str, Any]],
    rival_pulses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return every same-step/item pair; never collapse repeated same-item buys."""
    own_by_key: dict[tuple[int, str], list[dict[str, Any]]] = {}
    rival_by_key: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for pulse in own_pulses:
        own_by_key.setdefault((pulse["step"], pulse["item"]), []).append(pulse)
    for pulse in rival_pulses:
        rival_by_key.setdefault((pulse["step"], pulse["item"]), []).append(pulse)
    collisions: list[dict[str, Any]] = []
    for key in sorted(set(own_by_key) & set(rival_by_key)):
        owns = sorted(own_by_key[key], key=lambda p: (p["row"], p["qty"]))
        rivals = sorted(rival_by_key[key], key=lambda p: (p["row"], p["qty"]))
        for own in owns:
            for rival in rivals:
                collisions.append({
                    "step": own["step"],
                    "item": own["item"],
                    "own_row": own["row"],
                    "own_qty": own["qty"],
                    "rival_row": rival["row"],
                    "rival_qty": rival["qty"],
                    "same_raw_index": own["row"] == rival["row"],
                    "row_delta_own_minus_rival": own["row"] - rival["row"],
                })
    return collisions


def _is_known_opening_guardrail(collision: dict[str, Any]) -> bool:
    return (
        collision.get("step") == 0
        and collision.get("item") == "WHEAT"
        and collision.get("own_row") == 0
        and collision.get("own_qty") == 13
        and collision.get("rival_row") == 0
        and collision.get("rival_qty") == 13
    )


def _classify_collisions(
    collisions: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    novel = [c for c in collisions if not _is_known_opening_guardrail(c)]
    if novel:
        return "NOVEL_AUTHORITATIVE_COLLISIONS_FOUND", novel
    if any(_is_known_opening_guardrail(c) for c in collisions):
        return "OPENING_ONLY_GUARDRAIL_NO_NEW_COLLISIONS", []
    return "COLD_NO_ROUTE_INVARIANT_AUTHORED_COLLISIONS", []


def _load_opening_receipt(path: Path) -> dict[str, Any]:
    receipt = json.loads(_require_blob(path, OPENING_RECEIPT_BLOB, "COBUY opening receipt"))
    if receipt.get("schema") != "titan-v4-cobuy-current-native-opening-v1":
        raise ValueError("unexpected COBUY opening receipt schema")
    native = receipt.get("native_entrypoint_verification") or {}
    receipt["_native_opening_verified"] = (
        native.get("apex_agent_step0_post_guard")
        == "VERIFIED_WHEAT13_RAW_ROW0_BOTH_SEATS"
    )
    return receipt


def _assert_apex_source_contracts(
    main_text: str,
    guard_text: str,
    policy_text: str,
) -> int:
    for marker in (
        "action['market'] = market[:10]",
        "market = [o for o in market if o[0] == 'SELL']",
    ):
        if marker not in main_text:
            raise ValueError(f"Apex main source contract missing: {marker}")
    for marker in (
        "inline void budget_sales_first(Action& action)",
        "if (added > 0 && settings.sales_first) budget_sales_first(result);",
        "action.orders[action.n_orders++]",
    ):
        if marker not in guard_text:
            raise ValueError(f"Apex guard source contract missing: {marker}")
    for marker in (
        "if (state.step == 0) selected_route = 0;",
        "if (state.step % kSegmentTurns != 0) return input;",
        "settings.interval_turns = kSegmentTurns;",
    ):
        if marker not in policy_text:
            raise ValueError(f"Apex policy source contract missing: {marker}")
    match = re.search(r"constexpr int kSegmentTurns\s*=\s*(\d+)\s*;", policy_text)
    if not match:
        raise ValueError("Apex policy kSegmentTurns contract missing")
    interval = int(match.group(1))
    if interval != EXPECTED_APEX_GUARD_INTERVAL:
        raise ValueError(
            f"Apex effective guard cadence drift: {interval} != "
            f"{EXPECTED_APEX_GUARD_INTERVAL}"
        )
    return interval


def build_atlas(
    *,
    engine_path: Path,
    arlene_path: Path,
    apex_tape_path: Path,
    apex_policy_path: Path,
    apex_main_path: Path,
    apex_guard_path: Path,
    opening_receipt_path: Path,
) -> dict[str, Any]:
    checked_text(engine_path, ENGINE_BLOB)
    arlene_routes = arlene_route_pulses(load_arlene(arlene_path))
    own_invariant = _invariant_pulses(arlene_routes)

    tape_text = checked_text(apex_tape_path, APEX_TAPE_BLOB)
    policy_text = checked_text(apex_policy_path, APEX_POLICY_BLOB)
    main_text = checked_text(apex_main_path, APEX_MAIN_BLOB)
    guard_text = checked_text(apex_guard_path, APEX_GUARD_BLOB)
    guard_interval = _assert_apex_source_contracts(main_text, guard_text, policy_text)

    opening_receipt = _load_opening_receipt(opening_receipt_path)
    apex_routes = apex_route_pulses(
        tape_text,
        native_verified_opening=opening_receipt["_native_opening_verified"],
        guard_interval=guard_interval,
    )
    rival_invariant = _invariant_pulses(apex_routes)
    collisions = _pair_collisions(own_invariant, rival_invariant)
    status, novel_collisions = _classify_collisions(collisions)

    route_pair_candidates: list[dict[str, Any]] = []
    for own_route, own_pulses in sorted(arlene_routes.items()):
        own_stable = [p for p in own_pulses if p["raw_index_stable"]]
        for rival_route, rival_pulses in sorted(apex_routes.items()):
            rival_stable = [p for p in rival_pulses if p["raw_index_stable"]]
            for pair in _pair_collisions(own_stable, rival_stable):
                route_pair_candidates.append({
                    "own_route": own_route,
                    "rival_route": rival_route,
                    **pair,
                })

    opening = [c for c in collisions if _is_known_opening_guardrail(c)]
    excluded = [
        step for step in range(0, TURNS, guard_interval)
        if step != 0
    ]
    return {
        "schema": SCHEMA,
        "status": status,
        "decision_authority": False,
        "source_blobs": {
            "official_engine": ENGINE_BLOB,
            "cobuy_opening_collision.py": COBUY_HELPER_BLOB,
            "arlene": ARLENE_BLOB,
            "apex_tape": APEX_TAPE_BLOB,
            "apex_policy": APEX_POLICY_BLOB,
            "apex_main": APEX_MAIN_BLOB,
            "apex_six_day_guard": APEX_GUARD_BLOB,
            "opening_receipt": OPENING_RECEIPT_BLOB,
        },
        "scope": {
            "steps": [0, TURNS - 1],
            "max_market_rows": MAX_ORDERS,
            "buyable_items": list(BUYABLE),
            "apex_effective_guard_interval": guard_interval,
            "own_authority": "exact stable route-invariant Arlene BUY_PRODUCT only",
            "rival_authority": "exact stable route-invariant Apex tape BUY_PRODUCT only",
            "route_conditional_is_authority": False,
            "private_current_rival_action_used": False,
            "field_economics_claimed": False,
            "guard_boundaries_excluded_without_native_receipt": excluded,
            "terminal_non_sell_strip_step": APEX_TERMINAL_STRIP_STEP,
        },
        "opening_native_receipt_verified": opening_receipt["_native_opening_verified"],
        "own_route_ids": sorted(arlene_routes),
        "rival_route_ids": sorted(apex_routes),
        "own_invariant_pulses": own_invariant,
        "rival_invariant_pulses": rival_invariant,
        "authoritative_collisions": collisions,
        "novel_authoritative_collisions": novel_collisions,
        "route_pair_candidates": route_pair_candidates,
        "counts": {
            "own_routes": len(arlene_routes),
            "rival_routes": len(apex_routes),
            "own_stable_route_invariant_pulses": len(own_invariant),
            "rival_stable_route_invariant_pulses": len(rival_invariant),
            "authoritative_collisions": len(collisions),
            "known_opening_guardrails": len(opening),
            "novel_authoritative_collisions": len(novel_collisions),
            "authoritative_same_row_collisions": sum(c["same_raw_index"] for c in collisions),
            "novel_same_row_collisions": sum(c["same_raw_index"] for c in novel_collisions),
            "route_pair_candidates": len(route_pair_candidates),
        },
        "controls": {
            "step0_wheat_collision_present": bool(opening),
            "step0_wheat_same_row": any(c["same_raw_index"] for c in opening),
        },
        "limits": [
            "This is an authored-source atlas, not a replay of hidden rival current actions.",
            "The already-closed step-0 WHEAT13 guardrail is separated from novel frontier collisions.",
            "The official engine identity is authenticated as theorem authority before any atlas is emitted.",
            "Arlene and the shared COBUY helper execute only from authenticated in-memory source snapshots.",
            "Apex guard cadence is bound from authenticated policy.cpp; every nonzero 72-turn boundary fails closed.",
            "Arlene rows after an authored SELL fail closed because clamp_sells may delete that SELL and shift the buy.",
            "Route-pair candidates are research narrowing only; only route-invariant collisions are authoritative.",
            "Repeated same-item buys are retained as distinct raw-row pairs rather than collapsed.",
            "No price/EV claim is made for later-game collisions without realized public market state.",
            "No runtime/default/config/archive/Kaggle activation is authorized by this atlas.",
        ],
    }


def default_paths(root: Path) -> dict[str, Path]:
    lab = root / "revenue/kaggriculture/cloud-execution-lab"
    apex = root / "revenue/kaggriculture/cloud-frontier-policy/next-panel/vendor/apex"
    package = lab / "candidates/v4/research/market-baseline"
    return {
        "engine_path": lab / "reference/engine/kaggriculture.py",
        "arlene_path": lab / "reference/next-panel/vendor/arlene.py",
        "apex_tape_path": apex / "source/tape.inc",
        "apex_policy_path": apex / "source/policy.cpp",
        "apex_main_path": apex / "main.py",
        "apex_guard_path": apex / "source/include/six_day_budget_guard.hpp",
        "opening_receipt_path": package / "COBUY-CURRENT-NATIVE-OPENING.json",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[7])
    ap.add_argument("--output", type=Path)
    ns = ap.parse_args(argv)
    result = build_atlas(**default_paths(ns.repo_root))
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if ns.output:
        ns.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
