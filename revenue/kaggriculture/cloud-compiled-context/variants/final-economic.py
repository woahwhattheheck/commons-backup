# FLORA composition: exact ROWAN dispatch_sales + SORREL purchasing.
# SPDX-License-Identifier: MIT OR CC-BY-4.0
# Derived from Euler / TokenJunkieLabs / Bryce Muhlnickel.
# Frozen source: c57fc2962d7a0da5109162f0b6a267967c3a616e/revenue/kaggriculture/20260907-offline-agent/main.py
# ASTRA-WORK lean20; ROWAN behavior variant dispatch_sales; source license retained.
"""Offline Kaggriculture farm manager; stdlib only, no network or hidden state."""
from __future__ import annotations
import math

ANIMALS = {
    "GOOSE": (300, "COOP", 4, 1, 4, "EGG"),
    "COW": (400, "PASTURE", 8, 2, 6, "MILK"),
    "SHEEP": (500, "PASTURE", 6, 3, 6, "WOOL"),
}
CROPS = {"WHEAT": (10, 2, 4, 4), "CARROT": (20, 2, 3, 3),
         "MELON": (80, 10, 10, 6)}
PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER")
SHOPS = {"BAKERY": ["EGG", "WHEAT"], "PIZZA_SHOP": ["MILK", "TOMATO", "WHEAT"],
         "BRUNCH_SPOT": ["EGG", "WHEAT", "STRAWBERRY"],
         "YARN_STORE": ["WOOL"], "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
         "PET_CAFE": ["CARROT"], "SMOOTHIE_SHOP": ["STRAWBERRY", "MILK"],
         "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"]}
# Official default price curves; any public observation overrides are honored.
PARAMS = {
    "WHEAT": (25, 400, "sqrt", .8, "log", .2),
    "CARROT": (35, 450, "hinge", 1., "sqrt", .7),
    "TOMATO": (60, 200, "hinge", .4, "sqrt", .6),
    "STRAWBERRY": (120, 100, "sqrt", .7, "linear", 1.6),
    "MELON": (250, 300, "log", .2, "sq", 3.6),
    "EGG": (50, 332, "hinge", .4, "log", .2),
    "MILK": (160, 122, "sqrt", .6, "linear", 1.6),
    "WOOL": (200, 105, "log", .2, "sq", 3.2),
    "FERTILIZER": (100, 200, "linear", .4, "linear", .4),
}
# Keep marginal land/labor demand below the costly outer-herd regime.
# Paired unseen-seed comparison and original incumbent: see ECONOMICS.md.
POLICY = {'animal_cap': 20, 'max_hands': 8, 'crop_cap': 6, 'forecast_days': 8, 'care': True, 'mixed': True, 'expansion': False}


HERD = {'pipeline': True, 'capital_weight': 0.5}

def choose_purchase(obs, configuration, remaining_days, horizon, production,
                    demand, future_prices, policy):
    """Value the next animal using public state and our own known inventory.

    Pending livestock is committed capital even before placement. Future shop
    demand, when enabled, is an expectation over the published uniform shop
    distribution, never a prediction from the hidden episode seed.
    """
    private, market = obs["private"], obs["market"]
    prices = market["prices"]
    projected = dict(production)
    if HERD.get("pipeline"):
        for animal, (_, _, _, interval, _, product) in ANIMALS.items():
            count = private["shed"].get(animal, 0) + sum(
                inv.get(animal, 0) for inv in private["inventories"])
            projected[product] += count * (1 + interval) / interval
    projected_demand = dict(demand)
    if HERD.get("town_expectation") and horizon > 0:
        turns = _cfg(configuration, "turnsPerDay", 24)
        unlock = max(1, _cfg(configuration, "townShopUnlockInterval", 3))
        consume = max(1, _cfg(configuration, "townShopSellInterval", 4))
        day = obs.get("day", 0) + obs.get("hour", 0) / turns
        available = max(0, 8 - len(obs.get("town", {}).get("unlocked_shops", [])))
        next_unlock = (math.floor(day / unlock) + 1) * unlock
        # Integrate the time each expected new shop is active over the horizon.
        mean_new_shops = sum(max(0.0, horizon - (next_unlock + i * unlock - day))
                             / horizon for i in range(available))
        for goods in SHOPS.values():
            weight = 2 if len(goods) == 1 else 1
            for product in goods:
                projected_demand[product] += (HERD["town_expectation"] * mean_new_shops
                    * turns / consume * weight / len(SHOPS))
    best, best_roi = None, 0.0
    for animal, (cost, kind, first, interval, held, product) in ANIMALS.items():
        if not policy["mixed"] and animal != "GOOSE":
            continue
        productive_days = max(0.0, remaining_days - first)
        rate = (1 + interval) / interval
        forecast = price(product, market["inventory"][product] +
            (projected[product] + rate * HERD.get("marginal_batch", 1)
             - projected_demand[product]) * horizon, market)
        daily = rate * (prices[product] * .2 + forecast * .8)
        fert = .4 * prices["FERTILIZER"] + .6 * future_prices["FERTILIZER"]
        feed = max(prices["WHEAT"], future_prices["WHEAT"])
        roi = productive_days * daily + remaining_days * (fert - feed - 9) - cost
        roi /= (cost / 300.0) ** HERD.get("capital_weight", 0.0)
        if roi > best_roi:
            best, best_roi = animal, roi
    return best


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def toward(pos, target):
    if pos[0] < target[0]: return ["EAST"]
    if pos[0] > target[0]: return ["WEST"]
    if pos[1] < target[1]: return ["SOUTH"]
    if pos[1] > target[1]: return ["NORTH"]
    return ["PASS"]


