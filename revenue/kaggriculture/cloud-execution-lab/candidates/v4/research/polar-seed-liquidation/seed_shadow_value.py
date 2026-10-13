# SPDX-License-Identifier: Apache-2.0
"""Research-only prospective seed economics for TITAN V4.

This is NOT an agent transform, a yield forecast, or a promotion gate. It values
specified realized output in an isolated standard-market liquidation scenario.
No opponent order, town tick, future shop draw, labor/cargo constraint, or route
change is predicted. Use paired full episodes before changing any seed/plant row.

Official source: reference/engine/kaggriculture.py, Git blob below. Its SELL
quotes each unit before commit and increments public stock ONLY above $1.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from typing import Optional

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
BASE_COMMIT = "465f4263da1c98acf78889d67cdd21b61dbba145"
# (seed cost, base quote, T, scarcity curve, scarcity target,
#  glut curve, glut target), copied from the pinned official CROPS/MARKET_PARAMS.
_PARAMS = {
    "WHEAT": (10, 25, 400, "sqrt", .80, "log", .20),
    "CARROT": (20, 35, 450, "hinge", 1., "sqrt", .70),
    "TOMATO": (50, 60, 200, "hinge", .40, "sqrt", .60),
    "STRAWBERRY": (100, 120, 100, "sqrt", .70, "linear", 1.60),
    "MELON": (80, 250, 300, "log", .20, "sq", 3.60),
}
# Bounded research input domain; 99,999 units also matches the engine's
# per-order loop's last executable iteration. Not a cargo-availability proof.
_MAX_UNITS = 99_999
_MAX_STOCK = 1_000_000_000


def _integer(value: object, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be a plain int in [{low}, {high}]")
    return value


def _crop(crop: object) -> str:
    if type(crop) is not str or crop not in _PARAMS:
        raise ValueError("crop must be one of " + ", ".join(_PARAMS))
    return crop


def _shape(curve: str, x: float, T: int) -> float:
    x = max(0.0, x)
    if curve == "linear":
        return x
    if curve == "sq":
        return x * x
    if curve == "sqrt":
        return math.sqrt(x)
    if curve == "log":
        return math.log(1.0 + x)
    if curve == "hinge":
        u = x / T
        return u + 8.0 * max(0.0, u - 1.0) ** 2
    raise ValueError("unsupported standard curve")


def quote(crop: str, inventory: int) -> int:
    """Standard-engine rounded quote; negative public stock is legal."""
    _crop(crop)
    _integer(inventory, "inventory", -_MAX_STOCK, _MAX_STOCK)
    _, base, T, below, below_target, above, above_target = _PARAMS[crop]
    if inventory < 10_000:
        amp = below_target * base / _shape(below, T, T)
        price = base + amp * _shape(below, 10_000 - inventory, T)
    else:
        amp = above_target * base / _shape(above, T, T)
        price = base - amp * _shape(above, inventory - 10_000, T)
    return max(1, int(round(price)))


@dataclass(frozen=True)
class Liquidation:
    units: int
    cash: int
    inventory_after: int
    floor_units: int


def liquidate(crop: str, inventory: int, units: int) -> Liquidation:
    """Exact isolated SELL cash, assuming all units are available in shed.

    No opposite-seat orders or other market rows occur during this liquidation.
    This function does not claim these units fit in a live standard shed.
    """
    _crop(crop)
    _integer(units, "units", 0, _MAX_UNITS)
    _integer(inventory, "inventory", -_MAX_STOCK, _MAX_STOCK - units)
    cash = 0
    for i in range(units):
        price = quote(crop, inventory)
        if price == 1:
            # $1 SELL does not add public inventory, so every remaining unit
            # has this same quote. The engine still pays $1 for each unit.
            remainder = units - i
            return Liquidation(units, cash + remainder, inventory, remainder)
        cash += price
        inventory += 1
    return Liquidation(units, cash, inventory, 0)


@dataclass(frozen=True)
class SeedValue:
    crop: str
    inventory: int
    committed_units: int
    extra_yield_units: int
    seed_already_owned: bool
    seed_cash_cost: int
    extra_cash_cost: int
    current_quote: int
    quote_times_extra_yield: int
    baseline_cash: int
    combined_cash: int
    marginal_cash: int
    net_incremental_cash: int
    combined_inventory_after: int
    extra_floor_units: int


def seed_value(crop: str, inventory: int, extra_yield_units: int, *,
               committed_units: int = 0, seed_already_owned: bool = False,
               extra_cash_cost: int = 0) -> SeedValue:
    """Value one prospective/owned seed's specified output AFTER committed stock.

    Already-owned seed has zero avoidable purchase cost; subtracting its original
    price would turn sunk spending into a false argument for skipping PLANT.
    extra_cash_cost is additional avoidable cash (e.g. future fertilizer), NOT
    already-spent cash. Unpriced labor, land and route opportunity costs remain
    outside this scenario, as do retained WHEAT feed utility and future prices.
    """
    _crop(crop)
    _integer(extra_yield_units, "extra_yield_units", 0, _MAX_UNITS)
    _integer(committed_units, "committed_units", 0, _MAX_UNITS)
    _integer(committed_units + extra_yield_units, "total_units", 0, _MAX_UNITS)
    _integer(inventory, "inventory", -_MAX_STOCK,
             _MAX_STOCK - committed_units - extra_yield_units)
    _integer(extra_cash_cost, "extra_cash_cost", 0, _MAX_STOCK)
    if type(seed_already_owned) is not bool:
        raise ValueError("seed_already_owned must be a literal bool")
    baseline = liquidate(crop, inventory, committed_units)
    extra = liquidate(crop, baseline.inventory_after, extra_yield_units)
    seed_cost = 0 if seed_already_owned else _PARAMS[crop][0]
    current_quote = quote(crop, inventory)
    return SeedValue(
        crop, inventory, committed_units, extra_yield_units, seed_already_owned,
        seed_cost, extra_cash_cost, current_quote,
        current_quote * extra_yield_units, baseline.cash,
        baseline.cash + extra.cash, extra.cash,
        extra.cash - seed_cost - extra_cash_cost,
        extra.inventory_after, extra.floor_units,
    )


def first_nonpositive_inventory(crop: str, extra_yield_units: int, *,
                                low: int, high: int, committed_units: int = 0,
                                seed_already_owned: bool = False,
                                extra_cash_cost: int = 0) -> Optional[int]:
    """First integer stock in [low, high] with scenario net cash <= 0.

    For fixed units/costs, the isolated standard sale curve is nonincreasing in
    starting inventory, including its $1 plateau. None means the whole supplied
    interval remains positive, not that planting is universally profitable.
    """
    _integer(low, "low", -_MAX_STOCK, _MAX_STOCK - _MAX_UNITS)
    _integer(high, "high", low, _MAX_STOCK - _MAX_UNITS)

    def net(stock: int) -> int:
        return seed_value(crop, stock, extra_yield_units,
                          committed_units=committed_units,
                          seed_already_owned=seed_already_owned,
                          extra_cash_cost=extra_cash_cost).net_incremental_cash

    if net(high) > 0:
        return None
    if net(low) <= 0:
        return low
    while low + 1 < high:
        middle = (low + high) // 2
        if net(middle) <= 0:
            high = middle
        else:
            low = middle
    return high


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crop", choices=tuple(_PARAMS), required=True)
    parser.add_argument("--inventory", type=int, required=True)
    parser.add_argument("--yield-units", type=int, required=True)
    parser.add_argument("--committed-units", type=int, default=0)
    parser.add_argument("--seed-already-owned", action="store_true")
    parser.add_argument("--extra-cash-cost", type=int, default=0)
    parser.add_argument("--inventory-deltas", type=int, nargs="+", default=[0])
    args = parser.parse_args()
    try:
        scenarios = [asdict(seed_value(
            args.crop, args.inventory + d, args.yield_units,
            committed_units=args.committed_units,
            seed_already_owned=args.seed_already_owned,
            extra_cash_cost=args.extra_cash_cost,
        )) for d in args.inventory_deltas]
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({
        "schema": "titan.v4.seed-shadow.v1", "engine_blob": ENGINE_BLOB,
        "base_commit": BASE_COMMIT,
        "scope": "isolated-liquidation-scenarios-not-policy-or-forecast",
        "policy_authorized": False, "scenarios": scenarios,
    }, sort_keys=True, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
