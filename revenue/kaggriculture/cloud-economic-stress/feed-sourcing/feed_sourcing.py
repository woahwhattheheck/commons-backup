# SPDX-License-Identifier: Apache-2.0
"""P18 physical/cost certificate for make-vs-buy livestock feed WHEAT.

This module deliberately does not own actor routing or TITAN market policy.  It
validates an already-authored WHEAT production route against mechanically
observable crop timing and converts a completed shed delivery into the E11
feed-service evaluator's existing SupplyArrival / FeedSupplyCandidate boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class WheatProductionRoute:
    """A producer-owned plant/water/harvest/deposit route.

    Steps are engine decision steps. ``water_steps`` are only WATER actions on
    this WHEAT tile. ``units`` is the number of WHEAT units the route promises
    to deposit; the certificate recomputes a conservative unfertilized yield
    ceiling from the official WHEAT crop definition.
    """
    plant_step: int
    water_steps: tuple[int, ...]
    harvest_step: int
    deposit_step: int
    units: int
    purchased_seed_units: int = 1
    field_opportunity_cost: float = 0.0
    actor_action_opportunity_cost: float = 0.0
    travel_opportunity_cost: float = 0.0
    feed_use_sale_opportunity_cost: float = 0.0
    extra_costs: Mapping[str, float] = field(default_factory=dict)


def _whole(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _positive_whole(value: Any, name: str) -> int:
    result = _whole(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _money(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} cannot be boolean")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


def _day(step: int, turns_per_day: int) -> int:
    return step // turns_per_day


def validate_wheat_route(
    mechanics: Any,
    route: WheatProductionRoute,
    *,
    turns_per_day: int,
    terminal_step: int,
    dependent_pickup_step: int | None = None,
    shed_room_at_deposit: int | None = None,
) -> dict[str, Any]:
    """Certify that the authored route can create the promised shed WHEAT.

    The certificate follows current extracted mechanics conservatively:
    planting day starts with one consecutive unwatered day; each day refresh
    weeds a plant at two consecutive unwatered days; one WATER per day can reset
    that counter; non-ongoing WHEAT begins with one unit and WATER in its yield
    window adds one unfertilized unit.  HARVEST must be at or after
    ``first_yield_day``.  Harvested WHEAT is not shed stock until a later deposit
    action, and E11 can credit that arrival only to a strictly later pickup.
    """
    tpd = _positive_whole(turns_per_day, "turns_per_day")
    terminal = _whole(terminal_step, "terminal_step")
    plant = _whole(route.plant_step, "route.plant_step")
    harvest = _whole(route.harvest_step, "route.harvest_step")
    deposit = _whole(route.deposit_step, "route.deposit_step")
    units = _positive_whole(route.units, "route.units")
    if not (plant < harvest < deposit):
        return {"physical": False, "reason": "route_order_not_plant_harvest_deposit"}
    if deposit > terminal:
        return {"physical": False, "reason": "deposit_after_terminal"}
    if dependent_pickup_step is not None:
        pickup = _whole(dependent_pickup_step, "dependent_pickup_step")
        if deposit >= pickup:
            return {"physical": False, "reason": "deposit_not_before_dependent_pickup"}
    if shed_room_at_deposit is not None:
        room = _whole(shed_room_at_deposit, "shed_room_at_deposit")
        if units > room:
            return {
                "physical": False,
                "reason": "shed_room_cannot_accept_promised_wheat",
                "promised_units": units,
                "shed_room": room,
            }

    crop = mechanics.CROPS["WHEAT"]
    if bool(crop.get("ongoing")):
        raise ValueError("P18 expects WHEAT to be a non-ongoing crop")
    plant_day = _day(plant, tpd)
    harvest_day = _day(harvest, tpd)
    age = harvest_day - plant_day
    first_yield_day = _whole(crop["first_yield_day"], "WHEAT.first_yield_day")
    max_yield_day = _whole(crop["max_yield_day"], "WHEAT.max_yield_day")
    max_yield = _positive_whole(crop["max_yield"], "WHEAT.max_yield")
    if age < first_yield_day:
        return {
            "physical": False,
            "reason": "harvest_before_first_yield_day",
            "harvest_age_days": age,
            "first_yield_day": first_yield_day,
        }

    water_steps = tuple(_whole(step, "route.water_step") for step in route.water_steps)
    if tuple(sorted(water_steps)) != water_steps or len(set(water_steps)) != len(water_steps):
        raise ValueError("route.water_steps must be unique and sorted")
    # Without actor/order proof this certificate cannot certify a same-step
    # PLANT->WATER handoff, so require each WATER on the authored route to be
    # strictly later than PLANT and strictly earlier than HARVEST.  This is
    # intentionally conservative; a producer with a richer actor-order proof can
    # expose that as a separate certified route rather than asking P18 to guess.
    if any(step <= plant or step >= harvest for step in water_steps):
        return {"physical": False, "reason": "water_outside_certified_postplant_preharvest_route"}
    water_days = [_day(step, tpd) for step in water_steps]
    if len(set(water_days)) != len(water_days):
        return {"physical": False, "reason": "multiple_waters_same_day_are_not_effective"}

    # _new_plant sets consecutive_unwatered=1.  At every refresh strictly before
    # harvest day, WATER resets to 0; otherwise the counter increments and a
    # value of two weeds the crop.  We do not require a harvest-day WATER merely
    # for survival because HARVEST occurs before that day's refresh.
    consecutive_unwatered = 1
    water_day_set = set(water_days)
    for current_day in range(plant_day, harvest_day):
        if current_day in water_day_set:
            consecutive_unwatered = 0
        else:
            consecutive_unwatered += 1
        if consecutive_unwatered >= 2:
            return {
                "physical": False,
                "reason": "crop_weeds_before_harvest",
                "weed_refresh_day": current_day,
            }

    window_start = (max_yield_day + 1) // 2
    bonus_waters = sum(
        1 for day in water_days
        if window_start <= day - plant_day <= max_yield_day
    )
    conservative_yield = min(max_yield, 1 + bonus_waters)
    if units > conservative_yield:
        return {
            "physical": False,
            "reason": "promised_units_exceed_certified_yield",
            "promised_units": units,
            "certified_yield_units": conservative_yield,
        }

    return {
        "physical": True,
        "reason": "completed_wheat_route",
        "plant_day": plant_day,
        "harvest_day": harvest_day,
        "harvest_age_days": age,
        "water_days": water_days,
        "certified_yield_units": conservative_yield,
        "promised_units": units,
        "arrival_step": deposit,
    }


def wheat_route_cost(mechanics: Any, route: WheatProductionRoute) -> dict[str, Any]:
    """Price only explicit completed-route costs; never credit future revenue."""
    seeds = _whole(route.purchased_seed_units, "route.purchased_seed_units")
    seed_cash = float(_whole(mechanics.CROPS["WHEAT"]["seed"], "WHEAT.seed") * seeds)
    costs = {
        "seed_cash": seed_cash,
        "field_opportunity_cost": _money(route.field_opportunity_cost, "route.field_opportunity_cost"),
        "actor_action_opportunity_cost": _money(
            route.actor_action_opportunity_cost, "route.actor_action_opportunity_cost"),
        "travel_opportunity_cost": _money(route.travel_opportunity_cost, "route.travel_opportunity_cost"),
        "feed_use_sale_opportunity_cost": _money(
            route.feed_use_sale_opportunity_cost, "route.feed_use_sale_opportunity_cost"),
    }
    for name, value in route.extra_costs.items():
        key = str(name)
        if key in costs:
            raise ValueError(f"extra_costs duplicates reserved key: {key}")
        costs[key] = _money(value, f"route.extra_costs.{key}")
    return {
        "costs": costs,
        "delivered_cost": float(sum(costs.values())),
        "future_sale_cash_credit": 0.0,
    }


def make_e11_candidate(
    e11: Any,
    mechanics: Any,
    route: WheatProductionRoute,
    *,
    key: str,
    turns_per_day: int,
    terminal_step: int,
    dependent_pickup_step: int,
    shed_room_at_deposit: int,
) -> tuple[Any, dict[str, Any]]:
    """Adapt a certified route to E11 instead of creating a second feed ledger."""
    certificate = validate_wheat_route(
        mechanics,
        route,
        turns_per_day=turns_per_day,
        terminal_step=terminal_step,
        dependent_pickup_step=dependent_pickup_step,
        shed_room_at_deposit=shed_room_at_deposit,
    )
    cost = wheat_route_cost(mechanics, route)
    if certificate["physical"]:
        arrivals = (
            e11.SupplyArrival(certificate["arrival_step"], route.units, "p18_completed_wheat_route"),
        )
    else:
        arrivals = ()
    candidate = e11.FeedSupplyCandidate(
        key=key,
        mode="make",
        initial_shed_wheat=0,
        arrivals=arrivals,
        costs=cost["costs"],
        funded=bool(certificate["physical"]),
        metadata={
            "p18_route_certificate": certificate,
            "p18_cost": cost,
        },
    )
    return candidate, certificate


def observed_feed_reserve_units(
    feed_steps: Sequence[int],
    *,
    now_step: int,
    turns_per_day: int,
    reserve_days: int,
    already_covered_units: int = 0,
    max_buffer_units: int = 2,
) -> dict[str, Any]:
    """Bound reserve to observed feed obligations inside a 0/1/2-day horizon."""
    now = _whole(now_step, "now_step")
    tpd = _positive_whole(turns_per_day, "turns_per_day")
    days = _whole(reserve_days, "reserve_days")
    if days > 2:
        raise ValueError("reserve_days is intentionally bounded to 0, 1, or 2")
    covered = _whole(already_covered_units, "already_covered_units")
    cap = _whole(max_buffer_units, "max_buffer_units")
    steps = sorted(_whole(step, "feed_step") for step in feed_steps if step >= now)
    horizon = now + days * tpd
    observed_due = sum(1 for step in steps if step <= horizon)
    target = min(cap, max(0, observed_due - covered))
    return {
        "reserve_days": days,
        "horizon_step": horizon,
        "observed_due_units": observed_due,
        "already_covered_units": covered,
        "target_reserve_units": target,
        "speculative_units": 0,
    }
