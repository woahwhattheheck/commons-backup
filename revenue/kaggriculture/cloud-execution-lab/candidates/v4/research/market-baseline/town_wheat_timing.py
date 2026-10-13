#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound WHEAT town-event timing oracle for TITAN V4 research.

This module does not choose gameplay actions.  It measures the deterministic
price advantage created when an already-needed WHEAT purchase is executed in
the MARKET phase immediately before the same callback's TOWN phase, instead of
after that town demand has lowered public inventory.  Optional round-trip
figures are a mechanism oracle only and assume zero rival WHEAT flow.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from engine_bound_baseline import ENGINE_BLOB, load_engine

ITEM = "WHEAT"
DEFAULTS = {
    "townShopSellInterval": 4,
    "townCenterSellInterval": 24,
    "shedCapacity": 100,
}


def _positive_int(value, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    value = int(value)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def town_demand_units(engine, step: int, unlocked_shops, config=None, item: str = ITEM) -> int:
    """Exact public town drain scheduled after MARKET on this callback."""
    if isinstance(step, bool) or not isinstance(step, int) or step < 0:
        raise ValueError("step must be a nonnegative integer")
    if item not in engine.PRODUCTS:
        raise ValueError(f"unknown product: {item}")
    cfg = dict(DEFAULTS)
    if isinstance(config, dict):
        for key in ("townShopSellInterval", "townCenterSellInterval"):
            if key in config:
                cfg[key] = config[key]
    shop_interval = _positive_int(cfg["townShopSellInterval"], "townShopSellInterval")
    center_interval = _positive_int(cfg["townCenterSellInterval"], "townCenterSellInterval")
    shops = list(unlocked_shops or [])
    if len(shops) > int(engine.MAX_SHOP_INSTANCES):
        raise ValueError(f"shop count exceeds official cap: {len(shops)} > {engine.MAX_SHOP_INSTANCES}")
    unknown = [name for name in shops if name not in engine.SHOPS]
    if unknown:
        raise ValueError(f"unknown shops: {unknown}")
    demand = 0
    if step % shop_interval == 0:
        for name in shops:
            products = engine.SHOPS[name]
            if item in products:
                demand += 2 if len(products) == 1 else 1
    if step % center_interval == 0 and item in engine.TOWN_CENTER_PRODUCTS:
        demand += 1
    return demand


def buy_ledger(engine, inventory: int, quantity: int, item: str = ITEM):
    """Exact BUY_PRODUCT quote ledger under zero rival flow."""
    quantity = _positive_int(quantity, "quantity")
    if item not in ("WHEAT", "FERTILIZER"):
        raise ValueError("official BUY_PRODUCT only admits WHEAT/FERTILIZER")
    inv = int(inventory)
    prices = []
    for _ in range(quantity):
        quote = int(engine.market_price(item, inv - 1))
        prices.append(quote)
        inv -= 1
    return {"cost": sum(prices), "prices": prices, "end_inventory": inv}


def sell_ledger(engine, inventory: int, quantity: int, item: str = ITEM):
    """Exact SELL quote ledger, including the $1 no-public-supply rule."""
    quantity = _positive_int(quantity, "quantity")
    if item not in engine.PRODUCTS:
        raise ValueError(f"unknown product: {item}")
    inv = int(inventory)
    prices = []
    for _ in range(quantity):
        quote = int(engine.market_price(item, inv))
        prices.append(quote)
        if quote > 1:
            inv += 1
    return {"revenue": sum(prices), "prices": prices, "end_inventory": inv}


def procurement_window(engine, inventory: int, quantity: int, demand_units: int, item: str = ITEM):
    """Compare buying an identical required quantity before vs after town demand."""
    quantity = _positive_int(quantity, "quantity")
    if isinstance(demand_units, bool) or not isinstance(demand_units, int) or demand_units < 0:
        raise ValueError("demand_units must be a nonnegative integer")
    before = buy_ledger(engine, inventory, quantity, item)
    after = buy_ledger(engine, int(inventory) - demand_units, quantity, item)
    savings = after["cost"] - before["cost"]
    return {
        "item": item,
        "inventory": int(inventory),
        "quantity": quantity,
        "town_demand_units": demand_units,
        "buy_before_cost": before["cost"],
        "buy_after_cost": after["cost"],
        "buy_before_savings": savings,
        "buy_before_is_never_worse": savings >= 0,
    }


def round_trip_window(engine, inventory: int, quantity: int, demand_units: int, item: str = ITEM):
    """Mechanism-only buy-before / sell-after ledger under zero rival flow."""
    quantity = _positive_int(quantity, "quantity")
    if isinstance(demand_units, bool) or not isinstance(demand_units, int) or demand_units < 0:
        raise ValueError("demand_units must be a nonnegative integer")
    buy = buy_ledger(engine, inventory, quantity, item)
    sell = sell_ledger(engine, buy["end_inventory"] - demand_units, quantity, item)
    return {
        "item": item,
        "inventory": int(inventory),
        "quantity": quantity,
        "town_demand_units": demand_units,
        "buy_cost": buy["cost"],
        "sell_revenue": sell["revenue"],
        "profit": sell["revenue"] - buy["cost"],
        "final_public_inventory": sell["end_inventory"],
        "zero_rival_wheat_flow_assumption": True,
    }


def opportunity(engine, observation: dict, *, quantity: int, config=None):
    """Public-state timing oracle; does not authorize or mutate an action."""
    if not isinstance(observation, dict):
        raise ValueError("observation must be an object")
    step = observation.get("step")
    market = observation.get("market") or {}
    town = observation.get("town") or {}
    inventory = (market.get("inventory") or {}).get(ITEM)
    if isinstance(inventory, bool) or not isinstance(inventory, (int, float)) or not math.isfinite(inventory):
        raise ValueError("finite public WHEAT inventory required")
    demand = town_demand_units(engine, step, town.get("unlocked_shops", []), config, ITEM)
    window = procurement_window(engine, int(inventory), quantity, demand, ITEM)
    return {
        "status": "DEMAND_WINDOW" if demand > 0 else "NO_TOWN_WHEAT_DEMAND_THIS_STEP",
        "step": step,
        "unlocked_shops": list(town.get("unlocked_shops", [])),
        **window,
        "limits": [
            "research oracle only; does not prove speculative live EV",
            "rival WHEAT flow is not forecast here",
            "cash, shed room, feed obligations, market-row ownership and later resale are external admission constraints",
        ],
    }


def audit_grid(engine, *, inventories=(8000, 9000, 10000, 10500, 11000, 12000), quantities=(1, 5, 20, 50, 100), demands=range(0, 10)):
    rows = []
    for inv in inventories:
        for demand in demands:
            for qty in quantities:
                p = procurement_window(engine, inv, qty, demand)
                r = round_trip_window(engine, inv, qty, demand)
                if p["buy_before_savings"] < 0 or r["profit"] < 0:
                    raise AssertionError(f"negative deterministic window inv={inv} demand={demand} qty={qty}")
                rows.append({"inventory": inv, "demand": demand, "quantity": qty,
                             "procurement_savings": p["buy_before_savings"], "round_trip_profit": r["profit"]})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine", required=True)
    ap.add_argument("--inventory", type=int, default=10000)
    ap.add_argument("--quantity", type=int, default=100)
    ap.add_argument("--step", type=int, default=100)
    ap.add_argument("--shops", default="BAKERY,PIZZA_SHOP,BRUNCH_SPOT,ICE_CREAM_SHOP,FARMERS_MARKET")
    args = ap.parse_args(argv)
    engine = load_engine(args.engine)
    demand = town_demand_units(engine, args.step, [x for x in args.shops.split(",") if x])
    result = {
        "schema": "titan.v4.market-baseline.town-wheat-timing.v1",
        "engine_git_blob": ENGINE_BLOB,
        "engine_sha256": __import__("hashlib").sha256(Path(args.engine).read_bytes()).hexdigest(),
        "step": args.step,
        "shops": [x for x in args.shops.split(",") if x],
        "demand_units": demand,
        "procurement": procurement_window(engine, args.inventory, args.quantity, demand),
        "round_trip_mechanism_only": round_trip_window(engine, args.inventory, args.quantity, demand),
        "grid_cells_checked": len(audit_grid(engine)),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