def shape(kind, x, t):
    x = max(0, x)
    if kind == "sqrt": return math.sqrt(x)
    if kind == "sq": return x * x
    if kind == "log": return math.log1p(x)
    if kind == "log10": return math.log10(1 + x)
    if kind == "hinge":
        u = x / max(1, t)
        return u + 8 * max(0, u - 1) ** 2
    return x


def price(item, inventory, market):
    base, t, low, lt, high, ht = PARAMS[item]
    p = market.get("params", {}).get(item, {})
    base, t, anchor = p.get("base", base), p.get("T", t), p.get("I0", 10000)
    low, high = p.get("below_func", low), p.get("above_func", high)
    lt, ht = p.get("below_target", lt), p.get("above_target", ht)
    below = inventory < anchor
    f, target = (low, lt) if below else (high, ht)
    movement = target * base * shape(f, abs(inventory - anchor), t) / max(1e-9, shape(f, t, t))
    return max(1, round(base + movement if below else base - movement))


def _cfg(configuration, name, default):
    if configuration is None: return default
    if isinstance(configuration, dict): return configuration.get(name, default)
    return getattr(configuration, name, default)


def _dispatch(obs, configuration=None):
    if not obs.get("farms"):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    policy = POLICY
    player, day, hour = obs["player"], obs.get("day", 0), obs.get("hour", 0)
    farm, private, market = obs["farms"][player], obs["private"], obs["market"]
    tiles, shed, seeds = farm["tiles"], private["shed"], private["seeds"]
    units = [farm["farmer"]] + farm.get("hands", [])
    inventories = private["inventories"]
    size = len(tiles)
    half = size // 2
    depot = [(half-1, half-1), (half, half-1), (half-1, half), (half, half)]
    turns = _cfg(configuration, "turnsPerDay", 24)
    steps = _cfg(configuration, "episodeSteps", 720)
    step = obs.get("step", day * turns + hour)
    # Framework's terminal action is episodeSteps - 2.
    remaining_turns = max(0, steps - 2 - step)
    remaining_days = remaining_turns / turns
    ending = remaining_turns < turns
    spots = [(x, y) for y in range(size) for x in range(size) if tiles[y][x] != "LOCKED"]
    animals = [(x, y, tiles[y][x]) for x, y in spots
               if isinstance(tiles[y][x], dict) and "animal" in tiles[y][x]]
    plants = [(x, y, tiles[y][x]) for x, y in spots
              if isinstance(tiles[y][x], dict) and tiles[y][x].get("kind") == "PLANT"]
    pending = sum(shed.get(a, 0) for a in ANIMALS) + sum(
        inv.get(a, 0) for inv in inventories for a in ANIMALS)
    unfed = sum(not a["fed_today"] for _, _, a in animals)
    prices = market["prices"]
    demand = {p: 1.0 for p in PRODUCTS}
    demand["FERTILIZER"] = 0
    for shop in obs.get("town", {}).get("unlocked_shops", []):
        goods = SHOPS.get(shop, [])
        for good in goods: demand[good] += turns / 4 * (2 if len(goods) == 1 else 1)
    production = {p: 0.0 for p in PRODUCTS}
    for f in obs["farms"]:
        for row in f["tiles"]:
            for tile in row:
                if isinstance(tile, dict) and "animal" in tile:
                    cost, kind, first, interval, held, product = ANIMALS[tile["animal"]]
                    production[product] += (1 + interval) / interval
                    production["FERTILIZER"] += 1
    horizon = min(policy["forecast_days"], remaining_days)
    future_prices = {p: price(p, market["inventory"][p] +
                       (production[p] - demand[p]) * horizon, market) for p in PRODUCTS}
    can_develop = remaining_days > 6 and len(animals) + pending < policy["animal_cap"]
    affordable_animal = choose_purchase(obs, configuration, remaining_days,
        horizon, production, demand, future_prices, policy)

    total_capacity = len(spots)
    crop_cap = min(policy["crop_cap"], max(0, total_capacity - len(animals) - pending - 2))
    choice, crop_roi = None, 0
    for crop, (cost, first, mature, yield_) in CROPS.items():
        if remaining_days < mature + .25: continue
        net = (yield_ * (.5 * prices[crop] + .5 * future_prices[crop]) - cost) / (mature + 1)
        if crop == "WHEAT" and animals: net *= 1.3
        if net > crop_roi: crop_roi, choice = net, crop
    if len(animals) > 24: crop_cap = min(3, crop_cap)

    # Sell carried goods immediately after DROP as well as goods already in shed.
    # Orders occur after unit actions; unfilled quantities stop without penalty.
    orders = []
    wheat_keep = max(0, unfed - sum(inv.get("WHEAT", 0) for inv in inventories))
    for product in PRODUCTS:
        qty = shed.get(product, 0)
        if ending: qty += sum(inv.get(product, 0) for inv in inventories)
        if product == "WHEAT" and not ending: qty = max(0, qty - wheat_keep - 2)
        if qty: orders.append(["SELL", product, qty])

    cash = farm["money"] + sum(
        qty * prices[p] for op, p, qty in orders if op == "SELL")
    cash = max(0, cash)
    reserve = 150 + max(2, len(animals)) * prices["WHEAT"]
    can_buy = can_develop and affordable_animal is not None and pending < 5
    if can_buy and cash > reserve + ANIMALS[affordable_animal][0]:
        qty = min(3, 5-pending, policy["animal_cap"]-len(animals)-pending,
                  max(0, total_capacity-len(animals)-len(plants)-pending),
                  int((cash-reserve)/ANIMALS[affordable_animal][0]))
        if qty:
            orders.append(["BUY_ANIMAL", affordable_animal, qty])
            cash -= qty * ANIMALS[affordable_animal][0]

    # Hire useful capacity cheaply; Fibonacci prices prohibit indiscriminate hiring.
    target_hands = min(policy["max_hands"], max(3, math.ceil(
        (len(animals)*5.5 + len(plants)*2.0 + pending*6 + (30 if can_develop else 0))/18)))
    if ending: target_hands = min(target_hands, max(1, math.ceil(len(animals)/3)))
    a, b = 1, 1
    for _ in range(farm["hires_today"]): a, b = b, a+b
    hire_count = max(0, target_hands-len(farm.get("hands", []))) if hour < 3 else 0
    for _ in range(hire_count):
        cost = a * _cfg(configuration, "farmHandCostMult", 1)
        if cash < cost + 30 or len(orders) >= 9: break
        orders.append(["HIRE"])
        cash -= cost
        a, b = b, a+b

    carried_wheat = sum(inv.get("WHEAT", 0) for inv in inventories)
    feed_needed = max(0, unfed + min(pending, 3) - carried_wheat - shed.get("WHEAT", 0))
    if not ending and feed_needed and cash >= prices["WHEAT"]:
        qty = min(feed_needed + 2, int(cash / max(1, prices["WHEAT"] + 1)))
        if qty: orders.append(["BUY_PRODUCT", "WHEAT", qty])
    if choice and len(plants) < crop_cap and seeds.get(choice, 0) < 2 and cash > 100:
        orders.append(["BUY_SEED", choice, min(4, crop_cap-len(plants))])
    if (policy["expansion"] and remaining_days > 12 and len(spots) < size*size
        and len(animals) + pending >= len(spots)-len(plants)-3
        and cash > reserve + 1000 * 2**(len(farm["unlocked_quadrants"])-1) + 800):
        orders.append(["BUY_LAND"])

    claims = set()
    available_shed = dict(shed)
    available_seeds = dict(seeds)
    actions = [None] * len(units)
    plans = []
    for index, pos in enumerate(units):
        inv = inventories[index] if index < len(inventories) else {}
        near = min(depot, key=lambda p: distance(pos, p))
        d_home = distance(pos, near)
        carried_value = sum(inv.get(p, 0)*prices[p] for p in PRODUCTS)
        # Liquidate early enough to deposit and execute a market order before DONE.
        if ending and carried_value and remaining_turns <= d_home + 3:
            actions[index] = ["DROP"] if d_home == 0 else toward(pos, near)
            continue
        carried_animal = next((a for a in ANIMALS if inv.get(a, 0)), None)
        candidates = []
        def add(target, action, value, key=None, deadline=False):
            key = target if key is None else key
            d = distance(pos, target)
            if key in claims: return
            job = next((j for j in _PLAN.get("installation_jobs", []) if j["worker"] == index), None)
            if carried_animal and job and action[0] in ("DIG", "BUILD_COOP", "BUILD_PASTURE", "PLACE") and tuple(target) != tuple(job["target"]): return
            if ending and d + 1 + min(distance(target, p) for p in depot) + 1 > remaining_turns:
                return
            if d >= turns-hour: return
            score = value / (1 + d * .65)
            if target == tuple(pos): score *= 1.15
            candidates.append((score, -d, target, action, key))

        # An animal already carried is capital in transit: finish its installation.
        if carried_animal:
            kind = ANIMALS[carried_animal][1]
            for x, y in spots:
                tile = tiles[y][x]
                center_dist = min(distance((x,y), p) for p in depot)
                if tile is None:
                    add((x,y), ["BUILD_"+kind], 220/(1+center_dist*.16))
                elif isinstance(tile, dict) and tile.get("kind") == "WEED":
                    add((x,y), ["DIG"], 160/(1+center_dist*.16))
                elif isinstance(tile, dict) and tile.get("kind") == kind and "animal" not in tile:
                    add((x,y), ["PLACE", carried_animal], 260/(1+center_dist*.16))
        else:
            for x, y, animal in animals:
                p = (x, y)
                product = ANIMALS[animal["animal"]][5]
                if not animal["fed_today"] and inv.get("WHEAT", 0) and not ending:
                    urgency = 1 + hour/turns + (4 if animal["consecutive_unfed"] else 0)
                    add(p, ["FEED"], (75 + prices["FERTILIZER"]*.5 + prices[product]) * urgency)
                if animal.get("yield_units", 0):
                    value = animal["yield_units"] * prices[product]
                    if ending: value *= 2
                    add(p, ["HARVEST"], value)
                if animal.get("fertilizer_available"):
                    add(p, ["COLLECT_FERTILIZER"], prices["FERTILIZER"] * (1.5 if ending else 1))
                if (policy["care"] and not ending and not animal["cared_today"]
                    and animal["fed_today"] and remaining_days > 1):
                    add(p, ["CARE"], prices[product] * .9)
            # Pick up enough feed for a small route, with reservation across workers.
            if not ending and inv.get("WHEAT", 0) == 0 and unfed:
                qty = min(available_shed.get("WHEAT",0), max(1, math.ceil(unfed/max(1,len(units)))+1))
                if qty:
                    add(near, ["PICKUP","WHEAT",qty], 170 + hour*8,
                        ("pickup_wheat", index))
            if remaining_days > 2 and pending and not ending:
                animal = next((a for a in ANIMALS if available_shed.get(a,0)), None)
                if animal:
                    add(near, ["PICKUP",animal,1], 190, ("pickup_animal", index))
            for x,y,plant in plants:
                age = day-plant["planted_day"]
                crop = plant["crop"]
                if not plant["watered_today"] and not ending:
                    urgency = 1 + hour/turns*2 + 2*plant["consecutive_unwatered"]
                    add((x,y), ["WATER"], 55*urgency)
                if crop in CROPS and age >= CROPS[crop][2] and plant.get("yield_units",0):
                    add((x,y), ["HARVEST"], plant["yield_units"]*prices[crop]*1.1)
                elif ending and crop in CROPS and age >= CROPS[crop][1] and plant.get("yield_units",0):
                    add((x,y), ["HARVEST"], plant["yield_units"]*prices[crop]*2)
            if choice and len(plants) < crop_cap and hour < turns-5 and not ending:
                for x,y in spots:
                    tile = tiles[y][x]
                    if tile is None and available_seeds.get(choice,0):
                        add((x,y),["PLANT",choice], max(10,crop_roi)*.8)
                    elif isinstance(tile,dict) and tile.get("kind")=="WEED":
                        add((x,y),["DIG"],max(8,crop_roi)*.4)
        # Deposit bulky cargo midday before shed-cap overflow; on final day this is mandatory.
        if carried_value and (ending or sum(inv.values()) >= 10):
            add(near, ["DROP"], carried_value*(1.4 if ending else .2),
                ("drop", index))
        plans.append((index, pos, candidates, near, d_home, carried_value))
    # All workers bid before any target is reserved. Select the strongest
    # worker/job pair globally, then remove its worker and claimed destination.
    # Stock is reserved only for an action that executes here this turn.
    while plans:
        offers = []
        for index, pos, candidates, near, d_home, carried_value in plans:
            for score, negd, target, action, key in candidates:
                if key in claims:
                    continue
                if tuple(pos) == tuple(target):
                    if action[0] == "PICKUP" and available_shed.get(action[1], 0) <= 0:
                        continue
                    if action[0] == "PLANT" and available_seeds.get(action[1], 0) <= 0:
                        continue
                offers.append((score, negd, -target[1], -target[0], str(action), -index,
                               index, pos, target, action, key))
        if not offers:
            for index, pos, candidates, near, d_home, carried_value in plans:
                if ending and carried_value:
                    actions[index] = ["DROP"] if d_home == 0 else toward(pos, near)
                else:
                    actions[index] = ["PASS"]
            break
        *_, index, pos, target, action, key = max(offers, key=lambda offer: offer[:6])
        claims.add(key)
        plans = [plan for plan in plans if plan[0] != index]
        if tuple(pos) != tuple(target):
            actions[index] = toward(pos, target)
        else:
            action = list(action)
            if action[0] == "PICKUP":
                action[2] = min(action[2], available_shed[action[1]])
                available_shed[action[1]] -= action[2]
            elif action[0] == "PLANT":
                available_seeds[action[1]] -= 1
            actions[index] = action
    # Unit actions run before market orders. Include exactly the cargo from
    # planned on-depot DROPs in this turn's sales, keeping the existing feed
    # reserve. Avoid extra empty sales that would crowd out hires or purchases.
    deposits = {product: 0 for product in PRODUCTS}
    for index, action in enumerate(actions):
        if action == ["DROP"] and tuple(units[index]) in set(depot):
            for product in PRODUCTS:
                deposits[product] += inventories[index].get(product, 0)
    if any(deposits.values()) and not ending:
        existing = {order[1]: order[2] for order in orders if order[0] == "SELL"}
        sales = []
        for product in PRODUCTS:
            qty = existing.get(product, 0) + deposits[product]
            if qty:
                sales.append(["SELL", product, qty])
        orders = sales + [order for order in orders if order[0] != "SELL"]
    return {"farmer": actions[0], "hands": actions[1:], "market": orders[:10]}


