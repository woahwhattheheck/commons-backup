# SPDX-License-Identifier: Apache-2.0
"""V3.1 H4 experiment: reconcile an undersized current STRAWBERRY sale.

This is a live-R04 candidate module, not a default policy change.  The parent E184
sale window intentionally refuses to advance an item when the current action already
contains a SELL for that item.  For STRAWBERRY only, this module can reuse that
existing row as the reservation sink: it moves already-planned future strawberry
sales into the current row, bounded by current projected shed stock, and records the
same per-due-step debt that E184 subtracts later.

No new market row is created.  No sale is invented: every added unit is backed by a
future tape SELL inside E184's normal horizon and by stock already projected in the
shed this turn.  The feature is default-off and is intended for paired official-gate
measurement before any runtime/default integration.
"""

from __future__ import annotations

import copy

import r04_full_router as base

KEY = "r04_strawberry_topup"
STRAWBERRY_TOPUP = False
ITEM = "STRAWBERRY"


def reconcile_strawberry(action, view, state, tape, step, enabled=False):
    """Top up one current STRAWBERRY SELL from future planned sells.

    Returns ``(action, added_quantity)``.  When disabled or ineligible, the exact
    input action object is returned unchanged.  Eligibility deliberately mirrors
    E184's conservative blockers: route/shop boundaries, current/future pickup,
    current/future same-item purchase, animal PLACE uncertainty, price floor and
    already-recorded sale-window debt.
    """
    if not enabled or step < base.ADVANCE_START or step >= base.LAST_STEP:
        return action, 0

    market = action.get("market") or []
    sell_rows = [i for i, order in enumerate(market)
                 if len(order) >= 3 and order[:2] == ["SELL", ITEM]]
    if len(sell_rows) != 1:
        return action, 0
    if any(len(order) > 1 and order[:2] == ["BUY_PRODUCT", ITEM] for order in market):
        return action, 0
    if int(view.prices.get(ITEM, 0)) < 2:
        return action, 0

    # Match E184's current/queued pickup blocker.  A planned consumer owns the stock.
    if any(len(command) > 1 and command[:2] == ["PICKUP", ITEM]
           for queue in state.queues.values() for command in queue):
        return action, 0
    commands = [action.get("farmer") or ["PASS"], *(action.get("hands") or [])]
    if any(len(command) > 1 and command[:2] == ["PICKUP", ITEM]
           for command in commands):
        return action, 0

    # E184 also fails closed when an animal PLACE can fall back into the shed because
    # projected_shed() intentionally does not model that fallback.
    if any(len(command) > 1 and command[0] == "PLACE" and command[1] in base.ANIMALS
           and view.inventory(actor).get(command[1], 0) > 0
           for actor, command in enumerate(commands)):
        return action, 0

    row_index = sell_rows[0]
    current_quantity = max(0, int(market[row_index][2]))
    stock = base.projected_shed(action, view)
    available = max(0, int(stock.get(ITEM, 0)) - current_quantity)
    if not available:
        return action, 0

    horizon = base.SALE_HORIZON if step >= 144 else 1
    end = min(base.LAST_STEP, step + horizon, (step // 72 + 1) * 72 - 1)
    if end <= step:
        return action, 0

    original_debts = getattr(state, "sale_window_debts", {})
    reservations = []
    remaining_stock = available
    for due_step in range(step + 1, end + 1):
        future = tape[due_step]
        work = [future.get("farmer") or ["PASS"], *(future.get("hands") or [])]
        if any(len(command) > 1 and command[:2] == ["PICKUP", ITEM]
               for command in work):
            break
        if any(len(order) > 1 and order[:2] == ["BUY_PRODUCT", ITEM]
               for order in future.get("market", [])):
            break
        planned = sum(max(0, int(order[2])) for order in future.get("market", [])
                      if len(order) >= 3 and order[:2] == ["SELL", ITEM])
        already_advanced = original_debts.get(due_step, {}).get(ITEM, 0)
        amount = min(remaining_stock, max(0, planned - already_advanced))
        if amount:
            reservations.append((due_step, amount))
            remaining_stock -= amount
        if not remaining_stock:
            break

    added = sum(amount for _, amount in reservations)
    if not added:
        return action, 0

    result = copy.deepcopy(action)
    result["market"][row_index][2] = current_quantity + added
    debts = {due: dict(items) for due, items in original_debts.items()}
    for due_step, amount in reservations:
        due = debts.setdefault(due_step, {})
        due[ITEM] = due.get(ITEM, 0) + amount
    state.sale_window_debts = debts
    return result, added


def h4_agent(observation, configuration=None):
    """R04 V3 seam with H4 inserted before ROW_ORDER and EVENING_FLUSH."""
    action = base.POLICY_AGENT(observation, configuration)
    if STRAWBERRY_TOPUP and base._POLICY is not None:
        player = int(observation["player"])
        state = base._POLICY.players.get(player)
        if state is not None:
            view = base.FarmView(observation)
            tape = base._POLICY.tapes[state.plan]
            action, _ = reconcile_strawberry(
                action, view, state, tape, int(observation["step"]), enabled=True)

    # Preserve the live V3.1 post-policy order exactly.
    if base.ROW_ORDER and not ((configuration or {}).get("marketParams") or {}):
        inventory = (observation.get("market") or {}).get("inventory") or {}
        market = [list(order) for order in action.get("market") or [] if order]
        ordered = base.order_sells(market, inventory)
        if ordered != market:
            action = dict(action)
            action["market"] = ordered
    if base.EVENING_FLUSH:
        action = base.evening_flush(observation, action)
    if (base.OPEN_ROUNDTRIP > 0 and int(observation["step"]) == 0
            and [list(order) for order in action.get("market") or []] == base.TAPE_OPENING):
        action = dict(action)
        action["market"] = [["BUY_PRODUCT", "WHEAT", 13],
                            ["BUY_PRODUCT", "WHEAT", base.OPEN_ROUNDTRIP],
                            ["SELL", "WHEAT", base.OPEN_ROUNDTRIP]]
    return action


def install(host=None, horizon=None, opening=None, row_order=None, evening_flush=None,
            sale_fertilizer=None, cattle_early=None, strawberry_topup=None):
    """Configure the parent R04 policy and return the H4 experimental agent."""
    global STRAWBERRY_TOPUP
    # Parent install owns all existing V3.1 parameters and their validation.
    base.install(host, horizon, opening, row_order, evening_flush,
                 sale_fertilizer, cattle_early)
    if strawberry_topup is not None:
        STRAWBERRY_TOPUP = bool(strawberry_topup)
    return h4_agent
