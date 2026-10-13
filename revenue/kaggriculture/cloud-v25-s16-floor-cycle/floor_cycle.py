# SPDX-License-Identifier: Apache-2.0
"""Bounded S16 shadow candidate for the pinned Kaggriculture floor asymmetry.

This is an experiment helper, not a controller.  It proposes one BUY_PRODUCT 1
then SELL 1 cycle only when the physical gates hold and the caller's complete
future scenario deltas are all strictly positive.  It never assigns immediate
profit to the cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

PRICE_FLOOR = 1
FERT_PARAMS = {
    "base": 100,
    "I0": 10000,
    "T": 200,
    "below_func": "linear",
    "below_target": 0.40,
    "above_func": "linear",
    "above_target": 0.40,
}


def market_price_fertilizer(inventory: int) -> int:
    """Exact pinned-engine price for FERTILIZER."""
    p = FERT_PARAMS
    base, i0, T = p["base"], p["I0"], p["T"]
    x = abs(inventory - i0)
    if inventory < i0:
        price = base + (p["below_target"] * base / T) * x
    else:
        price = base - (p["above_target"] * base / T) * x
    return max(PRICE_FLOOR, int(round(price)))


@dataclass(frozen=True)
class CycleState:
    cash: int
    stock: int
    public_inventory: int


def exact_floor_cycle(state: CycleState, *, shed_room: int) -> CycleState | None:
    """Execute exact BUY_PRODUCT FERT1 -> SELL FERT1, or decline.

    BUY is quoted at post-buy inventory.  A SELL at price 1 does not replenish
    public supply in the pinned engine.  This models only the two own orders;
    opponent interleaving belongs in the future scenario evaluator.
    """
    buy_price = market_price_fertilizer(state.public_inventory - 1)
    if buy_price != PRICE_FLOOR or state.cash < buy_price or shed_room < 1:
        return None
    after_buy = CycleState(state.cash - buy_price, state.stock + 1,
                           state.public_inventory - 1)
    sell_price = market_price_fertilizer(after_buy.public_inventory)
    if sell_price != PRICE_FLOOR or after_buy.stock < 1:
        return None
    public_inventory = after_buy.public_inventory + (1 if sell_price > 1 else 0)
    return CycleState(after_buy.cash + sell_price, after_buy.stock - 1,
                      public_inventory)


def paired_future_margin(inventory: int, rival: str) -> int:
    """One future own FERT1 sale; return own-minus-rival cash change.

    Rival action is simultaneous in the same market slot, so both players quote
    from the same pre-commit inventory, matching the pinned per-unit lockstep.
    Supported rival cases are none, buy, and sell.  Only the cash change of this
    future slot is returned; physical feasibility is a caller-side scenario gate.
    """
    own = market_price_fertilizer(inventory)
    if rival == "none":
        return own
    if rival == "buy":
        rival_spend = market_price_fertilizer(inventory - 1)
        return own + rival_spend
    if rival == "sell":
        rival_receipt = market_price_fertilizer(inventory)
        return own - rival_receipt
    raise ValueError("rival must be none, buy, or sell")


def future_scenario_deltas(start_inventory: int, *, absorption_units: int) -> dict[str, int]:
    """Compare baseline versus one completed neutral cycle before a future sale."""
    if absorption_units < 0:
        raise ValueError("absorption_units must be nonnegative")
    initial = CycleState(cash=10_000, stock=1, public_inventory=start_inventory)
    cycled = exact_floor_cycle(initial, shed_room=99)
    if cycled is None or (cycled.cash, cycled.stock) != (initial.cash, initial.stock):
        raise ValueError("start inventory is not an exact cash/stock-neutral floor cycle")
    baseline_inv = start_inventory - absorption_units
    cycle_inv = cycled.public_inventory - absorption_units
    return {name: paired_future_margin(cycle_inv, name) - paired_future_margin(baseline_inv, name)
            for name in ("none", "buy", "sell")}


def admit_floor_cycle(*, cash: int, shed_room: int, free_market_slots: int,
                      downstream_steps: int, scenario_deltas: Mapping[str, float]) -> dict:
    """Fail closed unless physical gates and strict worst-scenario value hold."""
    reason = None
    if cash < 1:
        reason = "insufficient_cash"
    elif shed_room < 1:
        reason = "no_shed_room"
    elif free_market_slots < 2:
        reason = "need_two_market_slots"
    elif downstream_steps < 1:
        reason = "no_downstream_opportunity"
    elif not scenario_deltas:
        reason = "no_scenarios"
    else:
        try:
            values = tuple(float(v) for v in scenario_deltas.values())
        except (TypeError, ValueError):
            values = ()
        if (not values or any(not isfinite(v) for v in values)):
            reason = "invalid_scenario_value"
        elif min(values) <= 0:
            reason = "nonpositive_worst_case"
    if reason:
        return {"admitted": False, "reason": reason, "orders": (),
                "immediate_profit_credit": 0}
    return {"admitted": True, "reason": "strict_positive_future_value",
            "orders": (("BUY_PRODUCT", "FERTILIZER", 1), ("SELL", "FERTILIZER", 1)),
            "immediate_profit_credit": 0,
            "worst_scenario_gain": min(float(v) for v in scenario_deltas.values())}
