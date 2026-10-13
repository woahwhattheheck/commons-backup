#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed B7 EOD cargo-custody oracle/admission.

The official engine auto-drops inventories in actor-index order at EOD. When the
shed is full during unit actions and a later market SELL frees room, an earlier
actor's low-value carried cargo can consume that room before a later actor's
higher-value cargo. This module models that exact deposit order and exposes one
narrow default-OFF admission: on an EOD callback with a completely full shed,
all unit rows literal PASS, and only valid SELL market rows, rewrite at most one
shed-adjacent actor PASS -> DROP when doing so strictly increases the current-
price value of cargo retained by the subsequent EOD auto-drop.

This is not a general optimizer or an activation recommendation. It intentionally
refuses non-EOD turns, partial shed room, unit mutations, BUY/HIRE/LAND rows,
non-product carried cargo, ambiguous price/state types, ties, and source drift.
"""
from __future__ import annotations

import copy
import hashlib
import math
from collections import Counter
from pathlib import Path
from typing import Any

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
DEFAULT_BOARD_SIZE = 10
DEFAULT_SHED_CAPACITY = 100
DEFAULT_TURNS_PER_DAY = 24
DEFAULT_MAX_MARKET_ORDERS = 10
PRODUCTS = frozenset(
    (
        "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
        "EGG", "MILK", "WOOL", "FERTILIZER",
    )
)

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[4]
ENGINE_PATH = LAB / "reference" / "engine" / "kaggriculture.py"
telemetry = Counter()


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def assert_engine_source(path: Path = ENGINE_PATH) -> str:
    data = path.read_bytes()
    actual = git_blob_sha(data)
    if actual != ENGINE_GIT_BLOB:
        raise RuntimeError(f"engine drift: expected {ENGINE_GIT_BLOB}, got {actual}")
    return actual


def _cfg(configuration: Any, name: str, default: Any) -> Any:
    if configuration is None:
        return default
    if isinstance(configuration, dict):
        return configuration.get(name, default)
    return getattr(configuration, name, default)


def _strict_positive_int(configuration: Any, name: str, default: int) -> int | None:
    value = _cfg(configuration, name, default)
    return value if type(value) is int and value > 0 else None


def _strict_nonnegative_mapping(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    out: dict[str, int] = {}
    for key, qty in value.items():
        if not isinstance(key, str) or type(qty) is not int or qty < 0:
            return None
        out[key] = qty
    return out


def _strict_product_inventory(value: Any) -> dict[str, int] | None:
    out = _strict_nonnegative_mapping(value)
    if out is None or any(key not in PRODUCTS for key in out):
        return None
    return out


def _strict_price(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    price = float(value)
    if not math.isfinite(price) or price < 0:
        return None
    return price


def _shed_access_tiles(board_size: int) -> set[tuple[int, int]]:
    half = board_size // 2
    return {
        (half - 1, half - 1),
        (half, half - 1),
        (half - 1, half),
        (half, half),
    }


def _strict_position(value: Any, board_size: int) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    x, y = value
    if type(x) is not int or type(y) is not int:
        return None
    if not (0 <= x < board_size and 0 <= y < board_size):
        return None
    return (x, y)


def project_eod_drop(
    shed: dict[str, int], inventories: list[dict[str, int]], capacity: int
) -> dict[str, Any]:
    """Mirror `_drop_inventories_to_shed` without mutating inputs.

    Actor order and each inventory's insertion order are semantically relevant.
    Existing shed keys may include animals; carried inventories are product-only
    for this package's admission path.
    """
    if type(capacity) is not int or capacity <= 0:
        raise ValueError("capacity must be a positive int")
    checked_shed = _strict_nonnegative_mapping(shed)
    if checked_shed is None:
        raise ValueError("malformed shed")
    checked_inventories: list[dict[str, int]] = []
    for inventory in inventories:
        checked = _strict_product_inventory(inventory)
        if checked is None:
            raise ValueError("malformed carried inventory")
        checked_inventories.append(checked)

    out_shed = dict(checked_shed)
    deposited: list[dict[str, int]] = []
    discarded: list[dict[str, int]] = []
    for inventory in checked_inventories:
        actor_deposited: dict[str, int] = {}
        actor_discarded: dict[str, int] = {}
        for item, qty in inventory.items():
            if qty <= 0:
                continue
            room = max(0, capacity - sum(out_shed.values()))
            take = min(qty, room)
            if take:
                out_shed[item] = out_shed.get(item, 0) + take
                actor_deposited[item] = take
            if qty > take:
                actor_discarded[item] = qty - take
        deposited.append(actor_deposited)
        discarded.append(actor_discarded)
    return {"shed": out_shed, "deposited": deposited, "discarded": discarded}


def _deposit_value(projection: dict[str, Any], prices: dict[str, float]) -> float:
    total = 0.0
    for actor in projection["deposited"]:
        for item, qty in actor.items():
            total += prices[item] * qty
    return total


def _postmarket_shed_after_sells(
    shed: dict[str, int], rows: Any, max_orders: int
) -> tuple[dict[str, int], dict[str, int]] | None:
    """Capacity-only projection for a market queue containing SELL rows only.

    The engine removes one shed unit for every successful SELL even at the $1
    floor. Price/supply side effects are irrelevant to this custody calculation.
    """
    if not isinstance(rows, list):
        return None
    out = dict(shed)
    sold: dict[str, int] = {}
    for row in rows[:max_orders]:
        if (
            not isinstance(row, list)
            or len(row) < 3
            or row[0] != "SELL"
            or row[1] not in PRODUCTS
            or type(row[2]) is not int
            or row[2] <= 0
        ):
            return None
        item = row[1]
        units = min(row[2], out.get(item, 0))
        if units:
            out[item] -= units
            sold[item] = sold.get(item, 0) + units
    return out, sold


def analyze(observation: Any, action: Any, configuration: Any = None) -> dict[str, Any]:
    """Return a machine-readable narrow EOD custody decision.

    `admit` is true only when exactly one shed-adjacent PASS actor can DROP all
    currently carried product at a full shed and strictly improve the current-
    price value of cargo retained by the engine's later EOD auto-drop.
    """
    result: dict[str, Any] = {"admit": False, "reason": "malformed"}
    if not isinstance(observation, dict) or not isinstance(action, dict):
        return result

    board_size = _strict_positive_int(configuration, "boardSize", DEFAULT_BOARD_SIZE)
    capacity = _strict_positive_int(configuration, "shedCapacity", DEFAULT_SHED_CAPACITY)
    turns = _strict_positive_int(configuration, "turnsPerDay", DEFAULT_TURNS_PER_DAY)
    max_orders = _strict_positive_int(
        configuration, "maxMarketOrdersPerTurn", DEFAULT_MAX_MARKET_ORDERS
    )
    if None in (board_size, capacity, turns, max_orders):
        result["reason"] = "configuration"
        return result

    step = observation.get("step")
    if type(step) is not int or step < 0 or (step + 1) % turns != 0:
        result["reason"] = "not_eod"
        return result

    player = observation.get("player")
    farms = observation.get("farms")
    private = observation.get("private")
    market = observation.get("market")
    if (
        type(player) is not int
        or not isinstance(farms, list)
        or player < 0
        or player >= len(farms)
        or not isinstance(farms[player], dict)
        or not isinstance(private, dict)
        or not isinstance(market, dict)
    ):
        return result

    farm = farms[player]
    hands = farm.get("hands")
    if not isinstance(hands, list):
        return result
    positions_raw = [farm.get("farmer"), *hands]
    positions: list[tuple[int, int]] = []
    for raw in positions_raw:
        pos = _strict_position(raw, board_size)
        if pos is None:
            result["reason"] = "position"
            return result
        positions.append(pos)

    farmer_row = action.get("farmer")
    hand_rows = action.get("hands")
    if not isinstance(farmer_row, list) or not isinstance(hand_rows, list):
        result["reason"] = "action"
        return result
    rows = [farmer_row, *hand_rows]
    if len(rows) != len(positions) or any(row != ["PASS"] for row in rows):
        result["reason"] = "unit_mutation"
        return result

    shed = _strict_nonnegative_mapping(private.get("shed"))
    inventories_raw = private.get("inventories")
    if shed is None or not isinstance(inventories_raw, list) or len(inventories_raw) != len(positions):
        result["reason"] = "inventory"
        return result
    inventories: list[dict[str, int]] = []
    for raw in inventories_raw:
        inv = _strict_product_inventory(raw)
        if inv is None:
            result["reason"] = "inventory"
            return result
        inventories.append(inv)
    if sum(shed.values()) != capacity:
        result["reason"] = "shed_not_full"
        return result

    prices_raw = market.get("prices")
    if not isinstance(prices_raw, dict):
        result["reason"] = "prices"
        return result
    carried_items = {item for inv in inventories for item, qty in inv.items() if qty > 0}
    prices: dict[str, float] = {}
    for item in carried_items:
        price = _strict_price(prices_raw.get(item))
        if price is None:
            result["reason"] = "prices"
            return result
        prices[item] = price

    market_projection = _postmarket_shed_after_sells(shed, action.get("market"), max_orders)
    if market_projection is None:
        result["reason"] = "market_not_sell_only"
        return result
    postmarket_shed, sold = market_projection
    sold_units = sum(sold.values())
    if sold_units <= 0:
        result["reason"] = "no_capacity_release"
        return result

    baseline = project_eod_drop(postmarket_shed, inventories, capacity)
    baseline_value = _deposit_value(baseline, prices)
    candidates: list[dict[str, Any]] = []
    access = _shed_access_tiles(board_size)
    for actor, inventory in enumerate(inventories):
        if positions[actor] not in access or sum(inventory.values()) <= 0:
            continue
        alternative_inventories = [dict(inv) for inv in inventories]
        alternative_inventories[actor] = {}
        alternative = project_eod_drop(postmarket_shed, alternative_inventories, capacity)
        value = _deposit_value(alternative, prices)
        gain = value - baseline_value
        if gain > 0:
            candidates.append(
                {
                    "actor": actor,
                    "gain": gain,
                    "baseline_value": baseline_value,
                    "candidate_value": value,
                    "baseline_deposited": baseline["deposited"],
                    "candidate_deposited": alternative["deposited"],
                    "discard_now": dict(inventory),
                    "market_sold": sold,
                }
            )

    if not candidates:
        result["reason"] = "no_strict_value_gain"
        return result
    best_gain = max(candidate["gain"] for candidate in candidates)
    best = [candidate for candidate in candidates if candidate["gain"] == best_gain]
    if len(best) != 1:
        result["reason"] = "ambiguous_best_actor"
        return result

    result.update(best[0])
    result["admit"] = True
    result["reason"] = "strict_current_price_retention_gain"
    return result


def transform(observation: Any, action: Any, configuration: Any = None, enabled: bool = False):
    """Apply the narrow EOD custody admission; no-op paths preserve identity."""
    if enabled is not True:
        telemetry["disabled"] += 1
        if enabled is not False:
            telemetry["invalid_enabled"] += 1
        return action
    decision = analyze(observation, action, configuration)
    if not decision.get("admit"):
        telemetry[f"reject_{decision.get('reason', 'unknown')}"] += 1
        return action

    actor = decision["actor"]
    out = copy.deepcopy(action)
    if actor == 0:
        out["farmer"] = ["DROP"]
    else:
        out["hands"][actor - 1] = ["DROP"]
    telemetry["changed_actions"] += 1
    telemetry["current_price_value_gain"] += decision["gain"]
    telemetry["discarded_before_market_units"] += sum(decision["discard_now"].values())
    return out


def install(parent, enabled: bool = False):
    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return transform(observation, action, configuration, enabled=enabled)

    agent.parent = parent
    agent.telemetry = telemetry
    agent.b7_custody_enabled = enabled is True
    return agent
