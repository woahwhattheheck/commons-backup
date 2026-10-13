#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Default-OFF B9 terminal fertilizer micro-stacker.

This experiment wraps an existing V3.1 agent. Under the explicit standard
720-step / 24-turn-day runtime with a strictly typed market execution cap, it
changes literal PASS worker commands at steps 716-717 when that represented
worker is already on a shed-adjacent animal tile with public
``fertilizer_available is True``. Missing, empty, malformed, or
cardinality-mismatched parent worker commands are never synthesized into PASS.

At step 718 the existing V3.1 liquidator remains authoritative; iff this wrapper
collected terminal fertilizer in the same episode, ``SELL FERTILIZER`` rows are
stable-partitioned behind the other rows *inside the exact executable market
prefix only*. The raw tail is left at its original indexes, so B9 cannot change
which parent market rows are executable under ``maxMarketOrdersPerTurn``.
"""
from __future__ import annotations

import copy

COLLECT_STEPS = frozenset((716, 717))
TERMINAL_STEP = 718
EPISODE_STEPS = 720
TURNS_PER_DAY = 24
ANIMALS = frozenset(("GOOSE", "COW", "SHEEP"))
_MISSING = object()


def _exact_int(value):
    return type(value) is int


def _configuration_value(configuration, key):
    if configuration is None:
        return _MISSING
    if isinstance(configuration, dict):
        return configuration[key] if key in configuration else _MISSING
    getter = getattr(configuration, "get", None)
    if callable(getter):
        try:
            return getter(key, _MISSING)
        except Exception:
            return _MISSING
    return getattr(configuration, key, _MISSING)


def _standard_terminal_timing(configuration):
    episode_steps = _configuration_value(configuration, "episodeSteps")
    turns_per_day = _configuration_value(configuration, "turnsPerDay")
    return (
        _exact_int(episode_steps)
        and episode_steps == EPISODE_STEPS
        and _exact_int(turns_per_day)
        and turns_per_day == TURNS_PER_DAY
    )


def _executable_market_cap(configuration):
    raw_cap = _configuration_value(configuration, "maxMarketOrdersPerTurn")
    if not _exact_int(raw_cap):
        return None
    return max(1, raw_cap)


def _valid_worker_position(position, board_size):
    return (
        type(position) is list
        and len(position) == 2
        and all(_exact_int(v) for v in position)
        and _exact_int(board_size)
        and board_size > 0
        and all(0 <= v < board_size for v in position)
    )


def _valid_selected_farm_envelope(farm):
    if not isinstance(farm, dict):
        return False
    try:
        tiles = farm["tiles"]
        farmer = farm["farmer"]
        hands = farm["hands"]
    except (KeyError, TypeError):
        return False
    if (not isinstance(tiles, list) or not tiles
            or any(not isinstance(row, list) for row in tiles)
            or any(len(row) != len(tiles) for row in tiles)
            or not isinstance(hands, list)):
        return False
    positions = [farmer, *hands]
    return all(_valid_worker_position(position, len(tiles)) for position in positions)


def _beside_shed(position, board_size):
    if not _valid_worker_position(position, board_size):
        return False
    center = board_size // 2
    return position[0] in (center - 1, center) and position[1] in (center - 1, center)


def _valid_parent_command(command):
    return isinstance(command, list) and bool(command) and isinstance(command[0], str)


def _collect_passes(observation, action):
    if type(action) is not dict:
        return action, False
    try:
        player = observation["player"]
        farms = observation["farms"]
        if not _exact_int(player) or not isinstance(farms, list) or not (0 <= player < len(farms)):
            return action, False
        farm = farms[player]
        if not _valid_selected_farm_envelope(farm):
            return action, False
        tiles, farmer, hands = farm["tiles"], farm["farmer"], farm["hands"]
        positions = [farmer, *hands]
        if "farmer" not in action or "hands" not in action:
            return action, False
        farmer_action = action["farmer"]
        action_hands = action["hands"]
        if not isinstance(action_hands, list) or len(action_hands) != len(hands):
            return action, False
        workers = [farmer_action, *action_hands]
        if len(workers) != len(positions) or any(not _valid_parent_command(command) for command in workers):
            return action, False
    except (KeyError, IndexError, TypeError):
        return action, False

    changed = False
    for index, (command, position) in enumerate(zip(workers, positions)):
        if command != ["PASS"] or not _beside_shed(position, len(tiles)):
            continue
        x, y = position
        tile = tiles[y][x]
        if (not isinstance(tile, dict) or tile.get("animal") not in ANIMALS
                or tile.get("fertilizer_available") is not True):
            continue
        workers[index] = ["COLLECT_FERTILIZER"]
        changed = True

    if not changed:
        return action, False
    result = copy.deepcopy(action)
    result["farmer"] = workers[0]
    result["hands"] = workers[1:]
    return result, True


def _trail_fertilizer_sales(action, executable_market_cap):
    if (type(action) is not dict or type(action.get("market")) is not list
            or not _exact_int(executable_market_cap) or executable_market_cap < 1):
        return action
    market = action["market"]
    prefix_end = min(len(market), executable_market_cap)
    prefix = market[:prefix_end]
    tail = market[prefix_end:]
    non_fert = []
    fert = []
    for order in prefix:
        if type(order) is list and len(order) >= 2 and order[0] == "SELL" and order[1] == "FERTILIZER":
            fert.append(order)
        else:
            non_fert.append(order)
    reordered_prefix = non_fert + fert
    if not fert or reordered_prefix == prefix:
        return action
    result = copy.deepcopy(action)
    result["market"] = copy.deepcopy(reordered_prefix + tail)
    return result


class TerminalFertilizerAgent:
    def __init__(self, parent):
        if not callable(parent):
            raise TypeError("parent must be callable")
        self.parent = parent
        self._state = {}

    def __call__(self, observation, configuration=None):
        action = self.parent(observation, configuration)
        executable_market_cap = _executable_market_cap(configuration)
        if not _standard_terminal_timing(configuration) or executable_market_cap is None:
            self._state.clear()
            return action
        try:
            step = observation["step"]
            player = observation["player"]
            farms = observation["farms"]
        except (KeyError, TypeError):
            self._state.clear()
            return action
        if (not _exact_int(step) or not 0 <= step < EPISODE_STEPS
                or not _exact_int(player) or not isinstance(farms, list)
                or not 0 <= player < len(farms)):
            self._state.clear()
            return action
        if not _valid_selected_farm_envelope(farms[player]):
            self._state.clear()
            return action

        state = self._state.get(player)
        if state is None or step <= state["last_step"]:
            state = self._state[player] = {"last_step": -1, "collected": False}
        state["last_step"] = step

        if step in COLLECT_STEPS:
            result, changed = _collect_passes(observation, action)
            if changed:
                state["collected"] = True
            return result
        if step == TERMINAL_STEP and state["collected"]:
            return _trail_fertilizer_sales(action, executable_market_cap)
        return action


def make_agent(parent):
    return TerminalFertilizerAgent(parent)
