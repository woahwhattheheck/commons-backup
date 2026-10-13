# SPDX-License-Identifier: Apache-2.0
"""A1: current-ABI V233 hour-23 sheep-service salvage.

At a non-final hour-23 callback, a V233 hand carrying WOOL/FERTILIZER that is
still away from the shed cannot complete a manual delivery before EOD reset:
the official engine will auto-drop every worker inventory after unit + market
work. When that exact V233 cargo-return MOVE was authored on a SHEEP the hand is
already assigned to, this default-OFF transform may replace the dead MOVE with
same-tile FEED or CARE.

The transform is fail-closed. It requires literal enablement, the canonical
standard configuration, a committed same-callback V233 snapshot, exact actor
cardinality/commands, strict sheep + inventory fields, unambiguous same-tile
ordering, no executable same-turn physical market inflow, and a whole-farm
upper bound proving the EOD shed cannot discard carried/harvested cargo.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

import r04_full_router as base

SHEEP_MAX_HELD = 6
STANDARD_CONFIG = {
    "episodeSteps": 720,
    "boardSize": 10,
    "turnsPerDay": 24,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}
_MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
_MARKET_VERBS = {
    "HIRE", "BUY_LAND", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL",
}
_MISSING = object()
telemetry = Counter()


def _cfg(configuration: Any, name: str, default: Any) -> Any:
    if configuration is None:
        return default
    try:
        if isinstance(configuration, dict):
            return configuration.get(name, default)
        return getattr(configuration, name, default)
    except Exception:
        return _MISSING


def _standard_configuration(configuration: Any) -> bool:
    for name, expected in STANDARD_CONFIG.items():
        actual = _cfg(configuration, name, _MISSING)
        if actual is _MISSING or type(actual) is not type(expected) or actual != expected:
            return False
    return True


def _commands(action: Any):
    if not isinstance(action, dict):
        return None
    farmer = action.get("farmer", _MISSING)
    hands = action.get("hands", _MISSING)
    if (not isinstance(farmer, list) or not farmer
            or not isinstance(hands, list)
            or any(not isinstance(command, list) or not command for command in hands)):
        return None
    return [farmer, *hands]


def _strict_position(position: Any):
    if (not isinstance(position, (list, tuple)) or len(position) != 2
            or type(position[0]) is not int or type(position[1]) is not int):
        return None
    x, y = position
    size = STANDARD_CONFIG["boardSize"]
    if not (0 <= x < size and 0 <= y < size):
        return None
    return x, y


def _strict_targets(targets: Any):
    if not isinstance(targets, list) or not targets:
        return None
    result = []
    for target in targets:
        site = _strict_position(target)
        if site is None:
            return None
        result.append(site)
    return result


def _strict_inventory_total(mapping: Any) -> int | None:
    if not isinstance(mapping, dict):
        return None
    total = 0
    for item, quantity in mapping.items():
        if not isinstance(item, str) or type(quantity) is not int or quantity < 0:
            return None
        total += quantity
    return total


def _strict_sheep(tile: Any):
    if (not isinstance(tile, dict) or tile.get("kind") != "PASTURE"
            or tile.get("animal") != "SHEEP"):
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
    if type(units) is not int or not 0 <= units <= SHEEP_MAX_HELD:
        return None
    if type(consecutive_unfed) is not int or consecutive_unfed < 0:
        return None
    if type(fed) is not bool or type(cared) is not bool or type(fertilizer) is not bool:
        return None
    if type(bonus) is not int or bonus < 0:
        return None
    return fed, cared


def _return_move(position: Any, inventory: Any):
    if _strict_position(position) is None or not isinstance(inventory, dict):
        return None
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
    command = base._v219_walk(pos, home)
    if not isinstance(command, list) or len(command) != 1 or command[0] not in _MOVES:
        return None
    return command


def _service(tile: Any, inventory: Any):
    sheep = _strict_sheep(tile)
    if sheep is None or not isinstance(inventory, dict):
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


def _harvest_upper_bound(tile: Any) -> int | None:
    """Exact upper bound on physical units the official HARVEST can add now."""
    if not isinstance(tile, dict):
        return 0
    units = tile.get("yield_units", 0)
    if type(units) is not int or units < 0:
        return None
    return units


def _market_has_physical_inflow(action: Any) -> bool | None:
    """Return True for executable shed inflow, False for none, None on ambiguity."""
    if not isinstance(action, dict):
        return None
    market = action.get("market", _MISSING)
    if not isinstance(market, list):
        return None
    limit = STANDARD_CONFIG["maxMarketOrdersPerTurn"]
    for order in market[:limit]:
        if not isinstance(order, list):
            return None
        if not order:
            continue
        op = order[0]
        if type(op) is not str or op not in _MARKET_VERBS:
            return None
        # Official BUY_SEED writes private["seeds"], not physical shed/worker stock.
        if op in ("BUY_PRODUCT", "BUY_ANIMAL"):
            return True
    return False


def apply_v233_eod_service(
    action: Any,
    observation: Any,
    configuration=None,
    *,
    enabled=False,
):
    """Return a candidate action; every no-match/ambiguity preserves parent identity."""
    if enabled is not True:
        return action
    if not _standard_configuration(configuration):
        telemetry["nonstandard_configuration"] += 1
        return action
    if not isinstance(observation, dict):
        return action

    try:
        step = observation["step"]
        day = observation["day"]
        hour = observation["hour"]
        player = observation["player"]
        farms = observation["farms"]
        private = observation["private"]
    except (KeyError, TypeError):
        return action

    if (type(step) is not int or type(day) is not int or type(hour) is not int
            or day != step // STANDARD_CONFIG["turnsPerDay"]
            or hour != step % STANDARD_CONFIG["turnsPerDay"]
            or hour != STANDARD_CONFIG["turnsPerDay"] - 1
            or not 12 <= day <= 28):
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
    size = STANDARD_CONFIG["boardSize"]
    if (not isinstance(farmer, (list, tuple))
            or not isinstance(hands, list)
            or not isinstance(tiles, list) or len(tiles) != size
            or any(not isinstance(row, list) or len(row) != size for row in tiles)
            or not isinstance(inventories, list)):
        return action

    positions = [farmer, *hands]
    commands = _commands(action)
    if (commands is None or len(commands) != len(positions)
            or len(inventories) != len(positions)):
        return action

    normalized_positions = []
    actor_tiles = []
    carried_total = 0
    for position, inventory in zip(positions, inventories):
        site = _strict_position(position)
        subtotal = _strict_inventory_total(inventory)
        if site is None or subtotal is None:
            return action
        normalized_positions.append(site)
        actor_tiles.append(tiles[site[1]][site[0]])
        carried_total += subtotal

    shed_total = _strict_inventory_total(shed)
    if shed_total is None:
        return action

    market_inflow = _market_has_physical_inflow(action)
    if market_inflow is None:
        return action
    if market_inflow:
        telemetry["market_inflow_block"] += 1
        return action

    states = getattr(base, "_V233_STATES", None)
    if not isinstance(states, dict):
        return action
    state = states.get(player)
    if (not isinstance(state, dict) or state.get("committed") is not True
            or state.get("last_step") != step or state.get("day") != day):
        return action
    workers = state.get("workers")
    work = state.get("work")
    if not isinstance(workers, dict) or not isinstance(work, dict):
        return action

    parsed_targets = {}
    for actor, targets in workers.items():
        if type(actor) is not int or actor <= 0 or actor >= len(commands):
            return action
        parsed = _strict_targets(targets)
        if parsed is None:
            return action
        parsed_targets[actor] = parsed

    candidates = []
    for actor, command in enumerate(commands):
        targets = parsed_targets.get(actor)
        if targets is None:
            continue
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

    for actor, site, _service_command in candidates:
        for other, (other_site, other_command) in enumerate(zip(normalized_positions, commands)):
            if other != actor and other_site == site and other_command != ["PASS"]:
                telemetry["stacked_worker_block"] += 1
                return action

    candidate_actors = {actor for actor, _site, _service_command in candidates}
    unit_inflow_upper_bound = 0
    for actor, (command, tile) in enumerate(zip(commands, actor_tiles)):
        if actor in candidate_actors:
            continue
        op = command[0]
        if op == "HARVEST":
            gain = _harvest_upper_bound(tile)
            if gain is None:
                return action
            unit_inflow_upper_bound += gain
        elif op == "COLLECT_FERTILIZER":
            unit_inflow_upper_bound += 1

    if (shed_total + carried_total + unit_inflow_upper_bound
            > STANDARD_CONFIG["shedCapacity"]):
        telemetry["capacity_block"] += 1
        return action

    result = copy.deepcopy(action)
    result_commands = [result["farmer"], *result["hands"]]
    for actor, _site, service_command in candidates:
        result_commands[actor] = list(service_command)
        work[actor]["command"] = list(service_command)
        telemetry["activations"] += 1
        telemetry["feed_salvaged" if service_command == ["FEED"] else "care_salvaged"] += 1
    result["farmer"], result["hands"] = result_commands[0], result_commands[1:]
    return result


def install(parent, *, enabled=False):
    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return apply_v233_eod_service(
            action, observation, configuration, enabled=enabled,
        )

    agent.telemetry = telemetry
    return agent
