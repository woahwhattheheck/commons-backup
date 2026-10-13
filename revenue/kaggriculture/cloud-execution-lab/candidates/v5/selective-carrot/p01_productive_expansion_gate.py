# SPDX-License-Identifier: Apache-2.0
"""Telemetry-only public-evidence accounting for V219's late tomato expansion.

This module never prices HIREs from standing hand count. The authenticated R04
parent prices HIREs from the same-day ``hires_today`` ordinal. At the day-18
admission point the only mechanically required appended labor is the two HIREs
requested by that commitment; later V219 HIREs remain conditional and therefore
contribute zero to the cost-floor telemetry.

A later source audit invalidated P01's previous reject theorem. ``BUY_SEED``
executes per unit under the available budget, so observing V219 revenue proves
that land, at least one TOMATO seed, and the day-18 HIRE commitment executed, but
it does not prove that all ten requested seeds were bought. Until a full-seed
completion receipt/invariant is authenticated, the mechanically proven cost
floor below is diagnostic only and this gate has no reject or accept authority.
Every supported record therefore returns ``decision=None`` and preserves the
exact parent.
"""

PROVEN_LAND_COST_FLOOR = 4000
PROVEN_MIN_SEED_COST_FLOOR = 50
MECHANICALLY_PROVEN_FIXED_COST_FLOOR = (
    PROVEN_LAND_COST_FLOOR + PROVEN_MIN_SEED_COST_FLOOR
)
MODELED_FERTILIZER_RESERVE = 700  # telemetry only; not guaranteed spend.
MAX_OWN_UNITS = 80
START_DAY = 18
TERMINAL_DAY = 29
TURNS_PER_DAY = 24
# Fail-safe per-step TOMATO drain bound from the pinned engine: at most eight
# shop instances * at most two units each + one town-center unit. TOMATO shops
# actually consume less, but 17 avoids depending on shop composition.
MAX_TOMATO_TOWN_DRAIN_PER_STEP = 17


def _extra_workers(day):
    if day in (19, 20, 21, 22, 23, 25):
        return 1
    if day in (26, 27, 28):
        return 3 + int(day == 27)
    return 2


def incremental_hire_cost(hires_today, parent_hires, count, fib):
    """Exact cost of ``count`` appended HIREs after same-day parent HIREs."""
    values = (hires_today, parent_hires, count)
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("HIRE ordinals/counts must be nonnegative integers")
    start = hires_today + parent_hires
    costs = []
    for index in range(start, start + count):
        cost = fib(index)
        if type(cost) is not int or cost < 0:
            raise ValueError("Fibonacci HIRE cost must be a nonnegative integer")
        costs.append(cost)
    return sum(costs)


def route_labor_cost_floor(observation, native, native_day, fib):
    """Mechanically required V219 day-18 HIRE cost under exact pricing.

    Telemetry intentionally includes only the two day-18 commitment HIREs.
    Every later V219 request can be skipped by runtime guards, so future HIREs
    are conditional route spend. ``native_day`` is consulted only at day 18 as
    a fail-closed source-shape check; the parent qualification owns the full
    route scan.
    """
    player = observation.get("player")
    farms = observation.get("farms") or []
    if type(player) is not int or player < 0 or player >= len(farms):
        raise ValueError("missing candidate farm")
    farm = farms[player]
    if not isinstance(farm, dict):
        raise ValueError("candidate farm must be an object")
    step = observation.get("step")
    if type(step) is not int or step < 0 or step // TURNS_PER_DAY != START_DAY:
        raise ValueError("V219 telemetry requires the day-18 admission boundary")
    current_hires = farm.get("hires_today")
    if type(current_hires) is not int or current_hires < 0:
        raise ValueError("candidate hires_today must be a nonnegative integer")
    planned = native_day(native, START_DAY)
    if not planned:
        raise ValueError("V219 telemetry requires a day-18 parent route")

    count = _extra_workers(START_DAY)
    cost = incremental_hire_cost(current_hires, 0, count, fib)
    return cost, {START_DAY: cost}


def rival_tomato_field_projection(observation):
    """Project TOMATO units visible on the rival field through day 29.

    This is diagnostic only. Rival private shed/carried inventory is not public,
    so this value is never used as authority over the parent decision.
    """
    player = observation.get("player")
    farms = observation.get("farms") or []
    if type(player) is not int or player < 0 or player >= len(farms) or len(farms) < 2:
        return 0
    rival_index = (
        1 - player
        if player in (0, 1) and len(farms) == 2
        else next((index for index in range(len(farms)) if index != player), None)
    )
    if rival_index is None:
        return 0
    rival = farms[rival_index]
    if not isinstance(rival, dict):
        return 0
    step = observation.get("step")
    if type(step) is not int or step < 0:
        return 0
    day = step // TURNS_PER_DAY
    units = 0
    for row in rival.get("tiles", []):
        if not isinstance(row, list):
            continue
        for tile in row:
            if not isinstance(tile, dict) or tile.get("crop") != "TOMATO":
                continue
            units += max(0, int(tile.get("yield_units", 0) or 0))
            planted = tile.get("planted_day")
            if not isinstance(planted, int):
                units += 8
                continue
            for production_day in range(planted + 8, planted + 12):
                if day < production_day <= TERMINAL_DAY:
                    units += 2
    return units


