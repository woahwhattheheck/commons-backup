# SPDX-License-Identifier: Apache-2.0
"""V4 F2: pre-buy WHEAT only when it unlocks shipped V217 starvation rescue.

V217 already owns the feeding decision. This helper does not route a worker or
feed an animal itself. At hour 15 it asks a narrower counterfactual question:
would V217 be unable to schedule a step-16 pickup/feed rescue with the current
shed, but able to schedule one if one or two WHEAT were already in the shed?

The market order is emitted one callback before V217's earliest active hour
because farm actions execute before market orders in a turn. The lane ships
off as ``r04_feed_prebuy``.
"""
from __future__ import annotations

import copy
import math

_PRODUCT_BY_ANIMAL = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
_MAX_PREBUY = 2
_CASH_RESERVE = 1000
_PRICE_PAD = 25
_MISSING = object()
_CASH_SPEND_OPS = frozenset({
    "HIRE", "BUY_LAND", "BUY_PRODUCT", "BUY_SEED", "BUY_ANIMAL",
})
_MARKET_NONSPEND_OPS = frozenset({"SELL"})

REPORT = {"probes": 0, "armed": 0, "units_requested": 0,
          "baseline_rescue": 0, "no_proxy_rescue": 0}


def _plain_nonnegative_int(value):
    return type(value) is int and value >= 0


def _finite_nonnegative_number(value):
    """Accept only the engine's exact int/float money surface, fail closed."""
    if type(value) not in (int, float) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _cfg(configuration, key, default=_MISSING):
    """Read a public config field from mapping or Kaggle Struct shape."""
    if configuration is None:
        return default
    try:
        if isinstance(configuration, dict):
            return configuration.get(key, default)
        return getattr(configuration, key, default)
    except Exception:
        return default


def _config_ok(configuration, r04):
    """Require the exact standard geometry/timing/capacity contract V217 assumes."""
    if configuration is None:
        return False
    expected = {
        "episodeSteps": 720,
        "boardSize": 10,
        "turnsPerDay": 24,
        "shedCapacity": int(r04.SHED_CAPACITY),
        "maxMarketOrdersPerTurn": int(r04.MAX_ORDERS),
    }
    for key, expected_value in expected.items():
        value = _cfg(configuration, key)
        if value is _MISSING or type(value) is not int or value != expected_value:
            return False
    market_params = _cfg(configuration, "marketParams", None)
    if market_params is None:
        return True
    return isinstance(market_params, dict) and not market_params


def _all_pass(observation, action):
    """Prove every currently owned actor has one literal PASS action row."""
    if not isinstance(action, dict) or not isinstance(observation, dict):
        return False
    player = observation.get("player")
    farms = observation.get("farms")
    if type(player) is not int or not isinstance(farms, list) or not 0 <= player < len(farms):
        return False
    farm = farms[player]
    if not isinstance(farm, dict) or not isinstance(farm.get("hands"), list):
        return False
    farmer = action.get("farmer")
    hands = action.get("hands")
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return False
    if farmer != ["PASS"] or len(hands) != len(farm["hands"]):
        return False
    return all(isinstance(command, list) and command == ["PASS"] for command in hands)


def _proxy_view(observation, quantity, r04):
    proxy = copy.deepcopy(observation)
    private = proxy.get("private")
    if not isinstance(private, dict):
        return None
    shed = private.get("shed")
    if not isinstance(shed, dict):
        return None
    wheat = shed.get("WHEAT", 0)
    if not _plain_nonnegative_int(wheat):
        return None
    shed["WHEAT"] = wheat + quantity
    try:
        return r04.FarmView(proxy)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError):
        return None


def _next_v217_task(observation, action, quantity, r04):
    """Return V217's next-step task under an exact WHEAT shed increment."""
    step = observation.get("step")
    player = observation.get("player")
    if type(step) is not int or type(player) is not int:
        return None
    if step % 24 != 15 or step + 1 > r04.LAST_STEP:
        return None

    policy = getattr(r04, "_POLICY", None)
    players = getattr(policy, "players", None)
    tapes = getattr(policy, "tapes", None)
    if not isinstance(players, dict) or not isinstance(tapes, list):
        return None
    state = players.get(player)
    if state is None or getattr(state, "last_step", None) != step:
        return None
    if getattr(state, "queues", None) is None:
        return None
    if any(state.queues.values()) or getattr(state, "v217_task", None):
        return None

    st = vars(state)
    if st.get("v217_used", 0) >= 2:
        return None
    plan = st.get("plan")
    if type(plan) is not int or not 0 <= plan < len(tapes):
        return None
    tape = tapes[plan]
    next_step = step + 1
    if not isinstance(tape, list) or next_step >= len(tape):
        return None
    planned = tape[next_step]
    if not isinstance(planned, dict):
        return None
    next_action = {
        "farmer": list(planned.get("farmer") or ["PASS"]),
        "hands": copy.deepcopy(planned.get("hands") or []),
        "market": copy.deepcopy(planned.get("market") or []),
    }
    if next_action["farmer"] != ["PASS"]:
        return None

    pending = [cmd for queue in state.queues.values() for cmd in queue]
    if pending:
        return None

    if quantity:
        view = _proxy_view(observation, quantity, r04)
    else:
        try:
            view = r04.FarmView(observation)
        except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError):
            return None
    if view is None:
        return None
    return r04._v217_plan(view, st, next_step, next_action, pending)


