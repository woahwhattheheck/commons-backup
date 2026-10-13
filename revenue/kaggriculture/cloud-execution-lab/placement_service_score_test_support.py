# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy


class M:
    @staticmethod
    def _default_spawn(board):
        h = board // 2
        return (h - 1, h - 1)

    @staticmethod
    def _shed_access_tiles(board):
        h = board // 2
        return [(h - 1, h - 1), (h, h - 1), (h - 1, h), (h, h)]


def farm(*, unlocked=None):
    unlocked = ["NW"] if unlocked is None else list(unlocked)
    tiles = []
    for y in range(10):
        row = []
        for x in range(10):
            q = ("N" if y < 5 else "S") + ("W" if x < 5 else "E")
            row.append(None if q in unlocked else "LOCKED")
        tiles.append(row)
    return {
        "farmer": [4, 4], "hands": [], "money": 1000, "hires_today": 0,
        "unlocked_quadrants": unlocked, "tiles": tiles,
    }
