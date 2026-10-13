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
POLICY = {"animal_cap": 36, "max_hands": 11, "crop_cap": 6,
          "forecast_days": 8, "care": True, "mixed": True, "expansion": True,
          "marginal_economics": True, "same_tile_bonus": 1.15}


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
    affordable_animal = None
    best_roi = 0
    for animal, (cost, kind, first, interval, held, product) in ANIMALS.items():
        if not policy["mixed"] and animal != "GOOSE": continue
        productive_days = max(0, remaining_days - first)
        rate = (1 + interval) / interval
        forecast = price(product, market["inventory"][product] +
                         (production[product] + rate - demand[product]) * horizon, market)
        daily = rate * (prices[product] * .2 + forecast * .8)
        fert = .4 * prices["FERTILIZER"] + .6 * future_prices["FERTILIZER"]
        feed = max(prices["WHEAT"], future_prices["WHEAT"])
        # Feed/fertilizer also occur during maturation. Allow realistic worker cost.
        roi = productive_days * daily + remaining_days * (fert - feed - 9) - cost
        if policy.get("marginal_economics"):
            # Price each remaining day, including maturation and market saturation.
            # Account for the new animal's price impact on the existing herd.
            own_rate = sum((1 + ANIMALS[a["animal"]][3]) / ANIMALS[a["animal"]][3]
                           for _, _, a in animals if ANIMALS[a["animal"]][5] == product)
            own_fert = len(animals)
            eligible = [(x,y) for x,y in spots if tiles[y][x] is None]
            route = min((min(distance(p,d) for d in depot) for p in eligible), default=4)
            # A marginal animal needs feed/care/collection and a shared depot route.
            workload = 5.5 + route * .8
            current_work = len(animals)*5.5 + len(plants)*2 + pending*6
            old_hands = min(policy["max_hands"], max(3, math.ceil(current_work/18)))
            new_hands = min(policy["max_hands"], max(3, math.ceil((current_work+workload)/18)))
            def wages(n):
                a,b,total=1,1,0
                for _ in range(n):
                    total += a
                    a,b=b,a+b
                return total
            marginal_wage = max(4.0 + route, wages(new_hands)-wages(old_hands))
            roi = -cost - (1000 * 2**(len(farm["unlocked_quadrants"])-1)/12
                           if not eligible and len(spots)<size*size else 0)
            for elapsed in range(1, math.ceil(remaining_days)+1):
                fraction = min(1., remaining_days-elapsed+1)
                maturity = elapsed > first
                sold = max(0, elapsed-first)*rate
                base_inventory = market["inventory"][product] + (production[product]-demand[product])*elapsed
                before_price = price(product, base_inventory, market)
                after_price = price(product, base_inventory+sold, market)
                baseline_fert = market["inventory"]["FERTILIZER"]+production["FERTILIZER"]*elapsed
                fert_before = price("FERTILIZER",baseline_fert,market)
                fert_after = price("FERTILIZER",baseline_fert+elapsed,market)
                feed_price = price("WHEAT",market["inventory"]["WHEAT"]-demand["WHEAT"]*elapsed,market)
                # Marginal contribution, not the misleading new animal's gross revenue.
                value = (rate*after_price if maturity else 0)
                value += own_rate*(after_price-before_price) + fert_after
                value += own_fert*(fert_after-fert_before)
                roi += fraction*(value-feed_price-marginal_wage)
        if roi > best_roi:
            best_roi, affordable_animal = roi, animal

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
    actions = []
    for index, pos in enumerate(units):
        inv = inventories[index] if index < len(inventories) else {}
        near = min(depot, key=lambda p: distance(pos, p))
        d_home = distance(pos, near)
        carried_value = sum(inv.get(p, 0)*prices[p] for p in PRODUCTS)
        # Liquidate early enough to deposit and execute a market order before DONE.
        if ending and carried_value and remaining_turns <= d_home + 3:
            actions.append(["DROP"] if d_home == 0 else toward(pos, near))
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
            if target == tuple(pos): score *= policy.get("same_tile_bonus", 1.15)
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
        if candidates:
            score, negd, target, action, key = max(candidates,
                key=lambda c: (c[0],c[1],-c[2][1],-c[2][0],str(c[3])))
            claims.add(key)
            if tuple(pos) != tuple(target):
                actions.append(toward(pos,target))
            else:
                actions.append(action)
                if action[0]=="PICKUP":
                    available_shed[action[1]] -= action[2]
                elif action[0]=="PLANT":
                    available_seeds[action[1]] -= 1
        else:
            if ending and carried_value:
                actions.append(["DROP"] if d_home == 0 else toward(pos,near))
            else:
                actions.append(["PASS"])
    return {"farmer": actions[0], "hands": actions[1:], "market": orders[:10]}
