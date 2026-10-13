"""Wrap an unmodified farm policy with the additive market-making layer.

The base policy file is imported by path and never edited. Its farmer and
hands actions pass through verbatim; its own market orders are preserved and
kept first. Only the market-order slots it did not use are filled.
"""

from __future__ import annotations

import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import market_layer as ml

MAX_ORDERS = 10
SHED_CAP = 100
SHED_HEADROOM = 20        # never fill the shed the farm policy needs
CASH_RESERVE = 1500.0     # leave the farm policy its working capital
MIN_PROFIT = 1.0

_STATE = {"pending": {}, "episode": None}


def load_base(path):
    spec = importlib.util.spec_from_file_location("base_policy", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["base_policy"] = mod
    spec.loader.exec_module(mod)
    return mod.agent


def _reset_if_new_episode(obs):
    step = int(ml._get(obs, "step", 0) or 0)
    if step == 0:
        _STATE["pending"] = {}
    return step


def _shed_total(private):
    shed = ml._get(private, "shed", {}) or {}
    try:
        return sum(int(v) for v in shed.values())
    except Exception:
        return 0


def market_orders(obs, configuration, free_slots, base_orders):
    """Return additional market orders for the unused slots."""
    if free_slots <= 0:
        return []
    step = _reset_if_new_episode(obs)
    player = int(ml._get(obs, "player", 0) or 0)
    farms = ml._get(obs, "farms", []) or []
    if player >= len(farms):
        return []
    money = float(ml._get(farms[player], "money", 0) or 0)
    private = ml._get(obs, "private", {}) or {}
    shed = ml._get(private, "shed", {}) or {}
    market = ml._get(obs, "market", {}) or {}
    inventory = ml._get(market, "inventory", {}) or {}

    orders = []

    # 1. Liquidate the previous turn's round trip first.
    pending = _STATE.get("pending", {})
    for item, qty in list(pending.items()):
        have = int(shed.get(item, 0) or 0)
        sell_qty = min(int(qty), have)
        if sell_qty > 0 and len(orders) < free_slots:
            orders.append(["SELL", item, sell_qty])
        pending.pop(item, None)
    _STATE["pending"] = {}

    # 2. Open a new round trip where the town's known drain makes it pay.
    shed_room = SHED_CAP - SHED_HEADROOM - _shed_total(private)
    budget = money - CASH_RESERVE
    for item in ml.TRADABLE:
        if len(orders) >= free_slots or shed_room <= 0 or budget <= 0:
            break
        # Items the base policy is already trading this turn are left alone.
        if any(len(o) >= 2 and str(o[1]) == item for o in base_orders if isinstance(o, (list, tuple))):
            continue
        inv = int(inventory.get(item, ml.MARKET_I0) or ml.MARKET_I0)
        drain = ml.town_drain(obs, configuration, item)
        if drain <= 0:
            continue
        unit = ml.market_price(item, inv - 1)
        cap = min(shed_room, int(budget // max(1, unit)), 40)
        if cap < 1:
            continue
        plan = ml.best_round_trip(item, inv, drain, cap, MIN_PROFIT)
        if not plan:
            continue
        qty = int(plan["quantity"])
        cost, _ = ml.execute_buy(item, inv, qty)
        if cost > budget:
            continue
        orders.append(["BUY_PRODUCT", item, qty])
        _STATE["pending"][item] = qty
        budget -= cost
        shed_room -= qty
    return orders


def build(base_path):
    base_agent = load_base(base_path)

    def agent(observation, configuration=None):
        try:
            action = base_agent(observation, configuration)
        except TypeError:
            action = base_agent(observation)
        if not isinstance(action, dict):
            return action
        base_orders = action.get("market") or []
        if not isinstance(base_orders, list):
            base_orders = []
        try:
            extra = market_orders(observation, configuration,
                                  MAX_ORDERS - len(base_orders), base_orders)
        except Exception:
            extra = []          # never let the layer cost a game
        if extra:
            action = dict(action)
            action["market"] = list(base_orders) + extra
        return action

    return agent


_BASE = os.environ.get(
    "HYBRID_BASE",
    "/home/user/commons/revenue/kaggriculture/cloud-market/main.py",
)
agent = build(_BASE)
