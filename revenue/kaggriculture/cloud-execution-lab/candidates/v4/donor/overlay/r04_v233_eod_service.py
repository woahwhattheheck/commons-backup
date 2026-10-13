# SPDX-License-Identifier: Apache-2.0
"""A1: salvage same-tile V233 sheep service from a dead hour-23 cargo return.

The official engine performs unit actions, then market work, then the end-of-day
refresh and finally drops every worker inventory into the shed before hands are
removed.  On non-final days a V233 sheep worker that is still one or more tiles
from the shed at hour 23 cannot complete a manual cargo delivery before reset;
its carried inventory is deposited automatically instead.

V233 nevertheless prioritizes carried WOOL/FERTILIZER return travel before sheep
service.  This default-off helper changes only that provably-dead hour-23 return
movement to FEED or CARE on the SHEEP the assigned V233 worker is already standing
on.  It never creates new cargo: HARVEST/COLLECT are out of scope.  A whole-farm
capacity upper bound proves the EOD auto-drop cannot discard existing cargo.
Malformed, nonstandard, ambiguous, or non-V233 state returns the exact parent.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

import h3c_goose_eod_cap_rescue as h3c
import r04_full_router as r04

STANDARD_CONFIG = {
    "episodeSteps": 720,
    "boardSize": 10,
    "turnsPerDay": 24,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}
_MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
_MARKET_VERBS = {"HIRE", "BUY_LAND", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL"}
_MISSING = object()
telemetry = Counter()


def _standard_configuration(configuration: Any) -> bool:
    for name, expected in STANDARD_CONFIG.items():
        actual = h3c._cfg(configuration, name)
        if actual is h3c._MISSING or type(actual) is not int or actual != expected:
            return False
    return True


def _strict_position(position: Any):
    if (not isinstance(position, list) or len(position) != 2
            or type(position[0]) is not int or type(position[1]) is not int):
        return None
    x, y = position
    if not (0 <= x < 10 and 0 <= y < 10):
        return None
    return x, y


def _strict_targets(targets: Any):
    if not isinstance(targets, list):
        return None
    result = []
    for target in targets:
        if (not isinstance(target, (list, tuple)) or len(target) != 2
                or type(target[0]) is not int or type(target[1]) is not int):
            return None
        x, y = target
        if not (0 <= x < 10 and 0 <= y < 10):
            return None
        result.append((x, y))
    return result


def _strict_sheep(tile: Any):
    """Validate every field the rescued hour-23 sheep can reach during EOD refresh."""
    if not isinstance(tile, dict) or tile.get("kind") != "PASTURE" or tile.get("animal") != "SHEEP":
        return None
    placed = tile.get("placed_day", _MISSING)
    units = tile.get("yield_units", _MISSING)
    consecutive_unfed = tile.get("consecutive_unfed", _MISSING)
    fed = tile.get("fed_today", _MISSING)
    cared = tile.get("cared_today", _MISSING)
    fertilizer = tile.get("fertilizer_available", _MISSING)
    bonus = tile.get("pending_care_bonus", _MISSING)
    if type(placed) is not int or placed < 0:
        return None
    if type(units) is not int or units < 0:
        return None
    if type(consecutive_unfed) is not int or consecutive_unfed < 0:
        return None
    if type(fed) is not bool or type(cared) is not bool or type(fertilizer) is not bool:
        return None
    if type(bonus) is not int or bonus < 0:
        return None
    return fed, cared


def _return_move(position, inventory):
    """Recompute V233's cargo-return MOVE.  Shed-adjacent PLACE is intentionally excluded."""
    cargo = []
    for item in ("WOOL", "FERTILIZER"):
        quantity = inventory.get(item, 0)
        if type(quantity) is not int or quantity < 0:
            return None
        if quantity:
            cargo.append(item)
    if not cargo:
        return None
    access = ((4, 4), (5, 4), (4, 5), (5, 5))
    pos = tuple(position)
    home = min(access, key=lambda p: (abs(pos[0] - p[0]) + abs(pos[1] - p[1]), p))
    command = r04._v219_walk(pos, home)
    if not isinstance(command, list) or len(command) != 1 or command[0] not in _MOVES:
        return None
    return command


def _service(tile, inventory):
    sheep = _strict_sheep(tile)
    if sheep is None:
        return None
    fed, cared = sheep
    wheat = inventory.get("WHEAT", 0)
    if type(wheat) is not int or wheat < 0:
        return None
    if not fed and wheat > 0:
        return ["FEED"]
    if fed and not cared:
        return ["CARE"]
    return None


