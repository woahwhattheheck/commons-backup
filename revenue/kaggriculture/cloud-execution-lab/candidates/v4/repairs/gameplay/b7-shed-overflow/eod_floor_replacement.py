#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Default-OFF B7 $1 EOD same-product replacement guard.

This helper covers a strict-dominance corner of the official market/EOD order.
When an EOD callback would discard only one non-buyable carried product X, an
appended floor-price SELL of X can replace shed X with the otherwise-discarded
carried X. At the official $1 floor that sale credits cash without adding public
supply.

The transform intentionally requires observed theorem-critical configuration and
an authenticated ``market_price_fn`` ABI. Missing configuration never falls back
to guessed defaults. This is research/default-OFF evidence and has no runtime
wiring or activation authority.
"""
from __future__ import annotations

import copy
import math
from collections import Counter
from typing import Any, Callable

DEFAULT_TURNS_PER_DAY = 24
DEFAULT_SHED_CAPACITY = 100
DEFAULT_MAX_MARKET_ORDERS = 10
# Official _process_market increments idx_esc before checking >= 100_000,
# therefore a single row can commit at most 99,999 units.
MAX_MARKET_UNITS_PER_ROW = 99_999
PRODUCTS = frozenset((
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
))
ANIMALS = frozenset(("GOOSE", "COW", "SHEEP"))
CARRYABLE = PRODUCTS | ANIMALS
BUYABLE_PRODUCTS = frozenset(("WHEAT", "FERTILIZER"))
NONBUYABLE_PRODUCTS = PRODUCTS - BUYABLE_PRODUCTS
telemetry = Counter()
_MISSING = object()


def _required_cfg(configuration: Any, name: str) -> Any:
    """Return an observed configuration field; never synthesize a default."""
    if configuration is None:
        return _MISSING
    try:
        if isinstance(configuration, dict):
            return configuration[name] if name in configuration else _MISSING
        return getattr(configuration, name)
    except Exception:
        return _MISSING


def _positive_int_cfg(configuration: Any, name: str) -> int | None:
    value = _required_cfg(configuration, name)
    return value if type(value) is int and value > 0 else None


def _market_cap(configuration: Any) -> int | None:
    raw = _required_cfg(configuration, "maxMarketOrdersPerTurn")
    if type(raw) is not int:
        return None
    return max(1, raw)


def _strict_money(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def _strict_inventory(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    out: dict[str, int] = {}
    for item, qty in value.items():
        if not isinstance(item, str) or item not in CARRYABLE or type(qty) is not int or qty < 0:
            return None
        out[item] = qty
    return out


def _strict_shed(value: Any) -> dict[str, int] | None:
    return _strict_inventory(value)


def _sell_prefix(shed: dict[str, int], rows: Any, cap: int) -> tuple[dict[str, int], dict[str, int]] | None:
    """Project our private shed through an exact SELL-only prefix, possibly empty."""
    if not isinstance(rows, list) or len(rows) >= cap:
        return None
    out = dict(shed)
    sold: dict[str, int] = {}
    for row in rows:
        if (
            not isinstance(row, list)
            or len(row) != 3
            or row[0] != "SELL"
            or row[1] not in PRODUCTS
            or type(row[2]) is not int
            or row[2] <= 0
            or row[2] > MAX_MARKET_UNITS_PER_ROW
        ):
            return None
        item, requested = row[1], row[2]
        units = min(requested, out.get(item, 0))
        if units:
            out[item] -= units
            sold[item] = sold.get(item, 0) + units
    return out, sold


def project_eod_drop(
    shed: dict[str, int], inventories: list[dict[str, int]], capacity: int
) -> dict[str, Any]:
    """Mirror official actor/insertion-order EOD drop without mutating inputs."""
    if type(capacity) is not int or capacity <= 0:
        raise ValueError("capacity must be a positive int")
    out_shed = _strict_shed(shed)
    if out_shed is None or sum(out_shed.values()) > capacity:
        raise ValueError("malformed or over-capacity shed")
    out_shed = dict(out_shed)
    deposited: list[dict[str, int]] = []
    discarded: list[dict[str, int]] = []
    for raw in inventories:
        inventory = _strict_inventory(raw)
        if inventory is None:
            raise ValueError("malformed inventory")
        actor_deposit: dict[str, int] = {}
        actor_discard: dict[str, int] = {}
        for item, qty in inventory.items():
            if qty <= 0:
                continue
            room = max(0, capacity - sum(out_shed.values()))
            take = min(qty, room)
            if take:
                out_shed[item] = out_shed.get(item, 0) + take
                actor_deposit[item] = take
            if qty > take:
                actor_discard[item] = qty - take
        deposited.append(actor_deposit)
        discarded.append(actor_discard)
    return {"shed": out_shed, "deposited": deposited, "discarded": discarded}


def _validated_prices(market: dict[str, Any], market_price_fn: Callable[..., Any]) -> dict[str, int] | None:
    """Authenticate the complete observed price map before adding a refresh row."""
    public_inventory = market.get("inventory")
    observed_prices = market.get("prices")
    if not isinstance(public_inventory, dict) or not isinstance(observed_prices, dict):
        return None
    params = market.get("params")
    resolved: dict[str, int] = {}
    for item in PRODUCTS:
        stock = public_inventory.get(item)
        observed = observed_prices.get(item)
        if type(stock) is not int or type(observed) is not int:
            return None
        try:
            quote = market_price_fn(item, stock, params)
        except Exception:
            return None
        if type(quote) is not int or quote != observed:
            return None
        resolved[item] = quote
    return resolved


def analyze(
    observation: Any,
    action: Any,
    configuration: Any = None,
    *,
    market_price_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Return a machine-readable certificate for one appended SELL row."""
    result: dict[str, Any] = {"admit": False, "reason": "malformed"}
    if not isinstance(observation, dict) or not isinstance(action, dict):
        return result
    if not callable(market_price_fn):
        result["reason"] = "missing_market_price_abi"
        return result

    turns = _positive_int_cfg(configuration, "turnsPerDay")
    capacity = _positive_int_cfg(configuration, "shedCapacity")
    cap = _market_cap(configuration)
    step = observation.get("step")
    if turns is None or capacity is None or cap is None or type(step) is not int or step < 0:
        result["reason"] = "clock_or_configuration"
        return result
    if (step + 1) % turns != 0:
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
        result["reason"] = "state_shape"
        return result

    farm = farms[player]
    hands = farm.get("hands")
    if not isinstance(hands, list) or not _strict_money(farm.get("money")):
        result["reason"] = "farm_state"
        return result

    farmer_row = action.get("farmer")
    hand_rows = action.get("hands")
    if not isinstance(farmer_row, list) or not isinstance(hand_rows, list):
        result["reason"] = "action_shape"
        return result
    unit_rows = [farmer_row, *hand_rows]
    if len(hand_rows) != len(hands) or any(row != ["PASS"] for row in unit_rows):
        result["reason"] = "unit_mutation"
        return result

    shed = _strict_shed(private.get("shed"))
    raw_inventories = private.get("inventories")
    if shed is None or sum(shed.values()) > capacity or not isinstance(raw_inventories, list):
        result["reason"] = "private_state"
        return result
    if len(raw_inventories) != len(unit_rows):
        result["reason"] = "inventory_actor_mismatch"
        return result
    inventories: list[dict[str, int]] = []
    for raw in raw_inventories:
        checked = _strict_inventory(raw)
        if checked is None:
            result["reason"] = "private_state"
            return result
        inventories.append(checked)

    projected_prefix = _sell_prefix(shed, action.get("market"), cap)
    if projected_prefix is None:
        result["reason"] = "market_prefix_or_slot"
        return result
    post_prefix_shed, prefix_sold = projected_prefix

    try:
        baseline = project_eod_drop(post_prefix_shed, inventories, capacity)
    except ValueError:
        result["reason"] = "eod_projection"
        return result

    discarded: dict[str, int] = {}
    for actor in baseline["discarded"]:
        for item, qty in actor.items():
            if qty > 0:
                discarded[item] = discarded.get(item, 0) + qty
    if not discarded:
        result["reason"] = "no_eod_discard"
        return result
    if len(discarded) != 1:
        result["reason"] = "mixed_discard"
        return result
    item, units = next(iter(discarded.items()))
    if units > MAX_MARKET_UNITS_PER_ROW:
        result["reason"] = "market_unit_loop_guard"
        return result
    if item not in NONBUYABLE_PRODUCTS:
        result["reason"] = "buyable_discard_product"
        return result
    if post_prefix_shed.get(item, 0) < units:
        result["reason"] = "insufficient_same_product_shed_stock"
        return result

    prices = _validated_prices(market, market_price_fn)
    if prices is None:
        result["reason"] = "market_price_map_drift"
        return result
    quote = prices[item]
    if quote != 1:
        result["reason"] = "not_exact_floor_quote"
        return result
    public_stock = market["inventory"][item]

    candidate_shed = dict(post_prefix_shed)
    candidate_shed[item] -= units
    try:
        candidate_eod = project_eod_drop(candidate_shed, inventories, capacity)
    except ValueError:
        result["reason"] = "candidate_projection"
        return result
    if candidate_eod["shed"] != baseline["shed"]:
        result["reason"] = "same_product_replacement_not_exact"
        return result
    if any(candidate_eod["discarded"]):
        result["reason"] = "candidate_still_discards"
        return result

    result.update({
        "admit": True,
        "reason": "exact_floor_same_product_replacement",
        "proposal": ["SELL", item, units],
        "item": item,
        "units": units,
        "cash_gain": units,
        "prefix_sold": prefix_sold,
        "baseline_discarded": baseline["discarded"],
        "baseline_final_shed": baseline["shed"],
        "candidate_final_shed": candidate_eod["shed"],
        "public_stock": public_stock,
        "quote": quote,
        "full_callback_promotion": False,
    })
    return result


def transform(
    observation: Any,
    action: Any,
    configuration: Any = None,
    enabled: bool = False,
    *,
    market_price_fn: Callable[..., Any] | None = None,
):
    """Append the certified floor SELL; all rejected paths preserve identity."""
    if enabled is not True:
        telemetry["disabled" if enabled is False else "invalid_enabled"] += 1
        return action
    decision = analyze(
        observation, action, configuration, market_price_fn=market_price_fn
    )
    if not decision.get("admit"):
        telemetry[f"reject_{decision.get('reason', 'unknown')}"] += 1
        return action
    out = copy.deepcopy(action)
    out["market"].append(list(decision["proposal"]))
    telemetry["changed_actions"] += 1
    telemetry["cash_gain_units"] += decision["cash_gain"]
    telemetry["replacement_units"] += decision["units"]
    return out


def install(parent, *, market_price_fn=None, enabled: bool = False):
    """Wrap a parent policy; literal True is the only enabling token."""
    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return transform(
            observation,
            action,
            configuration,
            enabled=enabled,
            market_price_fn=market_price_fn,
        )
    agent.parent = parent
    agent.telemetry = telemetry
    agent.b7_eod_floor_replacement_enabled = enabled is True and callable(market_price_fn)
    return agent
