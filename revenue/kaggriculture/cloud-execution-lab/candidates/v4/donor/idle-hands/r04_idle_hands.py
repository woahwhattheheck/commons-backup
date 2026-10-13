# SPDX-License-Identifier: Apache-2.0
"""V4 donor: turn provably idle PASS rows into local feed/care/WHEAT-fertilize work.

This module is intentionally policy-local.  It never moves an actor, never emits a
market row, and never consumes shared shed resources.  Every resource it spends is
already carried by the actor whose exact literal PASS row is replaced.  Malformed,
ambiguous, disabled, or non-matching states return the exact parent action object.
"""
from __future__ import annotations

import copy
from collections import Counter

_MISSING = object()
_STANDARD = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
}
_ANIMAL_STRUCTURE = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}
telemetry = Counter()


def _cfg(configuration, name):
    if isinstance(configuration, dict):
        return configuration.get(name, _MISSING)
    return getattr(configuration, name, _MISSING) if configuration is not None else _MISSING


def _standard_configuration(configuration):
    for name, expected in _STANDARD.items():
        value = _cfg(configuration, name)
        if type(value) is not int or value != expected:
            return False
    return True


def _strict_animal(tile, day):
    if not isinstance(tile, dict):
        return None
    animal = tile.get("animal", _MISSING)
    if animal not in _ANIMAL_STRUCTURE or tile.get("kind") != _ANIMAL_STRUCTURE[animal]:
        return None
    placed = tile.get("placed_day", _MISSING)
    units = tile.get("yield_units", _MISSING)
    unfed = tile.get("consecutive_unfed", _MISSING)
    fed = tile.get("fed_today", _MISSING)
    cared = tile.get("cared_today", _MISSING)
    fert = tile.get("fertilizer_available", _MISSING)
    bonus = tile.get("pending_care_bonus", _MISSING)
    if type(placed) is not int or placed < 0 or placed > day:
        return None
    if type(units) is not int or units < 0:
        return None
    if type(unfed) is not int or unfed < 0:
        return None
    if type(fed) is not bool or type(cared) is not bool or type(fert) is not bool:
        return None
    if type(bonus) is not int or bonus < 0:
        return None
    return animal, fed, cared


def _strict_wheat(tile, day):
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT" or tile.get("crop") != "WHEAT":
        return None
    planted = tile.get("planted_day", _MISSING)
    watered = tile.get("watered_today", _MISSING)
    dry = tile.get("consecutive_unwatered", _MISSING)
    units = tile.get("yield_units", _MISSING)
    lifespan = tile.get("max_lifespan_step", _MISSING)
    coverage = tile.get("fertilized_until_day", _MISSING)
    if type(planted) is not int or planted < 0 or planted > day:
        return None
    if type(watered) is not bool:
        return None
    if type(dry) is not int or dry < 0:
        return None
    if type(units) is not int or units < 0:
        return None
    if type(lifespan) is not int or type(coverage) is not int:
        return None
    return day - planted, coverage


def _strict_inventory(inventory):
    if not isinstance(inventory, dict):
        return False
    for item, value in inventory.items():
        if type(item) is not str or type(value) is not int or value < 0:
            return False
    return True


def _context(action, observation, configuration):
    if not _standard_configuration(configuration):
        return None
    if not isinstance(action, dict) or not isinstance(observation, dict):
        return None
    step = observation.get("step", _MISSING)
    player = observation.get("player", _MISSING)
    farms = observation.get("farms", _MISSING)
    private = observation.get("private", _MISSING)
    if type(step) is not int or step < 0 or step >= 720:
        return None
    if player not in (0, 1) or type(player) is not int:
        return None
    if not isinstance(farms, list) or len(farms) != 2 or not isinstance(private, dict):
        return None
    farm = farms[player]
    if not isinstance(farm, dict):
        return None
    farmer = farm.get("farmer", _MISSING)
    hands = farm.get("hands", _MISSING)
    tiles = farm.get("tiles", _MISSING)
    inventories = private.get("inventories", _MISSING)
    parent_farmer = action.get("farmer", _MISSING)
    parent_hands = action.get("hands", _MISSING)
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return None
    if not isinstance(parent_farmer, list) or not isinstance(parent_hands, list):
        return None
    if not isinstance(tiles, list) or len(tiles) != 10 or not isinstance(inventories, list):
        return None
    positions = [farmer, *hands]
    rows = [parent_farmer, *parent_hands]
    if len(rows) != len(positions) or len(inventories) != len(positions):
        return None

    actor_rows = []
    site_counts = Counter()
    for position, command, inventory in zip(positions, rows, inventories):
        if (not isinstance(position, list) or len(position) != 2
                or type(position[0]) is not int or type(position[1]) is not int):
            return None
        x, y = position
        if not (0 <= x < 10 and 0 <= y < 10):
            return None
        if not isinstance(tiles[y], list) or len(tiles[y]) != 10:
            return None
        if not isinstance(command, list) or not command or type(command[0]) is not str:
            return None
        if command[0] == "PASS" and command != ["PASS"]:
            return None
        if not _strict_inventory(inventory):
            return None
        site = (x, y)
        site_counts[site] += 1
        actor_rows.append((command, inventory, site, tiles[y][x]))
    return actor_rows, site_counts, step // 24