def apply_v233_eod_service(action: Any, observation: Any, configuration: Any, *, enabled=False):
    """Return a candidate action; no-match and every ambiguity preserve parent identity."""
    if not enabled or not _standard_configuration(configuration):
        return action
    if not isinstance(observation, dict):
        return action

    step = observation.get("step", _MISSING)
    day = observation.get("day", _MISSING)
    hour = observation.get("hour", _MISSING)
    player = observation.get("player", _MISSING)
    farms = observation.get("farms", _MISSING)
    private = observation.get("private", _MISSING)
    if (type(step) is not int or type(day) is not int or type(hour) is not int
            or day != step // 24 or hour != step % 24 or hour != 23 or not 12 <= day <= 28):
        return action
    if type(player) is not int or player not in (0, 1):
        return action
    if not isinstance(farms, list) or len(farms) != 2 or not isinstance(private, dict):
        return action

    farm = farms[player]
    if not isinstance(farm, dict):
        return action
    farmer = farm.get("farmer", _MISSING)
    hands = farm.get("hands", _MISSING)
    tiles = farm.get("tiles", _MISSING)
    inventories = private.get("inventories", _MISSING)
    shed = private.get("shed", _MISSING)
    if (not isinstance(hands, list) or not isinstance(tiles, list) or len(tiles) != 10
            or any(not isinstance(row, list) or len(row) != 10 for row in tiles)
            or not isinstance(inventories, list)):
        return action

    positions = [farmer, *hands]
    rows = h3c._parent_rows(action)
    if rows is None or len(rows) != len(positions) or len(inventories) != len(positions):
        return action

    normalized_positions = []
    actor_tiles = []
    carried_total = 0
    for position, inventory in zip(positions, inventories):
        site = _strict_position(position)
        subtotal = h3c._strict_inventory_total(inventory)
        if site is None or subtotal is None:
            return action
        normalized_positions.append(site)
        actor_tiles.append(tiles[site[1]][site[0]])
        carried_total += subtotal

    shed_total = h3c._strict_inventory_total(shed)
    if shed_total is None:
        return action

    market = action.get("market", _MISSING)
    if not isinstance(market, list):
        return action
    for order in market:
        if not isinstance(order, list):
            return action
        if not order:
            continue
        if type(order[0]) is not str or order[0] not in _MARKET_VERBS:
            return action
        # These can add physical shed stock after unit work and before EOD auto-drop.
        if order[0] in ("BUY_PRODUCT", "BUY_ANIMAL"):
            telemetry["market_inflow_block"] += 1
            return action

    states = getattr(r04, "_V233_STATES", None)
    if not isinstance(states, dict):
        return action
    state = states.get(player)
    if (not isinstance(state, dict) or state.get("last_step") != step
            or state.get("day") != day):
        return action
    workers = state.get("workers")
    work = state.get("work")
    if not isinstance(workers, dict) or not isinstance(work, dict):
        return action

    candidates = []
    for actor, command in enumerate(rows):
        if actor not in workers:
            continue
        if type(actor) is not int or actor <= 0 or actor >= len(rows):
            return action
        targets = _strict_targets(workers.get(actor))
        if targets is None:
            return action
        site = normalized_positions[actor]
        if site not in targets:
            continue
        inventory = inventories[actor]
        expected = _return_move(positions[actor], inventory)
        if expected is None or command != expected:
            continue
        previous = work.get(actor)
        if (not isinstance(previous, dict) or previous.get("step") != step
                or previous.get("command") != expected
                or not isinstance(previous.get("inventory"), dict)):
            continue
        service = _service(actor_tiles[actor], inventory)
        if service is None:
            continue
        candidates.append((actor, site, service))

    if not candidates:
        return action

    # Same-tile active workers make FEED/CARE ordering ambiguous. PASS is harmless.
    for actor, site, _service_command in candidates:
        for other, (other_site, other_command) in enumerate(zip(normalized_positions, rows)):
            if other != actor and other_site == site and other_command != ["PASS"]:
                telemetry["stacked_worker_block"] += 1
                return action

    candidate_actors = {actor for actor, _site, _service_command in candidates}
    unit_inflow_upper_bound = 0
    for actor, (command, tile) in enumerate(zip(rows, actor_tiles)):
        if actor in candidate_actors:
            continue  # FEED/CARE only consumes or preserves carried stock.
        op = command[0] if command else None
        if op == "HARVEST":
            gain = h3c._harvest_upper_bound(tile)
            if gain is None:
                return action
            unit_inflow_upper_bound += gain
        elif op == "COLLECT_FERTILIZER":
            unit_inflow_upper_bound += 1

    if shed_total + carried_total + unit_inflow_upper_bound > STANDARD_CONFIG["shedCapacity"]:
        telemetry["capacity_block"] += 1
        return action

    result = copy.deepcopy(action)
    result_rows = [result["farmer"], *result["hands"]]
    for actor, _site, service_command in candidates:
        result_rows[actor] = service_command
        # Keep V233's own same-callback work receipt coherent with the returned action.
        work[actor]["command"] = list(service_command)
        telemetry["activations"] += 1
        telemetry["feed_salvaged" if service_command == ["FEED"] else "care_salvaged"] += 1
    result["farmer"], result["hands"] = result_rows[0], result_rows[1:]
    return result
