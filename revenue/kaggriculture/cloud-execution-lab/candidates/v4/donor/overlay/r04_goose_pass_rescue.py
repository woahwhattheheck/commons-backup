# SPDX-License-Identifier: Apache-2.0
"""V4 H3d: bank clipping goose eggs when the authored action is already PASS.

H3c rescues the hour-23 COLLECT_FERTILIZER case.  H3d is deliberately
orthogonal: it only replaces a literal PASS for an actor already standing on a
fed+cared GOOSE whose held eggs would clip at tonight's refresh.  It reuses the
same strict public-state, stacked-worker, market-inflow, and shed-capacity
theorem as H3c.  Disabled and ambiguous paths return the exact parent object.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

import h3c_goose_eod_cap_rescue as h3c

_MISSING = object()
telemetry = Counter()


def apply_goose_pass_rescue(action: Any, observation: Any, configuration: Any, *, enabled=False):
    """Return the candidate action; no-match and malformed paths preserve identity."""
    if not enabled or not h3c._standard_configuration(configuration):
        return action
    if not isinstance(observation, dict):
        return action

    step = observation.get("step", _MISSING)
    player = observation.get("player", _MISSING)
    farms = observation.get("farms", _MISSING)
    private = observation.get("private", _MISSING)
    if type(step) is not int or step < 0 or step % 24 != 23:
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
    if (not isinstance(farmer, list) or not isinstance(hands, list)
            or not isinstance(tiles, list) or len(tiles) != 10
            or not isinstance(inventories, list)):
        return action

    positions = [farmer, *hands]
    rows = h3c._parent_rows(action)
    if rows is None or len(rows) != len(positions) or len(inventories) != len(positions):
        return action

    market = action.get("market", _MISSING)
    if not isinstance(market, list):
        return action
    for order in market:
        if not isinstance(order, list):
            return action
        if order and not isinstance(order[0], str):
            return action
        if order and order[0] in ("BUY_PRODUCT", "BUY_ANIMAL"):
            telemetry["market_inflow_block"] += 1
            return action

    shed_total = h3c._strict_inventory_total(shed)
    if shed_total is None:
        return action
    carried_total = 0
    for inventory in inventories:
        subtotal = h3c._strict_inventory_total(inventory)
        if subtotal is None:
            return action
        carried_total += subtotal

    candidates = []
    actor_tiles = []
    normalized_positions = []
    candidate_sites = set()
    day = step // 24

    for actor, (position, command) in enumerate(zip(positions, rows)):
        if (not isinstance(position, list) or len(position) != 2
                or type(position[0]) is not int or type(position[1]) is not int):
            return action
        x, y = position
        if not (0 <= y < len(tiles) and isinstance(tiles[y], list)
                and len(tiles[y]) == 10 and 0 <= x < 10):
            return action
        tile = tiles[y][x]
        actor_tiles.append(tile)
        site = (x, y)
        normalized_positions.append(site)

        if command != ["PASS"]:
            continue
        goose = h3c._strict_goose(tile)
        if goose is None:
            continue
        _placed, units, _unfed, fed, cared, _fertilizer, _bonus = goose
        if not fed or not cared or units <= 0:
            continue
        overflow = h3c._overflow_at_refresh(tile, day)
        if overflow is None or overflow <= 0:
            continue
        if site in candidate_sites:
            telemetry["duplicate_pass_block"] += 1
            return action
        candidate_sites.add(site)
        candidates.append((actor, site, units, overflow))

    if not candidates:
        return action

    # A second active actor on a candidate animal can change legality or make
    # the new HARVEST a no-op.  Duplicate PASS candidates were rejected above.
    for actor, site, _units, _overflow in candidates:
        for other, (other_site, other_command) in enumerate(zip(normalized_positions, rows)):
            if other == actor or other_site != site:
                continue
            if other_command != ["PASS"]:
                telemetry["stacked_worker_block"] += 1
                return action

    candidate_by_actor = {actor: units for actor, _site, units, _overflow in candidates}
    unit_inflow_upper_bound = 0
    for actor, (command, tile) in enumerate(zip(rows, actor_tiles)):
        if actor in candidate_by_actor:
            unit_inflow_upper_bound += candidate_by_actor[actor]
            continue
        op = command[0] if command else None
        if op == "HARVEST":
            gain = h3c._harvest_upper_bound(tile)
            if gain is None:
                return action
            unit_inflow_upper_bound += gain
        elif op == "COLLECT_FERTILIZER":
            unit_inflow_upper_bound += 1

    capacity = h3c.STANDARD_CONFIG["shedCapacity"]
    if shed_total + carried_total + unit_inflow_upper_bound > capacity:
        telemetry["capacity_block"] += 1
        return action

    result = copy.deepcopy(action)
    result_rows = [result["farmer"], *result["hands"]]
    for actor, _site, units, overflow in candidates:
        result_rows[actor] = ["HARVEST"]
        telemetry["activations"] += 1
        telemetry["egg_units_banked"] += units
        telemetry["egg_units_clipping_avoided"] += overflow
    result["farmer"], result["hands"] = result_rows[0], result_rows[1:]
    return result


def install(parent, *, enabled=False):
    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return apply_goose_pass_rescue(action, observation, configuration, enabled=enabled)

    agent.telemetry = telemetry
    return agent
