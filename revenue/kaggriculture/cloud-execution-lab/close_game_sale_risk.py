# SPDX-License-Identifier: Apache-2.0
"""Public-state close-game SELL risk selector for TITAN V5.

This module never creates, deletes, resizes, or crosses an economic order.  It
only re-ranks contiguous, already-issued sale-only rows inside the executable
market prefix.  Missing/ambiguous evidence is identity.

The selector is opt-in through ``titanCloseGameSaleRisk`` in the configuration
used by a simulation/candidate:

* ``cash_max``: prioritize exact current public-curve cash receipts;
* ``ahead_conservative``: when publicly ahead, protect a fragile lead against a
  shed-cap rival liquidation stress; a lead larger than that stress falls back
  to cash-max ordering;
* ``behind_aggressive``: when publicly behind, prioritize public-flow exposure
  while the deficit is catchable by the same liquidation bound, otherwise
  maximize immediate cash;
* ``adaptive``: choose ahead/behind mode from the public cash gap.

The default/missing mode is ``legacy`` and is byte-for-byte identity.  This is a
bounded action policy, not an inference of hidden rival inventory.
"""
from __future__ import annotations

import copy
import math
from collections.abc import Callable, Mapping
from typing import Any

PriceFunction = Callable[[str, int, Mapping | None], int | float]
SALE_ONLY_GOODS = frozenset(
    ("CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL")
)
MODES = frozenset(("cash_max", "ahead_conservative", "behind_aggressive", "adaptive"))
MAX_STRESS_UNITS = 256
DEFAULT_WINDOW = 48


def _plain_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _sale(order: Any) -> tuple[str, int] | None:
    """Return one engine-executable movable SELL lot, else a hard barrier.

    Match the pinned market parser: SELL rows may carry trailing fields and the
    requested quantity is positive ``int()``-coercible.  Classification never
    rewrites the inherited row; the caller preserves its exact bytes.
    """
    if not isinstance(order, list) or len(order) < 3 or order[0] != "SELL":
        return None
    item = order[1]
    if not isinstance(item, str) or item not in SALE_ONLY_GOODS:
        return None
    try:
        quantity = int(order[2])
    except (TypeError, ValueError, OverflowError):
        return None
    if quantity <= 0 or quantity > MAX_STRESS_UNITS:
        return None
    return item, quantity


def _lot_receipts(item: str, quantity: int, inventory: int, params: Mapping | None,
                  quote: PriceFunction, *, rival_before: int = 0) -> float | None:
    total = 0.0
    try:
        for offset in range(rival_before, rival_before + quantity):
            value = _finite_number(quote(item, inventory + offset, params))
            if value is None or value < 1:
                return None
            total += value
    except (ArithmeticError, LookupError, TypeError, ValueError):
        return None
    return total


def _public_context(observation: Mapping, configuration: Mapping,
                    quote: PriceFunction) -> dict | None:
    step = _plain_int(observation.get("step"))
    episode_steps = _plain_int(configuration.get("episodeSteps", 720))
    window = _plain_int(configuration.get("titanCloseGameWindow", DEFAULT_WINDOW))
    if (step is None or episode_steps is None or window is None
            or episode_steps < 2 or window <= 0):
        return None
    last = episode_steps - 2
    if step > last or step < max(0, last - window + 1):
        return None

    player = _plain_int(observation.get("player"))
    farms = observation.get("farms")
    if player not in (0, 1) or not isinstance(farms, list) or len(farms) != 2:
        return None
    own = farms[player] if isinstance(farms[player], Mapping) else None
    rival = farms[1 - player] if isinstance(farms[1 - player], Mapping) else None
    if own is None or rival is None:
        return None
    own_cash = _finite_number(own.get("money"))
    rival_cash = _finite_number(rival.get("money"))
    if own_cash is None or rival_cash is None:
        return None

    market = observation.get("market")
    if not isinstance(market, Mapping):
        return None
    prices = market.get("prices")
    inventories = market.get("inventory")
    params = market.get("params")
    if (not isinstance(prices, Mapping) or not isinstance(inventories, Mapping)
            or (params is not None and not isinstance(params, Mapping))):
        return None

    capacity = _plain_int(configuration.get("shedCapacity", 100))
    if capacity is None or capacity <= 0:
        return None
    stress_units = min(capacity, MAX_STRESS_UNITS)

    max_visible = 0.0
    for item in SALE_ONLY_GOODS:
        if item not in inventories:
            continue
        inventory = _plain_int(inventories.get(item))
        visible = _finite_number(prices.get(item))
        if inventory is None or visible is None or visible < 1:
            return None
        try:
            checked = _finite_number(quote(item, inventory, params))
        except (ArithmeticError, LookupError, TypeError, ValueError):
            return None
        if checked is None or checked != visible:
            return None
        max_visible = max(max_visible, visible)
    if max_visible <= 0:
        return None

    return {
        "step": step,
        "last": last,
        "gap": own_cash - rival_cash,
        # Deliberately coarse upper stress: every hidden shed slot at the best
        # visible first-unit quote.  It overstates, rather than understates, the
        # cash a bounded rival shed could realize before price decay.
        "liquidation_cash_bound": float(stress_units) * max_visible,
        "stress_units": stress_units,
        "market": market,
        "params": params,
    }


