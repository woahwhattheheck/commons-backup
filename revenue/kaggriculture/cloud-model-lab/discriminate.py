"""Discriminating pairs: one field changes, the admissible set must change with it.

Each pair takes a REAL captured card and produces two variants that differ in
exactly one field -- a resource count, a per-day negation flag, or a maturity
deadline. The expected direction is not an invented optimality label: it is read
off the pinned engine, because both variants are run back through the engine's
own gates by `constraints.admissible`.

Tiles that need to exist for a case are built with the engine's own constructors
(`_new_plant`, `_new_animal`), never hand-assembled, so a variant is a state the
engine could itself have produced.
"""

import copy
import json

import constraints
from constraints import engine


def _place_unit(card, x, y):
    card["observation"]["farms"][card["seat"]]["farmer"] = [x, y]
    return card


def _unlocked_empty(card):
    """First unlocked empty tile, preferring one in the always-unlocked NW quadrant."""
    tiles = card["observation"]["farms"][card["seat"]]["tiles"]
    for y in range(len(tiles)):
        for x in range(len(tiles[0])):
            if tiles[y][x] is None:
                return x, y
    raise RuntimeError("no empty unlocked tile on this card")


def _variant(card, label, mutate):
    v = copy.deepcopy(card)
    v["card_id"] = f"{card['card_id']}::{label}"
    mutate(v)
    return v


def _has(adm_units, idx, op):
    return any(o == op for o in adm_units[idx])


# --------------------------------------------------------------------------
# The five pair builders, one per engine gate
# --------------------------------------------------------------------------

def pair_seed_stock(card):
    """Resource limit: seeds[WHEAT] 1 vs 0. PLANT WHEAT must follow the seed count."""
    x, y = _unlocked_empty(card)

    def base(v):
        _place_unit(v, x, y)

    def have(v):
        base(v)
        v["observation"]["private"]["seeds"]["WHEAT"] = 1

    def lack(v):
        base(v)
        v["observation"]["private"]["seeds"]["WHEAT"] = 0

    return {
        "name": "seed_stock",
        "kind": "resource",
        "changed_field": "private.seeds.WHEAT",
        "a": _variant(card, "seeds1", have),
        "b": _variant(card, "seeds0", lack),
        "op": ["PLANT", "WHEAT"],
        "unit": 0,
        "expect": "admissible in a, inadmissible in b",
    }


def pair_shed_capacity(card):
    """Resource limit: shed full vs room.

    BUY_PRODUCT and BUY_ANIMAL are gated on shed room; BUY_SEED is NOT, because
    seeds never enter the shed. Same one-field change, opposite consequences --
    the asymmetry is the discriminator.
    """
    cap = int(card["configuration"].get("shedCapacity", 100) or 100)

    def full(v):
        v["observation"]["private"]["shed"] = {"WHEAT": cap}

    def room(v):
        v["observation"]["private"]["shed"] = {"WHEAT": cap - 5}

    return {
        "name": "shed_capacity",
        "kind": "resource",
        "changed_field": "private.shed (full vs room)",
        "a": _variant(card, "shedroom", room),
        "b": _variant(card, "shedfull", full),
        "market_op": ["BUY_PRODUCT", "WHEAT", 1],
        "market_unaffected": ["BUY_SEED", "WHEAT", 1],
        "expect": "BUY_PRODUCT admissible in a only; BUY_SEED admissible in both",
    }


def pair_watered_negation(card):
    """Negation: watered_today False vs True on the same plant. WATER must follow."""
    K = engine()
    x, y = _unlocked_empty(card)
    day = int(card["observation"]["day"])
    tpd = int(card["configuration"].get("turnsPerDay", 24) or 24)

    def mk(v, watered):
        _place_unit(v, x, y)
        tile = K._new_plant("WHEAT", day, tpd)
        tile["watered_today"] = watered
        v["observation"]["farms"][v["seat"]]["tiles"][y][x] = tile

    return {
        "name": "watered_negation",
        "kind": "negation",
        "changed_field": "tile.watered_today",
        "a": _variant(card, "unwatered", lambda v: mk(v, False)),
        "b": _variant(card, "watered", lambda v: mk(v, True)),
        "op": ["WATER"],
        "unit": 0,
        "expect": "admissible in a, inadmissible in b",
    }


