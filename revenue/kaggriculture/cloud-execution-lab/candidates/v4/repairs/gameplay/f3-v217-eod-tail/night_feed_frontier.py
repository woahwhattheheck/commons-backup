# SPDX-License-Identifier: Apache-2.0
"""Opt-in F3 research: bounded, multi-target feed tails before the real reset.

This is a proposal generator, NOT a controller, runtime hook, or profit gate.
It uses only this player's observation, selected action, and incumbent route.
A proposal must be tested against ACTUAL future returned actions, full engine
transitions, and realized economics before integration. No donor is rewritten.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Any, Mapping, Sequence

STANDARD = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
            "shedCapacity": 100, "maxMarketOrdersPerTurn": 10}
MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}
ANIMALS = {"COW", "SHEEP", "GOOSE"}


@dataclass(frozen=True)
class FeedTail:
    seat: int
    step: int
    end: int  # exclusive: the final command triggers an ACTUAL night reset
    actor: int
    start: tuple[int, int]
    targets: tuple[tuple[int, int], ...]
    commands: tuple[tuple[str, ...], ...]
    positions: tuple[tuple[int, int], ...]  # position BEFORE each command
    wheat_cost: int
    search_pool_size: int
    truncated_pool: bool


def unit(action: Mapping[str, Any], actor: int) -> Any:
    """Match omitted-unit defaults without compacting or renumbering hands."""
    if actor == 0:
        return action.get("farmer", ["PASS"])
    hands = action.get("hands", [])
    if not isinstance(hands, list):
        return ["PASS"]
    return hands[actor - 1] if actor <= len(hands) else ["PASS"]


def _position(value: Any) -> tuple[int, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("invalid position")
    if any(type(x) is not int or not 0 <= x < 10 for x in value):
        raise ValueError("position outside pinned board")
    return value[0], value[1]


def _walk(start: tuple[int, int], target: tuple[int, int]) -> list[tuple[str, ...]]:
    # Stable horizontal-first Manhattan path; crossing LOCKED is engine-legal.
    x, y = start
    tx, ty = target
    return ([("EAST" if tx > x else "WEST",)] * abs(tx - x)
            + [("SOUTH" if ty > y else "NORTH",)] * abs(ty - y))


def _move(pos: tuple[int, int], row: Any) -> tuple[int, int]:
    if not isinstance(row, list) or not row or not isinstance(row[0], str):
        return pos
    dx, dy = MOVES.get(row[0], (0, 0))
    x, y = pos[0] + dx, pos[1] + dy
    return (x, y) if 0 <= x < 10 and 0 <= y < 10 else pos


def incumbent_feeds(positions: Sequence[tuple[int, int]], actions: Sequence[Mapping[str, Any]]) -> set[tuple[int, int]]:
    """Conservatively reserve ANY represented FEED, even if wheat is absent.

This avoids creating duplicate animal service. It can miss opportunities when
an incumbent FEED would be a no-op; it must not claim an exact fill forecast.
"""
    pos = list(positions)
    covered: set[tuple[int, int]] = set()
    for action in actions:
        # A later hire may give identity to a currently nonexistent hand. Its
        # future location is not certified by this narrow route-only model.
        hands = action.get("hands", [])
        if isinstance(hands, list) and any(isinstance(row, list) and row and row[0] == "FEED"
                                          for row in hands[max(0, len(pos) - 1):]):
            return {(x, y) for x in range(10) for y in range(10)}
        for actor in range(len(pos)):
            row = unit(action, actor)
            if isinstance(row, list) and row and row[0] == "FEED":
                covered.add(pos[actor])
            pos[actor] = _move(pos[actor], row)
    return covered


def propose_feed_tails(observation: Mapping[str, Any], selected: Mapping[str, Any],
                       route: Sequence[Mapping[str, Any]], configuration: Mapping[str, Any],
                       *, enabled: bool = False, max_targets: int = 3,
                       pool_limit: int = 6) -> tuple[FeedTail, ...]:
    """Return at most one deterministic best-count proposal per idle actor.

Only already carried wheat; no purchase, pickup, cash, sale, or shed assumption.
Only visible animals facing next-night escape. Every displaced incumbent unit
command through that night must be literal PASS. Actor identity/order is kept.
Search maximizes rescue COUNT (not value), then minimizes non-PASS actions, then
lexicographic target order, within an explicitly bounded candidate pool.
"""
    if enabled is not True:
        return ()
    if (type(max_targets) is not int or not 1 <= max_targets <= 3
            or type(pool_limit) is not int or not 1 <= pool_limit <= 6):
        raise ValueError("max_targets must be 1..3 and pool_limit 1..6")
    try:
        if any(type(configuration.get(k)) is not int or configuration[k] != v
               for k, v in STANDARD.items()):
            return ()
        step, seat = observation["step"], observation["player"]
        if (type(step) is not int or type(seat) is not int or seat not in (0, 1)
                or not 0 <= step < 696 or step % 24 < 16):
            return ()
        end = (step // 24 + 1) * 24
        if not isinstance(route, (list, tuple)) or len(route) < end:
            return ()
        actions = [selected, *route[step + 1:end]]
        if any(not isinstance(a, Mapping) for a in actions):
            return ()
        farm = observation["farms"][seat]
        positions = [_position(farm["farmer"]), *map(_position, farm["hands"])]
        inventories = observation["private"]["inventories"]
        if not isinstance(inventories, list) or len(inventories) != len(positions):
            return ()
        tiles = farm["tiles"]
        if len(tiles) != 10 or any(len(row) != 10 for row in tiles):
            return ()
        covered = incumbent_feeds(positions, actions)
        targets = [(x, y) for y, row in enumerate(tiles) for x, tile in enumerate(row)
                   if isinstance(tile, dict) and tile.get("animal") in ANIMALS
                   and tile.get("fed_today") is False
                   and type(tile.get("consecutive_unfed")) is int
                   and tile["consecutive_unfed"] >= 1 and (x, y) not in covered]
        out: list[FeedTail] = []
        for actor, start in enumerate(positions):
            wheat = inventories[actor].get("WHEAT", 0)
            if type(wheat) is not int or wheat <= 0:
                continue
            if any(unit(a, actor) != ["PASS"] for a in actions):
                continue
            reachable = sorted((t for t in targets if
                                abs(start[0] - t[0]) + abs(start[1] - t[1]) + 1 <= end - step),
                               key=lambda t: (abs(start[0] - t[0]) + abs(start[1] - t[1]), t))
            pool = reachable[:pool_limit]
            best = None
            for count in range(1, min(wheat, max_targets, len(pool)) + 1):
                for order in permutations(pool, count):
                    commands: list[tuple[str, ...]] = []
                    pos = start
                    for target in order:
                        commands.extend(_walk(pos, target))
                        commands.append(("FEED",))
                        pos = target
                    if len(commands) > end - step:
                        continue
                    key = (-count, len(commands), order)
                    if best is None or key < best[0]:
                        best = (key, order, tuple(commands))
            if best is None:
                continue
            _, order, commands = best
            commands += (("PASS",),) * (end - step - len(commands))
            pos = start
            expected = []
            for cmd in commands:
                expected.append(pos)
                pos = _move(pos, list(cmd))
            out.append(FeedTail(seat, step, end, actor, start, order, commands,
                                tuple(expected), len(order), len(pool), len(reachable) > pool_limit))
        return tuple(sorted(out, key=lambda p: (-len(p.targets), sum(c != ("PASS",) for c in p.commands),
                                              p.actor, p.targets)))
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        # Malformed/unfamiliar observations do not become a guessed forecast.
        return ()
