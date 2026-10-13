#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound all-product town-drain SELL timing oracle for TITAN V4.

This module does not choose gameplay actions. It measures the deterministic
revenue difference between selling an already-intended quantity in MARKET
immediately before a known town drain and deferring that identical sale until
the next MARKET callback after the drain. The comparison assumes no intervening
rival market flow; custody, cash timing, row budget, and downstream obligations
remain external policy constraints.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine_bound_baseline import ENGINE_BLOB, load_engine
from town_wheat_timing import sell_ledger, town_demand_units


def _nonnegative_int(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _positive_int(value, name: str) -> int:
    value = _nonnegative_int(value, name)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def sale_deferral_window(engine, inventory: int, quantity: int, demand_units: int, item: str):
    """Compare identical SELL quantity before vs after deterministic town drain."""
    if item not in engine.PRODUCTS:
        raise ValueError(f"unknown product: {item}")
    if isinstance(inventory, bool) or not isinstance(inventory, int):
        raise ValueError("inventory must be an integer")
    quantity = _positive_int(quantity, "quantity")
    demand_units = _nonnegative_int(demand_units, "demand_units")

    before = sell_ledger(engine, inventory, quantity, item)
    after = sell_ledger(engine, inventory - demand_units, quantity, item)
    premium = after["revenue"] - before["revenue"]
    return {
        "item": item,
        "inventory": inventory,
        "quantity": quantity,
        "town_demand_units": demand_units,
        "sell_before_revenue": before["revenue"],
        "sell_after_revenue": after["revenue"],
        "post_drain_premium": premium,
        "post_drain_is_never_worse": premium >= 0,
        "before_end_inventory": before["end_inventory"],
        "after_end_inventory": after["end_inventory"],
    }


def opportunity(engine, observation: dict, *, item: str, quantity: int, config=None):
    """Public-state mechanism oracle; never authorizes or mutates an action."""
    if not isinstance(observation, dict):
        raise ValueError("observation must be an object")
    if item not in engine.PRODUCTS:
        raise ValueError(f"unknown product: {item}")
    market = observation.get("market") or {}
    town = observation.get("town") or {}
    inventory = (market.get("inventory") or {}).get(item)
    if isinstance(inventory, bool) or not isinstance(inventory, int):
        raise ValueError(f"integer public {item} inventory required")

    demand = town_demand_units(
        engine,
        observation.get("step"),
        town.get("unlocked_shops", []),
        config,
        item,
    )
    window = sale_deferral_window(engine, inventory, quantity, demand, item)
    if demand <= 0:
        status = "NO_TOWN_DEMAND_THIS_STEP"
    elif window["post_drain_premium"] > 0:
        status = "DETERMINISTIC_POST_DRAIN_PREMIUM"
    else:
        status = "TOWN_DRAIN_PRICE_FLAT"
    return {
        "status": status,
        "step": observation.get("step"),
        "unlocked_shops": list(town.get("unlocked_shops", [])),
        **window,
        "limits": [
            "mechanism theorem only; does not authorize delaying a live sale",
            "comparison preserves item and quantity and defers by one market callback",
            "assumes zero intervening rival market flow between the two callbacks",
            "cash timing, custody, feed/seed obligations, order-row budget and terminal horizon are external admission constraints",
        ],
    }


def sensitivity_table(engine, *, inventory: int = 10_000, quantity: int = 100, demand_units: int = 5):
    """Return same-cell post-drain premium for every town-center-consumed product."""
    _positive_int(quantity, "quantity")
    _nonnegative_int(demand_units, "demand_units")
    return [
        sale_deferral_window(engine, inventory, quantity, demand_units, item)
        for item in engine.TOWN_CENTER_PRODUCTS
    ]


def audit_grid(
    engine,
    *,
    inventories=(8000, 9000, 10000, 10500, 11000, 12000),
    quantities=(1, 5, 20, 50, 100),
    demands=range(0, 10),
):
    """Falsify the nonnegative deterministic premium over a broad source curve grid."""
    rows = []
    for item in engine.TOWN_CENTER_PRODUCTS:
        for inventory in inventories:
            for demand in demands:
                for quantity in quantities:
                    row = sale_deferral_window(engine, inventory, quantity, demand, item)
                    if row["post_drain_premium"] < 0:
                        raise AssertionError(
                            f"negative post-drain premium item={item} inv={inventory} "
                            f"demand={demand} qty={quantity}"
                        )
                    if demand == 0 and row["post_drain_premium"] != 0:
                        raise AssertionError(
                            f"zero-demand identity failed item={item} inv={inventory} qty={quantity}"
                        )
                    rows.append(row)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine", required=True)
    ap.add_argument("--item", default="MILK")
    ap.add_argument("--inventory", type=int, default=10000)
    ap.add_argument("--quantity", type=int, default=100)
    ap.add_argument("--step", type=int, default=100)
    ap.add_argument(
        "--shops",
        default="PIZZA_SHOP,PIZZA_SHOP,ICE_CREAM_SHOP,SMOOTHIE_SHOP,SMOOTHIE_SHOP",
    )
    args = ap.parse_args(argv)
    engine = load_engine(args.engine)
    shops = [x for x in args.shops.split(",") if x]
    demand = town_demand_units(engine, args.step, shops, item=args.item)
    result = {
        "schema": "titan.v4.market-baseline.town-sale-deferral.v1",
        "engine_git_blob": ENGINE_BLOB,
        "engine_sha256": __import__("hashlib").sha256(Path(args.engine).read_bytes()).hexdigest(),
        "step": args.step,
        "shops": shops,
        "witness": sale_deferral_window(
            engine, args.inventory, args.quantity, demand, args.item
        ),
        "sensitivity_at_same_cell": sensitivity_table(
            engine,
            inventory=args.inventory,
            quantity=args.quantity,
            demand_units=demand,
        ),
        "grid_cells_checked": len(audit_grid(engine)),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
