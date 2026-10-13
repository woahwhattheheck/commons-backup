# SPDX-License-Identifier: Apache-2.0
"""V4 D4: repaired midgame STRAWBERRY sale timing carrier.

Ported from repaired V3.1 donor #12469.  The lane never invents liquidation:
it may only advance STRAWBERRY already present in projected shed stock and
already authored for a later SELL in the same day, beyond the incumbent E184
sale horizon but strictly before the next live EVENING_FLUSH callback.

The corresponding ``sale_window_debts`` entry is booked on the authored due
step so the future tape row is reduced by exactly the amount advanced.  H4 keeps
ownership of an existing current STRAWBERRY row.  Any malformed or ambiguous
state fails closed to the exact parent action.
"""
from __future__ import annotations

import copy

KEY = "r04_d4_strawberry_timing"
ITEM = "STRAWBERRY"
START_DAY = 12
END_DAY = 18
DEFAULT_MIN_PRICE = 180
STANDARD_CONFIG = {
    "boardSize": 10,
    "turnsPerDay": 24,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}
_MISSING = object()
REPORT = {
    "engaged": 0,
    "units_advanced": 0,
    "last_step": None,
    "last_price": None,
}


def _strict_nonnegative_int(value):
    return value if type(value) is int and value >= 0 else None


def _cfg(configuration, name):
    if configuration is None:
        return _MISSING
    try:
        if isinstance(configuration, dict):
            return configuration.get(name, _MISSING)
        return getattr(configuration, name, _MISSING)
    except Exception:
        return _MISSING


def _standard_configuration(configuration):
    for name, expected in STANDARD_CONFIG.items():
        actual = _cfg(configuration, name)
        if actual is _MISSING or type(actual) is not int or actual != expected:
            return False
    params = _cfg(configuration, "marketParams")
    return params is _MISSING or params is None or params == {}


def _valid_debt_map(base, debts):
    if not isinstance(debts, dict):
        return False
    for due_step, ledger in debts.items():
        if type(due_step) is not int or not (0 <= due_step <= base.LAST_STEP):
            return False
        if not isinstance(ledger, dict):
            return False
        for item, quantity in ledger.items():
            if item not in base.PRODUCTS or _strict_nonnegative_int(quantity) is None:
                return False
    return True


