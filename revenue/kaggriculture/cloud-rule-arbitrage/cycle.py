# SPDX-License-Identifier: MIT
"""Exact, bounded market-cycle transforms over one already-selected action.

The transform intentionally implements only the rule-backed case that is safe
without predicting the other player's private orders: while a product is deep
inside the price-floor plateau, SELL then BUY_PRODUCT returns the same private
stock and cash but removes one unit of public market inventory.  This can move a
future sale closer to price recovery.  It is available only for WHEAT and
FERTILIZER because those are the products the official engine permits buying.

The simultaneous-BUY receipt effect is exposed as analysis, not activated by
the runtime policy.  A same-slot rival SELL reverses its sign, and current rival
orders are not visible when an action is chosen.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
TITAN = HERE.parent / "cloud-titan-composition"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mechanics = _load("t11_pinned_market_mechanics", TITAN / "vendor/sell/mechanics.py")
BUYABLE = ("WHEAT", "FERTILIZER")


def _cfg(config, name, default):
    if isinstance(config, dict):
        return config.get(name, default)
    return getattr(config, name, default)


def _project_unit_stage(observation, configuration, base_action):
    """Run the existing pinned unit helper on our public/private observation."""
    seat = int(observation["player"])
    farm = copy.deepcopy(observation["farms"][seat])
    private = copy.deepcopy(observation["private"])
    actions = [base_action.get("farmer", ["PASS"]), *base_action.get("hands", [])]
    board = int(_cfg(configuration, "boardSize", len(farm["tiles"])))
    turns = int(_cfg(configuration, "turnsPerDay", 24))
    capacity = int(_cfg(configuration, "shedCapacity", 100))
    day = int(observation.get("step", 0)) // turns
    for index, action in enumerate(actions):
        mechanics._apply_unit_action(farm, private, index, action, board, day, turns, capacity)
    return farm, private


def _available_after_inherited_orders(private, orders, item):
    """Conservative stock remaining before an appended cycle.

    Inherited BUY orders are deliberately not credited.  Existing and same-turn
    deposited stock is credited, then every inherited SELL request consumes it.
    This prevents an appended SELL from firing merely because a preceding BUY
    was requested but could fail for cash or capacity.
    """
    available = max(0, int(private.get("shed", {}).get(item, 0)))
    for order in orders:
        if order and len(order) >= 3 and order[0] == "SELL" and order[1] == item:
            available = max(0, available - max(0, int(order[2])))
    return available


def floor_quote(item, inventory, params):
    return mechanics.market_price(item, int(inventory), params)


def simultaneous_cycle_delta(item, inventory, params, rival_operation):
    """One-unit BUY->SELL cash delta under a named same-slot rival operation.

    Both seats are quoted before either unit commits.  This helper is evidence
    math only; the runtime cannot observe the rival's current order.
    """
    inventory = int(inventory)
    paid = floor_quote(item, inventory - 1, params)
    if rival_operation == "BUY_PRODUCT":
        received = floor_quote(item, inventory - 2, params)
    elif rival_operation == "SELL":
        received = floor_quote(item, inventory, params)
    elif rival_operation in (None, "PASS"):
        received = floor_quote(item, inventory - 1, params)
    else:
        raise ValueError("rival_operation must be BUY_PRODUCT, SELL, PASS or None")
    return received - paid


class RuleCycleTransform:
    """Append conservative floor-recycling pairs without changing base slots."""

    def __init__(self):
        self.last = {"status": "not-called"}
        self.total_cycles = 0

    def transform(self, observation, configuration, base_action):
        action = copy.deepcopy(base_action)
        orders = action.setdefault("market", [])
        max_orders = max(1, int(_cfg(configuration, "maxMarketOrdersPerTurn", 10)))
        free_pairs = max(0, (max_orders - len(orders)) // 2)
        if free_pairs == 0:
            self.last = {"status": "no-slots", "cycles": 0}
            return action

        _, private = _project_unit_stage(observation, configuration, action)
        capacity = max(1, int(_cfg(configuration, "shedCapacity", 100)))
        # An unknown rival can alternate full-shed BUY/SELL orders.  At most one
        # full withdrawal fits per pair of its market slots.  Include one extra
        # unit for its order aligned with our SELL/BUY boundary.
        rival_withdrawal_bound = capacity * ((max_orders + 1) // 2) + 1
        params = observation["market"].get("params")
        chosen = None
        for item in BUYABLE:
            available = _available_after_inherited_orders(private, orders, item)
            if available <= 0:
                continue
            inherited_buys = sum(
                max(0, int(o[2])) for o in orders
                if o and len(o) >= 3 and o[0] == "BUY_PRODUCT" and o[1] == item
            )
            inventory = int(observation["market"]["inventory"][item])
            limit = min(free_pairs, available)
            cycles = 0
            for count in range(1, limit + 1):
                worst_inventory = inventory - inherited_buys - rival_withdrawal_bound - count
                if floor_quote(item, worst_inventory, params) != 1:
                    break
                cycles = count
            if cycles:
                chosen = (item, cycles, inventory, available, rival_withdrawal_bound)
                break

        if chosen is None:
            self.last = {"status": "no-deep-floor", "cycles": 0,
                         "rival_withdrawal_bound": rival_withdrawal_bound}
            return action

        item, cycles, inventory, available, bound = chosen
        for _ in range(cycles):
            # SELL first makes the pair executable from zero cash. At the
            # proven floor both commits are $1, stock and cash return unchanged,
            # and the BUY removes exactly one public market unit.
            orders.extend((["SELL", item, 1], ["BUY_PRODUCT", item, 1]))
        self.total_cycles += cycles
        self.last = {"status": "applied", "item": item, "cycles": cycles,
                     "start_inventory": inventory, "available": available,
                     "rival_withdrawal_bound": bound}
        return action
