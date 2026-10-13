# SPDX-License-Identifier: Apache-2.0
"""Bounded marginal-demand forecast for producer-owned reinvestment choices.

This module is an evaluator only. It never calls a producer, mutates a route,
executes an environment, or reads opponent-private state. The current producer
supplies authored output timing and fully attributed incremental costs; the
existing funded-payback layer remains the authority for route funding/physical
feasibility. The seller may supply its existing public supply stress directly.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ProductionCandidate:
    """One producer-owned reinvestment alternative.

    ``outputs`` are (sale_step, units) tuples for one market product. ``costs``
    must include every incremental paid obligation the caller attributes to the
    alternative: land/prep, seed or animal, worker service, travel/operating
    inputs, harvest/deposit handling, and any other paid route commitment.
    """
    key: str
    item: str
    outputs: tuple[tuple[int, int], ...]
    costs: Mapping[str, float]
    funded: bool = True
    ready_step: int | None = None
    idle_assets: int = 0
    rival_supply_units: int | None = None


def _integer(value: Any, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _money(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} cannot be a boolean")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return result


def public_rival_standing_units(mechanics: Any, observation: Mapping[str, Any], item: str) -> int:
    """Visible standing yield only; never rival shed, carried stock, or seeds."""
    player = _integer(observation["player"], "player", minimum=0)
    farms = observation["farms"]
    if len(farms) != 2 or player not in (0, 1):
        raise ValueError("forecast requires the official two-player public farm surface")
    total = 0
    for row in farms[1 - player]["tiles"]:
        for tile in row:
            if not isinstance(tile, Mapping):
                continue
            product = tile.get("crop")
            animal = tile.get("animal")
            if animal is not None:
                data = mechanics.ANIMALS.get(animal)
                product = None if data is None else data.get("product")
            if product == item:
                total += max(0, _integer(tile.get("yield_units", 0), "yield_units"))
    return total


def known_town_absorption(mechanics: Any, observation: Mapping[str, Any],
                          configuration: Mapping[str, Any], item: str, step: int) -> int:
    """Deterministic public demand after the market phase of ``step``.

    This matches the ordering already used by funded_payback: player/rival
    market processing happens first, then unlocked shops and town center remove
    inventory and refresh quotes. Unknown future shop unlocks are not invented.
    """
    shop_interval = max(1, _integer(configuration.get("townShopSellInterval", 4),
                                    "townShopSellInterval", minimum=1))
    center_interval = max(1, _integer(configuration.get("townCenterSellInterval", 24),
                                      "townCenterSellInterval", minimum=1))
    demand = 0
    shops = observation.get("town", {}).get("unlocked_shops", [])
    if step % shop_interval == 0:
        for shop in shops:
            products = mechanics.SHOPS.get(shop)
            if not products:
                continue
            if item in products:
                demand += 2 if len(products) == 1 else 1
    if step % center_interval == 0 and item in mechanics.TOWN_CENTER_PRODUCTS:
        demand += 1
    return demand


def _validated_outputs(outputs: Sequence[Sequence[int]], now: int, terminal: int) -> tuple[tuple[int, int], ...]:
    result = []
    for index, pair in enumerate(outputs):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError(f"outputs[{index}] must be (sale_step, units)")
        step = _integer(pair[0], f"outputs[{index}].step", minimum=now)
        units = _integer(pair[1], f"outputs[{index}].units", minimum=0)
        if units:
            result.append((step, units))
    result.sort()
    if result and result[-1][0] > terminal:
        raise ValueError("output sale lies beyond the executable terminal horizon")
    return tuple(result)


def forecast_marginal_receipts(mechanics: Any, observation: Mapping[str, Any],
                               configuration: Mapping[str, Any], item: str,
                               outputs: Sequence[Sequence[int]], *,
                               rival_supply_units: int | None = None) -> dict[str, Any]:
    """Price only candidate-added units through known public absorption.

    Public rival standing yield (or a caller-supplied seller forecast/stress) is
    conservatively placed in market inventory before the first candidate sale.
    Candidate sales use the official sequential SELL quote rule: each sold unit
    receives its current quote, and only sales above the $1 floor increase
    market supply. Known town demand is then applied after each step's market
    phase. No future own or rival cash receipt is used to fund the candidate.
    """
    if item not in mechanics.PRODUCTS:
        raise ValueError("candidate item is not an official market product")
    now = _integer(observation["step"], "step", minimum=0)
    terminal = _integer(configuration.get("episodeSteps", 720), "episodeSteps", minimum=2) - 2
    schedule = _validated_outputs(outputs, now, terminal)
    if rival_supply_units is None:
        rival_units = public_rival_standing_units(mechanics, observation, item)
        rival_source = "public_standing_yield"
    else:
        rival_units = _integer(rival_supply_units, "rival_supply_units", minimum=0)
        rival_source = "caller_supplied_public_seller_forecast"

    market = observation["market"]
    inventory = _integer(market["inventory"][item], f"market.inventory.{item}") + rival_units
    params = market.get("params")
    floor = int(getattr(mechanics, "PRICE_FLOOR", 1))
    by_step: dict[int, int] = {}
    for step, quantity in schedule:
        by_step[step] = by_step.get(step, 0) + quantity

    receipts = 0.0
    unit_prices: list[int] = []
    absorption = 0
    floor_units = 0
    inventory_trace = []
    through = schedule[-1][0] if schedule else now
    for step in range(now, through + 1):
        before = inventory
        quantity = by_step.get(step, 0)
        step_receipts = 0.0
        for _ in range(quantity):
            price = int(mechanics.market_price(item, inventory, params))
            step_receipts += price
            receipts += price
            unit_prices.append(price)
            if price > floor:
                inventory += 1
            else:
                floor_units += 1
        demand = known_town_absorption(mechanics, observation, configuration, item, step)
        inventory -= demand
        absorption += demand
        inventory_trace.append({
            "step": step,
            "inventory_before_market": before,
            "candidate_units": quantity,
            "candidate_receipts": step_receipts,
            "known_town_absorption": demand,
            "inventory_after_town": inventory,
        })

    return {
        "item": item,
        "now": now,
        "terminal_step": terminal,
        "outputs": [list(pair) for pair in schedule],
        "rival_supply_units": rival_units,
        "rival_supply_source": rival_source,
        "known_town_absorption_units": absorption,
        "marginal_receipts": receipts,
        "minimum_unit_price": min(unit_prices) if unit_prices else None,
        "maximum_unit_price": max(unit_prices) if unit_prices else None,
        "floor_price_units": floor_units,
        "market_saturated": bool(unit_prices) and floor_units == len(unit_prices),
        "inventory_trace": inventory_trace,
        "future_cash_credit": 0,
        "unknown_future_demand_credit": 0,
    }


def evaluate_candidate(mechanics: Any, observation: Mapping[str, Any],
                       configuration: Mapping[str, Any], candidate: ProductionCandidate) -> dict[str, Any]:
    """Return a bounded economic report; never an action or route."""
    now = _integer(observation["step"], "step", minimum=0)
    terminal = _integer(configuration.get("episodeSteps", 720), "episodeSteps", minimum=2) - 2
    costs = {str(name): _money(value, f"costs.{name}") for name, value in candidate.costs.items()}
    total_cost = sum(costs.values())
    ready = now if candidate.ready_step is None else _integer(candidate.ready_step, "ready_step", minimum=now)
    idle_assets = _integer(candidate.idle_assets, "idle_assets", minimum=0)
    try:
        outputs = _validated_outputs(candidate.outputs, now, terminal)
    except ValueError as error:
        return {
            "key": candidate.key, "item": candidate.item, "executable": False,
            "admissible": False, "reason": "output_beyond_terminal_horizon",
            "detail": str(error), "total_incremental_cost": total_cost,
            "net_marginal_value": float("-inf"), "payback_step": None,
            "idle_assets": idle_assets,
        }
    if not candidate.funded:
        return {
            "key": candidate.key, "item": candidate.item, "executable": False,
            "admissible": False, "reason": "funded_payback_rejected",
            "total_incremental_cost": total_cost, "net_marginal_value": float("-inf"),
            "payback_step": None, "idle_assets": idle_assets,
        }
    if ready > terminal or not outputs or outputs[0][0] < ready:
        return {
            "key": candidate.key, "item": candidate.item, "executable": False,
            "admissible": False, "reason": "production_not_ready_before_sale",
            "total_incremental_cost": total_cost, "net_marginal_value": float("-inf"),
            "payback_step": None, "idle_assets": idle_assets,
        }

    forecast = forecast_marginal_receipts(
        mechanics, observation, configuration, candidate.item, outputs,
        rival_supply_units=candidate.rival_supply_units,
    )
    cumulative = 0.0
    payback = None
    sale_steps = {step for step, _ in outputs}
    for row in forecast["inventory_trace"]:
        if row["step"] not in sale_steps:
            continue
        cumulative += row["candidate_receipts"]
        if payback is None and cumulative >= total_cost:
            payback = row["step"]
    net = forecast["marginal_receipts"] - total_cost
    return {
        "key": candidate.key,
        "item": candidate.item,
        "executable": True,
        "admissible": net > 0,
        "reason": "positive_executable_marginal_value" if net > 0 else "nonpositive_marginal_value",
        "costs": costs,
        "total_incremental_cost": total_cost,
        "marginal_receipts": forecast["marginal_receipts"],
        "net_marginal_value": net,
        "payback_step": payback,
        "idle_assets": idle_assets,
        "market_saturated": forecast["market_saturated"],
        "forecast": forecast,
    }


def choose_reinvestment(mechanics: Any, observation: Mapping[str, Any],
                        configuration: Mapping[str, Any], candidates: Sequence[ProductionCandidate],
                        *, inherited_key: str) -> dict[str, Any]:
    """Choose only a strictly better executable marginal value; otherwise no-op."""
    reports = [evaluate_candidate(mechanics, observation, configuration, candidate)
               for candidate in candidates]
    inherited = next((report for report in reports if report["key"] == inherited_key), None)
    if inherited is None:
        raise ValueError("inherited_key must name one supplied candidate")
    executable = [report for report in reports if report["executable"]]
    if not executable:
        return {"changed": False, "reason": "no_executable_candidate", "chosen": inherited_key,
                "reports": reports}
    best = max(executable, key=lambda report: report["net_marginal_value"])
    inherited_value = inherited["net_marginal_value"]
    if (best["key"] == inherited_key or best["net_marginal_value"] <= 0
            or best["net_marginal_value"] <= inherited_value):
        return {"changed": False, "reason": "inherited_mix_has_highest_executable_marginal_value",
                "chosen": inherited_key, "reports": reports}
    return {"changed": True, "reason": "strictly_higher_executable_marginal_value",
            "chosen": best["key"], "reports": reports}