def _rewrite(action, replacements, metric):
    if not replacements:
        return action
    result = copy.deepcopy(action)
    rows = [result["farmer"], *result["hands"]]
    for actor, command in replacements.items():
        rows[actor] = command
    result["farmer"], result["hands"] = rows[0], rows[1:]
    telemetry[metric] += len(replacements)
    telemetry["activations"] += len(replacements)
    return result


def apply_feed(action, observation, configuration, *, enabled=False):
    if not enabled:
        return action
    context = _context(action, observation, configuration)
    if context is None:
        return action
    actor_rows, site_counts, day = context
    replacements = {}
    for actor, (command, inventory, site, tile) in enumerate(actor_rows):
        if command != ["PASS"] or site_counts[site] != 1:
            continue
        animal = _strict_animal(tile, day)
        if animal is None or animal[1] is not False:
            continue
        wheat = inventory.get("WHEAT", 0)
        if type(wheat) is not int or wheat < 1:
            continue
        replacements[actor] = ["FEED"]
    return _rewrite(action, replacements, "feed_rows")


def apply_care(action, observation, configuration, *, enabled=False, goose_only=False):
    if not enabled:
        return action
    context = _context(action, observation, configuration)
    if context is None:
        return action
    actor_rows, site_counts, day = context
    replacements = {}
    for actor, (command, _inventory, site, tile) in enumerate(actor_rows):
        if command != ["PASS"] or site_counts[site] != 1:
            continue
        animal = _strict_animal(tile, day)
        if animal is None:
            continue
        kind, fed, cared = animal
        if goose_only and kind != "GOOSE":
            continue
        if fed is not True or cared is not False:
            continue
        replacements[actor] = ["CARE"]
    return _rewrite(action, replacements, "care_rows")


def apply_wheat_fertilize(action, observation, configuration, *, enabled=False):
    if not enabled:
        return action
    context = _context(action, observation, configuration)
    if context is None:
        return action
    actor_rows, site_counts, day = context
    replacements = {}
    for actor, (command, inventory, site, tile) in enumerate(actor_rows):
        if command != ["PASS"] or site_counts[site] != 1:
            continue
        wheat = _strict_wheat(tile, day)
        if wheat is None:
            continue
        age, coverage = wheat
        if age < 2 or age > 4 or coverage >= day:
            continue
        fertilizer = inventory.get("FERTILIZER", 0)
        if type(fertilizer) is not int or fertilizer < 1:
            continue
        replacements[actor] = ["FERTILIZE"]
    return _rewrite(action, replacements, "wheat_fertilize_rows")


def apply_all(action, observation, configuration, *, idle_all=False, feed_all=False,
              care_all=False, care_goose=False, wheat_fert=False):
    if idle_all:
        feed_all = True
        care_all = True
        wheat_fert = True
    result = apply_feed(action, observation, configuration, enabled=feed_all)
    result = apply_care(result, observation, configuration,
                        enabled=(care_all or care_goose),
                        goose_only=(care_goose and not care_all))
    result = apply_wheat_fertilize(result, observation, configuration, enabled=wheat_fert)
    return result


def install(parent, *, idle_all=False, feed_all=False, care_all=False,
            care_goose=False, wheat_fert=False):
    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return apply_all(action, observation, configuration,
                         idle_all=idle_all, feed_all=feed_all,
                         care_all=care_all, care_goose=care_goose,
                         wheat_fert=wheat_fert)
    agent.telemetry = telemetry
    return agent
