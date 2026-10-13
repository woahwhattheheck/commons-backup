#!/usr/bin/env python3
"""Source-bound row-lockstep oracle for current TITAN market-pressure compaction."""
from __future__ import annotations

from collections import Counter
import itertools
import math

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
PRESSURE_BLOB = "7261674962d10fc8bc6af5ff73ff9212c40f61ad"
MAIN_BLOB = "4a8cf7bcda1f0fea231a144692cb84a779a9e73e"
RUNTIME_BLOB = "6d9720f4aa1e6b46e92ee5183897074d8e9ea5a0"
CONFIG_BLOB = "3a3bef83899d3010fad623b628d9e95d9978111b"

MARKET_I0 = 10000
PRICE_FLOOR = 1
HINGE_GAIN = 8.0
SALE_ONLY_GOODS = ("CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL")
DIRECT_BUY_GOODS = frozenset(("WHEAT", "FERTILIZER"))

MARKET_PARAMS = {
    "CARROT":     {"base": 35,  "I0": 10000, "T": 450, "below_func": "hinge", "below_target": 1.00, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":     {"base": 60,  "I0": 10000, "T": 200, "below_func": "hinge", "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "I0": 10000, "T": 100, "below_func": "sqrt",  "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "I0": 10000, "T": 300, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":        {"base": 50,  "I0": 10000, "T": 332, "below_func": "hinge", "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":       {"base": 160, "I0": 10000, "T": 122, "below_func": "sqrt",  "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "I0": 10000, "T": 105, "below_func": "log",   "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
}

REPRESENTATIVE_GOODS = ("CARROT", "STRAWBERRY", "WOOL")


def _shape(func: str, x: float, T: float) -> float:
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
        u = x / T
        return u + HINGE_GAIN * max(0.0, u - 1.0) ** 2
    raise ValueError(func)


def market_price(item: str, inventory: int, params=None) -> int:
    """Exact pinned-engine price formula for the seven sale-only goods."""
    p = (params or MARKET_PARAMS)[item]
    base, i0, T = p["base"], p["I0"], p["T"]
    if inventory < i0:
        func = p["below_func"]
        amp = p["below_target"] * base / _shape(func, T, T)
        value = base + amp * _shape(func, i0 - inventory, T)
    else:
        func = p["above_func"]
        amp = p["above_target"] * base / _shape(func, T, T)
        value = base - amp * _shape(func, inventory - i0, T)
    return max(PRICE_FLOOR, int(round(value)))


def compact_model(orders: list, end: int | None = None) -> list:
    """Structural part of live compact_sale_only_prefix, after its quote guards pass."""
    end = len(orders) if end is None else min(len(orders), end)
    prefix = orders[:end]
    positive, empty = [], []
    totals = Counter()
    for order in prefix:
        if order == []:
            empty.append(order)
            continue
        if not isinstance(order, list) or len(order) != 3 or order[0] != "SELL":
            return orders
        item, quantity = order[1:]
        if (not isinstance(item, str) or item not in MARKET_PARAMS
                or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0):
            return orders
        if quantity == 0:
            empty.append(order)
            continue
        if item not in SALE_ONLY_GOODS:
            return orders
        positive.append(order)
        totals[item] += quantity
    candidate = positive + empty
    if not positive or not empty or candidate == prefix or sum(totals.values()) > 100:
        return orders
    return candidate + orders[end:]


def _sell_state(order):
    if (isinstance(order, list) and len(order) == 3 and order[0] == "SELL"
            and order[1] in MARKET_PARAMS and isinstance(order[2], int)
            and not isinstance(order[2], bool) and order[2] > 0):
        return [order[1], order[2]]
    return None


def settle_sell_rows(own: list, rival: list, *,
                     own_stock: dict[str, int] | None = None,
                     rival_stock: dict[str, int] | None = None,
                     inventory: dict[str, int] | None = None) -> tuple[tuple[int, int], dict[str, int]]:
    """Pinned _process_market SELL subset: quote both current units, then commit both."""
    own_stock = dict(own_stock or {item: 3 for item in SALE_ONLY_GOODS})
    rival_stock = dict(rival_stock or {item: 3 for item in SALE_ONLY_GOODS})
    stocks = [own_stock, rival_stock]
    cash = [0, 0]
    market_inventory = {
        item: int((inventory or {}).get(item, MARKET_I0)) for item in SALE_ONLY_GOODS
    }
    for row in range(max(len(own), len(rival))):
        states = [
            _sell_state(own[row]) if row < len(own) else None,
            _sell_state(rival[row]) if row < len(rival) else None,
        ]
        while True:
            quoted = [None, None]
            for player_id, state in enumerate(states):
                if state is not None and state[1] > 0:
                    item = state[0]
                    quoted[player_id] = (item, market_price(item, market_inventory[item]))
            committed_any = False
            for player_id, quote in enumerate(quoted):
                if quote is None:
                    continue
                item, unit_price = quote
                if stocks[player_id].get(item, 0) <= 0:
                    states[player_id] = None
                    continue
                stocks[player_id][item] -= 1
                cash[player_id] += unit_price
                market_inventory[item] += 1
                states[player_id][1] -= 1
                committed_any = True
            if not committed_any:
                break
    return (cash[0], cash[1]), market_inventory


def margin_delta(parent: list, candidate: list, rival: list, *,
                 inventory_offset: int = 0) -> int:
    inv = {item: MARKET_I0 + inventory_offset for item in SALE_ONLY_GOODS}
    before, _ = settle_sell_rows(parent, rival, inventory=inv)
    after, _ = settle_sell_rows(candidate, rival, inventory=inv)
    return (after[0] - after[1]) - (before[0] - before[1])


def curve_contract() -> dict:
    checks = 0
    minimum_drop = None
    for item in SALE_ONLY_GOODS:
        start = MARKET_I0 - 100
        values = [market_price(item, inv) for inv in range(start, MARKET_I0 + 201)]
        checks += len(values) - 1
        assert all(a >= b for a, b in zip(values, values[1:])), item
        drop = values[0] - values[-1]
        minimum_drop = drop if minimum_drop is None else min(minimum_drop, drop)
    return {"adjacent_quote_checks": checks, "minimum_300_unit_drop": minimum_drop}


def exhaustive_three_slot() -> dict:
    """Enumerate changed own prefixes against asymmetric rival SELL/empty rows."""
    own_rows = [[]]
    rival_rows = [[]]
    for item in REPRESENTATIVE_GOODS:
        own_rows.extend((["SELL", item, 0], ["SELL", item, 1], ["SELL", item, 2]))
        rival_rows.extend((["SELL", item, 1], ["SELL", item, 2]))
    comparisons = 0
    changed_prefixes = 0
    minimum = None
    positives = 0
    for length in range(1, 4):
        for own_tuple in itertools.product(own_rows, repeat=length):
            own = [list(row) for row in own_tuple]
            candidate = compact_model(own)
            if candidate == own:
                continue
            changed_prefixes += 1
            for rival_tuple in itertools.product(rival_rows, repeat=length):
                rival = [list(row) for row in rival_tuple]
                delta = margin_delta(own, candidate, rival)
                comparisons += 1
                minimum = delta if minimum is None else min(minimum, delta)
                positives += int(delta > 0)
                if delta < 0:
                    return {
                        "comparisons": comparisons,
                        "changed_prefixes": changed_prefixes,
                        "minimum_margin_delta": delta,
                        "counterexample": {"own": own, "candidate": candidate, "rival": rival},
                    }
    return {
        "comparisons": comparisons,
        "changed_prefixes": changed_prefixes,
        "minimum_margin_delta": minimum,
        "positive_margin_cases": positives,
        "counterexample": None,
    }


def result_bundle() -> dict:
    exhaustive = exhaustive_three_slot()
    return {
        "schema": "titan-v4-slotlock-oracle/v1",
        "source_pins": {
            "engine": ENGINE_BLOB,
            "pressure_priority": PRESSURE_BLOB,
            "main": MAIN_BLOB,
            "titan_runtime": RUNTIME_BLOB,
            "TITAN-CONFIG": CONFIG_BLOB,
        },
        "contracts": {
            "sale_only_goods": list(SALE_ONLY_GOODS),
            "direct_buy_goods": sorted(DIRECT_BUY_GOODS),
            "direct_buy_overlap": sorted(set(SALE_ONLY_GOODS) & DIRECT_BUY_GOODS),
            "quote_curve": curve_contract(),
        },
        "exhaustive": exhaustive,
        "disposition": (
            "PROVED_CURRENT_COMPACTION_MARGIN_NONNEGATIVE_FOR_ENUMERATED_LOCKSTEP_SELL_ROWS"
            if exhaustive["counterexample"] is None and exhaustive["minimum_margin_delta"] >= 0
            else "COUNTEREXAMPLE"
        ),
        "scope": (
            "Current-turn sale-only raw-slot compaction theorem only; not full-game EV, "
            "not contiguous SELL-pressure ranking economics, and not a default-change claim."
        ),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(result_bundle(), indent=2, sort_keys=True))
