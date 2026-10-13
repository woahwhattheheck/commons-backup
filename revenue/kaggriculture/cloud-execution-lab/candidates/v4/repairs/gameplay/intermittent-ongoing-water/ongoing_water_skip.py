# SPDX-License-Identifier: Apache-2.0
"""Conservative one-day WATER suppression for TITAN V4 ongoing crops.

Pinned engine theorem (kaggriculture.py blob 3c202c7e...): an established
ongoing plant with consecutive_unwatered == 0 survives one unwatered EOD and
still receives base scheduled production.  Fertilizer bonus requires
``was_watered``.  New plants start at streak 1, so planting-day WATER remains
mandatory.

Candidate-only transform.  Default-off at every integration seam.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

PINNED_ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
CROPS = {
    "TOMATO": {"first_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"first_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
}


def _cfg(configuration: Any, key: str) -> Any:
    if isinstance(configuration, dict):
        return configuration.get(key)
    return getattr(configuration, key, None)


def _position(value: Any, board_size: int):
    if (not isinstance(value, list) or len(value) != 2
            or any(type(v) is not int or not 0 <= v < board_size for v in value)):
        return None
    return tuple(value)


def _production_due(tile: dict, day: int, spec: dict) -> bool:
    """Mirror the ongoing-production boundary in _daily_refresh_plants."""
    placed = tile.get("planted_day")
    if type(placed) is not int or not 0 <= placed <= day:
        return False
    age = day + 1 - placed - spec["first_yield_day"]
    if age < 0 or age % spec["interval"] != 0:
        return False
    production_count = age // spec["interval"] + 1
    return production_count <= spec["max_yield"]


def _safe_tile(tile: Any, day: int):
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
        return None
    crop = tile.get("crop")
    if crop not in CROPS:
        return None
    spec = CROPS[crop]
    placed = tile.get("planted_day")
    streak = tile.get("consecutive_unwatered")
    watered = tile.get("watered_today")
    units = tile.get("yield_units")
    fertilized_until = tile.get("fertilized_until_day")
    if (type(placed) is not int or not 0 <= placed < day
            or type(streak) is not int or streak != 0
            or type(watered) is not bool or watered
            or type(units) is not int or not 0 <= units <= spec["max_yield"]
            or type(fertilized_until) is not int):
        return None
    production_due = _production_due(tile, day, spec)
    # A watered, fertilized production EOD can add 2 rather than 1.  Never trade
    # away that bonus unless the plant is already saturated and both paths clip.
    if production_due and fertilized_until >= day and units < spec["max_yield"]:
        return None
    return {"crop": crop, "production_due": production_due}


def plan_ongoing_water_skip(action: Any, observation: Any, configuration: Any) -> list[dict]:
    """Return certified WATER->PASS rewrites without mutating inputs.

    Fail-closed contract:
      * exact standard 10x10 / 24-turn-day / 720-step season;
      * only already-existing TOMATO/STRAWBERRY plants;
      * planted_day < current day and consecutive_unwatered == 0;
      * tile has not already been watered today;
      * no current fertilizer production bonus can be lost;
      * exactly one authored WATER at the site, leaving duplicate-row cleanup and
        same-turn PLANT->WATER ownership to their existing surfaces.
    """
    for key, expected in (("boardSize", 10), ("turnsPerDay", 24), ("episodeSteps", 720)):
        value = _cfg(configuration, key)
        if type(value) is not int or value != expected:
            return []
    if not isinstance(action, dict) or not isinstance(observation, dict):
        return []
    step, player = observation.get("step"), observation.get("player")
    farms = observation.get("farms")
    if (type(step) is not int or not 0 <= step <= 718
            or type(player) is not int or player not in (0, 1)
            or not isinstance(farms, list) or len(farms) != 2):
        return []
    farm = farms[player]
    if not isinstance(farm, dict):
        return []
    tiles, hands = farm.get("tiles"), farm.get("hands")
    farmer_row, hand_rows, market = action.get("farmer"), action.get("hands"), action.get("market")
    if (not isinstance(tiles, list) or len(tiles) != 10
            or any(not isinstance(row, list) or len(row) != 10 for row in tiles)
            or not isinstance(hands, list) or not isinstance(hand_rows, list)
            or len(hand_rows) != len(hands) or not isinstance(market, list)):
        return []
    positions = [_position(p, 10) for p in [farm.get("farmer"), *hands]]
    rows = [farmer_row, *hand_rows]
    if any(p is None for p in positions):
        return []
    if any(not isinstance(row, list) or not row or type(row[0]) is not str for row in rows):
        return []

    water_actors: dict[tuple[int, int], list[int]] = {}
    for actor, (site, row) in enumerate(zip(positions, rows)):
        if row == ["WATER"]:
            water_actors.setdefault(site, []).append(actor)

    day = step // 24
    changes = []
    for site, actors in water_actors.items():
        if len(actors) != 1:
            continue
        proof = _safe_tile(tiles[site[1]][site[0]], day)
        if proof is None:
            continue
        changes.append({
            "actor": actors[0],
            "site": list(site),
            "crop": proof["crop"],
            "production_due": proof["production_due"],
            "reason": "one_unwatered_eod_is_nonterminal",
        })
    return changes


def apply_ongoing_water_skip(action: Any, observation: Any, configuration: Any, *, enabled=False):
    """Default identity; enabled mode rewrites only certified WATER rows to PASS."""
    if not enabled:
        return action
    changes = plan_ongoing_water_skip(action, observation, configuration)
    if not changes:
        return action
    result = deepcopy(action)
    for change in changes:
        actor = change["actor"]
        if actor == 0:
            result["farmer"] = ["PASS"]
        else:
            result["hands"][actor - 1] = ["PASS"]
    return result
