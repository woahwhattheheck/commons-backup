"""Kaggriculture agent — Barnyard Economist v5 (replay-driven: livestock before land)."""

import math
from collections import deque

CROPS = {
    "WHEAT":      {"seed": 10, "first": 2, "maxday": 4,  "interval": 0, "maxy": 6, "ongoing": False, "ripe": 4},
    "CARROT":     {"seed": 20, "first": 2, "maxday": 3,  "interval": 0, "maxy": 4, "ongoing": False, "ripe": 3},
    "TOMATO":     {"seed": 50, "first": 8, "maxday": 8,  "interval": 1, "maxy": 4, "ongoing": True,  "ripe": 8},
    "STRAWBERRY": {"seed": 100, "first": 10, "maxday": 10, "interval": 2, "maxy": 4, "ongoing": True, "ripe": 13},
    "MELON":      {"seed": 80, "first": 10, "maxday": 12, "interval": 0, "maxy": 6, "ongoing": False, "ripe": 10},
}

ANIMALS = {
    "GOOSE": {"cost": 300, "struct": "COOP",    "first": 4, "interval": 1, "held": 4, "product": "EGG"},
    "COW":   {"cost": 400, "struct": "PASTURE", "first": 8, "interval": 2, "held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "struct": "PASTURE", "first": 6, "interval": 3, "held": 6, "product": "WOOL"},
}

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]

MP = {
    "WHEAT":      (25,  400, "sqrt",   0.80, "log",    0.20),
    "CARROT":     (35,  450, "log",    0.20, "sqrt",   0.70),
    "TOMATO":     (60,  200, "linear", 0.40, "sqrt",   0.60),
    "STRAWBERRY": (120, 100, "sqrt",   0.70, "linear", 1.60),
    "MELON":      (250, 300, "log",    0.20, "sq",     3.60),
    "EGG":        (50,  332, "linear", 0.40, "log",    0.20),
    "MILK":       (160, 122, "sqrt",   0.60, "linear", 1.60),
    "WOOL":       (200, 105, "log",    0.20, "sq",     3.20),
    "FERTILIZER": (100, 200, "linear", 0.40, "linear", 0.40),
}
I0 = 10000

MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}
LAND_PRICES = [1000, 2000, 4000]
TURNS_PER_DAY = 24
TOTAL_DAYS = 30
MAX_ORDERS = 10
SHED_CAP = 100

# --------------------------------------------------------------------------- #
# Tunables — baked in from a grid search against the public agents.
# Livestock is a 1 cow : 2 sheep mix; milk and wool have huge town demand
# (3 and 1 shops) so they hold price far better than the raw curve suggests.
# --------------------------------------------------------------------------- #

TRAVEL = 8.0            # coins charged per step of walking when scoring a job
MAX_HANDS = 12          # hire cost is fib(n): cheap to ~12, brutal past it
ANIMAL_CAP = 12         # more pens than we can feed daily = escaped animals
STRAW_TARGET = 45       # strawberry: 4 of 8 town shops demand it (max demand)
TOMATO_TARGET = 0
MELON_TARGET = 16       # melon price is quadratic in glut -> small patch
CARROT_TARGET = 999     # fallback so no owned tile is ever left idle
WHEAT_TARGET = 15       # feed for the herd, plus a glut-proof cash crop

ANIMAL_START_DAY = 0    # pens open once melon money is in sight
ANIMAL_RAMP = 2.5       # new pen slots per day
PEN_FILLER_LAST_DAY = 3
WAVE_SIZE = 16      # ongoing-crop tiles planted per wave
WAVE_GAP = 2         # days between successive waves # grow wheat on not-yet-built pen tiles until this day
MAX_QUADRANTS = 2
LAND_MIN_DAY = 4       # buy all three extra quadrants
MIN_CASH = 250.0        # hard cash floor so feed is always affordable
LAND_BUFFER = 900.0     # keep this much on top of the quadrant price
SEED_HOLDBACK = 1       # stop buying seed while saving for a quadrant
HAND_DIV = 8.0          # workload -> desired crew size
HAND_BUDGET = 0.10      # share of cash we will spend on a day's crew
FEED_STOCK_DAYS = 3.0
WHEAT_KEEP = 2.0        # days of feed kept in the 100-slot shed

