#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-neutral admission facts for FERTILIZER floor-price capacity disposal.

This does NOT mutate an action and it deliberately does NOT model a market as
owned storage.  Its only policy-facing output is the minimum floor-price FERT
quantity that would have to be disposed this EOD to make all currently carried
inventory fit, after conservatively reserving current product/animal buys.

Callers must separately decide whether destroying that FERT is worth the cargo
saved.  Existing FERT seller/operating-stock policy retains that ownership.
"""
from __future__ import annotations

FERTILIZER = "FERTILIZER"
DEFAULT_TURNS_PER_DAY = 24
DEFAULT_SHED_CAPACITY = 100
DEFAULT_MAX_MARKET_ORDERS = 10


def _cfg(configuration, key, default):
    if configuration is None:
        return default
    if isinstance(configuration, dict):
        return configuration.get(key, default)
    return getattr(configuration, key, default)


def _positive_int(value):
    return value if type(value) is int and value > 0 else None


def _nonnegative_total(mapping):
    if not isinstance(mapping, dict):
        return None
    total = 0
    for key, value in mapping.items():
        if not isinstance(key, str) or type(value) is not int or value < 0:
            return None
        total += value
    return total


def _inventories_total(inventories):
    if not isinstance(inventories, list):
        return None
    total = 0
    for inventory in inventories:
        subtotal = _nonnegative_total(inventory)
        if subtotal is None:
            return None
        total += subtotal
    return total


def _shed_buy_upper_bound(rows):
    total = 0
    for row in rows:
        if not isinstance(row, list) or not row:
            return None
        if row[0] not in ("BUY_PRODUCT", "BUY_ANIMAL"):
            continue
        if len(row) < 3 or type(row[2]) is not int or row[2] < 0:
            return None
        total += row[2]
    return total


def _report(reason, **extra):
    out = {
        "eligible": False,
        "reason": reason,
        "warehouse": False,
        "recoverable_custody": False,
        "proposal": None,
    }
    out.update(extra)
    return out


def analyze_floor_disposal(observation, action, configuration=None, *,
                           post_units_fn=None, market_price_fn=None):
    """Return a fail-closed EOD disposal certificate; never alter ``action``.

    The proposed quantity is the minimum current FERT shed stock whose $1 sale
    would make all post-unit carried inventory fit at EOD, assuming every
    requested current BUY_PRODUCT/BUY_ANIMAL deposits into the shed.  That is a
    capacity certificate only, not economic authorization.
    """
    if not isinstance(observation, dict) or not isinstance(action, dict):
        return _report("malformed_input")
    if post_units_fn is None or market_price_fn is None:
        return _report("missing_current_abi")

    step = observation.get("step")
    turns_per_day = _positive_int(_cfg(configuration, "turnsPerDay", DEFAULT_TURNS_PER_DAY))
    shed_capacity = _positive_int(_cfg(configuration, "shedCapacity", DEFAULT_SHED_CAPACITY))
    max_orders = _positive_int(_cfg(configuration, "maxMarketOrdersPerTurn", DEFAULT_MAX_MARKET_ORDERS))
    if type(step) is not int or step < 0 or None in (turns_per_day, shed_capacity, max_orders):
        return _report("malformed_clock_or_config")
    if (step + 1) % turns_per_day:
        return _report("not_eod")

    rows = action.get("market")
    if not isinstance(rows, list):
        return _report("malformed_market")
    if len(rows) >= max_orders:
        return _report("no_market_slot")
    for row in rows:
        if not isinstance(row, list) or not row:
            return _report("malformed_market")
        if len(row) > 1 and row[1] == FERTILIZER and row[0] in ("SELL", "BUY_PRODUCT"):
            return _report("existing_fertilizer_market_touch")

    market = observation.get("market")
    if not isinstance(market, dict):
        return _report("malformed_market_state")
    prices = market.get("prices")
    inventory = market.get("inventory")
    params = market.get("params")
    if not isinstance(prices, dict) or not isinstance(inventory, dict):
        return _report("malformed_market_state")
    price = prices.get(FERTILIZER)
    public_stock = inventory.get(FERTILIZER)
    if type(price) is not int or type(public_stock) is not int or public_stock < 0:
        return _report("malformed_market_state")
    if price != 1:
        return _report("not_floor", observed_price=price)

    try:
        projected = post_units_fn(observation, action, configuration)
    except Exception:
        return _report("unit_projection_failed")
    if not isinstance(projected, (tuple, list)) or len(projected) != 2:
        return _report("unit_projection_failed")
    _farm, private = projected
    if not isinstance(private, dict):
        return _report("unit_projection_failed")
    shed = private.get("shed")
    shed_total = _nonnegative_total(shed)
    carry_total = _inventories_total(private.get("inventories"))
    buys = _shed_buy_upper_bound(rows)
    if None in (shed_total, carry_total, buys):
        return _report("malformed_post_units")
    fert = shed.get(FERTILIZER, 0) if isinstance(shed, dict) else 0
    if type(fert) is not int or fert <= 0:
        return _report("no_fertilizer_stock")

    certified_demand = shed_total + carry_total + buys
    overflow = max(0, certified_demand - shed_capacity)
    if overflow == 0:
        return _report("no_certified_eod_overflow", certified_eod_demand=certified_demand)
    if overflow > fert:
        return _report("fertilizer_insufficient_for_full_carry",
                       certified_eod_demand=certified_demand,
                       overflow_units=overflow, fertilizer_units=fert)

    # A BUY_PRODUCT quote uses post-buy market inventory.  Since the exact engine
    # does not admit $1 sales into public inventory, this is the immediate cost
    # of buying the disposed quantity back from the same observed public stock,
    # before any unknown future player flow.  It is diagnostic, not a forecast.
    try:
        immediate_rebuy = sum(
            market_price_fn(FERTILIZER, max(0, public_stock - j), params)
            for j in range(1, overflow + 1)
        )
    except Exception:
        return _report("price_projection_failed")
    if type(immediate_rebuy) is not int or immediate_rebuy < overflow:
        return _report("price_projection_failed")

    return {
        "eligible": True,
        "reason": "capacity_disposal_candidate",
        "warehouse": False,
        "recoverable_custody": False,
        "proposal": ["SELL", FERTILIZER, overflow],
        "disposal_units": overflow,
        "floor_sale_cash": overflow,
        "immediate_rebuy_cost_same_public_state": immediate_rebuy,
        "immediate_round_trip_gap": immediate_rebuy - overflow,
        "certified_eod_demand_before_disposal": certified_demand,
        "certified_eod_demand_after_disposal": certified_demand - overflow,
        "shed_capacity": shed_capacity,
        "post_unit_fertilizer": fert,
        "public_fertilizer_inventory": public_stock,
        "economic_authorization": False,
        "note": "proposal quantifies capacity only; disposal destroys own FERT custody at the floor",
    }
