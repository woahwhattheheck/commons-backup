# FLORA KAG-PRODUCTION: integrated land/labor/crop/fertilizer policy.
# Generated from exact selected KAG-COMPOSE bytes; see build.py.
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
# cost, first yield age, final event age, harvest-capacity units
CROPS = {"WHEAT": (10, 2, 4, 6), "CARROT": (20, 2, 3, 4),
         "TOMATO": (50, 8, 11, 4), "STRAWBERRY": (100, 10, 16, 4),
         "MELON": (80, 10, 12, 6)}
ONGOING = {"TOMATO": (8, 1, 11), "STRAWBERRY": (10, 2, 16)}
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
POLICY = {'animal_cap': 18, 'max_hands': 12, 'crop_cap': 24, 'forecast_days': 8, 'care': True, 'mixed': True, 'expansion': True}


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


# Frozen standalone projection of ROWAN events.py at blob
# 48b3c0df949e13bf4c63ee86f5d5b3a58ec00aec; namespaced because this
# candidate's CROPS table also carries purchase cost and policy metadata.
EVENT_CROPS = {'WHEAT': (2,4,0,6), 'CARROT': (2,3,0,4),
               'TOMATO': (8,8,1,4), 'STRAWBERRY': (10,10,2,4),
               'MELON': (10,12,0,6)}


def production_events(tile, step, turns_per_day=24, episode_steps=720):
    """Return future EOD crop events under the exact public engine contract."""
    if tile.get('kind') != 'PLANT':
        return []
    first, _, interval, cap = EVENT_CROPS[tile['crop']]
    if not interval:
        return []
    last_action = episode_steps - 2
    start = tile['planted_day'] + first
    events = []
    for event_day in range(start, start + cap * interval, interval):
        available = event_day * turns_per_day
        boundary = available - 1
        if boundary < step or available > last_action:
            continue
        events.append({'refresh_step': boundary, 'available_step': available,
            'care_day': event_day - 1, 'held_capacity': cap,
            'fertilizer_application_days': [event_day-3, event_day-1],
            'fertilizer_already_covers': tile.get('fertilized_until_day',-1) >= event_day-1,
            'fertilizer_bonus_requires_water': True})
    return events


def _fertilizer_window(plant, day, step, turns, steps):
    """Return only the next unproduced event's uncovered application window."""
    events = production_events(plant, step, turns, steps)
    if not events:
        return None
    event = events[0]
    due_in = event['care_day'] - day
    if not 0 <= due_in <= 2 or event['fertilizer_already_covers']:
        return None
    return due_in, event['care_day']


def _sale_value(product, qty, market):
    """Project our sequential SELL fills from the observed inventory curve."""
    inventory, total = market["inventory"][product], 0
    for _ in range(max(0, qty)):
        unit = price(product, inventory, market)
        total += unit
        if unit > 1:
            inventory += 1
    return total


def _product_fill(product, wanted, cash, reserve, market):
    """Return affordable sequential BUY_PRODUCT quantity and projected cost."""
    inventory, total, filled = market["inventory"][product], 0, 0
    for _ in range(max(0, wanted)):
        unit = price(product, inventory - 1, market)
        if cash - total - unit < reserve:
            break
        total += unit
        inventory -= 1
        filled += 1
    return filled, total


def _dynamic_crop_cap(animals, plants, pending, units, turns, policy):
    """Bound crop growth from observable daily effect capacity.

    The 0.52 conversion is a policy allowance for productive effects after
    travel, not an engine constant or a promise that every reserved task lands.
    """
    workers = max(1, len(units))
    ongoing = sum(plant[2].get('crop') in ONGOING for plant in plants)
    animal_load = len(animals) * 3.2
    crop_load = 1.45 + 0.65 * ongoing / max(1, len(plants))
    effect_capacity = workers * turns * 0.52
    sustainable = int(max(0, effect_capacity - animal_load - pending * 2.0) / crop_load)
    crop_cap = min(policy['crop_cap'], max(len(plants), 4, sustainable))
    return crop_cap


