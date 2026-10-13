"""Two workers on one tile: sequential, not exclusive.

`_apply_unit_action` applies each worker's op in order to the tile as the previous
workers left it. Different actions on a shared tile can therefore all advance, and
the prompt must not tell the model otherwise. These cases are built with the
engine's own constructors and judged by the engine's own state.

Run: python -B tests/test_paired_workers.py
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cards
import constraints
from constraints import engine

FAIL = []


def check(name, cond, detail=""):
    ok = bool(cond)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAIL.append(name)


def _two_workers_on(card, x, y, tile):
    c = copy.deepcopy(card)
    seat = c["seat"]
    farm = c["observation"]["farms"][seat]
    farm["farmer"] = [x, y]
    farm["hands"] = [[x, y]]
    farm["tiles"][y][x] = tile
    invs = c["observation"]["private"].setdefault("inventories", [{}])
    while len(invs) < 2:
        invs.append({})
    return c


def case_feed_then_care(card):
    """FEED by one worker and CARE by the other both apply to the same animal."""
    K = engine()
    c = _two_workers_on(card, *_empty(card), K._new_animal("GOOSE", int(card["observation"]["day"])))
    seat = c["seat"]
    c["observation"]["private"]["inventories"][0] = {"WHEAT": 2}
    act = {"farmer": ["FEED"], "hands": [["CARE"]], "market": []}
    eff = constraints.unit_effects(c["observation"], c["configuration"], seat, act)
    check("FEED then CARE: both ops act", all(e["non_no_op"] for e in eff),
          f"{[(e['action'], e['non_no_op']) for e in eff]}")
    r = constraints.evaluate_turn(c["observation"], c["configuration"], seat, act)
    x, y = c["observation"]["farms"][seat]["farmer"]
    # replay the unit phase to read the tile the workers left
    farm = copy.deepcopy(c["observation"]["farms"][seat])
    priv = copy.deepcopy(c["observation"]["private"])
    for i, a in enumerate([act["farmer"]] + act["hands"]):
        K._apply_unit_action(farm, priv, i, list(a), int(c["configuration"]["boardSize"]),
                             int(c["observation"]["day"]),
                             int(c["configuration"]["turnsPerDay"]),
                             int(c["configuration"]["shedCapacity"]))
    t = farm["tiles"][y][x]
    check("FEED then CARE: both daily flags are set",
          t.get("fed_today") and t.get("cared_today"),
          f"fed={t.get('fed_today')} cared={t.get('cared_today')}")

    dup = {"farmer": ["CARE"], "hands": [["CARE"]], "market": []}
    effd = constraints.unit_effects(c["observation"], c["configuration"], seat, dup)
    check("CARE then CARE: the second does nothing",
          effd[0]["non_no_op"] and not effd[1]["non_no_op"],
          f"{[(e['action'], e['non_no_op']) for e in effd]}")


def case_fertilize_then_water(card):
    """FERTILIZE by one worker makes the other's WATER worth 2 instead of 1."""
    K = engine()
    day = int(card["observation"]["day"])
    tpd = int(card["configuration"]["turnsPerDay"])
    x, y = _empty(card)

    def build(with_fertilizer):
        tile = K._new_plant("WHEAT", day - 2, tpd)   # age 2 is inside WHEAT's 2-4d window
        tile["yield_units"] = 0
        tile["watered_today"] = False
        c = _two_workers_on(card, x, y, tile)
        c["observation"]["private"]["inventories"][0] = (
            {"FERTILIZER": 1} if with_fertilizer else {})
        return c

    def yield_after(c, act):
        farm = copy.deepcopy(c["observation"]["farms"][c["seat"]])
        priv = copy.deepcopy(c["observation"]["private"])
        for i, a in enumerate([act["farmer"]] + act["hands"]):
            K._apply_unit_action(farm, priv, i, list(a), int(c["configuration"]["boardSize"]),
                                 day, tpd, int(c["configuration"]["shedCapacity"]))
        return farm["tiles"][y][x]["yield_units"]

    both = build(True)
    y_both = yield_after(both, {"farmer": ["FERTILIZE"], "hands": [["WATER"]], "market": []})
    water_only = build(False)
    y_water = yield_after(water_only, {"farmer": ["PASS"], "hands": [["WATER"]], "market": []})
    check("FERTILIZE then WATER on one tile beats WATER alone",
          y_both == 2 and y_water == 1, f"fertilize+water={y_both} water only={y_water}")

    eff = constraints.unit_effects(both["observation"], both["configuration"], both["seat"],
                                   {"farmer": ["FERTILIZE"], "hands": [["WATER"]], "market": []})
    check("FERTILIZE then WATER: both ops act", all(e["non_no_op"] for e in eff),
          f"{[(e['action'], e['non_no_op']) for e in eff]}")


def case_dig_spares_animals(card):
    """DIG removes a plant or an empty structure but never an installed animal."""
    K = engine()
    day = int(card["observation"]["day"])
    x, y = _empty(card)
    c = _two_workers_on(card, x, y, K._new_animal("GOOSE", day))
    seat = c["seat"]
    adm = constraints.admissible(c["observation"], c["configuration"], seat)
    check("DIG is not admissible on an installed animal",
          ["DIG"] not in adm["units"][0], f"{[o for o in adm['units'][0] if o[0] == 'DIG']}")
    c2 = _two_workers_on(card, x, y, {"kind": "COOP"})
    adm2 = constraints.admissible(c2["observation"], c2["configuration"], c2["seat"])
    check("DIG IS admissible on an empty coop", ["DIG"] in adm2["units"][0])


def _empty(card):
    tiles = card["observation"]["farms"][card["seat"]]["tiles"]
    for yy in range(len(tiles)):
        for xx in range(len(tiles[0])):
            if tiles[yy][xx] is None:
                return xx, yy
    raise RuntimeError("no empty tile")


def main():
    card = cards.capture(7700001, [150], seat=0)[0]
    case_feed_then_care(card)
    case_fertilize_then_water(card)
    case_dig_spares_animals(card)
    print()
    if FAIL:
        print(f"{len(FAIL)} FAILED: {FAIL}")
        return 1
    print("paired-worker semantics hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
