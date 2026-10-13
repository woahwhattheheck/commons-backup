#!/usr/bin/env python3
"""Executable adversarial-market probe for TITAN V4.

This is intentionally a research/stress component, not a production policy.
It models the official WHEAT market exactly for the relevant BUY/SELL path and
exports a legal market-only pressure agent for gauntlet use.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, Mapping

ENGINE_BLOB_SHA = "3c202c7ee921da239356789e266b694635103fc4"
ENGINE_JSON_BLOB_SHA = "b354d06b742fe48402513792253f1a5c29366b20"
MARKET_I0 = 10_000
PRICE_FLOOR = 1
SHED_CAPACITY = 100
TURNS_PER_DAY = 24
STARTING_MONEY = 3_000

WHEAT = {
    "base": 25,
    "I0": MARKET_I0,
    "T": 400,
    "below_func": "sqrt",
    "below_target": 0.80,
    "above_func": "log",
    "above_target": 0.20,
}


def _shape(func: str, x: float, T: float | None = None) -> float:
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "log10":
        return math.log10(1.0 + x)
    if func == "hinge":
        if not T or T <= 0:
            return x
        u = x / T
        return u + 8.0 * max(0.0, u - 1.0) ** 2
    return x


def wheat_price(inventory: int) -> int:
    """Exact official market_price() specialization for WHEAT."""
    p = WHEAT
    base = p["base"]
    I0 = p["I0"]
    T = p["T"]
    if inventory < I0:
        f = p["below_func"]
        amp = p["below_target"] * base / _shape(f, T, T)
        value = base + amp * _shape(f, I0 - inventory, T)
    else:
        f = p["above_func"]
        amp = p["above_target"] * base / _shape(f, T, T)
        value = base - amp * _shape(f, inventory - I0, T)
    return max(PRICE_FLOOR, int(round(value)))


@dataclass(frozen=True)
class TradeTrace:
    quantity: int
    money: int
    start_inventory: int
    end_inventory: int

    def json(self) -> Dict[str, int]:
        return asdict(self)


def buy_wheat(start_inventory: int, quantity: int, money: int | None = None, room: int | None = None) -> TradeTrace:
    """Official BUY_PRODUCT WHEAT semantics for one order.

    Quote uses post-buy inventory; commit stops on insufficient cash or shed room.
    """
    inventory = int(start_inventory)
    spend = 0
    bought = 0
    room_left = quantity if room is None else max(0, int(room))
    cash = None if money is None else max(0, int(money))
    for _ in range(max(0, int(quantity))):
        if bought >= room_left:
            break
        quote = wheat_price(inventory - 1)
        if cash is not None and spend + quote > cash:
            break
        spend += quote
        bought += 1
        inventory -= 1
    return TradeTrace(bought, spend, int(start_inventory), inventory)


def sell_wheat(start_inventory: int, quantity: int, stock: int | None = None) -> TradeTrace:
    """Official SELL WHEAT semantics for a positive-price scarcity path."""
    inventory = int(start_inventory)
    revenue = 0
    sold = 0
    available = quantity if stock is None else max(0, int(stock))
    for _ in range(min(max(0, int(quantity)), available)):
        quote = wheat_price(inventory)
        revenue += quote
        sold += 1
        if quote > PRICE_FLOOR:
            inventory += 1
    return TradeTrace(sold, revenue, int(start_inventory), inventory)


def max_affordable_wheat(money: int = STARTING_MONEY, room: int = SHED_CAPACITY, inventory: int = MARKET_I0) -> TradeTrace:
    return buy_wheat(inventory, room, money=money, room=room)


def self_roundtrip(quantity: int, start_inventory: int = MARKET_I0) -> Dict[str, int]:
    bought = buy_wheat(start_inventory, quantity)
    sold = sell_wheat(bought.end_inventory, bought.quantity, stock=bought.quantity)
    return {
        "quantity": bought.quantity,
        "cost": bought.money,
        "revenue": sold.money,
        "profit": sold.money - bought.money,
        "final_inventory": sold.end_inventory,
    }


def front_run_external_demand(our_quantity: int, rival_quantity: int, start_inventory: int = MARKET_I0) -> Dict[str, int]:
    """Buy first, let rival make net purchases, then unwind exactly our units."""
    ours = buy_wheat(start_inventory, our_quantity)
    rival = buy_wheat(ours.end_inventory, rival_quantity)
    unwind = sell_wheat(rival.end_inventory, ours.quantity, stock=ours.quantity)
    rival_baseline = buy_wheat(start_inventory, rival_quantity)
    our_profit = unwind.money - ours.money
    rival_surcharge = rival.money - rival_baseline.money
    return {
        "our_quantity": ours.quantity,
        "rival_quantity": rival.quantity,
        "our_cost": ours.money,
        "our_unwind_revenue": unwind.money,
        "our_profit": our_profit,
        "rival_cost_under_pressure": rival.money,
        "rival_baseline_cost": rival_baseline.money,
        "rival_surcharge": rival_surcharge,
        "margin_swing": our_profit + rival_surcharge,
        "final_inventory": unwind.end_inventory,
    }


def _adjacent_to_shed(pos: Iterable[int], board_size: int = 10) -> bool:
    p = tuple(pos)
    half = board_size // 2
    return p in {(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)}


def pressure_agent(obs: Mapping[str, Any]) -> Dict[str, Any]:
    """Portable WHEAT-price-pressure gauntlet adversary.

    It is deliberately market-only: acquire early, hold the public inventory down,
    unwind late. It never attempts illegal CARROT/TOMATO/EGG BUY_PRODUCT orders and
    never relies on hidden opponent state. The component is a stress opponent, not
    a claim that this dominates ordinary farming.
    """
    farms = obs.get("farms") or []
    player = int(obs.get("player", 0))
    private = obs.get("private") or {}
    market = obs.get("market") or {}
    hour = int(obs.get("hour", 0))
    if not farms or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}

    farm = farms[player]
    hands = [["PASS"] for _ in farm.get("hands", [])]
    farmer = ["PASS"]
    orders = []
    shed = private.get("shed") or {}
    inventories = private.get("inventories") or [{}]
    carried = (inventories[0] or {}).get("WHEAT", 0) if inventories else 0
    shed_wheat = int(shed.get("WHEAT", 0))
    shed_total = sum(int(v) for v in shed.values())
    money = int(float(farm.get("money", 0)))
    inv = int((market.get("inventory") or {}).get("WHEAT", MARKET_I0))
    pos = farm.get("farmer", [0, 0])
    adjacent = _adjacent_to_shed(pos)

    # Early window: keep bought WHEAT off-market. If we already have wheat in the
    # shed, PICKUP frees capacity before market processing in the official engine.
    if hour <= 11:
        pickup = shed_wheat if adjacent and shed_wheat > 0 else 0
        if pickup:
            farmer = ["PICKUP", "WHEAT", pickup]
        projected_shed_total = shed_total - pickup
        room = max(0, SHED_CAPACITY - projected_shed_total)
        # Preserve a tiny operating reserve; the order itself still fails closed
        # under the official per-unit cash check if observation is stale.
        affordable = max_affordable_wheat(max(0, money - 5), room, inv)
        if affordable.quantity > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", affordable.quantity])

    # Late window: PLACE carried wheat before market, then sell all WHEAT that can
    # be in the shed on this action. This avoids EOD overflow/discard dependence.
    elif hour >= 18:
        room = max(0, SHED_CAPACITY - shed_total)
        deposit = min(int(carried), room) if adjacent else 0
        if deposit > 0:
            farmer = ["PLACE", "WHEAT", deposit]
        sellable = shed_wheat + deposit
        if sellable > 0:
            orders.append(["SELL", "WHEAT", sellable])

    return {"farmer": farmer, "hands": hands, "market": orders}


agent = pressure_agent


def result_bundle() -> Dict[str, Any]:
    start = max_affordable_wheat()
    fr64 = front_run_external_demand(64, 64)
    fr95 = front_run_external_demand(start.quantity, start.quantity)
    return {
        "engine_blob_sha": ENGINE_BLOB_SHA,
        "engine_json_blob_sha": ENGINE_JSON_BLOB_SHA,
        "legal_direct_buy_products": ["WHEAT", "FERTILIZER"],
        "starting_cash_wheat": start.json(),
        "self_roundtrip_q95": self_roundtrip(start.quantity),
        "front_run_q64_r64": fr64,
        "front_run_starting_cash_symmetry": fr95,
        "interpretation": {
            "hinge_direct_buy": "rejected: CARROT/TOMATO/EGG are not legal BUY_PRODUCT targets",
            "self_squeeze": "rejected: own buy->sell round-trip is exactly reversible absent external flow",
            "wheat_starvation": "price pressure only: market inventory has no nonnegative availability gate",
            "surviving_lane": "stress external WHEAT demand; profit/surcharge can arise when rival net buys between our buy and unwind",
        },
    }