def agent(obs, configuration=None):
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
    service_crop_cap = _dynamic_crop_cap(
        animals, plants, pending, units, turns, policy)
    crop_cap = min(service_crop_cap, max(0, total_capacity - len(animals) - pending - 3))
    choice, crop_roi = None, 0
    strawberry_demand = sum("STRAWBERRY" in SHOPS.get(shop, [])
                            for shop in obs.get("town", {}).get("unlocked_shops", []))
    for crop, (cost, first, mature, yield_) in CROPS.items():
        if remaining_days < first + 1.25: continue
        if crop in ONGOING:
            first_event, interval, last_event = ONGOING[crop]
            usable_last = min(last_event, int(remaining_days - 1))
            events = max(0, 1 + (usable_last - first_event) // interval)
            expected_units = events * 1.65
            net = (expected_units * (.35 * prices[crop] + .65 * future_prices[crop]) - cost) / (first + 1)
        else:
            net = (yield_ * (.5 * prices[crop] + .5 * future_prices[crop]) - cost) / (mature + 1)
        net *= 1 + min(1.5, demand[crop] / 12)
        if crop == "STRAWBERRY":
            net *= 1.35 + .18 * strawberry_demand
        if crop == "WHEAT" and animals: net *= 1.15
        if net > crop_roi: crop_roi, choice = net, crop

    # Sell carried goods immediately after DROP as well as goods already in shed.
    # Orders occur after unit actions; unfilled quantities stop without penalty.
    orders = []
    wheat_keep = max(0, unfed - sum(inv.get("WHEAT", 0) for inv in inventories))
    for product in PRODUCTS:
        qty = shed.get(product, 0)
        if ending: qty += sum(inv.get(product, 0) for inv in inventories)
        if product == "WHEAT" and not ending: qty = max(0, qty - wheat_keep - 2)
        if product == "FERTILIZER" and not ending:
            fert_keep = min(4, sum(_fertilizer_window(p[2], day, step, turns, steps) is not None for p in plants))
            qty = max(0, qty - fert_keep)
        if qty: orders.append(["SELL", product, qty])

    cash = farm["money"] + sum(
        _sale_value(p, qty, market) for op, p, qty in orders if op == "SELL")
    cash = max(0, cash)
    reserve = 180 + max(2, len(animals)) * prices["WHEAT"]
    quadrants = len(farm["unlocked_quadrants"])
    land_cost = 1000 * 2 ** max(0, quadrants - 1)
    land_day = (5, 10, 15)[min(2, max(0, quadrants - 1))]
    pressure = len(animals) + pending + len(plants) >= max(8, total_capacity - 8)
    want_land = (policy["expansion"] and quadrants < 4 and day >= land_day
                 and remaining_days > 11 and pressure and cash > reserve + land_cost + 600)
    if want_land and len(orders) < 10:
        orders.append(["BUY_LAND"])
        cash -= land_cost
    can_buy = can_develop and affordable_animal is not None and pending < 4
    if can_buy and cash > reserve + ANIMALS[affordable_animal][0]:
        qty = min(2, 4-pending, policy["animal_cap"]-len(animals)-pending,
                  max(0, total_capacity-len(animals)-len(plants)-pending),
                  int((cash-reserve)/ANIMALS[affordable_animal][0]))
        if qty and len(orders) < 10:
            orders.append(["BUY_ANIMAL", affordable_animal, qty])
            cash -= qty * ANIMALS[affordable_animal][0]

    # Hire useful capacity cheaply; Fibonacci prices prohibit indiscriminate hiring.
    ongoing_plants = sum(p[2]["crop"] in ONGOING for p in plants)
    target_hands = min(policy["max_hands"], max(4, math.ceil(
        (len(animals)*5.5 + len(plants)*2.0 + ongoing_plants*3.0
         + pending*6 + (24 if can_develop else 0))/17)))
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

    if (choice and len(plants) < crop_cap and seeds.get(choice, 0) < 2
        and cash > reserve and len(orders) < 10):
        seed_qty = min(4, crop_cap-len(plants))
        seed_cost = CROPS[choice][0]
        seed_qty = min(seed_qty, max(0, int((cash-reserve) / max(1, seed_cost))))
        if seed_qty:
            orders.append(["BUY_SEED", choice, seed_qty])
            cash -= seed_qty * seed_cost
    carried_wheat = sum(inv.get("WHEAT", 0) for inv in inventories)
    feed_needed = max(0, unfed + min(pending, 3) - carried_wheat - shed.get("WHEAT", 0))
    if not ending and feed_needed and len(orders) < 10:
        qty, cost = _product_fill("WHEAT", feed_needed, cash, 30, market)
        if qty:
            orders.append(["BUY_PRODUCT", "WHEAT", qty])
            cash -= cost

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
            # Reserve and route fertilizer from observable crop ages only.
            carried_fertilizer = inv.get("FERTILIZER", 0)
            needs_fertilizer = []
            for x, y, plant in plants:
                if plant["crop"] not in ONGOING:
                    continue
                window = _fertilizer_window(plant, day, step, turns, steps)
                if window is not None:
                    due_in, _ = window
                    needs_fertilizer.append((x, y, due_in, plant["crop"]))
            if carried_fertilizer and not ending:
                for x, y, due_in, crop in needs_fertilizer:
                    add((x, y), ["FERTILIZE"], 185 + prices[crop] * (1.4 if due_in == 0 else .9),
                        ("fertilize", x, y))
            elif needs_fertilizer and available_shed.get("FERTILIZER", 0) and not ending:
                add(near, ["PICKUP", "FERTILIZER", 1], 245 + hour * 5,
                    ("pickup_fertilizer", index))

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
                if crop in CROPS and plant.get("yield_units",0):
                    held = plant["yield_units"]
                    ongoing = crop in ONGOING
                    ready = age >= CROPS[crop][1] if ongoing else age >= CROPS[crop][2]
                    if ready and (not ongoing or held >= 2 or ending or age >= ONGOING[crop][2]):
                        add((x,y), ["HARVEST"], held*prices[crop]*(1.45 if ongoing else 1.1))
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
            if product == "FERTILIZER" and remaining_days > 2:
                keep = min(4, sum(_fertilizer_window(p[2], day, step, turns, steps) is not None for p in plants))
                qty = max(0, qty - min(deposits[product], keep))
            if qty:
                sales.append(["SELL", product, qty])
        orders = sales + [order for order in orders if order[0] != "SELL"]
    return {"farmer": actions[0], "hands": actions[1:], "market": orders[:10]}
