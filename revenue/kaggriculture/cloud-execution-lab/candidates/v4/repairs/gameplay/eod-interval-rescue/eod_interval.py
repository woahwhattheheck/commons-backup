# SPDX-License-Identifier: Apache-2.0
"""Order-invariant partial EOD rescue for the existing V4 EOD lane.

This is a stock/cargo proof, NOT a second agent, wrapper, key, or promotion.
The caller must retain the existing #12612 timing, cargo-neutral unit work,
shed-neutral executable market, configuration, actor, and price guards.

Let A(t) denote cargo admitted with t free shed slots. Selling vector R,
with k=sum(R), preserves the final shed exactly when A(r+k)-A(r)=R for
EVERY within-actor inventory-key order. Actor order itself remains fixed.
The difference is the cargo stream interval [r,r+k). Subset sums enumerate
all possible starts of each product block without enumerating permutations
or expanding cargo into individual units.
"""
from __future__ import annotations

PRODUCTS = frozenset({
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK",
    "WOOL", "FERTILIZER",
})
SHED_ITEMS = PRODUCTS | {"GOOSE", "COW", "SHEEP"}
# Defensive computational bounds, not claims about the engine's maximum hands.
MAX_ACTORS = 256
MAX_CAPACITY = 100
MAX_MARKET_ROWS = 10


def _block_starts(items):
    """Possible offsets for each product under every order of this actor."""
    result = []
    for product, quantity in items:
        starts = {0}
        for other, amount in items:
            if other != product:
                starts |= {start + amount for start in starts}
        result.append((product, quantity, tuple(sorted(starts))))
    return result


def _interval_vector(actors, left, right):
    """Exact invariant interval vector, or None when order changes it.

    Internal inputs are prevalidated snapshots. Orders of different actors
    are independent, so variation in one actor cannot be cancelled by another.
    """
    result = {}
    offset = 0
    for total, items, blocks in actors:
        lo, hi = max(0, left - offset), min(total, right - offset)
        offset += total
        if lo >= hi:
            continue
        if lo == 0 and hi == total:
            contributions = items
        else:
            contributions = []
            for product, quantity, starts in blocks:
                overlap = None
                for start in starts:
                    value = max(0, min(hi, start + quantity) - max(lo, start))
                    if overlap is None:
                        overlap = value
                    elif value != overlap:
                        return None
                if overlap:
                    contributions.append((product, overlap))
        for product, quantity in contributions:
            result[product] = result.get(product, 0) + quantity
    return result


def certified_rescue_vector(inventories, shed, *, capacity=100, order_slots=10):
    """Largest feasible order-invariant rescue, or None on no proof.

    Feasibility means positive integer sales from existing shed stock, within
    the supplied raw market-slot budget, restoring exactly the baseline final
    shed for every inventory-key permutation. Maximizes rescued UNITS, not
    expected cash or competitive margin. None includes invalid input, no
    overflow, insufficient stock/slots, or ambiguity at every feasible length.

    Capacity 1..100 and slots 0..10 are supported for bounded proof/testing.
    The live EOD caller still admits only the standard 100-capacity game.
    This function never modifies inventories or shed. Zero animal cargo is
    accepted; positive animal cargo is outside the saleable-product theorem.
    """
    if (type(capacity) is not int or not 1 <= capacity <= MAX_CAPACITY
            or type(order_slots) is not int or not 0 <= order_slots <= MAX_MARKET_ROWS
            or not isinstance(inventories, list) or not 1 <= len(inventories) <= MAX_ACTORS
            or not isinstance(shed, dict)):
        return None
    stock = {}
    for item, quantity in shed.items():
        if (type(item) is not str or item not in SHED_ITEMS
                or type(quantity) is not int or quantity < 0):
            return None
        stock[item] = quantity
    stock_total = sum(stock.values())
    if stock_total > capacity:
        return None
    actors = []
    cargo_total = 0
    for inventory in inventories:
        if not isinstance(inventory, dict):
            return None
        items = []
        for item, quantity in inventory.items():
            if (type(item) is not str or item not in SHED_ITEMS
                    or type(quantity) is not int or quantity < 0
                    or (quantity and item not in PRODUCTS)):
                return None
            if quantity:
                items.append((item, quantity))
        # Sorting is for deterministic proof traversal, not an assumed engine order.
        items.sort()
        total = sum(quantity for _, quantity in items)
        actors.append((total, items, ()))
        cargo_total += total
    room = capacity - stock_total
    upper = min(cargo_total - room, sum(stock.get(p, 0) for p in PRODUCTS))
    if upper <= 0 or order_slots == 0:
        return None
    # Compute subset sums only for actors the bounded interval could intersect.
    prepared = []
    offset = 0
    for total, items, _ in actors:
        intersects = offset < room + upper and offset + total > room
        blocks = _block_starts(items) if intersects else ()
        prepared.append((total, items, blocks))
        offset += total
    for units in range(upper, 0, -1):
        vector = _interval_vector(prepared, room, room + units)
        if (vector is None or not vector or sum(vector.values()) != units
                or len(vector) > order_slots):
            continue
        if all(stock.get(product, 0) >= quantity for product, quantity in vector.items()):
            return dict(sorted(vector.items()))
    return None
