"""Optional typed-slot renderer: every fact once, referenced by a stable ID.

The verbose renderer states the same fact several times. A tile's full description
is repeated inside every admissible op of every worker standing on it, the CARE and
FEED conditional prose is repeated per op, and the farm map, the holdings digest, the
production horizon and the FEEDING block each restate positions, yields and flags.

This renderer declares each tile, animal, worker and market line ONCE with an
explicit typed ID, states each opcode's conditional semantics ONCE, and has the
admissible lists reference the IDs. It is lossless with respect to decisions: every
value the verbose renderer carries appears here exactly once, including inventories
kept distinct from tiles, production clocks, decay steps, the survival counter,
market prices with per-order maximum quantities, shed capacity and room, the joint
turn rules, the terminal-cash objective and the horizon. Nothing is truncated and
nothing is dropped for being judged uninteresting.

It is selectable, so an active run is unchanged; effectiveness decides which ships,
with byte count only a tie-break.
"""

import os

from constraints import engine
import constraints as C
import prompt as P

# Opcode semantics, stated once for the whole prompt instead of per op per worker.
OPCODE_SEMANTICS = [
    "WATER t      resets that plant's unwatered streak; on a one-harvest crop inside its"
    " bonus window it also raises yield",
    "HARVEST t    takes the tile's yield into the acting worker's hands; a one-harvest"
    " crop's tile is then cleared",
    "PLANT c t    needs a seed of c and an EMPTY tile; the seed budget is joint across"
    " all workers this turn",
    "FEED t       spends 1 WHEAT from the acting worker's hands and feeds that animal",
    "CARE t       sets cared_today; the care bonus is granted at the daily refresh only"
    " if the animal is ALSO fed that day",
    "COLLECT_FERTILIZER t  takes the fertilizer that animal has ready",
    "FERTILIZE t  spends 1 FERTILIZER from the acting worker's hands",
    "DIG t        removes a plant, a weed, or an EMPTY coop/pasture; it does NOT remove an installed animal",
    "BUILD_COOP / BUILD_PASTURE t   needs an EMPTY tile; pays nothing until an animal is"
    " installed on it and fed",
    "PLACE x      installs animal x when the worker stands on an EMPTY matching structure;"
    " otherwise it only deposits x into the shed",
    "PICKUP x n   moves n of x from the shed into the worker's hands; shed access tiles only",
    "DROP         moves everything the worker carries into the shed; shed access tiles only",
    "NORTH/SOUTH/EAST/WEST  move one tile; PASS spends the worker's turn",
    "ORDER: workers act in order (farmer, then hand0, hand1, ...), each on the tile as the previous workers left it. Sharing a tile is NOT a conflict: FEED then CARE on one animal both apply; FERTILIZE then WATER both apply, and watering a fertilized plant inside its window adds 2 instead of 1; HARVEST of a one-harvest crop clears the tile so a later worker can PLANT there. What does nothing is repeating the SAME action whose flag is already set (a second CARE, a second WATER), or a second PLACE of an animal once the structure is occupied",
]


def _tid(x, y):
    return f"t{x}{y}" if x < 10 and y < 10 else f"t{x}_{y}"


