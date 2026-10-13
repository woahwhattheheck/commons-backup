# SPDX-License-Identifier: Apache-2.0
"""Legally reachable GOOSE fixture, not a TITAN policy or release controller.

Three geese are bought, carried, placed and fed from the official initial state.
An existing S8 adapter can inspect/transform this grower's actual returned action.
No world, cash, inventory, maturity, market parameter or seed is injected.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

SITES = ((4, 4), (3, 4), (4, 3))
# Day zero includes purchase -> pickup -> construction -> placement -> feeding.
SETUP = (
    ("PASS",), ("PICKUP", "GOOSE", 3), ("BUILD_COOP",), ("PLACE", "GOOSE"),
    ("WEST",), ("BUILD_COOP",), ("PLACE", "GOOSE"), ("NORTH",), ("EAST",),
    ("BUILD_COOP",), ("PLACE", "GOOSE"), ("SOUTH",), ("PICKUP", "WHEAT", 3),
    ("FEED",), ("WEST",), ("FEED",), ("NORTH",), ("EAST",), ("FEED",),
    ("SOUTH",), ("DROP",), ("PASS",), ("PASS",), ("COLLECT_FERTILIZER",),
)
DAILY = (
    ("PICKUP", "WHEAT", 3), ("FEED",), ("HARVEST",), ("WEST",),
    ("FEED",), ("HARVEST",), ("COLLECT_FERTILIZER",), ("NORTH",), ("EAST",),
    ("FEED",), ("HARVEST",), ("COLLECT_FERTILIZER",), ("SOUTH",), ("DROP",),
    ("PASS",), ("PASS",), ("PASS",), ("PASS",), ("PASS",), ("PASS",),
    ("PASS",), ("PASS",), ("PASS",), ("COLLECT_FERTILIZER",),
)


def _positions(tape: tuple) -> tuple:
    x, y = 4, 4
    positions = []
    for command in tape:
        positions.append((x, y))
        dx, dy = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0),
                  "WEST": (-1, 0)}.get(command[0], (0, 0))
        x, y = x + dx, y + dy
    return tuple(positions)


SETUP_POSITIONS, DAILY_POSITIONS = _positions(SETUP), _positions(DAILY)


def _nonnegative_integer(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"Expected nonnegative integer {name}")
    return value


def parent_action(observation: Mapping[str, Any], configuration: Mapping[str, Any], *, disposal: bool = False) -> dict:
    """Return a stateless legal test-grower action; reject incompatible setups.

    This is deliberately not a profitable-agent claim. It creates animal-service
    opportunities which the default TITAN tape often already consumes with CARE.
    """
    expected = {"boardSize": 10, "turnsPerDay": 24, "episodeSteps": 720,
                "shedCapacity": 100, "startingMoney": 3000}
    if any(type(configuration.get(k)) is not int or configuration[k] != v
           for k, v in expected.items()):
        raise ValueError("The reachable fixture requires the pinned standard configuration")
    step = _nonnegative_integer(observation.get("step"), "step")
    if step > 718:
        raise ValueError("No action exists beyond the official final executable turn")
    seat = observation.get("player")
    if type(seat) is not int or seat not in (0, 1):
        raise ValueError("Invalid player")
    day, hour = divmod(step, 24)
    if observation.get("day") != day or observation.get("hour") != hour:
        raise ValueError("Observation clock and step disagree")
    farm = observation["farms"][seat]
    private = observation["private"]
    positions = SETUP_POSITIONS if day == 0 else DAILY_POSITIONS
    if tuple(farm["farmer"]) != positions[hour] or farm["hands"]:
        raise ValueError("Fixture route/actor drift: do not silently repair the world")
    if day:
        for x, y in SITES:
            tile = farm["tiles"][y][x]
            if not isinstance(tile, dict) or tile.get("animal") != "GOOSE":
                raise ValueError("A bought and placed fixture goose is missing")
    tape = SETUP if day == 0 else DAILY
    orders = []
    if step == 0:
        orders = [["BUY_ANIMAL", "GOOSE", 3], ["BUY_PRODUCT", "WHEAT", 3]]
    if hour == 22 and day < 29:
        # The engine, not this fixture, resolves affordable fills. No cash or
        # inventory injection: a full shed emerges only after successful buys.
        target = 100 - sum(private["shed"].values()) if disposal and day >= 1 else 3
        if target > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", target])
    if day and hour == 12 and disposal:
        # Sell before the next turn's DROP, so the future egg has real room.
        needed = max(0, sum(private["shed"].values()) + sum(private["inventories"][0].values()) - 100)
        if needed > private["shed"].get("WHEAT", 0):
            raise ValueError("Cannot release legal harvest admission space")
        if needed:
            orders.append(["SELL", "WHEAT", needed])
    if day == 29 and hour == 22:
        # Liquidate actual residual stock before callback718 ends the game.
        for item in ("WHEAT", "FERTILIZER", "EGG"):
            quantity = private["shed"].get(item, 0)
            if quantity:
                orders.append(["SELL", item, quantity])
    if day and hour == 13:
        # DROP executes before market. Explicit projected quantities, not a
        # claim that requested SELL size is itself realized revenue.
        shed, inventory = private["shed"], private["inventories"][0]
        if sum(shed.values()) + sum(inventory.values()) > configuration["shedCapacity"]:
            raise ValueError("Fixture storage capacity exhausted; cannot quote a full DROP")
        eggs = _nonnegative_integer(shed.get("EGG", 0), "shed eggs") + _nonnegative_integer(inventory.get("EGG", 0), "carried eggs")
        fertilizer = _nonnegative_integer(shed.get("FERTILIZER", 0), "shed fertilizer") + _nonnegative_integer(inventory.get("FERTILIZER", 0), "carried fertilizer")
        if eggs:
            orders.append(["SELL", "EGG", eggs])
        if fertilizer > 4:
            orders.append(["SELL", "FERTILIZER", fertilizer - 4])
    return {"farmer": list(tape[hour]), "hands": [], "market": orders}


def identity_control(observation: dict, action: dict, configuration: dict) -> dict:
    """An exact identity control, not a candidate policy."""
    return action


def care_positive_control(observation: dict, action: dict, configuration: dict) -> dict:
    """TEST ONLY: replace one available hour-21 PASS with free CARE.

    Preserves fertilizer collection. Its purpose is to prove that legal CARE can
    mature, be harvested and affect cash in this setup. It is NOT GOSLING's S8
    repair, not a proposed runtime key, and not evidence for COLLECT replacement.
    """
    day, hour = divmod(observation["step"], 24)
    if hour != 21 or not 2 <= day <= 27 or action["farmer"] != ["PASS"]:
        return action
    farm = observation["farms"][observation["player"]]
    x, y = farm["farmer"]
    tile = farm["tiles"][y][x]
    if not isinstance(tile, dict) or tile.get("animal") != "GOOSE":
        return action
    if not tile["fed_today"] or tile["cared_today"] or tile.get("pending_care_bonus", 0):
        return action
    if tile["yield_units"] + int(day >= tile["placed_day"] + 3) + 2 > 4:
        return action
    result = copy.deepcopy(action)
    result["farmer"] = ["CARE"]
    return result


def collect_ablation_control(observation: dict, action: dict, configuration: dict) -> dict:
    """TEST ONLY: remove a real collection to expose lost FERT revenue."""
    if observation["step"] // 24 < 2 or observation["step"] % 24 != 23:
        return action
    if action["farmer"] != ["COLLECT_FERTILIZER"]:
        return action
    result = copy.deepcopy(action)
    result["farmer"] = ["PASS"]
    return result
