# SPDX-License-Identifier: Apache-2.0
"""D4's represented-sale timing idea at the native frozen SELL horizon seam.

This module never emits orders, mutates a route, or books a second debt ledger.
It identifies one extra represented STRAWBERRY sale date for the incumbent
optimizer. That optimizer retains funding, stock, shared-slot, and relative-
value admission. A returned date is an opportunity, not a promise of profit.
"""
from __future__ import annotations

ITEM = "STRAWBERRY"
KEY = "r04_d4_strawberry_timing"
DEFAULT_MIN_PRICE = 180


def sale_horizon(*, enabled, now, last, route, action, stock, price,
                 item_end, hard_end, max_orders=10, min_price=DEFAULT_MIN_PRICE,
                 turns_per_day=24):
    """Return a detached diagnostic; ``due`` is None unless every guard passes.

    hard_end is the native scheduler's day/terminal/controller-checkpoint bound.
    Raw order positions are retained: a suffix sale outside the executable cap
    is not an authored opportunity. A stock-consuming PICKUP or same-item buy
    at any intervening date ends the represented-stock proof.
    """
    out = {"reason": "disabled", "due": None, "represented_units": 0}
    if enabled is not True:
        return out
    if (type(enabled) is not bool or type(min_price) is not int or min_price < 2
            or type(turns_per_day) is not int or turns_per_day != 24
            or any(type(x) is not int for x in (now, last, item_end, hard_end, max_orders))):
        return dict(out, reason="invalid_parameters")
    if not 12 * 24 <= now < 19 * 24 or now >= last:
        return dict(out, reason="day_window")
    if type(stock) is not int or stock <= 0:
        return dict(out, reason="no_projected_stock")
    if type(price) is not int or price < min_price:
        return dict(out, reason="price_guard")
    cap = max(1, max_orders)
    stop = min(last, hard_end, (now // 24 + 1) * 24 - 1)
    if not now <= item_end < stop:
        return dict(out, reason="no_temporal_gap")
    if not isinstance(route, (tuple, list)) or len(route) <= stop:
        return dict(out, reason="unrepresented_route")

    def inspect(row, current=False):
        if not isinstance(row, dict):
            return "malformed_action", 0
        orders = row.get("market", [])
        farmer, hands = row.get("farmer", ["PASS"]), row.get("hands", [])
        if not isinstance(orders, list) or not isinstance(farmer, list) or not isinstance(hands, list):
            return "malformed_action", 0
        for command in [farmer, *hands]:
            if not isinstance(command, list) or not command:
                return "malformed_work", 0
            if command[:2] == ["PICKUP", ITEM]:
                return "pickup_barrier", 0
        planned = 0
        for order in orders[:cap]:
            if not isinstance(order, list):
                return "malformed_market", 0
            if len(order) > 1 and order[1] == ITEM:
                if order[0] == "BUY_PRODUCT":
                    return "buy_barrier", 0
                if order[0] == "SELL":
                    if len(order) < 3 or type(order[2]) is not int or order[2] < 0:
                        return "malformed_quantity", 0
                    if current:
                        return "incumbent_current_sale", 0
                    planned += order[2]
        if current and len(orders) >= cap:
            return "current_cap_full", 0
        return None, planned

    reason, _ = inspect(action, True)
    if reason:
        return dict(out, reason=reason)
    for due in range(now + 1, stop + 1):
        reason, quantity = inspect(route[due])
        if reason:
            return dict(out, reason=reason)
        # An earlier authored sale already gives the native optimizer a
        # represented reference. Do not invent residual stock after its fill.
        if quantity and due <= item_end:
            return dict(out, reason="incumbent_future_sale")
        if quantity:
            return {"reason": "represented_sale", "due": due,
                    "represented_units": min(stock, quantity),
                    "original_end": item_end, "price": price}
    return dict(out, reason="no_authored_sale")
