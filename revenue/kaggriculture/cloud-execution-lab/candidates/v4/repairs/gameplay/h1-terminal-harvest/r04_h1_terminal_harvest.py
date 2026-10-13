# SPDX-License-Identifier: Apache-2.0
"""V4 H1: rescue mature annual yield at the first-decay WATER boundary.

The official engine applies unit actions before plant decay.  For annual crops,
``max_lifespan_step == step`` is the first decay tick: WATER can no longer add
annual yield, while HARVEST can still collect currently mature yield before the
decay subtracts one unit.  H1 deliberately owns only this exact equality in the
late-game window and only rewrites a literal WATER action.

Disabled, malformed, ambiguous, non-WATER, and non-matching paths return the
exact parent action object.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

TURNS_PER_DAY = 24
LATE_START = 672
LATE_END = 718

FIRST_YIELD_DAY = {
    "WHEAT": 2,
    "CARROT": 2,
    "TOMATO": 8,
    "STRAWBERRY": 10,
    "MELON": 10,
}
ANNUAL = {"WHEAT", "CARROT", "MELON"}

telemetry = Counter()


def _cfg(configuration: Any, name: str, default: Any):
    if configuration is None:
        return default
    if isinstance(configuration, dict):
        return configuration.get(name, default)
    return getattr(configuration, name, default)


def _standard_configuration(configuration: Any) -> bool:
    value = _cfg(configuration, "turnsPerDay", TURNS_PER_DAY)
    return type(value) is int and value == TURNS_PER_DAY


def _tile_for_actor(observation: Any, actor: int):
    try:
        player = observation["player"]
        if type(player) is not int:
            return None
        farm = observation["farms"][player]
        hands = farm.get("hands")
        if hands is None:
            hands = []
        if not isinstance(hands, list):
            return None
        positions = [farm["farmer"], *hands]
        if actor < 0 or actor >= len(positions):
            return None
        position = positions[actor]
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            return None
        x, y = position
        if type(x) is not int or type(y) is not int:
            return None
        tiles = farm["tiles"]
        if y < 0 or y >= len(tiles):
            return None
        row = tiles[y]
        if not isinstance(row, list) or x < 0 or x >= len(row):
            return None
        return row[x]
    except (KeyError, TypeError, IndexError):
        return None


def _first_decay_harvestable(step: int, tile: Any) -> bool:
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
        return False
    crop = tile.get("crop")
    if crop not in ANNUAL:
        return False
    planted = tile.get("planted_day")
    units = tile.get("yield_units")
    lifespan = tile.get("max_lifespan_step")
    if type(planted) is not int or type(units) is not int or type(lifespan) is not int:
        return False
    if planted < 0 or units <= 0 or lifespan != step:
        return False
    day = step // TURNS_PER_DAY
    return day - planted >= FIRST_YIELD_DAY[crop]


def apply_h1_terminal_harvest(action: Any, observation: Any, configuration: Any, *, enabled=False):
    """Return parent action or a copy with exact first-decay WATER rescues."""
    if not enabled:
        telemetry["disabled"] += 1
        return action
    if not _standard_configuration(configuration):
        telemetry["nonstandard_configuration"] += 1
        return action
    if not isinstance(action, dict) or not isinstance(observation, dict):
        telemetry["malformed_input"] += 1
        return action

    step = observation.get("step")
    if type(step) is not int or step < LATE_START or step > LATE_END:
        telemetry["outside_window"] += 1
        return action

    farmer = action.get("farmer")
    hands = action.get("hands")
    if not isinstance(farmer, list) or not isinstance(hands, list):
        telemetry["malformed_action"] += 1
        return action

    commands = [farmer, *hands]
    replacements = []
    for actor, command in enumerate(commands):
        if command != ["WATER"]:
            continue
        if _first_decay_harvestable(step, _tile_for_actor(observation, actor)):
            replacements.append(actor)
        else:
            telemetry["water_not_rescuable"] += 1

    if not replacements:
        return action

    result = copy.deepcopy(action)
    for actor in replacements:
        if actor == 0:
            result["farmer"] = ["HARVEST"]
        else:
            result["hands"][actor - 1] = ["HARVEST"]
    telemetry["activations"] += len(replacements)
    return result


def install(parent, *, enabled=False):
    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return apply_h1_terminal_harvest(action, observation, configuration, enabled=enabled)

    agent.telemetry = telemetry
    return agent