def transform(action: dict, observation: Mapping,
              configuration: Mapping | None = None, *, quote: PriceFunction) -> dict:
    """Apply the configured close-game ranking without changing order topology."""
    if not isinstance(action, dict) or not isinstance(action.get("market", []), list):
        raise ValueError("parent policy must return an object with a market list")
    result = copy.deepcopy(action)
    cfg = configuration if isinstance(configuration, Mapping) else {}
    raw_mode = cfg.get("titanCloseGameSaleRisk", "legacy")
    mode = raw_mode.strip().lower() if isinstance(raw_mode, str) else "legacy"
    if mode not in MODES:
        return result

    context = _public_context(observation, cfg, quote)
    if context is None:
        return result
    gap = context["gap"]
    if mode == "adaptive":
        mode = "ahead_conservative" if gap >= 0 else "behind_aggressive"
    if mode == "ahead_conservative" and gap <= 0:
        return result
    if mode == "behind_aggressive" and gap >= 0:
        return result

    try:
        limit = max(1, int(cfg.get("maxMarketOrdersPerTurn", 10)))
    except (TypeError, ValueError, OverflowError):
        return result
    orders = result["market"]
    end = min(len(orders), limit)
    if end <= 1:
        return result

    market = context["market"]
    inventories = market.get("inventory", {})
    params = context["params"]
    stress_units = context["stress_units"]
    liquidation_bound = context["liquidation_cash_bound"]

    def score(order: Any) -> float | None:
        parsed = _sale(order)
        if parsed is None:
            return None
        item, quantity = parsed
        inventory = _plain_int(inventories.get(item))
        if inventory is None:
            return None
        current = _lot_receipts(item, quantity, inventory, params, quote)
        stressed = _lot_receipts(
            item, quantity, inventory, params, quote, rival_before=stress_units
        )
        if current is None or stressed is None:
            return None
        exposure = max(0.0, current - stressed)
        if mode == "cash_max":
            return current
        if mode == "ahead_conservative":
            # A lead that even the deliberately coarse rival-liquidation bound
            # cannot erase can safely use cash-max ordering.  Fragile leads rank
            # by guaranteed stressed cash instead.
            return current if gap > liquidation_bound else stressed
        # Behind: if one bounded rival shed still spans the deficit, front-run
        # the lots most exposed to public-flow deterioration.  If not, maximize
        # immediate cash rather than pretending the local reorder can catch up.
        return (current + 2.0 * exposure
                if -gap <= liquidation_bound else current)

    scores = [score(order) for order in orders[:end]]
    start = 0
    while start < end:
        if scores[start] is None:
            start += 1
            continue
        stop = start + 1
        while stop < end and scores[stop] is not None:
            stop += 1
        ranked = sorted(
            zip(orders[start:stop], scores[start:stop]),
            key=lambda pair: -pair[1],
        )
        orders[start:stop] = [order for order, _ in ranked]
        start = stop
    result["market"] = orders
    return result
