# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy


class M:
    LAND_ORDER = ["NE", "SW", "SE"]
    LAND_PRICES = [1000, 2000, 4000]
    CROPS = {
        "WHEAT": {"seed": 10, "first_yield_day": 2},
        "CARROT": {"seed": 20, "first_yield_day": 2},
        "MELON": {"seed": 80, "first_yield_day": 10},
    }
    ANIMALS = {"COW": {"cost": 400}}

    @staticmethod
    def _hire_cost(n, mult=1):
        a, b = 1, 1
        for _ in range(n):
            a, b = b, a + b
        return mult * a


def row(hands=0, market=None):
    return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(hands)],
            "market": [] if market is None else deepcopy(market)}


def observation(step=90, *, money=2000, unlocked=None, seeds=None, farmer=(4, 4), hands=()):
    tiles = [[None if x < 5 and y < 5 else "LOCKED" for x in range(10)] for y in range(10)]
    farm = {"farmer": list(farmer), "hands": [list(p) for p in hands], "money": money,
            "hires_today": len(hands), "unlocked_quadrants": ["NW"] if unlocked is None else list(unlocked),
            "tiles": tiles}
    private = {"shed": {}, "inventories": [{} for _ in range(1 + len(hands))],
               "seeds": {} if seeds is None else dict(seeds)}
    rival = {"farmer": [4, 4], "hands": [], "money": 1000, "hires_today": 0,
             "unlocked_quadrants": ["NW"], "tiles": deepcopy(tiles)}
    return {"step": step, "player": 0, "farms": [farm, rival], "private": private,
            "market": {"inventory": {"WHEAT": 10000}}}
