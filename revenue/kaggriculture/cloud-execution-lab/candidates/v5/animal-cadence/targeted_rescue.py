# SPDX-License-Identifier: Apache-2.0
"""Target-aware planner for TITAN V5's existing V217 starvation rescue.

The current V217 code treats *any* later FEED in the authored route as proof
that every starving animal is covered.  This helper conservatively projects the
actual tile of each later FEED and permits a rescue only for an uncovered own
animal.  It never buys wheat or animals and never guesses through queued work,
locked cells, or weeds that could shift the authored tail.

The module is deliberately not wired into the canonical runtime.  It is a
same-family candidate primitive for the production-v3 R04 controller.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

_MOVES = {
    "EAST": (1, 0),
    "WEST": (-1, 0),
    "SOUTH": (0, 1),
    "NORTH": (0, -1),
}
_OPPOSITE = {"EAST": "WEST", "WEST": "EAST", "SOUTH": "NORTH", "NORTH": "SOUTH"}
_ANIMALS = frozenset(("GOOSE", "COW", "SHEEP"))


@dataclass(frozen=True)
class Coverage:
    feed_targets: frozenset[tuple[int, int]]
    future_feed_count: int


@dataclass(frozen=True)
class RescuePlan:
    target: tuple[int, int]
    commands: tuple[tuple, ...]
    positions: tuple[tuple[int, int], ...]
    needs_pickup: bool


def _position(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or type(value[0]) is not int or type(value[1]) is not int):
        return None
    return (value[0], value[1])


def _commands(action, actors):
    if not isinstance(action, Mapping):
        return None
    farmer = action.get("farmer")
    hands = action.get("hands")
    if not isinstance(farmer, list) or not farmer or not isinstance(hands, list):
        return None
    result = [farmer, *hands]
    if len(result) != actors or any(not isinstance(c, list) or not c for c in result):
        return None
    return result


def _tile(tiles, position):
    x, y = position
    if y < 0 or y >= len(tiles) or not isinstance(tiles[y], list):
        return None, False
    row = tiles[y]
    if x < 0 or x >= len(row):
        return None, False
    return row[x], True


def _advance(tiles, position, command):
    if command[0] not in _MOVES:
        return position
    dx, dy = _MOVES[command[0]]
    nxt = (position[0] + dx, position[1] + dy)
    tile, valid = _tile(tiles, nxt)
    # A move into a weed can be consumed by repair_weeds and shift the tail.
    if not valid or tile == "LOCKED" or (isinstance(tile, Mapping) and tile.get("kind") == "WEED"):
        return None
    return nxt


def _public_context(observation, selected):
    if not isinstance(observation, Mapping):
        return None
    step = observation.get("step")
    player = observation.get("player")
    farms = observation.get("farms")
    if type(step) is not int or step < 0 or type(player) is not int or not isinstance(farms, list):
        return None
    if not 0 <= player < len(farms) or not isinstance(farms[player], Mapping):
        return None
    farm = farms[player]
    hands = farm.get("hands")
    tiles = farm.get("tiles")
    if not isinstance(hands, list) or not isinstance(tiles, list):
        return None
    positions = [_position(farm.get("farmer")), *[_position(p) for p in hands]]
    if any(p is None for p in positions):
        return None
    current = _commands(selected, len(positions))
    if current is None:
        return None
    return step, player, farm, tiles, list(positions), current


def coverage_from_tail(observation, selected, route_tail: Sequence[Mapping], *, turns_per_day=24):
    """Return exact same-day future FEED target coverage, or ``None`` if ambiguous.

    ``route_tail`` starts at the next callback.  The actually selected current
    command is projected first.  Only callbacks remaining in the current day
    are examined.  Callers with any outstanding delayed queue must not use this
    result to relax the existing V217 veto.
    """
    if type(turns_per_day) is not int or turns_per_day <= 0 or not isinstance(route_tail, Sequence):
        return None
    context = _public_context(observation, selected)
    if context is None:
        return None
    step, _, _, tiles, positions, current = context

    for actor, command in enumerate(current):
        nxt = _advance(tiles, positions[actor], command)
        if nxt is None:
            return None
        positions[actor] = nxt

    day_end = ((step // turns_per_day) + 1) * turns_per_day
    max_future = max(0, day_end - (step + 1))
    targets = set()
    count = 0
    for action in route_tail[:max_future]:
        commands = _commands(action, len(positions))
        if commands is None:
            return None
        for actor, command in enumerate(commands):
            if command[0] == "FEED":
                tile, valid = _tile(tiles, positions[actor])
                if not valid or not isinstance(tile, Mapping) or tile.get("animal") not in _ANIMALS:
                    return None
                targets.add(positions[actor])
                count += 1
        for actor, command in enumerate(commands):
            nxt = _advance(tiles, positions[actor], command)
            if nxt is None:
                return None
            positions[actor] = nxt
    return Coverage(frozenset(targets), count)


def uncovered_starving_targets(observation, coverage: Coverage):
    """Return starving own-animal coordinates not covered by a future FEED."""
    if not isinstance(observation, Mapping) or not isinstance(coverage, Coverage):
        return None
    player = observation.get("player")
    farms = observation.get("farms")
    if type(player) is not int or not isinstance(farms, list) or not 0 <= player < len(farms):
        return None
    farm = farms[player]
    if not isinstance(farm, Mapping) or not isinstance(farm.get("tiles"), list):
        return None
    result = []
    for y, row in enumerate(farm["tiles"]):
        if not isinstance(row, list):
            return None
        for x, tile in enumerate(row):
            if not isinstance(tile, Mapping) or tile.get("animal") not in _ANIMALS:
                continue
            strikes = tile.get("consecutive_unfed")
            if type(strikes) is not int or strikes < 0:
                return None
            position = (x, y)
            if strikes >= 1 and tile.get("fed_today") is False and position not in coverage.feed_targets:
                result.append(position)
    return tuple(result)


def _beside_shed(tiles, position):
    center = len(tiles) // 2
    return position[0] in (center - 1, center) and position[1] in (center - 1, center)


def _reserved_wheat(route_tail, actors, limit):
    reserved = 0
    for action in route_tail[:limit]:
        commands = _commands(action, actors)
        if commands is None:
            return None
        for command in commands:
            if len(command) >= 2 and command[:2] == ["PICKUP", "WHEAT"]:
                quantity = command[2] if len(command) > 2 else 1
                if type(quantity) is not int or quantity < 0:
                    return None
                reserved += quantity
    return reserved


def _path(tiles, start, target):
    x, y = start
    tx, ty = target
    result = []
    while x != tx:
        move = "EAST" if x < tx else "WEST"
        nxt = _advance(tiles, (x, y), [move])
        if nxt is None:
            return None
        x, y = nxt
        result.append(move)
    while y != ty:
        move = "SOUTH" if y < ty else "NORTH"
        nxt = _advance(tiles, (x, y), [move])
        if nxt is None:
            return None
        x, y = nxt
        result.append(move)
    return result


def plan_targeted_rescue(
        observation,
        selected,
        route_tail: Sequence[Mapping],
        *,
        queues_empty,
        turns_per_day=24,
):
    """Return ``(RescuePlan | None, reason)`` for one uncovered starving animal.

    This mirrors V217's bounded late-day, farmer-only, return-to-origin rescue
    but replaces the global "any future FEED" veto with tile-specific coverage.
    It is *strictly additive*: if queues exist, tail projection is ambiguous, the
    farmer is not currently PASS, wheat custody is unclear, or the authored
    farmer tail cannot fit the full round trip, the function returns no plan.
    """
    if queues_empty is not True:
        return None, "queued_work"
    if type(turns_per_day) is not int or turns_per_day <= 0 or not isinstance(route_tail, Sequence):
        return None, "malformed_route_tail"
    context = _public_context(observation, selected)
    if context is None:
        return None, "malformed_context"
    step, player, farm, tiles, positions, current = context
    hour = step % turns_per_day
    if not 16 <= hour <= 21:
        return None, "outside_rescue_window"
    if current[0] != ["PASS"]:
        return None, "farmer_busy"

    coverage = coverage_from_tail(observation, selected, route_tail, turns_per_day=turns_per_day)
    if coverage is None:
        return None, "ambiguous_feed_coverage"
    targets = uncovered_starving_targets(observation, coverage)
    if targets is None:
        return None, "malformed_starvation_state"
    if not targets:
        return None, "all_starving_targets_covered"

    private = observation.get("private")
    if not isinstance(private, Mapping):
        return None, "malformed_private_context"
    inventories = private.get("inventories")
    shed = private.get("shed")
    if (not isinstance(inventories, list) or len(inventories) != len(positions)
            or any(not isinstance(inv, Mapping) for inv in inventories) or not isinstance(shed, Mapping)):
        return None, "malformed_private_context"
    wheat = inventories[0].get("WHEAT", 0)
    if type(wheat) is not int or wheat < 0:
        return None, "malformed_wheat_inventory"
    needs_pickup = wheat < 1
    if needs_pickup and any(type(v) is not int or v < 0 or v for v in inventories[0].values()):
        return None, "farmer_carrying_other_stock"
    if needs_pickup and not _beside_shed(tiles, positions[0]):
        return None, "farmer_not_at_shed"

    market = selected.get("market")
    if not isinstance(market, list):
        return None, "malformed_market"
    if needs_pickup and any(isinstance(order, list) and len(order) > 1 and order[1] == "WHEAT" for order in market):
        return None, "same_turn_wheat_market"

    day_end = ((step // turns_per_day) + 1) * turns_per_day
    callbacks_left = day_end - step
    reserved = _reserved_wheat(route_tail, len(positions), max(0, callbacks_left - 1))
    if reserved is None:
        return None, "ambiguous_wheat_reserve"
    shed_wheat = shed.get("WHEAT", 0)
    if type(shed_wheat) is not int or shed_wheat < 0:
        return None, "malformed_wheat_inventory"
    if needs_pickup and shed_wheat < reserved + 1:
        return None, "wheat_reserved"

    # Closest target first, stable y/x tie break like V217's existing planner.
    start = positions[0]
    ranked = sorted(targets, key=lambda p: (abs(p[0] - start[0]) + abs(p[1] - start[1]), p[1], p[0]))
    for target in ranked:
        outward = _path(tiles, start, target)
        if outward is None:
            continue
        commands = ([("PICKUP", "WHEAT")] if needs_pickup else [])
        commands += [(m,) for m in outward]
        commands += [("FEED",)]
        commands += [(_OPPOSITE[m],) for m in reversed(outward)]
        if len(commands) > callbacks_left:
            continue
        # Current callback already checked via selected farmer PASS. Every later
        # occupied callback must also be an authored farmer PASS.
        safe = True
        for index in range(1, len(commands)):
            if index - 1 >= len(route_tail):
                safe = False
                break
            future = _commands(route_tail[index - 1], len(positions))
            if future is None or future[0] != ["PASS"]:
                safe = False
                break
        if not safe:
            continue
        projected = []
        pos = start
        for command in commands:
            projected.append(pos)
            nxt = _advance(tiles, pos, command)
            if nxt is None:
                safe = False
                break
            pos = nxt
        if not safe or pos != start:
            continue
        return RescuePlan(target, tuple(commands), tuple(projected), needs_pickup), "target_uncovered"
    return None, "no_safe_round_trip"
