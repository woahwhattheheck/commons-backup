# SPDX-License-Identifier: Apache-2.0
"""Physical-zero-lot extension of TITAN's existing final pressure transform.

No producer, private rival estimate, new ranking, or activation flag lives here.
The adapter delegates pressure exactly once, projects the returned unit vector
with the existing scheduler, then stably moves only provably zero-fill sales.
It is a current-market mechanism, NOT a whole-game value certificate.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

SALE_ONLY = frozenset(('CARROT', 'TOMATO', 'STRAWBERRY', 'MELON', 'EGG', 'MILK', 'WOOL'))
PRODUCTS = SALE_ONLY | {'WHEAT', 'FERTILIZER'}
MAX_ORDERS = 64
CAPACITY = 100


def _limit(configuration: Mapping) -> int | None:
    value = configuration.get('maxMarketOrdersPerTurn', 10)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    # The engine truncates raw slots before parsing, with a minimum of one.
    return max(1, value)


def _prefix(orders: Any, configuration: Mapping) -> tuple[list, int] | None:
    if not isinstance(orders, list):
        return None
    limit = _limit(configuration)
    capacity = configuration.get('shedCapacity', CAPACITY)
    if (limit is None or isinstance(capacity, bool) or capacity != CAPACITY
            or not isinstance(capacity, int)):
        return None
    end = min(len(orders), limit)
    if end > MAX_ORDERS:
        return None
    prefix = orders[:end]
    for row in prefix:
        if row == []:
            continue
        if (not isinstance(row, list) or len(row) != 3 or row[0] != 'SELL'
                or not isinstance(row[1], str) or row[1] not in PRODUCTS
                or isinstance(row[2], bool) or not isinstance(row[2], int)
                or not 0 <= row[2] <= 256):
            return None
        # Do not cross operating-input or capital/purchase ownership. A literal
        # SELL WHEAT/FERTILIZER 0 is the predecessor's already-known empty row.
        if row[2] and row[1] not in SALE_ONLY:
            return None
    return prefix, end


def compact_stockless_sales(orders: list, post_unit_shed: Mapping,
                             market: Mapping, configuration: Mapping, *,
                             quote: Callable) -> list:
    """Preserve all raw rows; compact stable positive fills ahead of zero fills.

    post_unit_shed MUST describe the same selected farmer/hands vector after
    units and before market, with finite shed capacity (not a future/uncapped
    planner snapshot). Missing product keys in that actual mapping mean zero.
    Malformed evidence declines by returning the original list object.

    Later duplicate lots consume only the remaining stock. Crossing a zero lot
    neither deletes it nor changes any productive lot's quantity/order. Quotes
    must match the visible, bounded, nonincreasing public curve. Rival buyable
    products are excluded; arbitrary rival funding responses and later policy
    changes remain evaluation questions, not guaranteed margin improvements.
    """
    if not isinstance(configuration, Mapping) or not isinstance(market, Mapping):
        return orders
    parsed = _prefix(orders, configuration)
    if parsed is None or not isinstance(post_unit_shed, Mapping):
        return orders
    if len(post_unit_shed) > 64:
        return orders
    remaining = {}
    for item, quantity in post_unit_shed.items():
        if (not isinstance(item, str) or isinstance(quantity, bool)
                or not isinstance(quantity, int) or quantity < 0):
            return orders
        remaining[item] = quantity
    if sum(remaining.values()) > CAPACITY:
        return orders
    prefix, end = parsed
    positive, empty, totals = [], [], {}
    for row in prefix:
        if row == [] or row[2] == 0:
            empty.append(row)
            continue
        item, requested = row[1:]
        fill = min(requested, remaining.get(item, 0))
        remaining[item] = remaining.get(item, 0) - fill
        if fill == 0:
            empty.append(row)
        else:
            positive.append(row)
            totals[item] = totals.get(item, 0) + fill
    candidate = positive + empty
    if not positive or not empty or candidate == prefix:
        return orders
    prices, inventories = market.get('prices'), market.get('inventory')
    params = market.get('params')
    if (not isinstance(prices, Mapping) or not isinstance(inventories, Mapping)
            or (params is not None and not isinstance(params, Mapping))):
        return orders
    exposed = False
    try:
        for item, quantity in totals.items():
            inventory, visible = inventories.get(item), prices.get(item)
            if (isinstance(inventory, bool) or not isinstance(inventory, int)
                    or isinstance(visible, bool) or not isinstance(visible, (int, float))
                    or not math.isfinite(visible) or visible < 1):
                return orders
            # At most 100 own + 100 rival physical units can affect these
            # nonbuyable goods in this market. At the price floor admission
            # stops, which stays within this verified interval.
            curve = [quote(item, inventory + k, params)
                     for k in range(quantity + CAPACITY + 1)]
            if (any(isinstance(p, bool) or not isinstance(p, (int, float))
                    or not math.isfinite(p) or p < 1 for p in curve)
                    or curve[0] != visible
                    or any(a < b for a, b in zip(curve, curve[1:]))):
                return orders
            exposed |= curve[0] > curve[-1]
    except (ArithmeticError, LookupError, TypeError, ValueError):
        return orders
    return candidate + orders[end:] if exposed else orders


def transform(action: dict, observation: Mapping, configuration: Mapping | None = None,
              *, pressure: Any, post_units: Callable, quote: Callable) -> dict:
    """Drop-in composition at the existing final pressure boundary, not after it.

    pressure is the existing module; post_units is the existing scheduler's
    real finite-capacity projector. No selected/future snapshot is accepted.
    This adapter is intentionally not wired into production by its presence.
    Cancellation (including TITAN's BaseException deadline) propagates normally.
    """
    baseline = pressure.transform(action, observation, configuration, quote=quote)
    cfg = dict(configuration) if isinstance(configuration, Mapping) else {}
    parsed = _prefix(baseline.get('market'), cfg) if isinstance(baseline, dict) else None
    if parsed is None or parsed[1] < 2:
        return baseline
    if not isinstance(observation, Mapping):
        return baseline
    player, farms = observation.get('player'), observation.get('farms')
    if (type(player) is not int or player not in (0, 1)
            or not isinstance(farms, list) or len(farms) != 2
            or not isinstance(farms[player], Mapping)
            or not isinstance(observation.get('private'), Mapping)
            or type(observation.get('step')) is not int or observation['step'] < 0):
        return baseline
    tiles = farms[player].get('tiles')
    board = cfg.get('boardSize', 10)
    turns = cfg.get('turnsPerDay', 24)
    if (type(board) is not int or board <= 0 or type(turns) is not int
            or not isinstance(tiles, list) or len(tiles) != board
            or any(not isinstance(row, list) or len(row) != board for row in tiles)):
        return baseline
    cfg['turnsPerDay'] = max(1, turns)
    farmer, hands = baseline.get('farmer', ['PASS']), baseline.get('hands', [])
    if (not isinstance(farmer, list) or not isinstance(hands, list)
            or len(hands) > 64 or any(not isinstance(a, list) for a in hands)):
        return baseline
    try:
        _, private = post_units(observation, baseline, cfg)
    except (ArithmeticError, LookupError, TypeError, ValueError):
        return baseline
    if not isinstance(private, Mapping):
        return baseline
    orders = baseline.get('market', [])
    compact = compact_stockless_sales(orders, private.get('shed'),
                                      observation.get('market'), cfg, quote=quote)
    if compact is orders:
        return baseline
    return dict(baseline, market=compact)