def evaluate(observation, native, native_day, fib, market_price):
    """Return telemetry only; ``decision=None`` always preserves the parent."""
    market = observation.get("market") or {}
    prices = market.get("prices") or {}
    inventory = market.get("inventory") or {}
    if "TOMATO" not in prices or "TOMATO" not in inventory:
        return {"decision": None, "reason": "missing_market"}
    # The pinned engine publishes resolved market params only when configuration
    # overrides are active. Price telemetry below relies on the exact default
    # monotone `_ro_price` source carried by the authenticated R04 router.
    if "params" in market:
        return {"decision": None, "reason": "custom_market_params"}
    try:
        current_inventory = int(inventory["TOMATO"])
        observed_quote = int(prices["TOMATO"])
    except (TypeError, ValueError):
        return {"decision": None, "reason": "invalid_market"}
    if current_inventory < 0 or observed_quote < 0:
        return {"decision": None, "reason": "invalid_market"}

    step = observation.get("step")
    if type(step) is not int or step < 0:
        return {"decision": None, "reason": "unsupported_route_state"}
    remaining_steps = max(0, (TERMINAL_DAY + 1) * TURNS_PER_DAY - step)
    future_inventory_floor = (
        current_inventory - MAX_TOMATO_TOWN_DRAIN_PER_STEP * remaining_steps
    )
    try:
        current_curve_quote = int(market_price("TOMATO", current_inventory))
        future_quote_ceiling = int(market_price("TOMATO", future_inventory_floor))
    except (TypeError, ValueError, OverflowError):
        return {"decision": None, "reason": "unsupported_market_curve"}
    if current_curve_quote != observed_quote:
        return {"decision": None, "reason": "custom_market_curve"}
    if future_quote_ceiling < observed_quote or future_quote_ceiling < 0:
        return {"decision": None, "reason": "unsupported_market_curve"}

    try:
        labor_floor, labor_floor_by_day = route_labor_cost_floor(
            observation, native, native_day, fib
        )
    except (TypeError, ValueError, KeyError):
        return {"decision": None, "reason": "unsupported_route_state"}

    mechanically_proven_cost_floor = (
        MECHANICALLY_PROVEN_FIXED_COST_FLOOR + labor_floor
    )
    gross_upper_bound = MAX_OWN_UNITS * future_quote_ceiling

    visible_field = rival_tomato_field_projection(observation)
    modeled_start_inventory = current_inventory + visible_field
    try:
        modeled_gross_visible_field = sum(
            int(market_price("TOMATO", modeled_start_inventory + sold))
            for sold in range(MAX_OWN_UNITS)
        )
    except (TypeError, ValueError, OverflowError):
        modeled_gross_visible_field = None

    # Diagnostic only. A true value does not authorize rejection because full
    # execution of the requested ten-seed purchase is not authenticated.
    negative_payback_telemetry = gross_upper_bound < mechanically_proven_cost_floor
    return {
        "decision": None,
        "reason": "seed_purchase_completion_unproven",
        "full_seed_purchase_authenticated": False,
        "negative_payback_telemetry": negative_payback_telemetry,
        "labor_cost_floor": labor_floor,
        "labor_cost_floor_by_day": labor_floor_by_day,
        "fixed_cost_floor": MECHANICALLY_PROVEN_FIXED_COST_FLOOR,
        "proven_land_cost_floor": PROVEN_LAND_COST_FLOOR,
        "proven_min_seed_cost_floor": PROVEN_MIN_SEED_COST_FLOOR,
        "modeled_fertilizer_reserve": MODELED_FERTILIZER_RESERVE,
        "unavoidable_cost_floor": mechanically_proven_cost_floor,
        "max_own_units": MAX_OWN_UNITS,
        "gross_revenue_upper_bound": gross_upper_bound,
        "future_inventory_floor": future_inventory_floor,
        "future_tomato_quote_ceiling": future_quote_ceiling,
        "observed_tomato_quote": observed_quote,
        "starting_market_inventory": current_inventory,
        "visible_rival_field_projection": visible_field,
        "modeled_gross_visible_field": modeled_gross_visible_field,
    }
