# SPDX-License-Identifier: Apache-2.0
"""R04 lane E1: dribble fragile goods, dump safe goods.

Execution policy by price-fragility. Code-verified + measured engine facts:

- STRAWBERRY / MILK floor after just ~61 / ~75 units of net supply sold
  (linear -$2/unit from the very first unit).
- WOOL / MELON floor at ~58 / ~157 (quadratic: gentle, then a cliff).
- WHEAT / EGG are effectively unfloorable (log shape): bulk volume belongs here.
- Measured: 50 WOOL dumped at once = $7,655 vs dribbled = $8,978 (+$1,323);
  60 MILK dumped = $5,886 vs dribbled = $6,640 (+$754).

The lane rewrites the SELL rows of the action produced by POLICY_AGENT:

1. Per-step dribble caps on fragile goods (STRAWBERRY, MILK, WOOL, MELON):
   a single step's sales can never push a good a large fraction of the way to
   its floor by itself. Caps are cumulative per good per step across rows.
2. Days 0-2 (steps 0-71): NO fragile-good sales at all. Town demand is zero
   early, so every unit of self-inflicted slip is permanent until day 3+;
   the early game is funded with EGG / WHEAT, which are never touched.
3. A good printing $1 is passed through uncapped: at the floor, further sales
   add zero marginal price harm, so the planned quantity liquidates free.

The lane never synthesizes new SELL rows (no stock knowledge at this seam;
the tape's own flush and terminal liquidation already sweep inventory) and
never touches WHEAT, EGG, CARROT, TOMATO, FERTILIZER, or non-SELL rows.
At/after LAST_STEP the terminal liquidation is left untouched: with no future
steps there is nothing to protect.

Attaches in r04_full_router.v3_agent between POLICY_AGENT and ROW_ORDER,
behind the TITAN-CONFIG.json key r04_dribble_dump (default False). When the
r04_full_router.DRIBBLE_DUMP module flag is off the condition short-circuits
and behavior is byte-identical to the pre-lane route.

Python standard library only.
"""

from __future__ import annotations

# Goods whose price curve floors fast under own supply.
FRAGILE = ("STRAWBERRY", "MILK", "WOOL", "MELON")

# Per-step SELL cap per fragile good (cumulative across rows in the step).
# Each cap is ~1/4 of the measured floor point (61 / 75 / 58 / 157 units of
# net supply), so one step can never do more than ~25% of the floor damage.
DRIBBLE_CAPS = {
    "STRAWBERRY": 15,
    "MILK": 15,
    "WOOL": 12,
    "MELON": 30,
}

# Steps 0-71 (days 0-2): zero town demand; fragile sales are dropped outright.
EARLY_BAN_END = 72

# r04_full_router.LAST_STEP; the terminal liquidation sells everything and is
# never capped (no future steps to protect).
LAST_STEP = 718

_FLOOR_PRICE = 1


def _fresh_report():
    return {
        "steps_active": 0,
        "rows_capped": 0,
        "units_deferred": 0,
        "rows_dropped_early": 0,
        "floor_passthrough": 0,
    }


# Module-level telemetry; reset() restores the zeros (for tests).
report = _fresh_report()


def reset():
    """Restore the module-level report counters to zero."""
    report.clear()
    report.update(_fresh_report())


def get_report():
    """Return a copy of the module-level report counters."""
    return dict(report)


def capped_quantity(good, quantity, price):
    """Return the allowed SELL quantity for a fragile good at this step.

    Pure function of (good, quantity, price): the $1 floor passes through
    uncapped, everything else is capped at DRIBBLE_CAPS[good]. Never raises.
    """
    try:
        if good not in DRIBBLE_CAPS:
            return quantity
        if int(price) <= _FLOOR_PRICE:
            return quantity
        cap = DRIBBLE_CAPS[good]
        return min(max(0, int(quantity)), cap)
    except Exception:
        return quantity


def apply_dribble_dump(observation, action):
    """Cap fragile-good SELL rows per the dribble policy; never raises.

    Returns the action unchanged outside steps 0..LAST_STEP-1, at/after the
    terminal liquidation, when the action is malformed, or when nothing
    changed. Steps 0-71 drop fragile SELL rows; later steps cap them per
    good (cumulative across rows), except goods printing $1, which pass
    through. WHEAT/EGG and every non-fragile row are untouched.
    """
    try:
        return _apply(observation, action)
    except Exception:
        return action


def _apply(observation, action):
    try:
        step = int(observation["step"])
    except Exception:
        return action
    if step < 0 or step >= LAST_STEP:
        return action
    if not isinstance(action, dict):
        return action
    market = action.get("market")
    if not market:
        return action
    try:
        prices = (observation.get("market") or {}).get("prices") or {}
    except Exception:
        return action

    report["steps_active"] += 1
    changed = False
    sold = {}  # cumulative capped units per fragile good, this step
    new_market = []
    for order in market:
        if not (order and order[0] == "SELL" and len(order) >= 3
                and order[1] in DRIBBLE_CAPS):
            new_market.append(order)
            continue
        good = order[1]
        try:
            quantity = int(order[2])
        except Exception:
            new_market.append(order)
            continue
        if quantity <= 0:
            new_market.append(order)
            continue
        if step < EARLY_BAN_END:
            # Days 0-2: no fragile sales; every unit of slip is permanent.
            report["rows_dropped_early"] += 1
            report["units_deferred"] += quantity
            changed = True
            continue
        price = prices.get(good)
        try:
            floored = price is not None and int(price) <= _FLOOR_PRICE
        except Exception:
            floored = False
        if floored:
            report["floor_passthrough"] += 1
            new_market.append(order)
            continue
        remaining = DRIBBLE_CAPS[good] - sold.get(good, 0)
        if remaining <= 0:
            report["rows_dropped_early"] += 0  # capped-out rows vanish
            report["units_deferred"] += quantity
            changed = True
            continue
        if quantity > remaining:
            capped = list(order)
            capped[2] = remaining
            new_market.append(capped)
            report["rows_capped"] += 1
            report["units_deferred"] += quantity - remaining
            sold[good] = DRIBBLE_CAPS[good]
            changed = True
        else:
            sold[good] = sold.get(good, 0) + quantity
            new_market.append(order)
    if not changed:
        return action
    new_action = dict(action)
    new_action["market"] = new_market
    return new_action
