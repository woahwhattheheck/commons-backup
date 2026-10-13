# SPDX-License-Identifier: Apache-2.0
"""V4 ADVANCE_SLOT_VALUE: spend scarce market slots on higher public-value sales.

The parent router owns eligibility and timing.  This helper only replaces the
already-audited value-ranking branch so the V4 key has a matching module seam
for monotonic plumbing checks.  Disabled use is an exact no-op.
"""
from __future__ import annotations


def apply_advance_slot_value(
    action,
    view,
    state,
    stock,
    planned,
    already_selling,
    products,
    max_orders,
    next_step,
    *,
    enabled=False,
):
    """Apply the existing value-ranked advanced-sale branch in place."""
    if not enabled:
        return False

    candidates = []
    for product_rank, item in enumerate(products):
        if item in ("WHEAT", "FERTILIZER") or item in already_selling:
            continue
        quantity = min(stock.get(item, 0), planned.get(item, 0))
        price = int(view.prices.get(item, 0))
        if quantity <= 0 or price < 2:
            continue
        candidates.append((-price * quantity, product_rank, item, quantity))
    candidates.sort()

    slots = max(0, max_orders - len(action["market"]))
    selected = {
        item: quantity
        for _neg_value, _product_rank, item, quantity in candidates[:slots]
    }
    for item in products:
        if item not in selected:
            continue
        quantity = selected[item]
        action["market"].append(["SELL", item, quantity])
        state.advanced_sales[item] = quantity
    if state.advanced_sales:
        state.sale_due_step = next_step
    return True
