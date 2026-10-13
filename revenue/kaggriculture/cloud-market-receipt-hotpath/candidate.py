# SPDX-License-Identifier: Apache-2.0
"""Reusable MarketPath._single candidate for the frozen SELL scheduler.

This module does not patch or import a controller. The function is intended to be
bound as MarketPath._single by the existing checkpoint builder after source-pinned
parity and timing checks. Unusual numeric inputs keep the caller's original
receipt-helper path via ``fallback``.
"""
from __future__ import annotations

import math


def single_pass_receipts(self, inv, quantity, *, fallback):
    """Return the same ``(int(cash), admitted_inventory)`` result in one pass.

    ``fallback`` must implement the exact pre-change MarketPath._single behavior
    for the caller. Ordinary integer market states take the fast path; all other
    inputs delegate unchanged.
    """
    if (type(inv) is int and type(quantity) is int and quantity >= 0
            and abs(inv) + quantity <= 2**53):
        cash = 0.0
        for index in range(quantity):
            price = float(self.quote(inv))
            if not math.isfinite(price):
                raise ValueError("Non-finite economic input")
            if (price == 1 and cash.is_integer()
                    and 0 <= cash <= 2**53 - (quantity - index)):
                cash += quantity - index
                break
            cash += price
            if price > 1:
                inv += 1
        return int(cash), inv
    return fallback(inv, quantity)