def render(card, adm, hz, plan=None, bank_block=None, head=None,
           tail_block=None, only_units=None, show_market=True):
    K = engine()
    obs, cfg, seat = card["observation"], card["configuration"], card["seat"]
    day, hour = int(obs["day"]), int(obs["hour"])
    farm = obs["farms"][seat]
    priv = obs["private"]
    tiles = farm["tiles"]
    n = len(tiles)
    cap = int(cfg.get("shedCapacity", 100) or 100)
    shed = priv.get("shed", {})
    used = sum(shed.values())
    invs = priv.get("inventories", [])
    access = {tuple(t) for t in K._shed_access_tiles(n)}
    hz_by_pos = {tuple(p["at"]): p for p in hz["plants"]}

    units = [("farmer", farm["farmer"])] + [(f"hand{i}", p)
                                            for i, p in enumerate(farm.get("hands", []))]
    out = []
    out.append("RULES AND ECONOMY")
    out.append(f"score = CASH at the end; shed and carried stock score 0. "
               f"{hz['remaining_decisions']} decisions left, last is step "
               f"{hz['last_decision_step']}; {hz['turns_left_today']} turns left today; "
               f"{int(cfg.get('turnsPerDay', 24) or 24)} turns per day.")
    out.append("crops  " + " | ".join(
        f"{c} seed${d['seed']} first{d['first_yield_day']}d cap{d['max_yield']}"
        + (f" ongoing every{d['interval']}d" if d["ongoing"] else
           f" window{(d['max_yield_day'] + 1) // 2}-{d['max_yield_day']}d")
        for c, d in K.CROPS.items()))
    out.append("animals  " + " | ".join(
        f"{a} ${d['cost']} on {d['structure']} gives {d['product']} first{d['first_yield_day']}d"
        f" every{d['interval']}d hold{d['max_held']}" for a, d in K.ANIMALS.items()))
    out.append("shops  " + " | ".join(f"{s}:{'+'.join(i)}" for s, i in K.SHOPS.items()))
    out.append(f"land NW free then " + ", ".join(
        f"{q} ${p}" for q, p in zip(K.LAND_ORDER, K.LAND_PRICES))
        + "; HIRE 1,1,2,3,5,... per extra worker that day, workers released each night")
    out.append("a plant dies at the refresh after 2 unwatered days; a new plant's planting "
               "day already counts as one")
    out.append("OPCODES (each stated once)")
    for line in OPCODE_SEMANTICS:
        out.append("  " + line)

    out.append("")
    out.append(f"OBJECTIVE  cash {int(farm['money'])} vs opponent "
               f"{int(obs['farms'][1 - seat]['money'])}; unsold {used} in shed, "
               f"{sum(sum(i.values()) for i in invs)} carried")
    out.append(f"PLAN  {plan or 'none yet - set one in the plan field'}")

    if bank_block:
        out.append("")
        out.append(bank_block)

    out.append("")
    out.append(f"STATE  day {day} hour {hour}, farm {n}x{n}, quadrants "
               f"{','.join(farm.get('unlocked_quadrants') or ['NW'])}")
    out.append(f"shed {used}/{cap} used, {cap - used} room: "
               + (", ".join(f"{k}{v}" for k, v in sorted(shed.items()) if v) or "empty"))
    out.append("seeds " + (", ".join(f"{k}{v}" for k, v in sorted(priv.get("seeds", {}).items()) if v)
                           or "none"))
    prices = obs["market"].get("prices") or {
        p: K.market_price(p, obs["market"]["inventory"][p], obs["market"].get("params"))
        for p in K.PRODUCTS}
    out.append("sell price " + ", ".join(f"{k}{int(round(v))}" for k, v in sorted(prices.items())))
    shops = obs.get("town", {}).get("unlocked_shops", [])
    out.append("town " + (", ".join(sorted(shops)) if shops else "no shops yet"))

    out.append("TILES (declared once; ops below reference these ids)")
    empties, locked = [], []
    for y in range(n):
        for x in range(n):
            t = tiles[y][x]
            tid = _tid(x, y)
            if t is None:
                empties.append(tid)
                continue
            if t == "LOCKED":
                locked.append(tid)
                continue
            desc = P._tile_str(t, day)
            extra = ""
            h = hz_by_pos.get((x, y))
            if h:
                bits = []
                if h["ongoing"]:
                    bits.append(f"{h['events_left']} events left"
                                + (" on day " + ",".join(str(e["day"]) for e in
                                                         h["remaining_production_days"][:4])
                                   if h["remaining_production_days"] else ""))
                if h["decay_starts_step"] is not None:
                    bits.append("decaying" if h["decaying"] else
                                f"decays from step{h['decay_starts_step']}")
                bits.append(f"unwatered{h['consecutive_unwatered']}")
                if h["dies_at_refresh_unless_watered"]:
                    bits.append("DIES at this refresh unless watered")
                extra = "; " + ", ".join(bits)
            out.append(f"  {tid} ({x},{y}) {desc}{extra}"
                       + ("  [shed access]" if (x, y) in access else ""))
    out.append(f"  empty tiles: {', '.join(empties) if empties else 'none'}")
    out.append(f"  locked tiles: {', '.join(locked) if locked else 'none'}")

    out.append("WORKERS (position, what each carries, and the tile each stands on)")
    shared = {}
    for label, p in units:
        shared.setdefault((int(p[0]), int(p[1])), []).append(label)
    for i, (label, p) in enumerate(units):
        x, y = int(p[0]), int(p[1])
        held = invs[i] if i < len(invs) else {}
        held_s = ", ".join(f"{k}{v}" for k, v in sorted(held.items()) if v) or "nothing"
        also = [l for l in shared[(x, y)] if l != label]
        out.append(f"  {label} on {_tid(x, y)}; carries {held_s}"
                   + (f"; SHARES this tile with {', '.join(also)}" if also else ""))

    # Animals held in the shed produce nothing there, and an installed animal only
    # pays its care bonus if fed the same day. The verbose renderer stated both; the
    # slot renderer did not, so a run that bought a cow was never shown the path to
    # get it onto a pasture, nor which worker could feed it.
    stock = {a: int(n) for a, n in shed.items() if a in K.ANIMALS and n > 0}
    if stock:
        empty_pens = []
        for y in range(n):
            for x in range(n):
                t = tiles[y][x]
                if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE") \
                        and "animal" not in t:
                    empty_pens.append((t["kind"], _tid(x, y)))
        out.append("ANIMALS IN THE SHED (they produce nothing there; to install: PICKUP "
                   "at a shed access tile, stand on an EMPTY matching structure, PLACE)")
        for a, cnt in sorted(stock.items()):
            need = K.ANIMALS[a]["structure"]
            free = [tid for kind, tid in empty_pens if kind == need]
            out.append(f"  {a} x{cnt} needs an empty {need}: "
                       + (", ".join(free) if free else
                          f"none built yet (BUILD_{need} on an empty tile)"))

    installed = []
    for y in range(n):
        for x in range(n):
            t = tiles[y][x]
            if isinstance(t, dict) and "animal" in t:
                installed.append((_tid(x, y), t))
    if installed:
        out.append("FEEDING (an installed animal pays its care bonus at the refresh only "
                   "if FED that same day; FEED spends 1 WHEAT from the hands of the worker "
                   "standing on it)")
        holders = []
        for i, (label, p) in enumerate(units):
            w = int((invs[i] if i < len(invs) else {}).get("WHEAT", 0))
            holders.append(f"{label} holds {w} WHEAT")
        out.append("  " + "; ".join(holders))
        out.append(f"  shed holds {int(shed.get('WHEAT', 0))} WHEAT"
                   + ("; PICKUP WHEAT at a shed access tile to carry it to an animal"
                      if int(shed.get("WHEAT", 0)) else
                      "; buy WHEAT from the market or harvest it"))
        for tid, t in installed:
            out.append(f"  {tid} {t['animal']} yield{t.get('yield_units', 0)} "
                       + ("fed_today" if t.get("fed_today") else "NOT fed today") + " "
                       + ("cared_today" if t.get("cared_today") else "not cared today")
                       + ("  fertilizer_ready" if t.get("fertilizer_available") else ""))

    import farmmap as _fm
    _bal = "" if os.environ.get("KAG_NO_STRUCTURE_BALANCE") else \
        _fm.structure_balance(obs, cfg, seat)
    if _bal:
        out.append("STRUCTURE BALANCE (empty structures vs animals available to fill them)")
        out.append("  " + _bal)

    out.append("TURN RULES")
    r = adm["rules"]
    plant = ", ".join(f"{k}{v}" for k, v in sorted(r["plant_budget"].items()) if v) or "none"
    out.append(f"  joint seed budget {plant}; exceeding a crop's seeds turns EVERY PLANT of "
               f"it into PASS")
    out.append(f"  all worker actions resolve before any market order: goods dropped this turn "
               f"can be sold this turn, a seed bought this turn cannot be planted until next")
    out.append(f"  market orders run in sequence on one cash balance and {r['shed_room']} shed "
               f"room, repricing per unit; at most {r['max_market_orders']} orders")
    if r["end_of_day_this_turn"]:
        out.append("  END OF DAY after this turn: carried goods drop to the shed and overflow "
                   "is DISCARDED, workers are released, the farmer respawns")
    if r["last_turn_of_episode"]:
        out.append("  LAST TURN: only cash counts")

    out.append("ALLOWED THIS TURN (ids refer to the tiles above)")
    labels = ["farmer"] + [f"hands[{i}]" for i in range(len(adm["units"]) - 1)]
    # `only_units` narrows the ALLOWED lists to the slots the caller is actually
    # asking the model to author. The other units' admissible sets are not part of
    # this action space, so listing them is noise, not withheld information -- the
    # full state above still describes every worker and its tile.
    for i, (label, ops) in enumerate(zip(labels, adm["units"])):
        if only_units is not None and i not in only_units:
            continue
        q = adm["quantities"][i]
        p = units[i][1]
        tid = _tid(int(p[0]), int(p[1]))
        rendered = []
        for op in ops:
            if op[0] == "PICKUP":
                rendered.append(f"PICKUP {op[1]} n<={q['PICKUP'].get(op[1], 1)}")
            elif op[0] == "PLACE":
                rendered.append(f"PLACE {op[1]} n<={q['PLACE_to_shed'].get(op[1], 1)}")
            elif op[0] in P.TILE_OPS:
                rendered.append(f"{' '.join(str(t) for t in op)}@{tid}")
            elif op[0] in P.MOVES:
                rendered.append(f"{op[0]}->{P._move_dest(op[0], obs, seat, i)}")
            else:
                rendered.append(" ".join(str(t) for t in op))
        out.append(f"  {label}: " + " | ".join(rendered))

    def _m(entries):
        return " | ".join(" ".join(m["order"]) + (f" n<={m['max_n']}" if m["max_n"] > 1 else "")
                          for m in entries)
    # The market line is dropped only when the caller's action space genuinely
    # excludes market orders (slot authoring over a route baseline keeps the
    # route's own orders). It is never dropped to save tokens on a turn the model
    # could author them.
    if show_market:
        out.append("  market: " + _m(adm["market"]))
        now = {tuple(m["order"]) for m in adm["market"]}
        extra = [m for m in adm["market_after_full_deposit"]
                 if tuple(m["order"]) not in now]
        if extra:
            out.append("  market after depositing carried goods this turn: "
                       + _m(extra))

    # A caller-supplied block that belongs AFTER the admissible lists, because it
    # talks about those entries: the open slots and what each one is standing on.
    if tail_block:
        out.append("")
        out.append(tail_block)
    if head:
        out.append("")
        out.append(head)
    return "\n".join(out) + "\n"
