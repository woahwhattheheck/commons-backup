"""Additive market-making layer for Kaggriculture farm policies.

This module never modifies a base policy. It calls the base agent, keeps its
farmer/hands/market decisions exactly as issued, and only fills the market
order slots the base policy left unused (the engine takes `market[:10]`, and
each order carries its own unit count, so unused slots are free capacity).

Economics are derived from the official engine's public constants and price
function (kaggle_environments/envs/kaggriculture, Apache-2.0), not from any
competitor implementation:

  price(inv) = base +/- amp * f(|inv - I0|),  amp = target * base / f(T)

The town removes a known number of units from market inventory on a fixed
schedule visible in the observation (`town.unlocked_shops`). Buying N units on
turn t and selling the same N back on turn t+1 therefore sells into a strictly
scarcer market whenever that drain is positive.
"""

from __future__ import annotations

import math

PRICE_FLOOR = 1
MARKET_I0 = 10000

# Official MARKET_PARAMS (kaggriculture.py).
MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "I0": MARKET_I0, "T": 400, "below_func": "sqrt",   "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":     {"base":  35, "I0": MARKET_I0, "T": 450, "below_func": "hinge",  "below_target": 1.00, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":     {"base":  60, "I0": MARKET_I0, "T": 200, "below_func": "hinge",  "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "I0": MARKET_I0, "T": 100, "below_func": "sqrt",   "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "I0": MARKET_I0, "T": 300, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":        {"base":  50, "I0": MARKET_I0, "T": 332, "below_func": "hinge",  "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":       {"base": 160, "I0": MARKET_I0, "T": 122, "below_func": "sqrt",   "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "I0": MARKET_I0, "T": 105, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER": {"base": 100, "I0": MARKET_I0, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}

SHOPS = {
    "BAKERY":         ["EGG", "WHEAT"],
    "PIZZA_SHOP":     ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT":    ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE":     ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE":       ["CARROT"],
    "SMOOTHIE_SHOP":  ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}

# BUY_PRODUCT is only offered for these two.
TRADABLE = ("WHEAT", "FERTILIZER")


def _shape(name, x, T):
    x = max(0.0, float(x))
    if name == "linear":
        return x
    if name == "sq":
        return x * x
    if name == "sqrt":
        return math.sqrt(x)
    if name == "log":
        return math.log(1.0 + x)
    if name == "log10":
        return math.log10(1.0 + x)
    if name == "hinge":
        u = x / float(T) if T else 0.0
        return u + 8.0 * max(0.0, u - 1.0) ** 2
    return x


def market_price(item, inventory, params=None):
    """Exact official quote for one unit at the given market inventory."""
    p = (params or MARKET_PARAMS)[item]
    base, I0, T = p["base"], p["I0"], p["T"]
    if inventory < I0:
        f = p["below_func"]
        amp = p["below_target"] * base / _shape(f, T, T)
        price = base + amp * _shape(f, I0 - inventory, T)
    else:
        f = p["above_func"]
        amp = p["above_target"] * base / _shape(f, T, T)
        price = base - amp * _shape(f, inventory - I0, T)
    return max(PRICE_FLOOR, int(round(price)))


def execute_buy(item, inventory, quantity):
    """Per-unit BUY_PRODUCT walk; each unit removes one from market supply."""
    cost = 0
    inv = int(inventory)
    for _ in range(max(0, int(quantity))):
        cost += market_price(item, inv - 1)
        inv -= 1
    return cost, inv


def execute_sell(item, inventory, quantity):
    """Per-unit SELL walk. Units priced at the floor do not add supply."""
    revenue = 0
    inv = int(inventory)
    for _ in range(max(0, int(quantity))):
        q = market_price(item, inv)
        revenue += q
        if q > PRICE_FLOOR:
            inv += 1
    return revenue, inv


def town_drain(obs, configuration, item):
    """Units the town removes from supply after this turn's market clears."""
    step = int(_get(obs, "step", 0) or 0)
    town = _get(obs, "town", {}) or {}
    shops = list(_get(town, "unlocked_shops", []) or [])
    shop_interval = max(1, int(_get(configuration, "townShopSellInterval", 4) or 4))
    center_interval = max(1, int(_get(configuration, "townCenterSellInterval", 24) or 24))
    drain = 0
    if step % shop_interval == 0:
        for shop in shops:
            products = SHOPS.get(str(shop), ())
            if item in products:
                drain += 2 if len(products) == 1 else 1
    if item != "FERTILIZER" and step % center_interval == 0:
        drain += 1
    return drain


def best_round_trip(item, inventory, drain, max_quantity, min_profit=1.0):
    """Smallest quantity attaining the best positive one-tick round-trip PnL."""
    best = None
    for qty in range(1, max(0, int(max_quantity)) + 1):
        cost, after_buy = execute_buy(item, inventory, qty)
        revenue, _ = execute_sell(item, after_buy - max(0, int(drain)), qty)
        profit = revenue - cost
        if best is None or profit > best[1]:
            best = (qty, profit)
    if best is None or best[1] < float(min_profit):
        return None
    return {"quantity": best[0], "expected_profit": float(best[1])}


def _get(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
