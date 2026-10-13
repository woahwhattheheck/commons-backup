# SPDX-License-Identifier: Apache-2.0
"""V4 S4 revival: route-12 just-in-time WHEAT seed reserve.

The original V4 S4 raw-volume census was a NO-BUILD: V3.1 already buys at
least as many seeds as top opponents.  A later exact-live replay census found a
much narrower residual: on the YARN_STORE -> YARN_STORE route (plan 12), the
authored tape can issue atomic WHEAT PLANT bursts with zero seeds.  The engine
counts every raw same-crop PLANT request before checking tile legality, so an
underfunded burst is cancelled as a group.

This helper does not change the tape, workers, land, crop mix, or shop policy.
At two measured prebuy callbacks it appends only the minimum fixed-cost WHEAT
seed order required by the *literal current plan-12 tape window*, and only when
current WHEAT seed stock is exactly zero and the existing market prefix proves
conservative funding.  The lane is source-only until the shared V4 plumbing
front clears and must ship OFF when wired.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

_ROUTE = ("YARN_STORE", "YARN_STORE")
_PLAN = 12
_SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50,
              "STRAWBERRY": 100, "MELON": 80}
_PRODUCTS = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
             "EGG", "MILK", "WOOL", "FERTILIZER"}

# These are not generic volume targets.  They are the exact high-signal windows
# exposed by the hosted route-12 starvation census.  The helper re-verifies the
# literal tape's raw PLANT counts at runtime, so tape drift fails closed.
_WINDOWS = {
    212: {213: 1},
    256: {257: 1, 261: 1, 262: 3},
}

REPORT = {"probes": 0, "armed": 0, "units_requested": 0,
          "tape_mismatch": 0, "funding_declines": 0}


def _plain_nonnegative_int(value):
    return type(value) is int and value >= 0


def _config_get(configuration, key, default):
    if isinstance(configuration, Mapping):
        return configuration.get(key, default)
    return getattr(configuration, key, default)


def _standard_config(configuration, r04):
    if configuration is None:
        return True
    expected = {
        "boardSize": 10,
        "turnsPerDay": 24,
        "shedCapacity": int(r04.SHED_CAPACITY),
        "maxMarketOrdersPerTurn": int(r04.MAX_ORDERS),
    }
    for key, default in expected.items():
        value = _config_get(configuration, key, default)
        if type(value) is not int or value != default:
            return False
    params = _config_get(configuration, "marketParams", None)
    if params is None:
        return True
    return isinstance(params, Mapping) and not params


def _route12_state(observation, r04):
    if not isinstance(observation, dict):
        return None
    step = observation.get("step")
    player = observation.get("player")
    if type(step) is not int or type(player) is not int:
        return None
    town = observation.get("town")
    shops = town.get("unlocked_shops") if isinstance(town, dict) else None
    if not isinstance(shops, list) or tuple(shops[:2]) != _ROUTE:
        return None

    policy = getattr(r04, "_POLICY", None)
    players = getattr(policy, "players", None)
    tapes = getattr(policy, "tapes", None)
    if not isinstance(players, dict) or not isinstance(tapes, list) or len(tapes) <= _PLAN:
        return None
    state = players.get(player)
    if state is None or getattr(state, "last_step", None) != step:
        return None
    if getattr(state, "plan", None) != _PLAN:
        return None
    tape = tapes[_PLAN]
    if not isinstance(tape, list) or len(tape) <= step:
        return None
    return tape


def _raw_plant_demand(planned, crop):
    if not isinstance(planned, dict):
        return None
    farmer = planned.get("farmer")
    hands = planned.get("hands")
    market = planned.get("market")
    if not isinstance(farmer, list) or not isinstance(hands, list) or not isinstance(market, list):
        return None
    commands = [farmer, *hands]
    demand = 0
    for command in commands:
        if not isinstance(command, list) or not command:
            return None
        if len(command) >= 2 and command[0] == "PLANT" and command[1] == crop:
            demand += 1
    return demand


def _literal_wheat_window(step, tape):
    expected = _WINDOWS.get(step)
    if expected is None:
        return None
    last = max(expected)
    if last >= len(tape):
        return None
    total = 0
    for future_step in range(step + 1, last + 1):
        planned = tape[future_step]
        demand = _raw_plant_demand(planned, "WHEAT")
        if demand is None or demand != expected.get(future_step, 0):
            return None
        # No authored WHEAT seed refill may already own this window.
        for order in planned["market"]:
            if (isinstance(order, list) and len(order) >= 3
                    and order[:2] == ["BUY_SEED", "WHEAT"]
                    and type(order[2]) is int and order[2] > 0):
                return None
        total += demand
    return total if total > 0 else None


def _workers_do_not_touch_shed(action):
    farmer = action.get("farmer")
    hands = action.get("hands")
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return False
    for command in [farmer, *hands]:
        if not isinstance(command, list) or not command:
            return False
        if command[0] in ("PICKUP", "DROP", "PLACE"):
            return False
    return True


def _standard_fertilizer_price(inventory):
    # MARKET_PARAMS[FERTILIZER] is linear on both sides: base=100, I0=10000,
    # target=0.40 over T=200 => $0.20 per inventory unit, floored at $1.
    return max(1, int(round(100 + 0.2 * (10000 - inventory))))


def _first_row_fertilizer_receipt_floor(observation, sold_units):
    if sold_units <= 0:
        return 0
    market = observation.get("market")
    inventory = market.get("inventory") if isinstance(market, dict) else None
    prices = market.get("prices") if isinstance(market, dict) else None
    if not isinstance(inventory, dict) or not isinstance(prices, dict):
        return None
    inv = inventory.get("FERTILIZER")
    price = prices.get("FERTILIZER")
    if type(inv) is not int or type(price) is not int:
        return None
    if price != _standard_fertilizer_price(inv):
        return None
    # At row 0, before our j-th unit quote, the rival can have committed at
    # most j FERTILIZER sells alongside our j previous sells.  Buying only
    # lowers inventory and raises our quote, so inv + 2*j is the worst case.
    return sum(_standard_fertilizer_price(inv + 2 * j) for j in range(sold_units))


def _cash_floor_after_parent_market(observation, action, r04):
    if not _workers_do_not_touch_shed(action):
        return None
    player = observation.get("player")
    farms = observation.get("farms")
    private = observation.get("private")
    if (type(player) is not int or not isinstance(farms, list)
            or not 0 <= player < len(farms) or not isinstance(private, dict)):
        return None
    farm = farms[player]
    money = farm.get("money") if isinstance(farm, dict) else None
    if type(money) not in (int, float) or isinstance(money, bool) or not math.isfinite(money) or money < 0:
        return None
    shed = private.get("shed")
    if not isinstance(shed, dict) or any(not _plain_nonnegative_int(q) for q in shed.values()):
        return None
    remaining = dict(shed)

    market = action.get("market")
    if not isinstance(market, list) or len(market) >= int(r04.MAX_ORDERS):
        return None
    cash = float(money)
    for index, order in enumerate(market):
        # C5 deliberately leaves an exact empty-list tombstone when relocating
        # one executable WHEAT SELL. The market interpreter treats that row as
        # inert, so the final-action S4 funding proof may safely skip it.
        if isinstance(order, list) and not order:
            continue
        if not isinstance(order, list) or type(order[0]) is not str:
            return None
        op = order[0]
        if op == "SELL":
            if (len(order) < 3 or order[1] not in _PRODUCTS
                    or type(order[2]) is not int or order[2] <= 0):
                return None
            item, requested = order[1], order[2]
            available = remaining.get(item, 0)
            if not _plain_nonnegative_int(available):
                return None
            sold = min(available, requested)
            remaining[item] = available - sold
            if index == 0 and item == "FERTILIZER":
                receipt = _first_row_fertilizer_receipt_floor(observation, sold)
                if receipt is None:
                    return None
                cash += receipt
            else:
                # Every valid product sale is floored at $1 per committed unit.
                cash += sold
        elif op == "BUY_SEED":
            if (len(order) < 3 or order[1] not in _SEED_COST
                    or type(order[2]) is not int or order[2] <= 0):
                return None
            cash -= _SEED_COST[order[1]] * order[2]
        else:
            # HIRE / BUY_LAND / BUY_PRODUCT / BUY_ANIMAL have cash- or
            # market-dependent execution.  This narrow lane refuses to infer
            # an end-of-prefix budget across them.
            return None
    return cash


def _purchase_quantity(observation, action, configuration, r04):
    if not _standard_config(configuration, r04) or not isinstance(action, dict):
        return None
    step = observation.get("step")
    if step not in _WINDOWS:
        return None
    tape = _route12_state(observation, r04)
    if tape is None:
        return None
    needed = _literal_wheat_window(step, tape)
    if needed is None:
        REPORT["tape_mismatch"] += 1
        return None

    private = observation.get("private")
    seeds = private.get("seeds") if isinstance(private, dict) else None
    if not isinstance(seeds, dict):
        return None
    wheat = seeds.get("WHEAT")
    if wheat != 0 or type(wheat) is not int:
        return None

    market = action.get("market")
    if not isinstance(market, list):
        return None
    if any(isinstance(order, list) and len(order) >= 2
           and order[:2] == ["BUY_SEED", "WHEAT"] for order in market):
        return None

    cash_floor = _cash_floor_after_parent_market(observation, action, r04)
    if cash_floor is None or cash_floor < needed * _SEED_COST["WHEAT"]:
        REPORT["funding_declines"] += 1
        return None
    return needed


def apply_route12_seed_reserve(observation, action, configuration=None, enabled=False):
    if not enabled:
        return action
    if not isinstance(observation, dict) or type(observation.get("step")) is not int:
        return action

    import r04_full_router as r04

    REPORT["probes"] += 1
    try:
        quantity = _purchase_quantity(observation, action, configuration, r04)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError):
        return action
    if quantity is None:
        return action

    out = dict(action)
    out["market"] = [list(order) if isinstance(order, list) else order
                     for order in action["market"]]
    out["market"].append(["BUY_SEED", "WHEAT", quantity])
    REPORT["armed"] += 1
    REPORT["units_requested"] += quantity
    return out