RESERVE_FRAC = {
    "WHEAT": 0.70, "CARROT": 0.62, "TOMATO": 0.55, "STRAWBERRY": 0.50,
    "MELON": 0.60, "EGG": 0.72, "MILK": 0.80, "WOOL": 0.80, "FERTILIZER": 0.15,
}

ANIMAL_SEQ = ["COW", "SHEEP", "SHEEP"] * 14


def _shape(f, x):
    x = max(0.0, x)
    if f == "linear":
        return x
    if f == "sq":
        return x * x
    if f == "sqrt":
        return math.sqrt(x)
    if f == "log":
        return math.log(1.0 + x)
    return x


def price_at(item, inv):
    base, T, bf, bt, af, at = MP[item]
    if inv < I0:
        return max(1, int(round(base + (bt * base / _shape(bf, T)) * _shape(bf, I0 - inv))))
    return max(1, int(round(base - (at * base / _shape(af, T)) * _shape(af, inv - I0))))


def sellable(item, inv, reserve, have):
    n = 0
    while n < have and price_at(item, inv + n) >= reserve:
        n += 1
    return n


def reserve_price(item, day, load):
    base = MP[item][0]
    frac = RESERVE_FRAC.get(item, 0.6)
    left = TOTAL_DAYS - day
    if left <= 2:
        return 0.0
    if left <= 7:
        frac *= (left - 2) / 5.0
    if load > 0.75:
        frac *= 0.5
    return base * frac


def shed_tiles(bs):
    h = bs // 2
    return [(h - 1, h - 1), (h, h - 1), (h - 1, h), (h, h)]


def bfs(start, tiles, bs):
    sx, sy = int(start[0]), int(start[1])
    dist = {(sx, sy): 0}
    step = {(sx, sy): None}
    q = deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        base = step[(x, y)]
        for name, (dx, dy) in MOVES.items():
            nx, ny = x + dx, y + dy
            if not (0 <= nx < bs and 0 <= ny < bs):
                continue
            if (nx, ny) in dist or tiles[ny][nx] == "LOCKED":
                continue
            dist[(nx, ny)] = dist[(x, y)] + 1
            step[(nx, ny)] = name if (x, y) == (sx, sy) else base
            q.append((nx, ny))
    return dist, step


LAST_PLANT = {"WHEAT": 24, "CARROT": 25, "TOMATO": 17,
              "STRAWBERRY": 15, "MELON": 18}


def last_plant_day(crop):
    return LAST_PLANT.get(crop, TOTAL_DAYS - 1 - CROPS[crop]["ripe"])


