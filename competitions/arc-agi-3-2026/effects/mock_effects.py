"""Deterministic no-network held-out visual-effect fixtures."""
from __future__ import annotations

from random import Random

from factorizer import ActionSequence, Grid, _validate_grid


def grid(rows: list[list[int]]) -> Grid:
    return _validate_grid(rows)


def base_scene() -> Grid:
    g = [[0] * 9 for _ in range(9)]
    g[2][2] = g[2][3] = 2
    g[5][5] = 3
    g[5][6] = 3
    return grid(g)


def moved_scene() -> Grid:
    g = [list(r) for r in base_scene()]
    g[2][2] = g[2][3] = 0
    g[3][2] = g[3][3] = 2
    return grid(g)


def spawn_scene() -> Grid:
    g = [list(r) for r in base_scene()]
    g[6][2] = 4
    return grid(g)


def despawn_scene() -> Grid:
    g = [list(r) for r in base_scene()]
    g[5][5] = g[5][6] = 0
    return grid(g)


def recolor_scene() -> Grid:
    g = [list(r) for r in base_scene()]
    g[5][5] = g[5][6] = 7
    return grid(g)


def topology_before() -> Grid:
    g = [[0] * 9 for _ in range(9)]
    for x, y in ((3,3),(4,3),(5,3),(4,4),(4,5)):
        g[y][x] = 6
    return grid(g)


def topology_after() -> Grid:
    g = [list(r) for r in topology_before()]
    g[3][4] = 0
    return grid(g)


def ui_before() -> Grid:
    return grid([list(r) for r in base_scene()])


def ui_after() -> Grid:
    g = [list(r) for r in base_scene()]
    for x in range(2, 7):
        g[0][x] = 8
    return grid(g)


def camera_before() -> Grid:
    g = [[0] * 10 for _ in range(10)]
    g[2][2] = 2; g[2][3] = 2
    g[5][5] = 3; g[6][5] = 3
    g[7][2] = 4
    return grid(g)


def camera_after() -> Grid:
    g = [[0] * 10 for _ in range(10)]
    for x, y, c in ((3,2,2),(4,2,2),(6,5,3),(6,6,3),(3,7,4)):
        g[y][x] = c
    return grid(g)


def compound_scene() -> Grid:
    g = [list(r) for r in moved_scene()]
    g[6][2] = 4
    return grid(g)


def shuffled_action(seed: int) -> str:
    names = [f"ACTION{i}" for i in range(1, 8)]
    Random(seed).shuffle(names)
    return names[0]


def sequence(seed: int, before: Grid, frames: tuple[Grid, ...]) -> ActionSequence:
    return ActionSequence(shuffled_action(seed), before, frames)
