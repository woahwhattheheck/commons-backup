# SPDX-License-Identifier: Apache-2.0
"""Default-OFF native-ABI port of the existing EOD-capacity-rescue theorem.

Use the current scheduler's exact unit projection, not pre-action cargo or a
possibly stale selected-action snapshot. This is a candidate component, not a
post-return wrapper: any eventual caller belongs before finalizer/history
receipts, after the final unit and pre-existing market action has been selected.
The existing legacy donor is retained unchanged in this package.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

PRODUCTS = frozenset(("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
                      "EGG", "MILK", "WOOL", "FERTILIZER"))
_STANDARD = {"boardSize": 10, "turnsPerDay": 24, "shedCapacity": 100,
             "maxMarketOrdersPerTurn": 10, "episodeSteps": 720,
             "townShopSellInterval": 4, "townCenterSellInterval": 24}
_UNIT_OPS = frozenset(("PASS", "NORTH", "SOUTH", "EAST", "WEST", "WATER",
                       "DIG", "CARE", "BUILD_COOP", "BUILD_PASTURE", "PLANT",
                       "DROP", "PICKUP", "PLACE", "HARVEST", "FERTILIZE",
                       "FEED", "COLLECT_FERTILIZER"))
_MARKET_NEUTRAL = frozenset(("HIRE", "BUY_LAND", "BUY_SEED"))


def _stock(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(k, str) and type(n) is int and n >= 0
        for k, n in value.items())


def _position(value: Any) -> bool:
    return (isinstance(value, list) and len(value) == 2
            and all(type(v) is int and 0 <= v < 10 for v in value))


def apply_native_eod_capacity_rescue(action: Any, observation: Any,
                                    configuration: Any, *, enabled=False):
    """Return (action, diagnostic), preserving parent identity on every skip.

    Appended SELL uses only actual post-unit, single-product carried overflow.
    Own earlier market rows must be shed-neutral. Private post-EOD shed equality
    does not imply equal public supply or positive whole-game competitive EV.
    No deadline exceptions are swallowed and no private state is retained.
    """
    def skip(reason):
        return action, {"changed": False, "reason": reason}

    if not enabled:
        return skip("disabled")
    if not isinstance(configuration, dict):
        return skip("configuration")
    if any(type(configuration.get(k, v)) is not int
           or configuration.get(k, v) != v for k, v in _STANDARD.items()):
        return skip("configuration")
    if not isinstance(action, dict) or not isinstance(observation, dict):
        return skip("schema")
    step, seat = observation.get("step"), observation.get("player")
    if type(step) is not int or not 0 <= step <= 695 or step % 24 != 23:
        return skip("not_usable_eod")
    if type(seat) is not int or seat not in (0, 1):
        return skip("player")
    farms, private = observation.get("farms"), observation.get("private")
    if not isinstance(farms, list) or len(farms) != 2 or not isinstance(private, dict):
        return skip("schema")
    farm = farms[seat]
    if not isinstance(farm, dict):
        return skip("schema")
    hands, positions = action.get("hands"), farm.get("hands")
    if (not isinstance(hands, list) or not isinstance(positions, list)
            or not all(_position(p) for p in [farm.get("farmer"), *positions])):
        return skip("actors")
    tiles = farm.get("tiles")
    if (not isinstance(tiles, list) or len(tiles) != 10
            or any(not isinstance(row, list) or len(row) != 10 for row in tiles)):
        return skip("board")
    money = farm.get("money")
    if (type(money) not in (int, float)
            or (type(money) is float and not math.isfinite(money)) or money < 0):
        return skip("money")
    rows = [action.get("farmer"), *hands]
    for row in rows:
        if (not isinstance(row, list) or not row or not isinstance(row[0], str)
                or row[0] not in _UNIT_OPS):
            return skip("unit_schema")
        if len(row) > 1 and not isinstance(row[1], str):
            return skip("unit_schema")
        if len(row) > 2 and (type(row[2]) is not int or row[2] < 0):
            return skip("unit_schema")
    inventories = private.get("inventories")
    if (not isinstance(inventories, list) or len(inventories) != 1 + len(positions)
            or not all(_stock(inv) for inv in inventories)
            or not _stock(private.get("shed")) or not _stock(private.get("seeds"))):
        return skip("private_schema")
    market = action.get("market")
    if not isinstance(market, list) or len(market) >= 10:
        return skip("market_capacity")
    for order in market:
        if not isinstance(order, list):
            return skip("market_schema")
        if not order:
            continue
        if not isinstance(order[0], str) or order[0] not in _MARKET_NEUTRAL:
            return skip("market_stock_or_unknown")
        if len(order) > 1 and not isinstance(order[1], str):
            return skip("market_schema")
        if len(order) > 2 and (type(order[2]) is not int or order[2] < 0):
            return skip("market_schema")

    # Omitted actors retain cargo; extra command rows have no position, but
    # still contribute to the engine's atomic PLANT-demand validation. Pass the
    # complete raw action to the projector; bind inventories to actual actors.
    # This is the exact current unit-stage routine, including atomic PLANT
    # validation and sequential actors. Import only on an eligible callback.
    from scheduler import post_units
    try:
        _, projected = post_units(observation, action, configuration)
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        return skip("projection_schema")
    if not isinstance(projected, dict):
        return skip("projection_schema")
    shed, cargo = projected.get("shed"), projected.get("inventories")
    if (not _stock(shed) or not isinstance(cargo, list) or len(cargo) != 1 + len(positions)
            or not all(_stock(inv) for inv in cargo)):
        return skip("projection_schema")
    positive = {p for inv in cargo for p, n in inv.items() if n > 0}
    if len(positive) != 1 or not positive.issubset(PRODUCTS):
        return skip("not_single_product")
    product = next(iter(positive))
    shed_total = sum(shed.values())
    carried_total = sum(inv.get(product, 0) for inv in cargo)
    if shed_total > 100:
        return skip("overfull_shed")
    overflow = shed_total + carried_total - 100
    if overflow <= 0:
        return skip("no_overflow")
    if overflow > carried_total or shed.get(product, 0) < overflow:
        return skip("insufficient_same_product")
    public_market = observation.get("market")
    prices = public_market.get("prices") if isinstance(public_market, dict) else None
    price = prices.get(product) if isinstance(prices, dict) else None
    if type(price) is not int or price < 1:
        return skip("price")

    result = deepcopy(action)
    result["market"].append(["SELL", product, overflow])
    return result, {"changed": True, "reason": "post_unit_overflow",
                    "product": product, "rescued_units": overflow,
                    "post_unit_shed_total": shed_total,
                    "post_unit_carried_total": carried_total,
                    "observed_quote": price}
