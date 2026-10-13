#!/usr/bin/env python3
"""TITAN V4 unit-before-market phase barrier.

This module is research/checker infrastructure only.  It does not rewrite an
action, schedule a purchase, or authorize runtime/default activation.

The official interpreter executes every farmer/hand action before
``_process_market`` in the same callback.  Therefore a unit action may consume
only resources/actors that existed in the pre-callback snapshot; a BUY/HIRE in
that callback becomes usable no earlier than a later callback.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

EXPECTED_ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ENGINE_RELATIVE_PATH = Path("reference/engine/kaggriculture.py")
DEFAULT_MAX_MARKET_ORDERS = 10
CURRENT_CROPS = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"}
CURRENT_ANIMALS = {"GOOSE", "COW", "SHEEP"}
BUYABLE_PRODUCTS = {"WHEAT", "FERTILIZER"}


class PhaseBarrierError(ValueError):
    """Raised when custody or caller input cannot be certified."""


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def default_engine_path() -> Path:
    here = Path(__file__).resolve()
    # Prefer discovery so copied test files fail cleanly instead of depending on
    # an absolute checkout depth.
    for parent in here.parents:
        candidate = parent / ENGINE_RELATIVE_PATH
        if candidate.exists():
            return candidate
    parents = list(here.parents)
    if len(parents) > 4:
        return parents[4] / ENGINE_RELATIVE_PATH
    return here.parent / ENGINE_RELATIVE_PATH


def _direct_call_name(call: ast.Call) -> str | None:
    return call.func.id if isinstance(call.func, ast.Name) else None


def certify_engine_source(
    source: bytes | str,
    *,
    expected_blob: str = EXPECTED_ENGINE_BLOB,
) -> dict[str, Any]:
    """Bind exact bytes and independently prove unit actions precede market.

    ``expected_blob`` is injectable only for mutation tests.  Production callers
    should use the pinned default.
    """
    raw = source.encode("utf-8") if isinstance(source, str) else bytes(source)
    got = git_blob_sha(raw)
    if got != expected_blob:
        raise PhaseBarrierError(
            f"ENGINE_BLOB_MISMATCH expected={expected_blob} got={got}"
        )
    try:
        tree = ast.parse(raw.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise PhaseBarrierError(f"ENGINE_PARSE_FAILURE {exc}") from exc

    interpreters = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "interpreter"
    ]
    if len(interpreters) != 1:
        raise PhaseBarrierError(
            f"INTERPRETER_COUNT expected=1 got={len(interpreters)}"
        )
    fn = interpreters[0]
    apply_lines = sorted(
        node.lineno
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and _direct_call_name(node) == "_apply_unit_action"
    )
    market_lines = sorted(
        node.lineno
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and _direct_call_name(node) == "_process_market"
    )
    if len(apply_lines) < 2:
        raise PhaseBarrierError(
            f"UNIT_PHASE_ANCHORS expected>=2 got={len(apply_lines)}"
        )
    if len(market_lines) != 1:
        raise PhaseBarrierError(
            f"MARKET_PHASE_ANCHORS expected=1 got={len(market_lines)}"
        )
    if max(apply_lines) >= market_lines[0]:
        raise PhaseBarrierError(
            "PHASE_ORDER_VIOLATION unit actions do not all precede market"
        )
    return {
        "engine_git_blob": got,
        "interpreter_lineno": fn.lineno,
        "unit_apply_lines": apply_lines,
        "market_process_line": market_lines[0],
        "unit_before_market": True,
    }


def certify_engine_path(path: Path | None = None) -> dict[str, Any]:
    target = default_engine_path() if path is None else Path(path)
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise PhaseBarrierError(f"ENGINE_READ_FAILURE path={target}: {exc}") from exc
    out = certify_engine_source(raw)
    out["engine_path"] = str(target)
    return out


def _nonnegative_count(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise PhaseBarrierError(f"{label} must be a nonnegative exact int")
    return value


def _count_map(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise PhaseBarrierError(f"{label} must be a mapping")
    out: dict[str, int] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not key:
            raise PhaseBarrierError(f"{label} keys must be nonempty strings")
        out[key] = _nonnegative_count(raw, f"{label}[{key!r}]")
    return out


def normalize_snapshot(pre: Any) -> dict[str, Any]:
    if not isinstance(pre, Mapping):
        raise PhaseBarrierError("snapshot must be a mapping")
    seeds = _count_map(pre.get("seeds", {}), "seeds")
    shed = _count_map(pre.get("shed", {}), "shed")
    raw_inventories = pre.get("inventories")
    if not isinstance(raw_inventories, list) or not raw_inventories:
        raise PhaseBarrierError("inventories must be a nonempty list")
    inventories = [
        _count_map(inv, f"inventories[{idx}]")
        for idx, inv in enumerate(raw_inventories)
    ]
    existing_hands = pre.get("existing_hands", len(inventories) - 1)
    existing_hands = _nonnegative_count(existing_hands, "existing_hands")
    if len(inventories) != existing_hands + 1:
        raise PhaseBarrierError(
            "inventories length must equal farmer + existing_hands"
        )
    return {
        "seeds": seeds,
        "shed": shed,
        "inventories": inventories,
        "existing_hands": existing_hands,
    }


def _engine_positive_qty(row: Any) -> int | None:
    if not isinstance(row, list) or len(row) < 3:
        return None
    try:
        qty = int(row[2])
    except (TypeError, ValueError, OverflowError):
        return None
    return qty if qty > 0 else None


def _market_acquisitions(action: Any, max_market_orders: int) -> dict[str, Any]:
    out = {
        "seed": {},
        "product": {},
        "animal": {},
        "hires": 0,
    }
    if not isinstance(action, Mapping):
        return out
    rows = action.get("market")
    if not isinstance(rows, list):
        return out
    for row in rows[:max_market_orders]:
        if not isinstance(row, list) or not row:
            continue
        op = row[0]
        if op == "HIRE":
            out["hires"] += 1
            continue
        if op not in {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL"} or len(row) < 3:
            continue
        item = row[1]
        qty = _engine_positive_qty(row)
        if not isinstance(item, str) or qty is None:
            continue
        if op == "BUY_SEED" and item not in CURRENT_CROPS:
            continue
        if op == "BUY_PRODUCT" and item not in BUYABLE_PRODUCTS:
            continue
        if op == "BUY_ANIMAL" and item not in CURRENT_ANIMALS:
            continue
        bucket = {
            "BUY_SEED": "seed",
            "BUY_PRODUCT": "product",
            "BUY_ANIMAL": "animal",
        }[op]
        out[bucket][item] = out[bucket].get(item, 0) + qty
    return out


def _unit_actions(action: Any) -> list[Any]:
    if not isinstance(action, Mapping):
        return [["PASS"]]
    farmer = action.get("farmer", ["PASS"])
    hands = action.get("hands", [])
    if not isinstance(hands, list):
        hands = []
    return [farmer, *hands]


def _action_head(action: Any) -> str | None:
    return (
        action[0]
        if isinstance(action, list) and action and isinstance(action[0], str)
        else None
    )


def _pickup_requested(action: Any) -> tuple[str, int] | None:
    if (
        not isinstance(action, list)
        or len(action) < 2
        or action[0] != "PICKUP"
        or not isinstance(action[1], str)
    ):
        return None
    if len(action) < 3:
        return action[1], 1
    try:
        qty = int(action[2])
    except (TypeError, ValueError, OverflowError):
        return None
    if qty <= 0:
        return None
    return action[1], qty


def _violation(
    code: str,
    *,
    actor_index: int | None,
    resource: str | None,
    pre_available: int,
    same_callback_market_qty: int,
    requested: int = 1,
) -> dict[str, Any]:
    return {
        "code": code,
        "actor_index": actor_index,
        "resource": resource,
        "pre_available": pre_available,
        "same_callback_market_qty": same_callback_market_qty,
        "requested": requested,
        "reason": "unit_phase_precedes_market_phase",
    }


def detect_same_callback_dependencies(
    pre_snapshot: Any,
    action: Any,
) -> list[dict[str, Any]]:
    """Return only dependencies caused by same-callback market acquisition.

    This is deliberately narrower than a full legality checker.  A unit action
    that is impossible for some other reason is not reported here unless a
    relevant BUY/HIRE in the same response could falsely appear to satisfy it.
    """
    pre = normalize_snapshot(pre_snapshot)
    max_market_orders = pre_snapshot.get("max_market_orders", DEFAULT_MAX_MARKET_ORDERS)
    if type(max_market_orders) is not int or max_market_orders <= 0:
        raise PhaseBarrierError("max_market_orders must be a positive exact int")
    acquired = _market_acquisitions(action, max_market_orders)
    units = _unit_actions(action)
    violations: list[dict[str, Any]] = []

    # PLANT validation is aggregate and atomic per crop before any market order.
    plant_demand: dict[str, int] = {}
    for unit in units:
        if (
            isinstance(unit, list)
            and len(unit) >= 2
            and unit[0] == "PLANT"
            and isinstance(unit[1], str)
        ):
            plant_demand[unit[1]] = plant_demand.get(unit[1], 0) + 1
    for crop in sorted(plant_demand):
        buy_qty = acquired["seed"].get(crop, 0)
        available = pre["seeds"].get(crop, 0)
        demand = plant_demand[crop]
        if buy_qty > 0 and demand > available:
            violations.append(
                _violation(
                    "BUY_SEED_AFTER_PLANT_PHASE",
                    actor_index=None,
                    resource=crop,
                    pre_available=available,
                    same_callback_market_qty=buy_qty,
                    requested=demand,
                )
            )

    # Actor-local inventory consumers and shed PICKUP use only pre-market state.
    for actor_index, unit in enumerate(units):
        op = _action_head(unit)
        inv = (
            pre["inventories"][actor_index]
            if actor_index < len(pre["inventories"])
            else {}
        )
        if op == "FEED":
            buy_qty = acquired["product"].get("WHEAT", 0)
            available = inv.get("WHEAT", 0)
            if buy_qty > 0 and available < 1:
                violations.append(
                    _violation(
                        "BUY_PRODUCT_AFTER_FEED_PHASE",
                        actor_index=actor_index,
                        resource="WHEAT",
                        pre_available=available,
                        same_callback_market_qty=buy_qty,
                    )
                )
        elif op == "FERTILIZE":
            buy_qty = acquired["product"].get("FERTILIZER", 0)
            available = inv.get("FERTILIZER", 0)
            if buy_qty > 0 and available < 1:
                violations.append(
                    _violation(
                        "BUY_PRODUCT_AFTER_FERTILIZE_PHASE",
                        actor_index=actor_index,
                        resource="FERTILIZER",
                        pre_available=available,
                        same_callback_market_qty=buy_qty,
                    )
                )
        elif op == "PICKUP":
            parsed = _pickup_requested(unit)
            if parsed is not None:
                item, requested = parsed
                buy_qty = (
                    acquired["animal"].get(item, 0)
                    + acquired["product"].get(item, 0)
                )
                available = pre["shed"].get(item, 0)
                if buy_qty > 0 and requested > available:
                    violations.append(
                        _violation(
                            "BUY_AFTER_PICKUP_PHASE",
                            actor_index=actor_index,
                            resource=item,
                            pre_available=available,
                            same_callback_market_qty=buy_qty,
                            requested=requested,
                        )
                    )
        elif op == "PLACE" and isinstance(unit, list) and len(unit) >= 2:
            item = unit[1]
            buy_qty = acquired["animal"].get(item, 0) if isinstance(item, str) else 0
            available = inv.get(item, 0) if isinstance(item, str) else 0
            if buy_qty > 0 and available < 1:
                violations.append(
                    _violation(
                        "BUY_ANIMAL_AFTER_PLACE_PHASE",
                        actor_index=actor_index,
                        resource=item if isinstance(item, str) else None,
                        pre_available=available,
                        same_callback_market_qty=buy_qty,
                    )
                )

    # Extra authored hand actions cannot be serviced by HIRE rows in this callback.
    existing_hands = pre["existing_hands"]
    if acquired["hires"] > 0:
        hands = units[1:]
        for hand_offset, hand_action in enumerate(hands):
            if hand_offset < existing_hands:
                continue
            if _action_head(hand_action) not in {None, "PASS"}:
                violations.append(
                    _violation(
                        "HIRE_AFTER_UNIT_PHASE",
                        actor_index=hand_offset + 1,
                        resource="HAND",
                        pre_available=existing_hands,
                        same_callback_market_qty=acquired["hires"],
                    )
                )

    return violations


def audit(pre_snapshot: Any, action: Any) -> dict[str, Any]:
    violations = detect_same_callback_dependencies(pre_snapshot, action)
    return {
        "contract": "unit_phase_precedes_market_phase",
        "engine_git_blob": EXPECTED_ENGINE_BLOB,
        "admissible": not violations,
        "violations": violations,
        "decision_authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, default=None)
    parser.add_argument("--snapshot-json", type=Path)
    parser.add_argument("--action-json", type=Path)
    ns = parser.parse_args()

    receipt = {"engine": certify_engine_path(ns.engine)}
    if (ns.snapshot_json is None) ^ (ns.action_json is None):
        parser.error("--snapshot-json and --action-json must be supplied together")
    if ns.snapshot_json is not None:
        pre = json.loads(ns.snapshot_json.read_text(encoding="utf-8"))
        action = json.loads(ns.action_json.read_text(encoding="utf-8"))
        receipt["audit"] = audit(pre, action)
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
