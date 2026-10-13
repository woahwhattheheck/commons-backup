# SPDX-License-Identifier: Apache-2.0
"""V4 W2: turn a provably dead same-tile FEED into CARE.

The official interpreter makes FEED a no-op when the animal is already fed. CARE
on that same fed, uncared animal consumes no inventory and only marks cared_today,
which can add a future production bonus at EOD. This lane never moves an actor or
changes market, land, seed, animal, fertilizer, or shop-RNG state. Disabled,
non-matching, nonstandard, and malformed paths return the exact parent object.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

import h3c_goose_eod_cap_rescue as h3c

_MISSING = object()
# species -> (required structure, max held product, max reachable pending-care bonus)
# A fed animal can carry consecutive_unfed 0 or 1 during the day; >=2 would have
# escaped at the previous EOD.  The pending bonus can accumulate for at most one
# production interval because it is consumed on the next fed production day.
_ANIMAL_LIMITS = {
    "GOOSE": ("COOP", 4, 1),
    "COW": ("PASTURE", 6, 2),
    "SHEEP": ("PASTURE", 6, 3),
}
telemetry = Counter()


def _standard_configuration(configuration: Any) -> bool:
    """H3c's public config theorem plus this lane's 720-step season bound."""
    if not h3c._standard_configuration(configuration):
        return False
    episode_steps = h3c._cfg(configuration, "episodeSteps")
    return type(episode_steps) is int and episode_steps == 720


def _strict_animal(tile: Any, day: int):
    if not isinstance(tile, dict):
        return None
    animal = tile.get("animal", _MISSING)
    if not isinstance(animal, str) or animal not in _ANIMAL_LIMITS:
        return None
    required_kind, max_held, max_bonus = _ANIMAL_LIMITS[animal]
    if tile.get("kind", _MISSING) != required_kind:
        return None
    placed = tile.get("placed_day", _MISSING)
    units = tile.get("yield_units", _MISSING)
    consecutive_unfed = tile.get("consecutive_unfed", _MISSING)
    fed = tile.get("fed_today", _MISSING)
    cared = tile.get("cared_today", _MISSING)
    fertilizer = tile.get("fertilizer_available", _MISSING)
    bonus = tile.get("pending_care_bonus", _MISSING)
    if type(placed) is not int or not 0 <= placed <= day:
        return None
    if type(units) is not int or not 0 <= units <= max_held:
        return None
    if type(consecutive_unfed) is not int or not 0 <= consecutive_unfed <= 1:
        return None
    if type(fed) is not bool or type(cared) is not bool or type(fertilizer) is not bool:
        return None
    if type(bonus) is not int or not 0 <= bonus <= max_bonus:
        return None
    return animal, fed, cared


def apply_dead_feed_care(action: Any, observation: Any, configuration: Any, *, enabled=False):
    """Replace only literal dead FEED rows; every uncertain path preserves identity."""
    if not enabled or not _standard_configuration(configuration):
        return action
    if not isinstance(observation, dict):
        return action

    step = observation.get("step", _MISSING)
    player = observation.get("player", _MISSING)
    farms = observation.get("farms", _MISSING)
    if type(step) is not int or not 0 <= step <= 718:
        return action
    if type(player) is not int or player not in (0, 1):
        return action
    if not isinstance(farms, list) or len(farms) != 2:
        return action

    farm = farms[player]
    if not isinstance(farm, dict):
        return action
    farmer = farm.get("farmer", _MISSING)
    hands = farm.get("hands", _MISSING)
    tiles = farm.get("tiles", _MISSING)
    if (not isinstance(farmer, list) or not isinstance(hands, list)
            or not isinstance(tiles, list) or len(tiles) != 10
            or any(not isinstance(row, list) or len(row) != 10 for row in tiles)):
        return action

    positions = [farmer, *hands]
    rows = h3c._parent_rows(action)
    if rows is None or len(rows) != len(positions):
        return action

    normalized = []
    for position in positions:
        if (not isinstance(position, list) or len(position) != 2
                or type(position[0]) is not int or type(position[1]) is not int):
            return action
        x, y = position
        if not (0 <= x < 10 and 0 <= y < 10):
            return action
        normalized.append((x, y))

    day = step // 24
    candidates = []
    candidate_sites = set()
    for actor, (site, command) in enumerate(zip(normalized, rows)):
        if command != ["FEED"]:
            continue
        x, y = site
        animal = _strict_animal(tiles[y][x], day)
        if animal is None:
            continue
        species, fed, cared = animal
        if not fed or cared:
            continue
        if site in candidate_sites:
            telemetry["duplicate_site_block"] += 1
            return action
        candidate_sites.add(site)
        candidates.append((actor, species))

    if not candidates:
        return action

    result = copy.deepcopy(action)
    result_rows = [result["farmer"], *result["hands"]]
    for actor, species in candidates:
        result_rows[actor] = ["CARE"]
        telemetry["activations"] += 1
        telemetry["care_salvaged_%s" % species.lower()] += 1
    result["farmer"], result["hands"] = result_rows[0], result_rows[1:]
    return result


def install(parent, *, enabled=False):
    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return apply_dead_feed_care(action, observation, configuration, enabled=enabled)

    agent.telemetry = telemetry
    return agent
