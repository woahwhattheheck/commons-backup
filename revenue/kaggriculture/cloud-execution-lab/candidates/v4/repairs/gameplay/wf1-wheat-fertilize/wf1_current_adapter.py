# SPDX-License-Identifier: Apache-2.0
"""Fail-closed current-V4 ABI guard for the exact WF1 wheat-fertilize donor.

The profitable donor policy remains byte-for-byte in ``r04_wheat_fert.py``.  This
module adds input-domain and selected-actor admission guards before calling it.  It is deliberately unwired and default-OFF.
"""
from __future__ import annotations

from typing import Any

import r04_wheat_fert as _donor

KEY = "r04_wheat_fertilize"
DEFAULT_ENABLED = False

_EXPECTED_CONFIG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}


def _cfg(configuration: Any, name: str):
    if isinstance(configuration, dict):
        return configuration.get(name, None)
    if configuration is None:
        return None
    return getattr(configuration, name, None)


def _standard_configuration(configuration: Any) -> bool:
    for name, expected in _EXPECTED_CONFIG.items():
        actual = _cfg(configuration, name)
        if type(actual) is not int or actual != expected:
            return False
    market_params = _cfg(configuration, "marketParams")
    return market_params is None or (isinstance(market_params, dict) and not market_params)


def _plain_int(value: Any) -> bool:
    return type(value) is int


def _command(row: Any) -> bool:
    return isinstance(row, list) and bool(row) and type(row[0]) is str


def _current_shape(observation: Any, action: Any) -> bool:
    if not isinstance(observation, dict) or not isinstance(action, dict):
        return False
    step = observation.get("step")
    player = observation.get("player")
    farms = observation.get("farms")
    private = observation.get("private")
    market_obs = observation.get("market")
    if not (_plain_int(step) and 0 <= step < 720):
        return False
    if type(player) is not int or player not in (0, 1):
        return False
    if not isinstance(farms, list) or len(farms) != 2:
        return False
    if not isinstance(private, dict) or not isinstance(market_obs, dict):
        return False
    farm = farms[player]
    if not isinstance(farm, dict):
        return False
    farmer = farm.get("farmer")
    hands = farm.get("hands")
    tiles = farm.get("tiles")
    inventories = private.get("inventories")
    shed = private.get("shed")
    if not isinstance(farmer, (list, tuple)) or len(farmer) != 2:
        return False
    if not isinstance(hands, list):
        return False
    if not isinstance(tiles, list) or len(tiles) != 10:
        return False
    if not isinstance(inventories, list) or len(inventories) != len(hands) + 1:
        return False
    if not isinstance(shed, dict):
        return False
    for row in tiles:
        if not isinstance(row, list) or len(row) != 10:
            return False
    for position in [farmer, *hands]:
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            return False
        x, y = position
        if not (_plain_int(x) and _plain_int(y) and 0 <= x < 10 and 0 <= y < 10):
            return False
    for inventory in inventories:
        if not isinstance(inventory, dict):
            return False
        for item, quantity in inventory.items():
            if type(item) is not str or not _plain_int(quantity) or quantity < 0:
                return False
    for item, quantity in shed.items():
        if type(item) is not str or not _plain_int(quantity) or quantity < 0:
            return False
    farmer_action = action.get("farmer")
    hand_actions = action.get("hands")
    market_actions = action.get("market")
    if not _command(farmer_action):
        return False
    if not isinstance(hand_actions, list) or len(hand_actions) != len(hands):
        return False
    if not all(_command(row) for row in hand_actions):
        return False
    if not isinstance(market_actions, list):
        return False
    # The donor scans all rows when spending stored wheat credit. Never let an
    # out-of-budget row consume that credit before it can reach an active sale.
    if len(market_actions) > _EXPECTED_CONFIG["maxMarketOrdersPerTurn"]:
        return False
    return True



def _selection_observation(observation: dict, action: dict) -> dict:
    """Do not replace WATER when selected own actors already fund tile coverage.

    The donor's ``claimed`` set covers only substitutions made by the donor,
    not FERTILIZE commands already selected by another controller. Mark only
    colliding WATER actors ineligible, before donor credit is recorded. Other
    actors, tiles, shed stock and the returned command rows remain untouched.
    No collision returns the original observation without allocating a copy.
    """
    farm = observation["farms"][observation["player"]]
    positions = [farm["farmer"], *farm["hands"]]
    commands = [action["farmer"], *action["hands"]]
    inventories = observation["private"]["inventories"]
    covered = {
        tuple(position)
        for position, command, inventory in zip(positions, commands, inventories)
        if command[0] == "FERTILIZE" and inventory.get("FERTILIZER", 0) > 0
    }
    blocked = [
        index
        for index, (position, command, inventory) in enumerate(
            zip(positions, commands, inventories))
        if (command[0] == "WATER" and tuple(position) in covered
            and inventory.get("FERTILIZER", 0) > 0)
    ]
    if not blocked:
        return observation
    # Shallow-copy only the admission surface. The exact donor reads these
    # structures but does not mutate observations; it copies modified actions.
    selected_inventories = list(inventories)
    for index in blocked:
        selected_inventories[index] = dict(inventories[index], FERTILIZER=0)
    selected_private = dict(observation["private"], inventories=selected_inventories)
    return dict(observation, private=selected_private)


def apply_wf1_current(observation: Any, action: Any, configuration: Any, *, enabled: bool = False):
    """Apply exact donor semantics only on the current canonical input domain."""
    if enabled is not True:
        return action
    if not _standard_configuration(configuration) or not _current_shape(observation, action):
        return action
    try:
        return _donor.apply_wheat_fertilize(
            _selection_observation(observation, action), action, enabled=True)
    except Exception:
        return action
