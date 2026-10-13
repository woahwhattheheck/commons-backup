# SPDX-License-Identifier: Apache-2.0
"""H3c: zero-movement GOOSE max-held rescue at the final action of a day.

The official interpreter executes hour-23 unit work before the animal daily refresh,
then auto-drops all carried inventory to the shed.  GOOSE production is daily after
maturity and is capped at four held EGG.  This default-off transform changes only a
literal ``COLLECT_FERTILIZER`` on the GOOSE the actor is already standing on to
``HARVEST`` when tonight's production would otherwise clip held yield.

The guard is deliberately narrow: the goose is already fed+cared, fertilizer is
actually collectible, the harvest is legal, the production tick is due, no stacked
worker has another non-PASS command on that same animal, and a whole-farm upper bound
proves every item that can be added by this turn's unit work still fits in the EOD
shed.  Same-turn BUY_PRODUCT/BUY_ANIMAL rows are vetoed because their lockstep
realization is rival-dependent.  Any ambiguity returns the exact parent action object.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

GOOSE_FIRST_YIELD_DAY = 4
GOOSE_INTERVAL = 1
GOOSE_MAX_HELD = 4
STANDARD_CONFIG = {
    "boardSize": 10,
    "turnsPerDay": 24,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}
_MISSING = object()
telemetry = Counter()


def _cfg(configuration: Any, name: str):
    if configuration is None:
        return _MISSING
    try:
        if isinstance(configuration, dict):
            return configuration.get(name, _MISSING)
        return getattr(configuration, name, _MISSING)
    except Exception:
        return _MISSING


def _standard_configuration(configuration: Any) -> bool:
    for name, expected in STANDARD_CONFIG.items():
        actual = _cfg(configuration, name)
        if actual is _MISSING or type(actual) is not int or actual != expected:
            return False
    return True


def _strict_inventory_total(mapping: Any) -> int | None:
    if not isinstance(mapping, dict):
        return None
    total = 0
    for item, quantity in mapping.items():
        if not isinstance(item, str) or type(quantity) is not int or quantity < 0:
            return None
        total += quantity
    return total


def _strict_goose(tile: Any):
    if not isinstance(tile, dict) or tile.get("kind") != "COOP" or tile.get("animal") != "GOOSE":
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
    if type(units) is not int or not 0 <= units <= GOOSE_MAX_HELD:
        return None
    if type(consecutive_unfed) is not int or consecutive_unfed < 0:
        return None
    if type(fed) is not bool or type(cared) is not bool or type(fertilizer) is not bool:
        return None
    if type(bonus) is not int or bonus < 0:
        return None
    return placed, units, consecutive_unfed, fed, cared, fertilizer, bonus


def _overflow_at_refresh(tile: Any, day: int) -> int | None:
    state = _strict_goose(tile)
    if state is None:
        return None
    placed, units, _unfed, fed, _cared, _fertilizer, bonus = state
    next_day = day + 1
    days_since_first = next_day - placed - GOOSE_FIRST_YIELD_DAY
    if days_since_first < 0 or days_since_first % GOOSE_INTERVAL != 0:
        return 0
    produced = 1 + (bonus if fed else 0)
    if units <= 0:
        return 0
    return max(0, units + produced - GOOSE_MAX_HELD)


def _parent_rows(action: Any):
    if not isinstance(action, dict):
        return None
    farmer = action.get("farmer", _MISSING)
    hands = action.get("hands", _MISSING)
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return None
    if any(not isinstance(command, list) for command in hands):
        return None
    return [farmer, *hands]


def _harvest_upper_bound(tile: Any) -> int | None:
    """Conservative current-turn carried-unit increase for a HARVEST row."""
    if not isinstance(tile, dict):
        return 0
    units = tile.get("yield_units", 0)
    if type(units) is not int or units < 0:
        return None
    return units


def apply_goose_eod_cap_rescue(action: Any, observation: Any, configuration: Any, *, enabled=False):
    """Return the candidate action; no-match and malformed paths preserve identity."""
    if not enabled or not _standard_configuration(configuration):
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
    rows = _parent_rows(action)
    if rows is None or len(rows) != len(positions) or len(inventories) != len(positions):
        return action

    market = action.get("market", _MISSING)
    if not isinstance(market, list):
        return action
    # The standard engine executes ten raw slots, not ten nonempty rows.
    # A capped suffix cannot add shed inflow; keep it untouched in the action.
    for order in market[:STANDARD_CONFIG["maxMarketOrdersPerTurn"]]:
        if not isinstance(order, list):
            return action
        if order and not isinstance(order[0], str):
            return action
        if order and order[0] in ("BUY_PRODUCT", "BUY_ANIMAL"):
            telemetry["market_inflow_block"] += 1
            return action

    shed_total = _strict_inventory_total(shed)
    if shed_total is None:
        return action
    carried_total = 0
    for inventory in inventories:
        subtotal = _strict_inventory_total(inventory)
        if subtotal is None:
            return action
        carried_total += subtotal

    candidates = []
    seen_sites = set()
    actor_tiles = []
    normalized_positions = []
    day = step // 24
    for actor, (position, command, inventory) in enumerate(zip(positions, rows, inventories)):
        if (not isinstance(position, list) or len(position) != 2
                or type(position[0]) is not int or type(position[1]) is not int):
            return action
        x, y = position
        if not (0 <= y < len(tiles) and isinstance(tiles[y], list) and len(tiles[y]) == 10 and 0 <= x < 10):
            return action
        tile = tiles[y][x]
        actor_tiles.append(tile)
        normalized_positions.append((x, y))
        if command != ["COLLECT_FERTILIZER"]:
            continue
        goose = _strict_goose(tile)
        if goose is None:
            continue
        placed, units, _unfed, fed, cared, fertilizer_available, _bonus = goose
        if not fed or not cared or not fertilizer_available or units <= 0:
            continue
        overflow = _overflow_at_refresh(tile, day)
        if overflow is None or overflow <= 0:
            continue
        site = (x, y)
        if site in seen_sites:
            # Two qualifying collectors on one animal are action-order ambiguous.
            return action
        seen_sites.add(site)
        candidates.append((actor, site, units, overflow, placed))

    if not candidates:
        return action

    # A stacked worker with any other active command can invalidate the claimed
    # zero-movement substitution.  The critical case is an existing HARVEST: then
    # H3c's second HARVEST would be a no-op while sacrificing fertilizer collection.
    for actor, site, _units, _overflow, _placed in candidates:
        for other, (other_site, other_command) in enumerate(zip(normalized_positions, rows)):
            if other == actor or other_site != site:
                continue
            if other_command != ["PASS"]:
                telemetry["stacked_worker_block"] += 1
                return action

    candidate_by_actor = {actor: units for actor, _site, units, _overflow, _placed in candidates}
    unit_inflow_upper_bound = 0
    for actor, (command, tile) in enumerate(zip(rows, actor_tiles)):
        if actor in candidate_by_actor:
            unit_inflow_upper_bound += candidate_by_actor[actor]
            continue
        op = command[0] if command else None
        if op == "HARVEST":
            gain = _harvest_upper_bound(tile)
            if gain is None:
                return action
            unit_inflow_upper_bound += gain
        elif op == "COLLECT_FERTILIZER":
            # At most one unit, even if the observed tile is not actually collectible.
            unit_inflow_upper_bound += 1

    if shed_total + carried_total + unit_inflow_upper_bound > STANDARD_CONFIG["shedCapacity"]:
        telemetry["capacity_block"] += 1
        return action

    result = copy.deepcopy(action)
    result_rows = [result["farmer"], *result["hands"]]
    for actor, _site, units, overflow, _placed in candidates:
        result_rows[actor] = ["HARVEST"]
        telemetry["activations"] += 1
        telemetry["egg_units_banked"] += units
        telemetry["egg_units_clipping_avoided"] += overflow
    result["farmer"], result["hands"] = result_rows[0], result_rows[1:]
    return result


def install(parent, *, enabled=False):
    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return apply_goose_eod_cap_rescue(action, observation, configuration, enabled=enabled)

    agent.telemetry = telemetry
    return agent