# SPDX-License-Identifier: MIT OR CC-BY-4.0
"""Bounded observable strategic state, not a language model or model compression.

Pure JSON interface: select_context -> advance -> constrain_orders.
Call advance once per distinct observation and retain the returned state.
Unit scheduling remains the caller's responsibility. No engine/random access.
"""
from copy import deepcopy

OBJECTIVE = "maximize terminal bank cash"
ANIMAL_FIRST = {"GOOSE": 4, "COW": 8, "SHEEP": 6}
CROP_FIRST = {"WHEAT": 2, "CARROT": 2, "MELON": 10,
              "TOMATO": 8, "STRAWBERRY": 10}
COST = {"GOOSE": 300, "COW": 400, "SHEEP": 500,
        "WHEAT": 10, "CARROT": 20, "MELON": 80,
        "TOMATO": 50, "STRAWBERRY": 100}
DEFAULTS = {"daily_animals": 8, "daily_crops": 4, "animal_cap": 20,
            "crop_cap": 6, "max_attempts": 6, "pipeline_cap": 3, "labor_reserve": 150,
            "installation_actions": 6, "animal_daily_actions": 5.5,
            "crop_daily_actions": 2, "max_hands": 8}


def _get(cfg, key, default):
    return cfg.get(key, default) if isinstance(cfg, dict) else getattr(cfg, key, default)