def _remaining_day_cash_spend_free(observation, r04):
    """Prove F2 cannot steal cash from a later authored same-day purchase.

    F2's flat reserve is intentionally not a budget model for future tape work.
    Rather than estimate future costs, inspect the selected literal tape and
    refuse the pre-buy whenever any executable market row later this day can
    spend cash. Unknown/malformed future market rows also fail closed.
    """
    step = observation.get("step")
    player = observation.get("player")
    if type(step) is not int or type(player) is not int or step % 24 != 15:
        return False

    policy = getattr(r04, "_POLICY", None)
    players = getattr(policy, "players", None)
    tapes = getattr(policy, "tapes", None)
    if not isinstance(players, dict) or not isinstance(tapes, list):
        return False
    state = players.get(player)
    if state is None or getattr(state, "last_step", None) != step:
        return False
    plan = vars(state).get("plan")
    if type(plan) is not int or not 0 <= plan < len(tapes):
        return False
    tape = tapes[plan]
    if not isinstance(tape, list):
        return False

    max_orders = getattr(r04, "MAX_ORDERS", None)
    if type(max_orders) is not int or max_orders != 10:
        return False

    last_step = getattr(r04, "LAST_STEP", None)
    if type(last_step) is not int or last_step != 718 or not 0 <= step <= last_step:
        return False
    next_day = ((step // 24) + 1) * 24
    stop = min(next_day, last_step + 1)
    # Missing tape suffix is unknown evidence, not a shorter cash-free day.
    # The terminal partial day needs all actionable rows through 718 only.
    if stop <= step + 1 or len(tape) < stop:
        return False

    for future_step in range(step + 1, stop):
        planned = tape[future_step]
        if not isinstance(planned, dict):
            return False
        market = planned.get("market", [])
        if market is None:
            market = []
        if not isinstance(market, list):
            return False
        for row in market[:max_orders]:
            if not isinstance(row, list) or not row or not isinstance(row[0], str):
                return False
            op = row[0]
            if op in _CASH_SPEND_OPS:
                return False
            if op not in _MARKET_NONSPEND_OPS:
                return False
    return True


def _purchase_quantity(observation, action, configuration, r04):
    if not _config_ok(configuration, r04) or not _all_pass(observation, action):
        return None
    market = action.get("market")
    if not isinstance(market, list) or market:
        return None
    if not _remaining_day_cash_spend_free(observation, r04):
        return None

    private = observation.get("private")
    shed = private.get("shed") if isinstance(private, dict) else None
    if not isinstance(shed, dict):
        return None
    if any(not _plain_nonnegative_int(quantity) for quantity in shed.values()):
        return None
    used = sum(shed.values())
    if used >= r04.SHED_CAPACITY:
        return None

    baseline = _next_v217_task(observation, action, 0, r04)
    if baseline is not None:
        REPORT["baseline_rescue"] += 1
        return None

    task = None
    quantity = None
    for candidate in range(1, _MAX_PREBUY + 1):
        if used + candidate > r04.SHED_CAPACITY:
            break
        task = _next_v217_task(observation, action, candidate, r04)
        if task is not None:
            quantity = candidate
            break
    if task is None or quantity is None:
        REPORT["no_proxy_rescue"] += 1
        return None

    market_state = observation.get("market")
    prices = market_state.get("prices") if isinstance(market_state, dict) else None
    inventory = market_state.get("inventory") if isinstance(market_state, dict) else None
    farms = observation.get("farms")
    player = observation.get("player")
    if not isinstance(prices, dict) or not isinstance(inventory, dict) or not isinstance(farms, list):
        return None
    if type(player) is not int or not 0 <= player < len(farms):
        return None
    wheat_price = prices.get("WHEAT")
    if type(wheat_price) is not int or wheat_price <= 0:
        return None
    wheat_stock = inventory.get("WHEAT")
    if type(wheat_stock) is not int or wheat_stock < quantity:
        return None

    # The V217 planner normally returns an in-bounds board coordinate, but F2's
    # fail-closed contract must not let malformed planner/state data exploit
    # Python negative indexing or non-integer coordinates when valuing a buy.
    if not isinstance(task, dict):
        return None
    target = task.get("target")
    if (not isinstance(target, (list, tuple)) or len(target) != 2
            or type(target[0]) is not int or type(target[1]) is not int):
        return None
    x, y = target
    farm = farms[player]
    tiles = farm.get("tiles") if isinstance(farm, dict) else None
    if not isinstance(tiles, list) or not 0 <= y < len(tiles):
        return None
    row = tiles[y]
    if not isinstance(row, list) or not 0 <= x < len(row):
        return None
    tile = row[x]
    if not isinstance(tile, dict):
        return None
    product = _PRODUCT_BY_ANIMAL.get(tile.get("animal"))
    output_price = prices.get(product) if product else None
    if type(output_price) is not int:
        return None
    if output_price < wheat_price + 20 or output_price * 2 < wheat_price * 3:
        return None

    money = farm.get("money") if isinstance(farm, dict) else None
    if not _finite_nonnegative_number(money):
        return None
    conservative_cost = quantity * (wheat_price + _PRICE_PAD)
    if money < conservative_cost + _CASH_RESERVE:
        return None
    return quantity


def apply_feed_prebuy(observation, action, configuration=None, enabled=False):
    if not enabled:
        return action
    if not isinstance(observation, dict) or type(observation.get("step")) is not int:
        return action
    if observation["step"] % 24 != 15:
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
    out["market"] = [["BUY_PRODUCT", "WHEAT", quantity]]
    REPORT["armed"] += 1
    REPORT["units_requested"] += quantity
    return out