def _next_incumbent_flush(base, step):
    """Return the next same-day live flush callback that owns STRAWBERRY."""
    if not base.EVENING_FLUSH or ITEM not in base.FLUSH_ITEMS:
        return None
    day_start = (step // 24) * 24
    for hour in base.FLUSH_HOURS:
        flush_step = day_start + hour
        if flush_step >= step:
            return flush_step
    return None


def advance_midgame_strawberry(base, action, view, state, tape, step,
                                min_price=DEFAULT_MIN_PRICE):
    """Return ``(action, added_qty, reservations)`` for the repaired D4 seam."""
    if type(min_price) is not int or min_price < 2:
        return action, 0, ()
    if type(step) is not int or step < START_DAY * 24 or step >= (END_DAY + 1) * 24:
        return action, 0, ()
    if step >= base.LAST_STEP or not isinstance(action, dict):
        return action, 0, ()

    prices = getattr(view, "prices", None)
    if not isinstance(prices, dict):
        return action, 0, ()
    price = prices.get(ITEM)
    if type(price) is not int or price < min_price:
        return action, 0, ()

    market = action.get("market")
    farmer = action.get("farmer")
    hands = action.get("hands")
    if (not isinstance(market, list) or len(market) >= base.MAX_ORDERS
            or not isinstance(farmer, list) or not isinstance(hands, list)):
        return action, 0, ()

    # H4 owns any current STRAWBERRY row; D4 covers only the temporal gap.
    for order in market:
        if not isinstance(order, list) or not order:
            return action, 0, ()
        if len(order) > 1 and order[1] == ITEM and order[0] in ("SELL", "BUY_PRODUCT"):
            return action, 0, ()

    commands = [farmer, *hands]
    if any(not isinstance(command, list) or not command for command in commands):
        return action, 0, ()
    if any(len(command) > 1 and command[:2] == ["PICKUP", ITEM] for command in commands):
        return action, 0, ()

    queues = getattr(state, "queues", _MISSING)
    if not isinstance(queues, dict):
        return action, 0, ()
    for queue in queues.values():
        if not isinstance(queue, (list, tuple)) and not hasattr(queue, "__iter__"):
            return action, 0, ()
        if any(isinstance(command, list) and len(command) > 1
               and command[:2] == ["PICKUP", ITEM] for command in queue):
            return action, 0, ()

    # Match E184's animal-PLACE uncertainty guard.
    try:
        if any(len(command) > 1 and command[0] == "PLACE" and command[1] in base.ANIMALS
               and view.inventory(actor).get(command[1], 0) > 0
               for actor, command in enumerate(commands)):
            return action, 0, ()
        stock = base.projected_shed(action, view)
    except Exception:
        return action, 0, ()
    if not isinstance(stock, dict):
        return action, 0, ()
    available = _strict_nonnegative_int(stock.get(ITEM, 0))
    if not available:
        return action, 0, ()

    horizon = _strict_nonnegative_int(base.SALE_HORIZON)
    if horizon is None:
        return action, 0, ()
    start = step + horizon + 1
    end = min(base.LAST_STEP, (step // 24 + 1) * 24 - 1, (END_DAY + 1) * 24 - 1)

    next_flush = _next_incumbent_flush(base, step)
    if next_flush is not None:
        end = min(end, next_flush - 1)
    if start > end:
        return action, 0, ()

    original_debts = getattr(state, "sale_window_debts", _MISSING)
    if original_debts is _MISSING or not _valid_debt_map(base, original_debts):
        return action, 0, ()

    if not isinstance(tape, (list, tuple)) or len(tape) <= end:
        return action, 0, ()

    reservations = []
    remaining_stock = available
    for due_step in range(start, end + 1):
        future = tape[due_step]
        if not isinstance(future, dict):
            return action, 0, ()
        future_farmer = future.get("farmer") or ["PASS"]
        future_hands = future.get("hands") or []
        if not isinstance(future_farmer, list) or not isinstance(future_hands, list):
            return action, 0, ()
        work = [future_farmer, *future_hands]
        if any(not isinstance(command, list) or not command for command in work):
            return action, 0, ()
        if any(len(command) > 1 and command[:2] == ["PICKUP", ITEM] for command in work):
            break
        future_market = future.get("market") or []
        if not isinstance(future_market, list):
            return action, 0, ()
        if any(isinstance(order, list) and len(order) > 1
               and order[:2] == ["BUY_PRODUCT", ITEM] for order in future_market):
            break

        planned = 0
        for order in future_market:
            if not isinstance(order, list) or not order:
                return action, 0, ()
            if len(order) >= 2 and order[:2] == ["SELL", ITEM]:
                if len(order) < 3:
                    return action, 0, ()
                quantity = _strict_nonnegative_int(order[2])
                if quantity is None:
                    return action, 0, ()
                planned += quantity

        due_map = original_debts.get(due_step, {})
        already = due_map.get(ITEM, 0)
        remaining_due = max(0, planned - already)
        amount = min(remaining_stock, remaining_due)
        if amount:
            reservations.append((due_step, amount))
            remaining_stock -= amount
        if not remaining_stock:
            break

    added = sum(amount for _, amount in reservations)
    if not added:
        return action, 0, ()

    result = copy.deepcopy(action)
    result["market"].append(["SELL", ITEM, added])

    debts = {due: dict(items) for due, items in original_debts.items()}
    for due_step, amount in reservations:
        due = debts.setdefault(due_step, {})
        due[ITEM] = due.get(ITEM, 0) + amount
    state.sale_window_debts = debts
    return result, added, tuple(reservations)


def apply_d4(observation, action, configuration=None, enabled=False,
             min_price=DEFAULT_MIN_PRICE):
    """Apply D4 to the current live R04 policy state; exact-parent on ambiguity."""
    if not enabled:
        return action
    if type(min_price) is not int or min_price < 2 or not _standard_configuration(configuration):
        return action
    try:
        import r04_full_router as base
        if not isinstance(observation, dict) or not isinstance(action, dict):
            return action
        player = observation.get("player")
        step = observation.get("step")
        if type(player) is not int or player not in (0, 1) or type(step) is not int:
            return action
        policy = base._POLICY
        if policy is None:
            return action
        state = policy.players.get(player)
        if state is None or type(getattr(state, "plan", None)) is not int:
            return action
        plan = state.plan
        if plan < 0 or plan >= len(policy.tapes):
            return action
        view = base.FarmView(observation)
        parent = action
        out, added, reservations = advance_midgame_strawberry(
            base, parent, view, state, policy.tapes[plan], step, min_price=min_price)
        if added:
            REPORT["engaged"] += 1
            REPORT["units_advanced"] += added
            REPORT["last_step"] = step
            REPORT["last_price"] = view.prices.get(ITEM)
            state.d4_last = {
                "step": step,
                "price": view.prices.get(ITEM),
                "quantity": added,
                "reservations": reservations,
            }
        return out
    except Exception:
        return action