def select_context(obs, configuration=None):
    """Select own observable stock/capacity and public deadlines, never future shops.

    remaining_actions includes this action. First-production dates are feasibility
    bounds, not yield forecasts; ROWAN's event interface may refine them downstream.
    Work estimates below are policy costs, not source-defined game constants.
    """
    turns = _get(configuration, "turnsPerDay", 24)
    steps = _get(configuration, "episodeSteps", 720)
    day, hour = obs.get("day", 0), obs.get("hour", 0)
    step = obs.get("step", day * turns + hour)
    farm = obs["farms"][obs["player"]]
    private = obs["private"]
    inventories = private["inventories"]
    stock = {k: private["shed"].get(k, 0) + sum(i.get(k, 0) for i in inventories)
             for k in (*ANIMAL_FIRST, "WHEAT")}
    animals, crops, vacant = [], [], 0
    for row in farm["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and "animal" in tile:
                animals.append(tile)
            elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
                crops.append(tile)
            elif tile is None or isinstance(tile, dict) and tile.get("kind") in ("WEED", "COOP", "PASTURE"):
                vacant += 1
    size = len(farm["tiles"])
    depot = [(x, y) for x in (size//2-1, size//2) for y in (size//2-1, size//2)]
    positions = [farm["farmer"], *farm.get("hands", [])]
    home = [min(abs(p[0]-q[0])+abs(p[1]-q[1]) for q in depot) for p in positions]
    remaining = max(0, steps - 1 - step)
    end_day = (steps - 2) // turns
    pending = sum(stock[a] for a in ANIMAL_FIRST)
    return {"schema": 1, "objective": OBJECTIVE, "player": obs["player"],
            "step": step, "day": day, "hour": hour, "turns_per_day": turns,
            "remaining_actions": remaining, "remaining_days": max(0, end_day-day),
            "cash": farm["money"], "prices": dict(obs["market"]["prices"]),
            "animals": len(animals), "crops": len(crops), "pending": pending,
            "stock": stock, "seed_stock": dict(private["seeds"]),
            "unfed": sum(not a["fed_today"] for a in animals),
            "workers": len(positions), "vacant": vacant, "hires_today": farm.get("hires_today", 0),
            "hire_multiplier": _get(configuration, "farmHandCostMult", 1),
            "worker_actions_left": len(positions) * min(turns-hour, remaining),
            "liquidation_distance": max(home, default=0),
            "animal_horizon": {a: end_day-day-first-1 for a, first in ANIMAL_FIRST.items()},
            "crop_horizon": {c: end_day-day-first-1 for c, first in CROP_FIRST.items()},
            "seed_total": sum(private["seeds"].values()),
            "goods_value": sum(n * obs["market"]["prices"].get(p, 0)
                               for inv in [private["shed"], *inventories] for p, n in inv.items()
                               if p not in ANIMAL_FIRST and p != "WHEAT")}


def advance(obs, configuration=None, previous=None, options=None):
    """Create/reconcile a daily commitment using observed progress, with bounded memory.

    Completion = installation/crop targets reached AND livestock backlog cleared.
    Expiry ends the old plan, records its unmet target and replans from actual stock.
    BUY proposals never count as installed assets. Same-step calls are idempotent.
    """
    c = select_context(obs, configuration)
    o = {**DEFAULTS, **(options or {})}
    s = deepcopy(previous) if previous else None
    if s and s["player"] == c["player"] and s["step"] == c["step"]:
        return s
    if s and (s["player"] != c["player"] or c["step"] < s["step"]):
        s = None
    prior_jobs = s.get("installation_jobs", []) if s and s["day"] == c["day"] else []
    jobs, job_outcomes = installation_jobs(obs, prior_jobs)
    history = list(s["feedback"]) if s else []
    history.extend(job_outcomes)
    bank = list(s.get("bank", [])) if s else []
    completed_count = s.get("completed_count", 0) if s else 0
    expired_count = s.get("expired_count", 0) if s else 0
    if s:
        delta = {k: c[k]-s["observed"][k] for k in ("animals", "crops", "pending", "cash")}
        s["last_outcome"] = delta
        if s["status"] == "active" and c["animals"] >= s["installation_target"] and c["crops"] >= s["crop_target"] and c["pending"] == 0:
            s["status"] = "completed"
            completed_count += 1
            gain = (c["animals"]-s["start_animals"]) + (c["crops"]-s["start_crops"])
            if gain > 0:
                bank.append({"situation": s["situation"], "day": s["day"],
                             "plan": {"animals": s["installation_target"]-s["start_animals"],
                                      "crops": s["crop_target"]-s["start_crops"]},
                             "outcome": {"advancement_score": gain,
                                         "cash_delta": c["cash"]-s["start_cash"]}})
            history.append({"day": s["day"], "step": c["step"], "outcome": "completed"})
        if c["day"] != s["day"] and s["status"] == "active":
            expired_count += 1
            history.append({"day": s["day"], "step": c["step"], "outcome": "expired",
                            "uninstalled": max(0, s["installation_target"]-c["animals"]),
                            "unplanted": max(0, s["crop_target"]-c["crops"])})
    if not s or c["day"] != s["day"]:
        situation = ("backlog" if c["pending"] else "growth") + (":late" if c["remaining_days"] < 12 else ":early")
        examples = []
        seen = set()
        for row in reversed(bank):
            shape = (row["plan"]["animals"], row["plan"]["crops"])
            if row["situation"] == situation and shape not in seen:
                examples.append(row)
                seen.add(shape)
            if len(examples) == 2:
                break
        # Today's currently hired labor plus affordable opening-hour cheap hires.
        # Work reservations are explicitly estimates, not a promise of execution.
        potential = c["workers"]
        if c["hour"] < 3:
            hire_a, hire_b = 1, 1
            for _ in range(c["hires_today"]):
                hire_a, hire_b = hire_b, hire_a+hire_b
            hiring_cash = max(0, c["cash"]-30-max(0, c["unfed"]-c["stock"]["WHEAT"])*(c["prices"]["WHEAT"]+1))
            while potential < o["max_hands"]+1 and hiring_cash >= hire_a*c["hire_multiplier"]:
                hiring_cash -= hire_a*c["hire_multiplier"]
                hire_a, hire_b = hire_b, hire_a+hire_b
                potential += 1
        budget = potential * (c["turns_per_day"]-c["hour"])
        service = c["animals"]*o["animal_daily_actions"] + c["crops"]*o["crop_daily_actions"]
        free_work = max(0, budget-service-c["pending"]*o["installation_actions"])
        animal_allowance = min(o["daily_animals"], max(0, o["animal_cap"]-c["animals"]-c["pending"]),
                               max(0, c["vacant"]-c["pending"]-2), int(free_work/o["installation_actions"]))
        if c["pending"] or max(c["animal_horizon"].values()) <= 0:
            animal_allowance = 0
        crop_allowance = min(o["daily_crops"], max(0, o["crop_cap"]-c["crops"]),
                            max(0, c["vacant"]-c["pending"]-animal_allowance-2),
                            int(max(0, free_work-animal_allowance*o["installation_actions"])/4))
        if max(c["crop_horizon"].values()) <= 0:
            crop_allowance = 0
        s = {"schema": 1, "objective": OBJECTIVE, "player": c["player"], "day": c["day"],
             "status": "active", "situation": situation, "examples": examples,
             "start_animals": c["animals"], "start_crops": c["crops"], "start_cash": c["cash"],
             "installation_target": c["animals"]+c["pending"]+animal_allowance,
             "crop_target": c["crops"]+crop_allowance, "animal_allowance": animal_allowance,
             "seed_allowance": max(0, crop_allowance-c["seed_total"]),
             "animal_attempts": 0, "seed_attempts": 0, "last_outcome": {},
             "last_proposed": [], "options": o, "budget_actions": budget,
             "reserved_service_actions": service}
    feed = max(0, c["unfed"]+c["pending"]-c["stock"]["WHEAT"])
    terminal = c["remaining_actions"] <= c["turns_per_day"]
    s.update(step=c["step"], observed={k:c[k] for k in ("animals", "crops", "pending", "cash")},
             backlog=c["pending"], feed_needed=0 if terminal else feed,
             cash_reserve=0 if terminal else o["labor_reserve"]+feed*(c["prices"]["WHEAT"]+1),
             phase="liquidate" if terminal else "install" if c["pending"] else "maintain" if s["status"] == "completed" else "develop",
             installation_jobs=jobs, feedback=history[-8:], bank=bank[-8:], completed_count=completed_count, expired_count=expired_count)
    return s


def constrain_orders(action, context, state):
    """Apply preconditions and priority to baseline market proposals, no unit rewrite.

    Priority: observed-inventory sales, labor/feed, then growth. Growth uses current
    cash only (future sales are not assumed). Returned state records proposals;
    next advance records outcomes. Retry attempts are bounded even after rejection.
    """
    c, s = context, deepcopy(state)
    o = s["options"]
    result = {"farmer": list(action["farmer"]), "hands": deepcopy(action["hands"]), "market": []}
    cash = c["cash"]
    orders = sorted(action["market"], key=lambda x: 0 if x[0] == "SELL" else 1 if x[0] in ("HIRE", "BUY_PRODUCT") else 2)
    proposed = []
    hire_a, hire_b = 1, 1
    for _ in range(c["hires_today"]):
        hire_a, hire_b = hire_b, hire_a+hire_b
    for order in orders:
        order = list(order)
        op = order[0]
        if op == "BUY_ANIMAL":
            a = order[1]
            missing = max(0, s["installation_target"]-c["animals"]-c["pending"])
            qty = min(order[2], missing, s["animal_allowance"], max(0, o["pipeline_cap"]-c["pending"]), max(0, int((cash-s["cash_reserve"])/COST[a])))
            if s["phase"] == "liquidate" or s["status"] == "completed" or s["animal_attempts"] >= o["max_attempts"] or c["animal_horizon"].get(a, 0) <= 0 or qty <= 0:
                continue
            order[2] = qty
            s["animal_attempts"] += 1
            cash -= qty*COST[a]
        elif op == "BUY_SEED":
            crop = order[1]
            qty = min(order[2], max(0, s["crop_target"]-c["crops"]-c["seed_total"]), s["seed_allowance"], max(0, int((cash-s["cash_reserve"])/COST[crop])))
            if s["phase"] == "liquidate" or s["seed_attempts"] >= o["max_attempts"] or c["crop_horizon"].get(crop, 0) <= 0 or qty <= 0:
                continue
            order[2] = qty
            s["seed_attempts"] += 1
            cash -= qty*COST[crop]
        elif op == "BUY_LAND":
            continue  # FLORA owns productive expansion; this adapter makes no land plan.
        elif op == "HIRE":
            cash -= hire_a*c["hire_multiplier"]
            hire_a, hire_b = hire_b, hire_a+hire_b
        elif op == "BUY_PRODUCT":
            cash -= order[2]*(c["prices"][order[1]]+1)
        result["market"].append(order)
        if op in ("BUY_ANIMAL", "BUY_SEED"):
            proposed.append(order)
    result["market"] = result["market"][:10]
    s["last_proposed"] = proposed
    return result, s


def situation_packet(context, state):
    """At most two own completed advancing plan examples, immediately before live state.

    This is a new plan-level analog of the LDA screen/action bank, not LDA's scored
    model-action corpus. Advancement is local asset progress, NOT terminal profit.
    Consumers must recheck current preconditions; examples are never replay scripts.
    """
    return [{"example": deepcopy(row)} for row in state["examples"]] + [
        {"live_state": deepcopy(context), "plan": {k: deepcopy(state[k]) for k in
         ("objective", "phase", "status", "installation_target", "crop_target", "backlog", "feed_needed", "cash_reserve")}}]


def installation_jobs(obs, previous=None):
    """Own carried-stock intents; commit through DIG/BUILD/PLACE, observe completion.

    New deterministic design. Each carried animal reserves one vacant
    compatible tile. Persistent worker identities last one day only; caller resets
    at EOD. Output is advisory data for FLORA; no peer scheduling code is imported.
    """
    farm = obs["farms"][obs["player"]]
    tiles, day, hour = farm["tiles"], obs.get("day", 0), obs.get("hour", 0)
    units = [farm["farmer"], *farm.get("hands", [])]
    inventories = obs["private"]["inventories"]
    prior = {j["worker"]: j for j in (previous or [])}
    reserved, jobs, feedback = set(), [], []
    for worker, pos in enumerate(units):
        inv = inventories[worker] if worker < len(inventories) else {}
        animal = next((a for a in ANIMAL_FIRST if inv.get(a, 0)), None)
        old = prior.get(worker)
        if old:
            x, y = old["target"]
            tile = tiles[y][x]
            if isinstance(tile, dict) and tile.get("animal") == old["animal"]:
                feedback.append({"day": day, "step": obs.get("step", 0),
                                 "outcome": "installation_completed", "worker": worker,
                                 "animal": old["animal"], "target": [x,y]})
                old = None
        if not animal:
            continue
        kind = "COOP" if animal == "GOOSE" else "PASTURE"
        choices = []
        for y, row in enumerate(tiles):
            for x, tile in enumerate(row):
                if (x,y) in reserved:
                    continue
                if tile is None:
                    action, operations = "BUILD_"+kind, 2
                elif isinstance(tile, dict) and tile.get("kind") == "WEED":
                    action, operations = "DIG", 3
                elif isinstance(tile, dict) and tile.get("kind") == kind and "animal" not in tile:
                    action, operations = "PLACE", 1
                else:
                    continue
                dist = abs(pos[0]-x)+abs(pos[1]-y)
                metric = dist+operations
                stale = (old.get("stale", 0)+1 if old and old["target"] == [x,y] and metric >= old["metric"] else 0)
                keep = old and old["animal"] == animal and old["target"] == [x,y] and stale < 8
                choices.append((0 if keep else 1, metric, y, x, action, stale))
        if not choices:
            continue
        _, metric, y, x, action, stale = min(choices)
        if old and old["target"] != [x,y]:
            feedback.append({"day": day, "step": obs.get("step", 0),
                             "outcome": "installation_replanned", "worker": worker,
                             "previous_target": old["target"], "target": [x,y]})
        reserved.add((x,y))
        jobs.append({"worker": worker, "animal": animal, "target": [x,y],
                     "next_operation": [action, animal] if action == "PLACE" else [action],
                     "metric": metric, "stale": stale,
                     "precondition": "own carried animal and vacant compatible target"})
    return jobs, feedback

_PLAN = None
_LAST_ACTION = None

def agent(obs, configuration=None):
    global _PLAN, _LAST_ACTION
    if not obs.get("farms"):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    context = select_context(obs, configuration)
    if _PLAN and _PLAN["step"] == context["step"] and _PLAN["player"] == context["player"]:
        return deepcopy(_LAST_ACTION)
    _PLAN = advance(obs, configuration, _PLAN)
    action = _dispatch(obs, configuration)
    action, _PLAN = constrain_orders(action, context, _PLAN)
    _LAST_ACTION = deepcopy(action)
    return action
