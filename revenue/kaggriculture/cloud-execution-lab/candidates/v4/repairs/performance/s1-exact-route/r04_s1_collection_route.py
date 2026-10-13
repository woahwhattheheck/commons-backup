# SPDX-License-Identifier: Apache-2.0
"""Bounded, deterministic collection routing for the V4 S1 hand.

This is source-only support, not a policy/default change. Targets must be the
already-admitted S1 animal tiles. Distances use the incumbent Manhattan model;
this module does not prove tile traversability, ownership, market economics or
future animal survival. One collection consumes one callback. The last target
needs no return trip because S1 relies on the existing EOD auto-drop contract.

Exactness is scoped to an unobstructed 10x10 grid, <=9 callbacks and <=6 distinct
collections. These are the post-HIRE S1 bounds (HIRE at hour >=14, first action
at >=15). Malformed or wider inputs return an empty plan, never an estimate.
"""
from __future__ import annotations

from functools import lru_cache

MAX_CALLBACKS = 9
MAX_COLLECTIONS = 6
BOARD_SIZE = 10


def _point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    x, y = value
    if (type(x) is not int or type(y) is not int
            or not (0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE)):
        return None
    return x, y


def plan_collection_route(start, targets, callbacks, *, max_collect=MAX_COLLECTIONS):
    """Return an exact max-count, then minimum-cost tuple of target positions.

    Equal-count/equal-cost routes have deterministic distance/row/column tie
    breaking. Input order and duplicate coordinates cannot change the result.
    Targets and the caller's input collections are never modified.

    The cache is local to this call; no game/player observations are retained.
    Every recursion consumes a target plus >=1 callback. Distinct subsequent
    targets need >=2 callbacks (move + collect). The finite horizon therefore
    bounds recursion to five collections, including when starting on a target.
    """
    origin = _point(start)
    if (origin is None or not isinstance(targets, (list, tuple))
            or len(targets) > BOARD_SIZE * BOARD_SIZE
            or type(callbacks) is not int or not 0 <= callbacks <= MAX_CALLBACKS
            or type(max_collect) is not int or not 0 <= max_collect <= MAX_COLLECTIONS):
        return ()
    points = []
    for value in targets:
        point = _point(value)
        if point is None:
            return ()
        points.append(point)
    if not callbacks or not max_collect:
        return ()
    points = sorted(set(points), key=lambda p: (p[1], p[0]))
    # A target outside the initial Manhattan ball cannot be reached via another
    # target either (triangle inequality); filtering it preserves exactness.
    points = tuple(p for p in points
                   if abs(origin[0] - p[0]) + abs(origin[1] - p[1]) + 1 <= callbacks)
    if not points:
        return ()
    n = len(points)
    positions = points + (origin,)
    costs = tuple(tuple(abs(a[0] - b[0]) + abs(a[1] - b[1]) + 1
                        for b in points) for a in positions)
    orders = tuple(tuple(sorted(range(n), key=lambda j: (row[j], points[j][1], points[j][0])))
                   for row in costs)

    @lru_cache(maxsize=None)
    def solve(at, left, visited, slots):
        candidates = tuple(j for j in orders[at]
                           if not visited & (1 << j) and costs[at][j] <= left)
        if not candidates or not slots:
            return (), 0
        first_cost = costs[at][candidates[0]]
        upper = min(slots, len(candidates), 1 + (left - first_cost) // 2)
        lower_cost = first_cost + 2 * (upper - 1)
        best_path, best_cost = (), 0
        for j in candidates:
            cost = costs[at][j]
            branch_upper = min(slots, len(candidates), 1 + (left - cost) // 2)
            if branch_upper < len(best_path):
                continue
            tail, tail_cost = solve(j, left - cost, visited | (1 << j), slots - 1)
            path, used = (j,) + tail, cost + tail_cost
            if len(path) > len(best_path) or (len(path) == len(best_path) and used < best_cost):
                best_path, best_cost = path, used
            if len(best_path) == upper and best_cost == lower_cost:
                break
        return best_path, best_cost

    indices, _used = solve(n, callbacks, 0, max_collect)
    return tuple(points[j] for j in indices)