def build_roles(tiles, bs):
    """Frozen layout: a tile's role depends ONLY on which tiles are unlocked.

    Earlier versions recomputed the split from cash and herd size every turn,
    so a tile could be a melon on day 8 and a wheat field on day 9 — the melon
    was then never watered again and rotted into a weed. The layout is now a
    pure function of the unlocked set, so a role never changes under a growing
    crop. How fast we *build* pens is decided separately, in build_jobs.
    """
    access = shed_tiles(bs)
    owned = []
    for y in range(bs):
        for x in range(bs):
            if tiles[y][x] == "LOCKED":
                continue
            d = min(abs(x - ax) + abs(y - ay) for ax, ay in access)
            owned.append((d, y, x))
    owned.sort()
    total = len(owned)

    n_animal = max(0, min(ANIMAL_CAP, total - 8))
    free = max(0, total - n_animal)
    n_melon = min(MELON_TARGET, free);            free -= n_melon
    n_wheat = min(WHEAT_TARGET, free);            free -= n_wheat
    n_straw = min(STRAW_TARGET, free);            free -= n_straw
    n_tom = min(TOMATO_TARGET, free);             free -= n_tom
    n_carrot = min(CARROT_TARGET, free)

    roles = {}
    wave = {}
    per_crop = {}
    slot = 0
    for i, (_d, y, x) in enumerate(owned):
        if i < n_animal:
            roles[(x, y)] = ("ANIMAL", ANIMAL_SEQ[min(slot, len(ANIMAL_SEQ) - 1)])
            slot += 1
            continue
        j = i - n_animal
        if j < n_melon:
            roles[(x, y)] = ("CROP", "MELON")
        elif j < n_melon + n_wheat:
            roles[(x, y)] = ("CROP", "WHEAT")
        elif j < n_melon + n_wheat + n_straw:
            roles[(x, y)] = ("CROP", "STRAWBERRY")
        elif j < n_melon + n_wheat + n_straw + n_tom:
            roles[(x, y)] = ("CROP", "TOMATO")
        else:
            roles[(x, y)] = ("CROP", "CARROT")
        crop = roles[(x, y)][1]
        k = per_crop.get(crop, 0)
        per_crop[crop] = k + 1
        # Stagger ongoing crops: planting 45 strawberries on one day means all
        # 45 hit their production cap on the same day and rot into weeds
        # together. Waves spread both the harvest peak and the price impact.
        wave[(x, y)] = (k // WAVE_SIZE) * WAVE_GAP if CROPS.get(crop, {}).get("ongoing") else 0
    return roles, wave


def survey(farm, priv, roles, day):
    tiles = farm["tiles"]
    c = dict(animals=0, unfed=0, uncared=0, pens_free=0, pens_todo=0,
             plants=0, plantable=0, weeds=0, geese=0)
    for (x, y), (kind, what) in roles.items():
        t = tiles[y][x]
        if t is None:
            if kind == "ANIMAL":
                c["pens_todo"] += 1
            elif day <= last_plant_day(what):
                c["plantable"] += 1
        elif isinstance(t, dict):
            k = t.get("kind")
            if k == "PLANT":
                c["plants"] += 1
            elif k == "WEED":
                c["weeds"] += 1
            elif "animal" in t:
                c["animals"] += 1
                if not t.get("fed_today"):
                    c["unfed"] += 1
                if not t.get("cared_today"):
                    c["uncared"] += 1
            else:
                c["pens_free"] += 1
    c["pen_slots"] = sum(1 for v in roles.values() if v[0] == "ANIMAL")
    return c


# --------------------------------------------------------------------------- #
# jobs
# --------------------------------------------------------------------------- #

def _planted_today(tiles, day):
    n = {}
    for row in tiles:
        for t in row:
            if isinstance(t, dict) and t.get("kind") == "PLANT" and t.get("planted_day") == day:
                n[t["crop"]] = n.get(t["crop"], 0) + 1
    return n


def build_jobs(obs, farm, priv, roles, prices, c, money=0.0, stored=0, waves=None):
    day = int(obs.get("day", 0) or 0)
    left = TOTAL_DAYS - day
    tiles = farm["tiles"]
    seeds = priv.get("seeds") or {}
    fertp = prices.get("FERTILIZER", 100)
    jobs = []
    # Planting 45 strawberries on one day means all 45 hit their production cap
    # together and rot into weeds together. Rate-limit ongoing crops per day so
    # the harvest peak (and the price impact) is spread out.
    today = _planted_today(tiles, day)
    quota = {}

    for (x, y), (kind, what) in roles.items():
        t = tiles[y][x]

        if t is None:
            if kind == "ANIMAL":
                ramp = int((day - ANIMAL_START_DAY) * ANIMAL_RAMP)
                afford = c["animals"] + stored + int(max(0.0, money - 600) // 350)
                allowed = max(0, min(c["pen_slots"], ramp, afford))
                if left >= 8 and c["pens_free"] + c["animals"] < allowed:
                    op = "BUILD_COOP" if ANIMALS[what]["struct"] == "COOP" else "BUILD_PASTURE"
                    jobs.append((x, y, [op], 240.0, None))
                elif left >= 8 and day <= PEN_FILLER_LAST_DAY and seeds.get("WHEAT", 0) > 0:
                    # Pen tiles are the best land on the farm and pens are not
                    # built until day ~5. Grow a 4-day wheat crop on them in the
                    # meantime; it clears itself on harvest, so the pen is never
                    # blocked when we are finally ready to build.
                    jobs.append((x, y, ["PLANT", "WHEAT"], 90.0, None))
            else:
                crop = what

                if CROPS[crop]["ongoing"]:
                    used = today.get(crop, 0) + quota.get(crop, 0)
                    if used >= WAVE_SIZE:
                        continue
                    quota[crop] = quota.get(crop, 0) + 1
                if day <= last_plant_day(crop) and seeds.get(crop, 0) > 0:
                    unit = prices.get(crop, 25)
                    exp = {"WHEAT": 4, "CARROT": 3, "MELON": 6, "STRAWBERRY": 4, "TOMATO": 4}.get(crop, 3)
                    jobs.append((x, y, ["PLANT", crop], max(60.0, 0.6 * exp * unit), None))
            continue

        if not isinstance(t, dict):
            continue
        k = t.get("kind")

        if k == "WEED":
            jobs.append((x, y, ["DIG"], 120.0 if left > 5 else 5.0, None))
            continue

        if k == "PLANT":
            _plant_jobs(jobs, t, x, y, day, left, prices)
            continue

        if "animal" not in t:
            want = "GOOSE" if k == "COOP" else ("SHEEP" if what == "SHEEP" else "COW")
            jobs.append((x, y, ["PLACE", want], 700.0, want))
            continue

        _animal_jobs(jobs, t, x, y, day, left, prices, fertp)

    return jobs


def _plant_jobs(jobs, t, x, y, day, left, prices):
    crop = t.get("crop")
    cd = CROPS.get(crop)
    if cd is None:
        return
    age = day - int(t.get("planted_day", day))
    units = int(t.get("yield_units", 0))
    watered = bool(t.get("watered_today"))
    dry = int(t.get("consecutive_unwatered", 0))
    p = prices.get(crop, 1)

    if cd["ongoing"]:
        # Ongoing crops produce on schedule whether or not they were watered
        # today (see _daily_refresh_plants), so watering is purely survival:
        # every other day is enough and halves the action cost per tile.
        if units > 0 and age >= cd["first"]:
            batch = units >= 2 or day >= TOTAL_DAYS - 2
            jobs.append((x, y, ["HARVEST"], units * p * (1.0 if batch else 0.45), None))
        if not watered and dry >= 1:
            jobs.append((x, y, ["WATER"], max(80.0, 0.7 * cd["maxy"] * p), None))
        return

    ws = (cd["maxday"] + 1) // 2
    ripe = units >= cd["maxy"] or age >= cd["maxday"] or age >= cd["ripe"]
    endgame = day >= TOTAL_DAYS - 2

    if units > 0 and age >= cd["first"] and (ripe or endgame):
        if not watered and ws <= age <= cd["maxday"] and units < cd["maxy"]:
            jobs.append((x, y, ["WATER"], 1.10 * p, None))
        jobs.append((x, y, ["HARVEST"], units * p * 0.95, None))
        return

    if not watered:
        if ws <= age <= cd["maxday"] and units < cd["maxy"]:
            jobs.append((x, y, ["WATER"], 1.10 * p, None))
        elif dry >= 1:
            # If we skip this, the tile is a weed tomorrow: price the whole crop.
            jobs.append((x, y, ["WATER"], max(60.0, 0.8 * cd["maxy"] * p), None))


def _animal_jobs(jobs, t, x, y, day, left, prices, fertp):
    a = ANIMALS.get(t.get("animal"))
    if a is None:
        return
    p = prices.get(a["product"], 1)
    units = int(t.get("yield_units", 0))

    if not t.get("fed_today"):
        jobs.append((x, y, ["FEED"], 900.0 if left > 2 else 60.0, "WHEAT"))
    if units > 0:
        full = units >= a["held"]
        jobs.append((x, y, ["HARVEST"], units * p * (1.3 if full else 0.55), None))
    if not t.get("cared_today") and left > 1:
        jobs.append((x, y, ["CARE"], 0.95 * p, None))
    if t.get("fertilizer_available") and left > 1:
        jobs.append((x, y, ["COLLECT_FERTILIZER"], 0.95 * fertp, None))


# --------------------------------------------------------------------------- #
# assignment
# --------------------------------------------------------------------------- #

def assign(obs, farm, priv, jobs, c):
    """Greedy economic matching: score = job value - walking distance x TRAVEL.

    Logistics (fetch feed / drop produce / carry livestock) are modelled as
    *shared* jobs with a limited number of slots, so a whole crew never piles
    onto the same errand.
    """
    tiles = farm["tiles"]
    bs = len(tiles)
    access = shed_tiles(bs)
    hour = int(obs.get("hour", 0) or 0)
    workers = [tuple(farm["farmer"])] + [tuple(p) for p in (farm.get("hands") or [])]
    invs = priv.get("inventories") or []
    shed = priv.get("shed") or {}
    n = len(workers)
    out = [["PASS"] for _ in range(n)]
    if n == 0:
        return out

    dists, steps, near = [], [], []
    for w in workers:
        d, st = bfs(w, tiles, bs)
        dists.append(d)
        steps.append(st)
        near.append(min(((d.get(t, 999), t) for t in access), key=lambda z: z[0]))

    # ---- shared logistics slots ----
    logi = []
    shed_wheat = int(shed.get("WHEAT", 0) or 0)
    if c["unfed"] > 0 and shed_wheat > 0:
        per = max(1, min(10, c["unfed"]))
        slots = max(1, min(3, (shed_wheat + per - 1) // per, (c["unfed"] + per - 1) // per))
        for _ in range(slots):
            logi.append(("PICKW", min(per, shed_wheat), 880.0))
    if c["pens_free"] > 0:
        for sp in ("GOOSE", "COW", "SHEEP"):
            avail = int(shed.get(sp, 0) or 0)
            if avail > 0:
                for _ in range(min(2, avail, c["pens_free"])):
                    logi.append(("PICKA", sp, 700.0))
                break

    pairs = []
    for wi in range(n):
        inv = invs[wi] if wi < len(invs) else {}
        wheat = inv.get("WHEAT", 0)
        carry = sum(v for k, v in inv.items() if k != "WHEAT" and k not in ANIMALS)
        holds_animal = any(inv.get(a, 0) for a in ANIMALS)
        di = dists[wi]

        for ji, (x, y, act, val, req) in enumerate(jobs):
            if req == "WHEAT":
                if wheat <= 0:
                    continue
            elif req is not None and inv.get(req, 0) <= 0:
                continue
            d = di.get((x, y))
            if d is None:
                continue
            sc = val - d * TRAVEL
            if sc > 0:
                pairs.append((sc, wi, ji))

        sd, spos = near[wi]
        if sd >= 900:
            continue
        if carry > 0 and hour < TURNS_PER_DAY - 2 and (carry >= 3 or sd == 0):
            pairs.append((45.0 * carry - sd * TRAVEL, wi, ("DROP", spos)))
        for li, (kind, arg, val) in enumerate(logi):
            if kind == "PICKW" and wheat > 0:
                continue
            if kind == "PICKA" and holds_animal:
                continue
            pairs.append((val - sd * TRAVEL, wi, ("L", li, spos)))

    pairs.sort(key=lambda z: -z[0])
    used_w, used_j, used_l = set(), set(), set()
    budget = dict(priv.get("seeds") or {})

    for _sc, wi, ji in pairs:
        if wi in used_w:
            continue
        if isinstance(ji, int):
            if ji in used_j:
                continue
            x, y, act, _v, _r = jobs[ji]
            d = dists[wi].get((x, y), 999)
            if d == 0:
                if act[0] == "PLANT":
                    if budget.get(act[1], 0) <= 0:
                        continue
                    budget[act[1]] -= 1
                out[wi] = list(act)
            else:
                out[wi] = [steps[wi][(x, y)]]
            used_j.add(ji)
        elif ji[0] == "DROP":
            tpos = ji[1]
            if dists[wi].get(tpos, 999) > 0:
                out[wi] = [steps[wi][tpos]]
            else:
                inv = invs[wi] if wi < len(invs) else {}
                others = [k for k, v in inv.items() if v > 0 and k != "WHEAT" and k not in ANIMALS]
                if len(others) == 1 and (inv.get("WHEAT", 0) > 0 or any(inv.get(a, 0) for a in ANIMALS)):
                    out[wi] = ["PLACE", others[0], inv[others[0]]]
                else:
                    out[wi] = ["DROP"]
        else:
            li, tpos = ji[1], ji[2]
            if li in used_l:
                continue
            kind, arg, _v = logi[li]
            if dists[wi].get(tpos, 999) > 0:
                out[wi] = [steps[wi][tpos]]
            else:
                out[wi] = ["PICKUP", "WHEAT", int(arg)] if kind == "PICKW" else ["PICKUP", arg, 1]
            used_l.add(li)
        used_w.add(wi)
    return out


# --------------------------------------------------------------------------- #
# market
# --------------------------------------------------------------------------- #

def hire_costs(already, k):
    a, b = 1, 1
    for _ in range(already):
        a, b = b, a + b
    tot, seq = 0, []
    for _ in range(k):
        seq.append(a)
        tot += a
        a, b = b, a + b
    return seq, tot


def desired_hands(c, money, day):
    """A hand costs fib(n) coins for 24 actions — absurdly cheap up to ~12."""
    if day >= TOTAL_DAYS - 1:
        return 0
    work = c["animals"] * 3.2 + c["plants"] * 1.3 + c["plantable"] * 1.4 + c["weeds"] * 0.8
    want = max(3, min(MAX_HANDS, int(math.ceil(work / HAND_DIV))))
    budget = 60.0 + money * HAND_BUDGET
    while want > 3:
        _seq, tot = hire_costs(0, want)
        if tot <= budget:
            break
        want -= 1
    return want


def market_orders(obs, farm, priv, roles, c, prices, waves=None):
    day = int(obs.get("day", 0) or 0)
    hour = int(obs.get("hour", 0) or 0)
    money = float(farm.get("money", 0) or 0)
    shed = priv.get("shed") or {}
    seeds = priv.get("seeds") or {}
    minv = (obs.get("market") or {}).get("inventory") or {}
    tiles = farm["tiles"]
    left = TOTAL_DAYS - day
    load = sum(shed.values()) / float(SHED_CAP)
    orders = []

    # 1. sell
    sells = []
    for item in PRODUCTS:
        have = int(shed.get(item, 0) or 0)
        if have <= 0:
            continue
        if item == "WHEAT":
            keep = int(math.ceil(c["animals"] * WHEAT_KEEP)) if left > 2 else 0
            have = max(0, have - keep)
            if have <= 0:
                continue
        inv = int(minv.get(item, I0))
        q = sellable(item, inv, reserve_price(item, day, load), have)
        # Glide path: whatever the price does, never end the season holding
        # stock. Spread the remainder evenly across the days that are left.
        floor_q = int(math.ceil(have / float(max(1, left - 1)))) if left <= 12 else 0
        q = max(q, min(have, floor_q))
        if q > 0:
            sells.append((price_at(item, inv) * q, ["SELL", item, q]))
    sells.sort(key=lambda z: -z[0])
    for v, o in sells:
        if len(orders) >= MAX_ORDERS:
            break
        orders.append(o)
        money += v

    if left <= 1:
        return orders[:MAX_ORDERS]

    # 2. feed wheat (highest-priority spend: a starved animal is a total loss)
    if c["animals"] > 0 and len(orders) < MAX_ORDERS:
        stock = int(shed.get("WHEAT", 0) or 0)
        need = int(math.ceil(c["animals"] * 1.5)) - stock
        wp = price_at("WHEAT", int(minv.get("WHEAT", I0)) - 1)
        if need > 0 and wp <= 70:
            q = int(min(need, money // max(1, wp)))
            if q > 0:
                orders.append(["BUY_PRODUCT", "WHEAT", q])
                money -= q * wp

    # 3. hire
    if hour <= 1 and len(orders) < MAX_ORDERS:
        want = desired_hands(c, money, day)
        have = int(farm.get("hires_today", 0) or 0)
        if want > have:
            seq, tot = hire_costs(have, want - have)
            for cost in seq:
                if len(orders) >= MAX_ORDERS or money < cost * 4:
                    break
                orders.append(["HIRE"])
                money -= cost

    # 4. land
    saving_for_land = 0.0
    n_extra = len(farm.get("unlocked_quadrants") or ["NW"]) - 1
    if (n_extra < min(MAX_QUADRANTS, len(LAND_PRICES)) and left >= 9
            and day >= LAND_MIN_DAY and len(orders) < MAX_ORDERS):
        cost = LAND_PRICES[n_extra]
        if money >= cost + LAND_BUFFER:
            orders.append(["BUY_LAND"])
            money -= cost
        elif left >= 12:
            saving_for_land = cost + LAND_BUFFER

    # 5. seeds
    waves = waves or {}
    need = {}
    for (x, y), (kind, what) in roles.items():
        if tiles[y][x] is not None:
            continue
        if kind == "ANIMAL":
            if day <= PEN_FILLER_LAST_DAY:
                need["WHEAT"] = need.get("WHEAT", 0) + 1
        elif day <= last_plant_day(what) and day >= waves.get((x, y), 0):
            need[what] = need.get(what, 0) + 1
    for crop in ("MELON", "STRAWBERRY", "TOMATO", "CARROT", "WHEAT"):
        if len(orders) >= MAX_ORDERS:
            break
        want = need.get(crop, 0) - int(seeds.get(crop, 0) or 0)
        if want <= 0:
            continue
        cost = CROPS[crop]["seed"]
        spare = money - MIN_CASH
        if SEED_HOLDBACK and saving_for_land > 0:
            spare = min(spare, money - saving_for_land)
        q = int(min(want, max(0.0, spare) // cost))
        if q > 0:
            orders.append(["BUY_SEED", crop, q])
            money -= q * cost

    # 6. livestock
    if len(orders) < MAX_ORDERS and left >= 8:
        in_shed = sum(int(shed.get(a, 0) or 0) for a in ANIMALS)
        # Never buy more stock than we have pens ready for (plus a small
        # pipeline), otherwise animals rot in the shed and eat the cash floor.
        room = c["pens_free"] + min(2, c["pens_todo"]) - in_shed
        want = min(c["pen_slots"] - c["animals"] - in_shed, room)
        if want > 0:
            nxt = ANIMAL_SEQ[min(c["animals"] + in_shed, len(ANIMAL_SEQ) - 1)]
            cost = ANIMALS[nxt]["cost"]
            q = int(min(want, max(0.0, money - MIN_CASH - 400) // cost))
            if q > 0:
                orders.append(["BUY_ANIMAL", nxt, q])
                money -= q * cost

    return orders[:MAX_ORDERS]


# --------------------------------------------------------------------------- #

def _impl(obs):
    player = int(obs.get("player", 0) or 0)
    farms = obs.get("farms") or []
    if not farms or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    priv = obs.get("private") or {}
    tiles = farm.get("tiles") or []
    bs = len(tiles)
    day = int(obs.get("day", 0) or 0)

    prices = dict((obs.get("market") or {}).get("prices") or {})
    for it in PRODUCTS:
        prices.setdefault(it, MP[it][0])

    animals_now = 0
    for row in tiles:
        for t in row:
            if isinstance(t, dict) and "animal" in t:
                animals_now += 1
    stored_animals = sum(int((priv.get("shed") or {}).get(a, 0) or 0) for a in ANIMALS)
    roles, waves = build_roles(tiles, bs)
    c = survey(farm, priv, roles, day)
    jobs = build_jobs(obs, farm, priv, roles, prices, c,
                      float(farm.get("money", 0) or 0), stored_animals, waves)
    acts = assign(obs, farm, priv, jobs, c)
    orders = market_orders(obs, farm, priv, roles, c, prices, waves)

    nh = len(farm.get("hands") or [])
    hands = acts[1:1 + nh]
    while len(hands) < nh:
        hands.append(["PASS"])
    return {"farmer": acts[0] if acts else ["PASS"], "hands": hands, "market": orders}


def agent(obs):
    try:
        return _impl(obs)
    except Exception:
        try:
            farms = obs.get("farms") or []
            p = int(obs.get("player", 0) or 0)
            nh = len(farms[p].get("hands") or []) if 0 <= p < len(farms) else 0
        except Exception:
            nh = 0
        return {"farmer": ["PASS"], "hands": [["PASS"]] * nh, "market": []}
