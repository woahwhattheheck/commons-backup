# SPDX-License-Identifier: Apache-2.0
"""V4 H3b: reprioritize an existing V233 sheep HARVEST before max-held clipping.

This is the repaired H3b theorem from #12457, ported as a V4 default-OFF
post-policy transform. It never adds workers, animals, land, seed, market rows,
or service work. A V233 sheep worker may only swap one already-authored
HARVEST target for another sheep in the same assigned block when that sheep is
provably due to lose held WOOL at tonight's production refresh. Movement
reroutes are restricted to an adjacent urgent sheep: V233 reselects its target
every callback, so a longer walk is not persistence-safe without a target lock.

Disabled, malformed, nonstandard, stale-snapshot, service-debt, cargo-return,
setup, final-day, and unreachable paths preserve the exact parent action object.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

import r04_full_router as base

SHEEP_FIRST_YIELD_DAY = 6
SHEEP_INTERVAL = 3
SHEEP_MAX_HELD = 6
STANDARD_CONFIG = {
    "episodeSteps": 720,
    "boardSize": 10,
    "turnsPerDay": 24,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}

telemetry = Counter()
_MISSING = object()


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


def _strict_sheep(tile: Any):
    if (not isinstance(tile, dict) or tile.get("kind") != "PASTURE"
            or tile.get("animal") != "SHEEP"):
        return None
    placed = tile.get("placed_day", _MISSING)
    units = tile.get("yield_units", _MISSING)
    fed = tile.get("fed_today", _MISSING)
    cared = tile.get("cared_today", _MISSING)
    bonus = tile.get("pending_care_bonus", _MISSING)
    if type(placed) is not int or placed < 0:
        return None
    if type(units) is not int or not 0 <= units <= SHEEP_MAX_HELD:
        return None
    if type(fed) is not bool or type(cared) is not bool:
        return None
    if type(bonus) is not int or bonus < 0:
        return None
    return placed, units, fed, cared, bonus


def _overflow_at_next_refresh(tile: Any, day: int) -> int | None:
    state = _strict_sheep(tile)
    if state is None:
        return None
    placed, units, fed, _cared, bonus = state
    next_day = day + 1
    days_since_first = next_day - placed - SHEEP_FIRST_YIELD_DAY
    if days_since_first < 0 or days_since_first % SHEEP_INTERVAL != 0:
        return 0
    produced = 1 + (bonus if fed else 0)
    if units <= 0:
        return 0
    return max(0, units + produced - SHEEP_MAX_HELD)


def _commands(action: Any):
    if not isinstance(action, dict):
        return None
    farmer = action.get("farmer", _MISSING)
    hands = action.get("hands", _MISSING)
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return None
    if not farmer or any(not isinstance(command, list) for command in hands):
        return None
    return [farmer, *list(hands)]


def apply_h3b_sheep_clip(action: Any, observation: Any, configuration=None, *, enabled=False):
    """Apply repaired H3b; no-match and malformed paths preserve identity."""
    if enabled is not True:
        return action
    if not _standard_configuration(configuration):
        telemetry["nonstandard_configuration"] += 1
        return action
    if not isinstance(observation, dict):
        return action
    try:
        step = observation["step"]
        player = observation["player"]
        if type(step) is not int or type(player) is not int or player not in (0, 1):
            return action
        day = step // 24
        hour = step % 24
        # V233 has final-day cargo behavior and there is no useful post-season refresh.
        if day < 12 or day >= 29:
            return action
        farm = observation["farms"][player]
        private = observation["private"]
        tiles = farm["tiles"]
        positions = [farm["farmer"], *(farm.get("hands") or [])]
        inventories = private["inventories"]
        state = base._V233_STATES.get(player)
    except (KeyError, TypeError, IndexError, AttributeError):
        return action

    if not isinstance(tiles, list) or not isinstance(positions, list) or not isinstance(inventories, list):
        return action
    if (
        not isinstance(state, dict)
        or state.get("committed") is not True
        or state.get("last_step") != step
    ):
        return action
    workers = state.get("workers")
    work = state.get("work")
    if not isinstance(workers, dict) or not isinstance(work, dict):
        return action
    commands = _commands(action)
    if commands is None or len(commands) != len(positions) or len(inventories) != len(positions):
        return action

    replacements: list[tuple[int, list[str], int]] = []
    for actor, targets in workers.items():
        if type(actor) is not int or actor <= 0 or actor >= len(positions) or actor >= len(inventories):
            return action
        if not isinstance(targets, list) or not targets:
            return action
        snapshot = work.get(actor)
        if not isinstance(snapshot, dict) or snapshot.get("step") != step:
            return action
        parent_command = snapshot.get("command")
        if not isinstance(parent_command, list) or commands[actor] != parent_command:
            # A later layer already changed the worker, or V233 accounting is stale.
            return action
        if parent_command != ["HARVEST"]:
            # H3b is harvest-for-harvest only; never preempt FEED/CARE/etc.
            continue
        inventory = inventories[actor]
        if not isinstance(inventory, dict):
            return action
        if any(type(inventory.get(item, 0)) is not int or inventory.get(item, 0) < 0
               for item in ("WOOL", "FERTILIZER")):
            return action
        if inventory.get("WOOL", 0) or inventory.get("FERTILIZER", 0):
            continue

        parsed = []
        for order, target in enumerate(targets):
            if (not isinstance(target, (list, tuple)) or len(target) != 2
                    or type(target[0]) is not int or type(target[1]) is not int):
                return action
            x, y = target
            if y < 0 or y >= len(tiles) or not isinstance(tiles[y], list) or x < 0 or x >= len(tiles[y]):
                return action
            sheep = _strict_sheep(tiles[y][x])
            if sheep is None:
                # Do not trade setup/placement/dig work for H3b.
                parsed = []
                break
            placed, units, fed, cared, bonus = sheep
            if not fed or not cared:
                # Preserve survival and care/feed compounding work.
                parsed = []
                break
            overflow = _overflow_at_next_refresh(tiles[y][x], day)
            if overflow is None:
                return action
            parsed.append((order, (x, y), units, overflow, placed, bonus))
        if not parsed:
            continue

        urgent = [row for row in parsed if row[3] > 0]
        if not urgent:
            continue
        pos = positions[actor]
        if (not isinstance(pos, (list, tuple)) or len(pos) != 2
                or type(pos[0]) is not int or type(pos[1]) is not int):
            return action
        board_size = STANDARD_CONFIG["boardSize"]
        if not (0 <= pos[0] < board_size and 0 <= pos[1] < board_size):
            return action

        # V233 chooses min(tasks) afresh on every callback.  H3b has no target
        # latch, so a multi-step detour can be immediately reversed by V233 and
        # lose both the parent harvest and the clipping rescue.  Restrict movement
        # overrides to an adjacent urgent target; after that one move the next
        # callback sees distance zero and V233 itself authors HARVEST there.
        remaining_callbacks = 24 - hour
        reachable = []
        for row in urgent:
            distance = abs(pos[0] - row[1][0]) + abs(pos[1] - row[1][1])
            if distance == 0 or (distance == 1 and remaining_callbacks >= 2):
                reachable.append(row)
        if not reachable:
            telemetry["deadline_declines"] += 1
            continue

        reachable.sort(key=lambda row: (
            -row[3],
            abs(pos[0] - row[1][0]) + abs(pos[1] - row[1][1]),
            row[0],
        ))
        _order, target, _units, overflow, _placed, _bonus = reachable[0]
        desired = base._v219_walk(tuple(pos), target) or ["HARVEST"]
        if commands[actor] == desired:
            telemetry["already_prioritized"] += 1
            continue
        replacements.append((actor, desired, overflow))

    if not replacements:
        return action

    result = copy.deepcopy(action)
    result_commands = [result["farmer"], *result["hands"]]
    for actor, desired, _overflow in replacements:
        if actor >= len(result_commands):
            return action
        result_commands[actor] = list(desired)
    result["farmer"], result["hands"] = result_commands[0], result_commands[1:]

    # Keep V233 physical-harvest accounting aligned with what was emitted.
    for actor, desired, overflow in replacements:
        work[actor]["command"] = list(desired)
        telemetry["overrides"] += 1
        telemetry["overflow_units_at_risk"] += overflow
    return result


def install(parent, *, enabled=False):
    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return apply_h3b_sheep_clip(action, observation, configuration, enabled=enabled)

    agent.telemetry = telemetry
    return agent