def pair_fed_negation(card):
    """Negation: fed_today False vs True, WHEAT held in both. FEED must follow."""
    K = engine()
    x, y = _unlocked_empty(card)
    day = int(card["observation"]["day"])

    def mk(v, fed):
        _place_unit(v, x, y)
        tile = K._new_animal("GOOSE", day)
        tile["fed_today"] = fed
        v["observation"]["farms"][v["seat"]]["tiles"][y][x] = tile
        v["observation"]["private"]["inventories"][0] = {"WHEAT": 3}

    return {
        "name": "fed_negation",
        "kind": "negation",
        "changed_field": "tile.fed_today",
        "a": _variant(card, "unfed", lambda v: mk(v, False)),
        "b": _variant(card, "fed", lambda v: mk(v, True)),
        "op": ["FEED"],
        "unit": 0,
        "expect": "admissible in a, inadmissible in b",
    }


def pair_maturity_deadline(card):
    """Deadline: planted_day set so age >= first_yield_day vs age < it.

    yield_units is > 0 in BOTH variants, so the only thing separating them is the
    maturity deadline the engine checks, not the presence of yield.
    """
    K = engine()
    x, y = _unlocked_empty(card)
    day = int(card["observation"]["day"])
    tpd = int(card["configuration"].get("turnsPerDay", 24) or 24)
    first = K.CROPS["WHEAT"]["first_yield_day"]

    def mk(v, age):
        _place_unit(v, x, y)
        tile = K._new_plant("WHEAT", day - age, tpd)
        tile["yield_units"] = 2
        v["observation"]["farms"][v["seat"]]["tiles"][y][x] = tile

    return {
        "name": "maturity_deadline",
        "kind": "deadline",
        "changed_field": f"tile.planted_day (age {first} vs {first - 1}, first_yield_day {first})",
        "a": _variant(card, f"age{first}", lambda v: mk(v, first)),
        "b": _variant(card, f"age{first - 1}", lambda v: mk(v, first - 1)),
        "op": ["HARVEST"],
        "unit": 0,
        "expect": "admissible in a, inadmissible in b",
    }


BUILDERS = [
    pair_seed_stock,
    pair_shed_capacity,
    pair_watered_negation,
    pair_fed_negation,
    pair_maturity_deadline,
]


def build_pairs(card):
    return [b(card) for b in BUILDERS]


def check_pair(pair):
    """Does the engine-derived admissible set move the way the gate says it must?"""
    out = {"name": pair["name"], "kind": pair["kind"],
           "changed_field": pair["changed_field"], "expect": pair["expect"]}
    adm_a = constraints.admissible(pair["a"]["observation"], pair["a"]["configuration"], pair["a"]["seat"])
    adm_b = constraints.admissible(pair["b"]["observation"], pair["b"]["configuration"], pair["b"]["seat"])
    out["adm_a"] = adm_a
    out["adm_b"] = adm_b
    if "op" in pair:
        ia = _has(adm_a["units"], pair["unit"], pair["op"])
        ib = _has(adm_b["units"], pair["unit"], pair["op"])
        out["in_a"], out["in_b"] = ia, ib
        out["ok"] = bool(ia and not ib)
    else:
        ma = pair["market_op"] in adm_a["market"]
        mb = pair["market_op"] in adm_b["market"]
        ua = pair["market_unaffected"] in adm_a["market"]
        ub = pair["market_unaffected"] in adm_b["market"]
        out["in_a"], out["in_b"] = ma, mb
        out["unaffected_a"], out["unaffected_b"] = ua, ub
        out["ok"] = bool(ma and not mb and ua and ub)
    return out


if __name__ == "__main__":
    import argparse
    import cards as cards_mod
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    results = []
    for card in cards_mod.load(a.cards):
        for pair in build_pairs(card):
            r = check_pair(pair)
            r["base_card"] = card["card_id"]
            results.append(r)
            print(f"{'PASS' if r['ok'] else 'FAIL'}  {card['card_id']}  {r['name']:18s} "
                  f"({r['kind']}) in_a={r['in_a']} in_b={r['in_b']}"
                  + (f" unaffected={r.get('unaffected_a')}/{r.get('unaffected_b')}"
                     if "unaffected_a" in r else ""))
    n_ok = sum(1 for r in results if r["ok"])
    print(f"\n{n_ok}/{len(results)} discriminating pairs behave as the engine gate requires")
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(results, fh, indent=1, sort_keys=True, default=str)
