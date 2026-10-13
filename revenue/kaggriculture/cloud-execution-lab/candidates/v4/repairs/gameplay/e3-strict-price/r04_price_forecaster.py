# SPDX-License-Identifier: Apache-2.0
"""R04 lane E3 "price-forecaster": forward-simulate the price path, defer sales into peaks.

Attaches in r04_full_router.v3_agent after EVENING_FLUSH, behind the
r04_price_forecaster flag (default False). When on and 288 <= step <= 717,
every SELL row in the action's market list is checked against a forward
simulation of that good's price path:

  * The price function is the pinned kaggriculture curve
    (price = base +/- amp * f(|inv - 10000|), floored at $1), ported exactly.
  * Town consumption is deterministic given the public unlocked-shop list
    (shops consume every 4 steps, the town center every 24; player trades run
    first within each step, town consumption second).
  * Rival per-good sale flow is estimated from public market-inventory deltas
    minus our own recorded sales minus deterministic town consumption
    (slow EMA, clamped >= 0; rivals buying is ignored, a conservative miss).

For each SELL row the lane compares selling each unit now against selling it
at the forecasted price peak within FORECAST_HORIZON steps and keeps only the
leading prefix that beats the peak (2% defer margin against churn). Deferred
units stay in the shed; the E184 sale window re-advances them on later steps
(receding horizon), so the forecast is re-evaluated daily with fresh data.

Cash guard: the tape's BUY_*/HIRE/BUY_LAND orders over the next 48 steps are
costed conservatively; sales are never deferred below the cash needed to fund
them (farm cash + kept-sale revenue must cover it).

The lane only ever drops or shrinks SELL rows; it never adds, grows, or
reorders rows, and it never touches non-SELL rows. Flag off (or a custom
marketParams configuration, or a malformed observation) leaves the action
byte-identical. apply_price_forecaster never raises.

Standard library only.
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Pinned market microstructure (kaggriculture MARKET_PARAMS / SHOPS).
# ---------------------------------------------------------------------------

PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER")

# (base, T, below_func, below_target, above_func, above_target); I0 = 10000.
_MARKET_PARAMS = {
    "WHEAT":      (25, 400, "sqrt",  0.80, "log",    0.20),
    "CARROT":     (35, 450, "hinge", 1.00, "sqrt",   0.70),
    "TOMATO":     (60, 200, "hinge", 0.40, "sqrt",   0.60),
    "STRAWBERRY": (120, 100, "sqrt", 0.70, "linear", 1.60),
    "MELON":      (250, 300, "log",  0.20, "sq",     3.60),
    "EGG":        (50, 332, "hinge", 0.40, "log",    0.20),
    "MILK":       (160, 122, "sqrt", 0.60, "linear", 1.60),
    "WOOL":       (200, 105, "log",  0.20, "sq",     3.20),
    "FERTILIZER": (100, 200, "linear", 0.40, "linear", 0.40),
}
_I0 = 10000
_PRICE_FLOOR = 1

_SHOPS = {
    "BAKERY":         ("EGG", "WHEAT"),
    "PIZZA_SHOP":     ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT":    ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE":     ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE":       ("CARROT",),
    "SMOOTHIE_SHOP":  ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}
_TOWN_CENTER_PRODUCTS = tuple(p for p in PRODUCTS if p != "FERTILIZER")

_SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50,
              "STRAWBERRY": 100, "MELON": 80}
_ANIMAL_COST = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
_BASE_PRICE = {item: params[0] for item, params in _MARKET_PARAMS.items()}

# ---------------------------------------------------------------------------
# Tuning.
# ---------------------------------------------------------------------------

# Forward-simulation horizon in steps (6 days). Bounded compute: the forecast
# is O(horizon + row qty) per SELL row, a few thousand price evals per step.
FORECAST_HORIZON = 144
# Active window: the sale window's own range; avoids the calibrated opening /
# early build and the terminal liquidation step.
ACTIVE_START = 288
ACTIVE_END = 717
# Defer only when the forecasted peak beats now by more than this fraction.
DEFER_MARGIN = 0.02
# Cash-guard lookahead in steps (2 days of tape purchases).
CASH_LOOKAHEAD = 48
# Rival-flow EMA weight for each new daily-ish sample (slow: noisy deltas).
RIVAL_EMA = 0.9


def _shape(func, x, span):
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "hinge":
        if not span or span <= 0:
            return x
        u = x / span
        return u + 8.0 * max(0.0, u - 1.0) ** 2
    return x


def market_price(item, inventory):
    """Pinned kaggriculture price for ``item`` at market ``inventory``.

    Exact port of the reference engine's market_price (PRICE_FLOOR = 1).
    """
    base, span, below_f, below_t, above_f, above_t = _MARKET_PARAMS[item]
    if inventory < _I0:
        amp = below_t * base / _shape(below_f, span, span)
        price = base + amp * _shape(below_f, _I0 - inventory, span)
    else:
        amp = above_t * base / _shape(above_f, span, span)
        price = base - amp * _shape(above_f, inventory - _I0, span)
    return max(_PRICE_FLOOR, int(round(price)))


def town_consumption(item, step_a, step_b, shops):
    """Deterministic town consumption of ``item`` over steps (step_a, step_b].

    Shops consume every 4 steps (x2 for single-product shops); the town
    center consumes every 24 steps. Engine _town_consume, applied after the
    players' trades within each step.
    """
    total = 0
    for s in range(int(step_a) + 1, int(step_b) + 1):
        if s % 4 == 0:
            for shop in shops or ():
                products = _SHOPS.get(shop)
                if products and item in products:
                    total += 2 if len(products) == 1 else 1
        if s % 24 == 0 and item in _TOWN_CENTER_PRODUCTS:
            total += 1
    return total


# ---------------------------------------------------------------------------
# Rival-flow estimator (module state; reset() clears it for tests / episodes).
# ---------------------------------------------------------------------------

def _fresh_flow():
    return {"step": None, "inv": {}, "rate": {}, "our_net": {}}


_FLOW = _fresh_flow()


def reset():
    """Clear telemetry and the rival-flow estimator state."""
    _FLOW.clear()
    _FLOW.update(_fresh_flow())
    REPORT.clear()
    REPORT.update(_fresh_report())


def _fresh_report():
    return {"steps_active": 0, "rows_kept": 0, "rows_deferred": 0,
            "rows_dropped": 0, "units_deferred": 0, "cash_guarded": 0}


REPORT = _fresh_report()


def get_report():
    """Return a copy of the module-level telemetry counters."""
    return dict(REPORT)


def _note_episode(step):
    """Reset flow state on episode boundaries (step counter restarted)."""
    if _FLOW["step"] is not None and int(step) <= int(_FLOW["step"]):
        _FLOW.clear()
        _FLOW.update(_fresh_flow())


def update_rival_flow(step, inventory, shops):
    """Fold one observation into the rival-flow EMA; return per-item rates.

    Rival sales over (last_step, step] = inventory delta - our net outflow
    + town consumption, clamped >= 0 and smoothed. Pure bookkeeping: never
    raises, returns {} when there is no previous snapshot.
    """
    try:
        step = int(step)
        _note_episode(step)
        prev_step = _FLOW["step"]
        prev_inv = _FLOW["inv"]
        rates = dict(_FLOW["rate"])
        if prev_step is not None and step > prev_step:
            dt = step - prev_step
            for item in PRODUCTS:
                now = int((inventory or {}).get(item, _I0))
                before = int(prev_inv.get(item, now))
                town = town_consumption(item, prev_step, step, shops)
                ours = float(_FLOW["our_net"].get(item, 0.0))
                sample = max(0.0, (now - before - ours + town) / dt)
                old = rates.get(item)
                rates[item] = sample if old is None else RIVAL_EMA * old + (1.0 - RIVAL_EMA) * sample
            _FLOW["rate"] = rates
        _FLOW["step"] = step
        _FLOW["inv"] = {item: int((inventory or {}).get(item, _I0)) for item in PRODUCTS}
        _FLOW["our_net"] = {}
        return dict(rates)
    except Exception:
        return dict(_FLOW.get("rate", {}))


def record_our_sales(market, inventory=None):
    """Record our SELL/BUY_PRODUCT net outflow for the rival-flow delta.

    Called with the final market rows we emit each step. When ``inventory``
    (the pre-trade market inventory snapshot) is given, SELL quantities are
    scaled to effective units: sales at the $1 floor do not increase market
    supply (engine _commit_unit), so they must not be subtracted from the
    rival-flow delta. Never raises.
    """
    try:
        net = _FLOW["our_net"]
        for order in market or []:
            if not isinstance(order, (list, tuple)) or len(order) < 2:
                continue
            op, item = order[0], order[1]
            qty = 0
            if len(order) >= 3:
                try:
                    qty = max(0, int(order[2]))
                except (TypeError, ValueError):
                    qty = 0
            if op == "SELL" and item in PRODUCTS:
                if inventory is not None:
                    try:
                        inv0 = int((inventory or {}).get(item, _I0))
                    except (TypeError, ValueError):
                        inv0 = _I0
                    qty = sum(1 for p in _unit_prices(item, inv0, qty)
                              if p > _PRICE_FLOOR)
                net[item] = net.get(item, 0.0) + qty
            elif op == "BUY_PRODUCT" and item in ("WHEAT", "FERTILIZER"):
                net[item] = net.get(item, 0.0) - qty
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Forecast + deferral decision (pure functions).
# ---------------------------------------------------------------------------

def forecast_peak(item, inv_now, step, horizon, shops, rival_rate):
    """Return (peak_step_offset, peak_inventory) for ``item``.

    Simulates market inventory forward: each step the town consumes (after
    the quote) and rivals add ``rival_rate`` units. Our own future sales are
    not modeled (upper bound on future prices). Returns the offset t in
    1..horizon with the highest quoted price and the inventory there.
    """
    inv = float(inv_now)
    best_t, best_price, best_inv = 1, -1, inv
    for t in range(1, int(horizon) + 1):
        s = int(step) + t - 1
        # Price quoted at step s uses pre-trade inventory; then the town
        # consumes and rivals sell during step s, forming the next step's
        # pre-trade inventory. town_consumption models (a, b], so the step-s
        # flow is (s-1, s]; (s, s) would be empty and forecast zero town
        # demand.
        price = market_price(item, inv)
        if price > best_price:
            best_price, best_t, best_inv = price, t, inv
        inv = inv + float(rival_rate) - town_consumption(item, s - 1, s, shops)
    return best_t, best_inv


def _unit_prices(item, inv_start, qty):
    """Per-unit realized prices selling ``qty`` now: inventory rises per unit.

    Sales at the $1 floor do not increase market supply (engine _commit_unit).
    """
    prices = []
    inv = float(inv_start)
    for _ in range(max(0, int(qty))):
        price = market_price(item, inv)
        prices.append(price)
        if price > _PRICE_FLOOR:
            inv += 1.0
    return prices


def keep_quantity(item, qty, inv_now, step, horizon, shops, rival_rate,
                  margin=DEFER_MARGIN):
    """How many leading units of a SELL row to keep selling now.

    Compares each unit's now-price against its price at the forecasted peak
    (same unit index, per-unit supply impact on both paths). Keeps the
    longest prefix where now beats peak / (1 + margin); the rest defers.
    """
    qty = max(0, int(qty))
    if qty == 0:
        return 0
    _, peak_inv = forecast_peak(item, inv_now, step, horizon, shops, rival_rate)
    now_prices = _unit_prices(item, inv_now, qty)
    peak_prices = _unit_prices(item, peak_inv, qty)
    keep = 0
    for now_p, peak_p in zip(now_prices, peak_prices):
        if now_p >= peak_p / (1.0 + margin):
            keep += 1
        else:
            break
    return keep


def upcoming_purchase_cost(tape, step, prices):
    """Conservative cash cost of the tape's BUY_*/HIRE/BUY_LAND over 48 steps.

    ``tape`` is the 719-step route tape (or None). Returns 0.0 when the tape
    is unavailable; the caller then falls back to a static cash floor.
    """
    if not tape:
        return 0.0
    need = 0.0
    try:
        last = len(tape) - 1
        for s in range(int(step) + 1, min(last, int(step) + CASH_LOOKAHEAD) + 1):
            entry = tape[s] if 0 <= s <= last else None
            if not isinstance(entry, dict):
                continue
            for order in entry.get("market") or []:
                if not isinstance(order, (list, tuple)) or len(order) < 2:
                    continue
                op, item = order[0], order[1]
                try:
                    qty = max(0, int(order[2])) if len(order) >= 3 else 1
                except (TypeError, ValueError):
                    continue
                if op == "BUY_PRODUCT" and item in ("WHEAT", "FERTILIZER"):
                    ref = max(int((prices or {}).get(item, 0)), _BASE_PRICE.get(item, 0))
                    need += qty * ref * 1.5
                elif op == "BUY_SEED" and item in _SEED_COST:
                    need += qty * _SEED_COST[item]
                elif op == "BUY_ANIMAL" and item in _ANIMAL_COST:
                    need += qty * _ANIMAL_COST[item]
                elif op == "BUY_LAND":
                    need += 20000.0 * max(qty, 1)
                elif op == "HIRE":
                    need += 5000.0 * max(qty, 1)
    except Exception:
        return 0.0
    return need


# ---------------------------------------------------------------------------
# Action rewrite.
# ---------------------------------------------------------------------------

def apply_price_forecaster(observation, action, tape=None):
    """Defer SELL rows whose forecasted peak beats selling now; never raises.

    Returns the action unchanged outside steps ACTIVE_START..ACTIVE_END, when
    the flag is off (checked by the router), or on any malformed input. Only
    ever drops or shrinks leading SELL rows.
    """
    try:
        return _apply(observation, action, tape)
    except Exception:
        return action


def _apply(observation, action, tape):
    try:
        step = int(observation["step"])
    except Exception:
        return action
    if step < ACTIVE_START or step > ACTIVE_END:
        return action
    if not isinstance(action, dict):
        return action
    market = action.get("market")
    if not market:
        return action
    try:
        player = int(observation.get("player", 0))
        inventory = (observation.get("market") or {}).get("inventory") or {}
        prices = (observation.get("market") or {}).get("prices") or {}
        shops = (observation.get("town") or {}).get("unlocked_shops") or []
        cash = float((observation.get("farms") or [{}])[player].get("money", 0))
    except Exception:
        return action

    REPORT["steps_active"] += 1
    rates = update_rival_flow(step, inventory, shops)

    # Cash guard: cost of upcoming tape purchases minus cash on hand.
    need = upcoming_purchase_cost(tape, step, prices) - cash
    if tape is None:
        # No tape available: conservative static floor, defer nothing when
        # cash is thin.
        need = max(need, 3000.0 - cash)

    decisions = []  # (index, keep_qty, now_revenue_if_kept)
    kept_revenue = 0.0
    for index, order in enumerate(market):
        if (not isinstance(order, (list, tuple)) or len(order) < 3
                or order[0] != "SELL" or order[1] not in PRODUCTS):
            continue
        item = order[1]
        try:
            qty = max(0, int(order[2]))
        except (TypeError, ValueError):
            continue
        if qty == 0:
            continue
        inv_now = inventory.get(item, _I0)
        try:
            inv_now = int(inv_now)
        except (TypeError, ValueError):
            inv_now = _I0
        keep = keep_quantity(item, qty, inv_now, step, FORECAST_HORIZON,
                             shops, rates.get(item, 0.0))
        now_prices = _unit_prices(item, inv_now, keep)
        decisions.append((index, keep, float(sum(now_prices))))

    if not decisions:
        record_our_sales(market, inventory)
        return action

    # Second pass: un-defer rows (in order) until the cash need is covered.
    # Deferral never starves a planned purchase.
    new_market = [list(o) if isinstance(o, (list, tuple)) else o for o in market]
    changed = False
    for index, keep, keep_rev in decisions:
        item = new_market[index][1]
        qty = int(new_market[index][2])
        if keep < qty and kept_revenue < need:
            REPORT["cash_guarded"] += 1
            keep = qty
            keep_rev = float(sum(_unit_prices(item, int(inventory.get(item, _I0)), qty)))
        kept_revenue += keep_rev
        if keep == 0:
            REPORT["rows_dropped"] += 1
            REPORT["units_deferred"] += qty
            new_market[index] = None
            changed = True
        elif keep < qty:
            REPORT["rows_deferred"] += 1
            REPORT["units_deferred"] += qty - keep
            new_market[index][2] = keep
            changed = True
        else:
            REPORT["rows_kept"] += 1

    if not changed:
        record_our_sales(market, inventory)
        return action
    new_market = [o for o in new_market if o is not None]
    new_action = dict(action)
    new_action["market"] = new_market
    record_our_sales(new_market, inventory)
    return new_action
