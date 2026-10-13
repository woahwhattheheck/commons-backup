"""Compact but complete farm topology: everything ownable, plantable or workable.

The legality list says what one unit can do where it stands. This says what the farm
IS -- owned versus locked quadrants, every non-empty tile with its exact contents,
every empty plantable tile, the pens, the shed access tiles and the unit positions --
so a plan can be about somewhere the units are not currently standing.

Compression is by grouping only. No tile is dropped because it looked irrelevant.
"""

import os

from constraints import engine


def _fmt_tile(tile, day):
    import prompt as P
    return P._tile_str(tile, day)



def structure_balance(obs, config, seat):
    """Empty structures with locations, animal stock, and placements already reserved.

    A segment built nine pastures while installing three animals: both renderers list
    empty pens and shed animals in separate places, so the balance between them has to
    be inferred by counting two lists. This states it, with the tile ids, what each
    structure needs, what stock is held in the shed and in workers' hands, what cash
    affords, and which structures a worker is ALREADY standing on carrying a matching
    animal, so the same structure is not counted twice.

    Board and price state only. How many structures to hold open, and whether to buy
    stock or build first, remains the model's decision.
    """
    from constraints import engine
    K = engine()
    farm = obs["farms"][seat]
    priv = obs["private"]
    tiles = farm["tiles"]
    empty = {"COOP": [], "PASTURE": []}
    for y, row in enumerate(tiles):
        for x, t in enumerate(row):
            if isinstance(t, dict) and t.get("kind") in empty and "animal" not in t:
                empty[t["kind"]].append((x, y))

    invs = priv.get("inventories", [])
    positions = [farm["farmer"]] + list(farm.get("hands", []))
    labels = ["farmer"] + [f"hand{i}" for i in range(len(positions) - 1)]
    reserved = {}
    for i, p in enumerate(positions):
        x, y = int(p[0]), int(p[1])
        t = tiles[y][x]
        if not (isinstance(t, dict) and t.get("kind") in empty and "animal" not in t):
            continue
        held = invs[i] if i < len(invs) else {}
        for a, n in held.items():
            if n and a in K.ANIMALS and K.ANIMALS[a]["structure"] == t["kind"]:
                reserved[(x, y)] = f"{labels[i]} is on it carrying {a}"
                break

    shed = priv.get("shed", {})
    carried = {}
    for inv in invs:
        for k, v in inv.items():
            if k in K.ANIMALS and v:
                carried[k] = carried.get(k, 0) + int(v)
    money = int(farm["money"])

    out = []
    for struct in ("COOP", "PASTURE"):
        spots = empty[struct]
        fits = [a for a, d in K.ANIMALS.items() if d["structure"] == struct]
        in_shed = sum(int(shed.get(a, 0)) for a in fits)
        in_hand = sum(int(carried.get(a, 0)) for a in fits)
        if not spots and not in_shed and not in_hand:
            continue
        ids = ", ".join(f"({x},{y})" + (f" [{reserved[(x, y)]}]" if (x, y) in reserved else "")
                        for x, y in spots) or "none"
        afford = min((money // K.ANIMALS[a]["cost"] for a in fits), default=0)
        prices = ", ".join("%s $%d" % (a, K.ANIMALS[a]["cost"]) for a in fits)
        out.append(f"{struct}: {len(spots)} empty at {ids}; stock {in_shed} in shed, "
                   f"{in_hand} carried; {len(reserved) and sum(1 for k in reserved if k in spots) or 0} "
                   f"already covered by a worker standing on it; cash {money} buys "
                   f"{afford} more ({prices})")
    return " | ".join(out)


def build(obs, config, seat):
    K = engine()
    farm = obs["farms"][seat]
    tiles = farm["tiles"]
    n = len(tiles)
    day = int(obs["day"])
    access = [tuple(t) for t in K._shed_access_tiles(n)]

    empty, locked, weeds, plants, pens, other = [], [], [], [], [], []
    for y in range(n):
        for x in range(n):
            t = tiles[y][x]
            if t is None:
                empty.append((x, y))
            elif t == "LOCKED":
                locked.append((x, y))
            elif isinstance(t, dict) and t.get("kind") == "PLANT":
                plants.append(((x, y), _fmt_tile(t, day)))
            elif isinstance(t, dict) and t.get("kind") == "WEED":
                weeds.append((x, y))
            elif isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE"):
                label = _fmt_tile(t, day)
                pens.append(((x, y), label if "animal" in t else f"{t['kind']} (empty)"))
            else:
                other.append(((x, y), _fmt_tile(t, day)))

    def coords(ps, limit=None):
        s = ps if limit is None else ps[:limit]
        out = ",".join(f"({x},{y})" for x, y in s)
        if limit is not None and len(ps) > limit:
            out += f" +{len(ps) - limit} more"
        return out or "none"

    lines = [f"farm {n}x{n}, quadrants unlocked: "
             f"{', '.join(farm.get('unlocked_quadrants') or ['NW'])}; "
             f"locked tiles {len(locked)}"]
    lines.append(f"shed access tiles (DROP/PICKUP work only here): {coords(access)}")
    units = [("farmer", farm["farmer"])] + [(f"hand{i}", p) for i, p in enumerate(farm.get("hands", []))]
    lines.append("units: " + "; ".join(f"{l} at ({int(p[0])},{int(p[1])})" for l, p in units))
    # Units sharing a tile: a tile op resolves in order, so the second unit's op on
    # the same tile hits a tile the first has already changed and usually does
    # nothing. This is state the accepted list cannot show, because that list is
    # derived per unit in isolation.
    shared = {}
    for label, p in units:
        shared.setdefault((int(p[0]), int(p[1])), []).append(label)
    dupes = {xy: ls for xy, ls in shared.items() if len(ls) > 1}
    if dupes:
        for (x, y), ls in dupes.items():
            lines.append(f"  NOTE {' and '.join(ls)} share ({x},{y}). They act in that "
                         f"order on the tile as the previous one left it. DIFFERENT actions "
                         f"can all apply -- FEED then CARE on one animal, FERTILIZE then "
                         f"WATER on one plant (a watered fertilized plant in its window "
                         f"gains 2 instead of 1), HARVEST of a one-harvest crop then PLANT "
                         f"on the cleared tile. Repeating the SAME action does nothing once "
                         f"its flag is set, and a second PLACE of an animal only deposits "
                         f"into the shed once the structure is occupied.")
    lines.append(f"empty plantable tiles ({len(empty)}): {coords(empty, 24)}")
    if plants:
        lines.append("plants:")
        for (x, y), s in plants:
            lines.append(f"  ({x},{y}) {s}")
    if pens:
        lines.append("pens:")
        for (x, y), s in pens:
            lines.append(f"  ({x},{y}) {s}")
    if weeds:
        lines.append(f"weeds to DIG ({len(weeds)}): {coords(weeds, 16)}")
    if other:
        for (x, y), s in other:
            lines.append(f"  ({x},{y}) {s}")
    if locked:
        lines.append(f"locked tiles: {coords(locked, 12)}")

    # Stock that is an ANIMAL sitting in the shed cannot produce anything there. The
    # engine's install path is PICKUP at a shed access tile, walk onto an EMPTY
    # matching structure, then PLACE. Stating that path is state, not advice: the
    # model still chooses whether to take it. A bought COW sat unused in the shed for
    # a whole diagnostic segment while the seat kept building structures.
    shed = obs["private"].get("shed", {})
    stock = {a: int(n) for a, n in shed.items() if a in K.ANIMALS and n > 0}
    if stock:
        empty_pens = {}
        for (x, y), desc in pens:
            kind = desc.split()[0] if desc else ""
            if "on" not in desc:
                empty_pens.setdefault(kind, []).append((x, y))
        out = []
        for a, n in sorted(stock.items()):
            need = K.ANIMALS[a]["structure"]
            free = empty_pens.get(need, [])
            where = coords(free, 6) if free else f"none built yet (BUILD_{need} on an empty tile)"
            out.append(f"{a} x{n} needs an empty {need}: {where}")
        lines.append("ANIMALS IN THE SHED (they produce nothing there; to install: PICKUP at a "
                     "shed access tile, stand on an empty matching structure, then PLACE):")
        for o in out:
            lines.append("  " + o)
    # Installed animals produce at the daily refresh, and the care bonus needs the
    # animal FED that same day. FEED consumes 1 WHEAT carried by the unit standing on
    # it, so the WHEAT has to be in that unit's hands, not in the shed. State where
    # the wheat is and what each unit is holding; the model still chooses.
    animals_on_board = [(xy, d) for xy, d in pens if "on" in d]
    if animals_on_board:
        invs = obs["private"].get("inventories", [])
        holders = []
        for i, (label, _p) in enumerate(units):
            w = int((invs[i] if i < len(invs) else {}).get("WHEAT", 0))
            holders.append(f"{label} holds {w} WHEAT")
        shed_wheat = int(shed.get("WHEAT", 0))
        lines.append("FEEDING (an installed animal only pays the care bonus if it is FED the "
                     "same day; FEED spends 1 WHEAT from the hands of the unit standing on it):")
        lines.append("  " + "; ".join(holders))
        lines.append(f"  shed holds {shed_wheat} WHEAT"
                     + ("; PICKUP WHEAT at a shed access tile to carry it to an animal"
                        if shed_wheat else "; buy WHEAT from the market or harvest it"))
        for (x, y), d in animals_on_board:
            lines.append(f"  ({x},{y}) {d}")
    bal = "" if os.environ.get("KAG_NO_STRUCTURE_BALANCE") else \
        structure_balance(obs, config, seat)
    if bal:
        lines.append("STRUCTURE BALANCE (empty structures vs animals available to fill them)")
        lines.append("  " + bal)
    return "\n".join(lines)
