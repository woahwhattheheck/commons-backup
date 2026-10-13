# SPDX-License-Identifier: Apache-2.0
"""V4 H3e: recycle provably dead COW service at the last EOD action into FEED.

V217 owns PASS-only farmer starvation rescue and V233 owns the dedicated sheep
service hand. H3e is deliberately narrower and orthogonal: at hour 23, it may
replace only an action that is provably a no-op for an actor already standing on
an escape-imminent COW, and only when that same actor already carries WHEAT.

There is no movement, pickup, market, hire, herd, or scheduling policy here.
Malformed/no-match/disabled paths return the exact parent action object.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

import h3c_goose_eod_cap_rescue as h3c

_MISSING = object()
telemetry = Counter()


def _strict_cow(tile: Any, day: int):
    """Return the service fields only for a cow safe to carry through EOD.

    Baseline escape at consecutive_unfed==2 replaces the tile before the engine
    reads production metadata. H3e prevents that escape, so it must validate the
    fields EOD will newly dereference rather than preserving a poison tile that
    baseline would have deleted first.
    """
    if not isinstance(tile, dict) or tile.get("kind") != "PASTURE" or tile.get("animal") != "COW":
        return None
    units = tile.get("yield_units", _MISSING)
    consecutive_unfed = tile.get("consecutive_unfed", _MISSING)
    fed = tile.get("fed_today", _MISSING)
    cared = tile.get("cared_today", _MISSING)
    fertilizer = tile.get("fertilizer_available", _MISSING)
    placed_day = tile.get("placed_day", _MISSING)
    pending_care_bonus = tile.get("pending_care_bonus", _MISSING)
    if type(units) is not int or units < 0:
        return None
    if type(consecutive_unfed) is not int or consecutive_unfed < 0:
        return None
    if type(fed) is not bool or type(cared) is not bool or type(fertilizer) is not bool:
        return None
    if type(placed_day) is not int or placed_day < 0 or placed_day > day:
        return None
    if type(pending_care_bonus) is not int or pending_care_bonus < 0:
        return None
    return units, consecutive_unfed, fed, cared, fertilizer


def _provably_dead(command: Any, cow) -> bool:
    if not isinstance(command, list) or len(command) != 1:
        return False
    units, _unfed, _fed, cared, fertilizer = cow
    if command == ["CARE"]:
        return cared
    if command == ["HARVEST"]:
        return units == 0
    if command == ["COLLECT_FERTILIZER"]:
        return not fertilizer
    return False


def apply_cow_feed_recycle(action: Any, observation: Any, configuration: Any, *, enabled=False):
    """Rewrite only same-tile, no-effect service into an immediately necessary FEED."""
    if not enabled or not h3c._standard_configuration(configuration):
        return action
    # This mechanism hard-codes the standard 720-step season boundary: step
    # 695 is the last real hour-23 callback followed by EOD animal refresh.
    # H3c's shared config predicate does not consume episodeSteps itself, so
    # require it explicitly here without bool/int coercion.
    episode_steps = h3c._cfg(configuration, "episodeSteps")
    if type(episode_steps) is not int or episode_steps != 720:
        return action
    if not isinstance(observation, dict):
        return action

    step = observation.get("step", _MISSING)
    player = observation.get("player", _MISSING)
    farms = observation.get("farms", _MISSING)
    private = observation.get("private", _MISSING)
    # 695 is the game's final hour-23/EOD callback; 696..718 are the terminal
    # partial day and have no following daily animal refresh to rescue.
    if type(step) is not int or step < 0 or step > 695 or step % 24 != 23:
        return action
    if type(player) is not int or player not in (0, 1):
        return action
    if not isinstance(farms, list) or len(farms) != 2 or not isinstance(private, dict):
        return action
    day = step // 24

    farm = farms[player]
    if not isinstance(farm, dict):
        return action
    farmer = farm.get("farmer", _MISSING)
    hands = farm.get("hands", _MISSING)
    tiles = farm.get("tiles", _MISSING)
    inventories = private.get("inventories", _MISSING)
    if (not isinstance(farmer, list) or not isinstance(hands, list)
            or not isinstance(tiles, list) or len(tiles) != 10
            or not isinstance(inventories, list)):
        return action

    positions = [farmer, *hands]
    rows = h3c._parent_rows(action)
    if rows is None or len(rows) != len(positions) or len(inventories) != len(positions):
        return action

    actor_sites = []
    candidates = []
    seen_sites = set()
    for actor, (position, command, inventory) in enumerate(zip(positions, rows, inventories)):
        if (not isinstance(position, list) or len(position) != 2
                or type(position[0]) is not int or type(position[1]) is not int):
            return action
        x, y = position
        if not (0 <= y < 10 and isinstance(tiles[y], list) and len(tiles[y]) == 10 and 0 <= x < 10):
            return action
        if h3c._strict_inventory_total(inventory) is None:
            return action

        site = (x, y)
        actor_sites.append(site)
        cow = _strict_cow(tiles[y][x], day)
        if cow is None:
            continue
        _units, consecutive_unfed, fed, _cared, _fertilizer = cow
        # Exactly one previous missed EOD + no feed today means another miss
        # would hit the official two-consecutive-unfed escape threshold tonight.
        if consecutive_unfed != 1 or fed:
            continue
        wheat = inventory.get("WHEAT", 0)
        if type(wheat) is not int or wheat < 1:
            continue
        if not _provably_dead(command, cow):
            continue
        if site in seen_sites:
            telemetry["duplicate_candidate_block"] += 1
            return action
        seen_sites.add(site)
        candidates.append((actor, site, command[0]))

    if not candidates:
        return action
    # H3e is deliberately a single-row salvage theorem. Multiple independent
    # candidates would widen resource spend and policy scope beyond the PR's
    # proved contract; fail closed rather than feed several cows at once.
    if len(candidates) != 1:
        telemetry["multiple_candidate_block"] += 1
        return action

    # A second active actor on the same COW can change the tile before this
    # actor executes. Only stacked PASS is order-independent.
    for actor, site, _op in candidates:
        for other, (other_site, other_command) in enumerate(zip(actor_sites, rows)):
            if other == actor or other_site != site:
                continue
            if other_command != ["PASS"]:
                telemetry["stacked_worker_block"] += 1
                return action

    result = copy.deepcopy(action)
    result_rows = [result["farmer"], *result["hands"]]
    for actor, _site, op in candidates:
        result_rows[actor] = ["FEED"]
        telemetry["activations"] += 1
        telemetry["escape_risk_cows_fed"] += 1
        telemetry["recycled_" + op.lower()] += 1
    result["farmer"], result["hands"] = result_rows[0], result_rows[1:]
    return result


def install(parent, *, enabled=False):
    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return apply_cow_feed_recycle(action, observation, configuration, enabled=enabled)

    agent.telemetry = telemetry
    return agent
