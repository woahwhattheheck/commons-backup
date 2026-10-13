# SPDX-License-Identifier: Apache-2.0
"""Legal, deterministic S8 service fixture; NOT another TITAN policy.

The official initializer supplies all state. This agent buys its goose and feed,
builds and places on the NW shed-access tile, and harvests/drops/sells its output.
The optional disposal regime buys real WHEAT to fill the shed only after day six;
it sells WHEAT before the next harvest to preserve room for actual EGG delivery.
Use startingMoney=10000 for that constructed regime, explicitly in both arms.
"""
from __future__ import annotations


def parent_action(observation, configuration=None, *, disposal=False):
    cfg = configuration or {}
    if cfg.get("boardSize", 10) != 10 or cfg.get("turnsPerDay", 24) != 24:
        raise ValueError("This reachable fixture covers only the standard 10x10/24-hour board")
    day, hour = divmod(observation["step"], 24)
    farm = observation["farms"][observation["player"]]
    private = observation["private"]
    shed, inventory = private["shed"], private["inventories"][0]
    x, y = farm["farmer"]
    tile = farm["tiles"][y][x]
    command, market = ["PASS"], []
    # Persistent occupation prevents weed admission after construction. On the
    # initial empty square BUILD_COOP is legal and has no purchase cost.
    if not isinstance(tile, dict) or tile.get("kind") != "COOP":
        command = ["DIG"] if tile is not None else ["BUILD_COOP"]
    elif tile.get("animal") != "GOOSE":
        if inventory.get("GOOSE", 0):
            command = ["PLACE", "GOOSE"]
        elif shed.get("GOOSE", 0):
            command = ["PICKUP", "GOOSE", 1]
        else:
            market.append(["BUY_ANIMAL", "GOOSE", 1])
    else:
        if not tile["fed_today"]:
            if inventory.get("WHEAT", 0):
                command = ["FEED"]
            elif shed.get("WHEAT", 0):
                command = ["PICKUP", "WHEAT", 1]
        elif tile["yield_units"] and hour < 23:
            command = ["HARVEST"]
        elif inventory.get("EGG", 0) and hour < 23:
            command = ["DROP"]
        elif hour == 23 and tile["fertilizer_available"]:
            command = ["COLLECT_FERTILIZER"]

    if shed.get("EGG", 0):
        market.append(["SELL", "EGG", shed["EGG"]])
    excess = max(0, shed.get("FERTILIZER", 0) - 4)
    if excess:
        market.append(["SELL", "FERTILIZER", excess])
    if disposal and day >= 6 and command == ["HARVEST"] and shed.get("WHEAT", 0) >= 4:
        # This current market clears room before the next callback's DROP.
        market.append(["SELL", "WHEAT", 4])
    if disposal and day >= 6 and hour == 22:
        room = max(0, int(cfg.get("shedCapacity", 100)) - sum(shed.values()))
        if room:
            market.append(["BUY_PRODUCT", "WHEAT", room])
    elif not shed.get("WHEAT", 0) and not inventory.get("WHEAT", 0):
        market.append(["BUY_PRODUCT", "WHEAT", 1])
    if observation["step"] == int(cfg.get("episodeSteps", 720)) - 2:
        market = [["SELL", item, amount] for item, amount in shed.items() if amount > 0][:8]
    return {"farmer": command, "hands": [], "market": market}


def agent(observation, configuration=None):
    return parent_action(observation, configuration)


def disposal_agent(observation, configuration=None):
    return parent_action(observation, configuration, disposal=True)
