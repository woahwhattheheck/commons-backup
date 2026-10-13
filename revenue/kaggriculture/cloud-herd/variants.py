"""Reproducible purchasing-only variations of the frozen lean20 agent.

Derived from Euler and ASTRA-WORK / TokenJunkieLabs / Bryce Muhlnickel.
SPDX-License-Identifier: MIT OR CC-BY-4.0
"""
from __future__ import annotations

import ast
import hashlib

BASE_SHA256 = "d9487c031b50ede06a706acc8bcb40e0b5a681d9b5e92c1a1a96492b26c2dd62"
BASE_REF = "5d9fe82d288ee2933b38e8db8871602e688410af"
BASE_PATH = "revenue/kaggriculture/cloud-market/main.py"

# Declared before development, including the unchanged control.
VARIANTS = {
    "lean20": {},
    "pipeline": {"pipeline": True},
    "pipeline_single": {"pipeline": True, "batch_size": 1},
    "capital": {"pipeline": True, "capital_weight": 1.0},
    "balanced": {"pipeline": True, "capital_weight": 0.5},
    "future_town": {"pipeline": True, "town_expectation": 1.0},
    "future_capital": {"pipeline": True, "capital_weight": 0.5, "town_expectation": 1.0},
    "batch_marginal": {"pipeline": True, "marginal_batch": 3},
}

HELPER = '''
def choose_purchase(obs, configuration, remaining_days, horizon, production,
                    demand, future_prices, policy):
    """Value the next animal using public state and our own known inventory.

    Pending livestock is committed capital even before placement. Future shop
    demand, when enabled, is an expectation over the published uniform shop
    distribution, never a prediction from the hidden episode seed.
    """
    private, market = obs["private"], obs["market"]
    prices = market["prices"]
    projected = dict(production)
    if HERD.get("pipeline"):
        for animal, (_, _, _, interval, _, product) in ANIMALS.items():
            count = private["shed"].get(animal, 0) + sum(
                inv.get(animal, 0) for inv in private["inventories"])
            projected[product] += count * (1 + interval) / interval
    projected_demand = dict(demand)
    if HERD.get("town_expectation") and horizon > 0:
        turns = _cfg(configuration, "turnsPerDay", 24)
        unlock = max(1, _cfg(configuration, "townShopUnlockInterval", 3))
        consume = max(1, _cfg(configuration, "townShopSellInterval", 4))
        day = obs.get("day", 0) + obs.get("hour", 0) / turns
        available = max(0, 8 - len(obs.get("town", {}).get("unlocked_shops", [])))
        next_unlock = (math.floor(day / unlock) + 1) * unlock
        # Integrate the time each expected new shop is active over the horizon.
        mean_new_shops = sum(max(0.0, horizon - (next_unlock + i * unlock - day))
                             / horizon for i in range(available))
        for goods in SHOPS.values():
            weight = 2 if len(goods) == 1 else 1
            for product in goods:
                projected_demand[product] += (HERD["town_expectation"] * mean_new_shops
                    * turns / consume * weight / len(SHOPS))
    best, best_roi = None, 0.0
    for animal, (cost, kind, first, interval, held, product) in ANIMALS.items():
        if not policy["mixed"] and animal != "GOOSE":
            continue
        productive_days = max(0.0, remaining_days - first)
        rate = (1 + interval) / interval
        forecast = price(product, market["inventory"][product] +
            (projected[product] + rate * HERD.get("marginal_batch", 1)
             - projected_demand[product]) * horizon, market)
        daily = rate * (prices[product] * .2 + forecast * .8)
        fert = .4 * prices["FERTILIZER"] + .6 * future_prices["FERTILIZER"]
        feed = max(prices["WHEAT"], future_prices["WHEAT"])
        roi = productive_days * daily + remaining_days * (fert - feed - 9) - cost
        roi /= (cost / 300.0) ** HERD.get("capital_weight", 0.0)
        if roi > best_roi:
            best, best_roi = animal, roi
    return best

'''


def build(source, options):
    """Emit a complete stdlib-only agent; retain all unit scheduling verbatim."""
    if hashlib.sha256(source.encode()).hexdigest() != BASE_SHA256:
        raise ValueError("Expected the exact frozen lean20 source")
    if not options:
        return source
    start = source.index("    affordable_animal = None\n")
    end = source.index("\n    total_capacity = len(spots)", start)
    updated = (source[:start] +
        "    affordable_animal = choose_purchase(obs, configuration, remaining_days,\n"
        "        horizon, production, demand, future_prices, policy)\n" + source[end:])
    marker = "\ndef distance(a, b):"
    if updated.count(marker) != 1:
        raise ValueError("Expected one helper insertion location")
    updated = updated.replace(marker, "\nHERD = " + repr(options) + "\n" + HELPER + marker, 1)
    if "batch_size" in options:
        marker = "qty = min(3, 5-pending,"
        if updated.count(marker) != 1:
            raise ValueError("Expected one animal purchase batch")
        updated = updated.replace(marker, f"qty = min({options['batch_size']}, 5-pending,", 1)
    updated = ("# SORREL purchasing continuation; MIT OR CC-BY-4.0.\n"
               f"# Lean20 source: {BASE_REF}/{BASE_PATH}\n" + updated)
    ast.parse(updated)
    return updated
