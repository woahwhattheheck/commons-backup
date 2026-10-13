"""Build FLORA KAG-PRODUCTION from the exact selected KAG-COMPOSE agent."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "cloud-composition" / "candidate.py"
PARENT_SHA256 = "3c68266c87b9ca048c4c25688f207cf41ba5da708f3eb0c1cc786a6d0383cf20"


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("Production transform anchor changed: " + old[:60])
    return source.replace(old, new, 1)


def build(source: str) -> str:
    if hashlib.sha256(source.encode()).hexdigest() != PARENT_SHA256:
        raise ValueError("Expected exact selected KAG-COMPOSE candidate")
    source = replace_once(source,
'''CROPS = {"WHEAT": (10, 2, 4, 4), "CARROT": (20, 2, 3, 3),
         "MELON": (80, 10, 10, 6)}''',
'''# cost, first yield age, final event age, harvest-capacity units
CROPS = {"WHEAT": (10, 2, 4, 6), "CARROT": (20, 2, 3, 4),
         "TOMATO": (50, 8, 11, 4), "STRAWBERRY": (100, 10, 16, 4),
         "MELON": (80, 10, 12, 6)}
ONGOING = {"TOMATO": (8, 1, 11), "STRAWBERRY": (10, 2, 16)}''')
    source = replace_once(source,
'''def agent(obs, configuration=None):''',
'''# Frozen standalone projection of ROWAN events.py at blob
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


def agent(obs, configuration=None):''')
    source = replace_once(source,
"POLICY = {'animal_cap': 20, 'max_hands': 8, 'crop_cap': 6, 'forecast_days': 8, 'care': True, 'mixed': True, 'expansion': False}",
"POLICY = {'animal_cap': 18, 'max_hands': 12, 'crop_cap': 24, 'forecast_days': 8, 'care': True, 'mixed': True, 'expansion': True}")
    source = replace_once(source,
'''    total_capacity = len(spots)
    crop_cap = min(policy["crop_cap"], max(0, total_capacity - len(animals) - pending - 2))
    choice, crop_roi = None, 0
    for crop, (cost, first, mature, yield_) in CROPS.items():
        if remaining_days < mature + .25: continue
        net = (yield_ * (.5 * prices[crop] + .5 * future_prices[crop]) - cost) / (mature + 1)
        if crop == "WHEAT" and animals: net *= 1.3
        if net > crop_roi: crop_roi, choice = net, crop
    if len(animals) > 24: crop_cap = min(3, crop_cap)
''',
'''    total_capacity = len(spots)
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
''')
    source = replace_once(source,
'''        if product == "WHEAT" and not ending: qty = max(0, qty - wheat_keep - 2)
        if qty: orders.append(["SELL", product, qty])''',
'''        if product == "WHEAT" and not ending: qty = max(0, qty - wheat_keep - 2)
        if product == "FERTILIZER" and not ending:
            fert_keep = min(4, sum(_fertilizer_window(p[2], day, step, turns, steps) is not None for p in plants))
            qty = max(0, qty - fert_keep)
        if qty: orders.append(["SELL", product, qty])''')
    source = replace_once(source,
'''    cash = farm["money"] + sum(
        qty * prices[p] for op, p, qty in orders if op == "SELL")''',
'''    cash = farm["money"] + sum(
        _sale_value(p, qty, market) for op, p, qty in orders if op == "SELL")''')
    source = replace_once(source,
'''    reserve = 150 + max(2, len(animals)) * prices["WHEAT"]
    can_buy = can_develop and affordable_animal is not None and pending < 5
    if can_buy and cash > reserve + ANIMALS[affordable_animal][0]:
        qty = min(3, 5-pending, policy["animal_cap"]-len(animals)-pending,
                  max(0, total_capacity-len(animals)-len(plants)-pending),
                  int((cash-reserve)/ANIMALS[affordable_animal][0]))
        if qty:
            orders.append(["BUY_ANIMAL", affordable_animal, qty])
            cash -= qty * ANIMALS[affordable_animal][0]
''',
'''    reserve = 180 + max(2, len(animals)) * prices["WHEAT"]
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
''')
    source = replace_once(source,
'''    target_hands = min(policy["max_hands"], max(3, math.ceil(
        (len(animals)*5.5 + len(plants)*2.0 + pending*6 + (30 if can_develop else 0))/18)))''',
'''    ongoing_plants = sum(p[2]["crop"] in ONGOING for p in plants)
    target_hands = min(policy["max_hands"], max(4, math.ceil(
        (len(animals)*5.5 + len(plants)*2.0 + ongoing_plants*3.0
         + pending*6 + (24 if can_develop else 0))/17)))''')
    source = replace_once(source,
'''    carried_wheat = sum(inv.get("WHEAT", 0) for inv in inventories)
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
''',
'''    if (choice and len(plants) < crop_cap and seeds.get(choice, 0) < 2
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
''')
    source = replace_once(source,
'''            # Pick up enough feed for a small route, with reservation across workers.
            if not ending and inv.get("WHEAT", 0) == 0 and unfed:''',
'''            # Reserve and route fertilizer from observable crop ages only.
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
            if not ending and inv.get("WHEAT", 0) == 0 and unfed:''')
    source = replace_once(source,
'''                if crop in CROPS and age >= CROPS[crop][2] and plant.get("yield_units",0):
                    add((x,y), ["HARVEST"], plant["yield_units"]*prices[crop]*1.1)
                elif ending and crop in CROPS and age >= CROPS[crop][1] and plant.get("yield_units",0):
                    add((x,y), ["HARVEST"], plant["yield_units"]*prices[crop]*2)''',
'''                if crop in CROPS and plant.get("yield_units",0):
                    held = plant["yield_units"]
                    ongoing = crop in ONGOING
                    ready = age >= CROPS[crop][1] if ongoing else age >= CROPS[crop][2]
                    if ready and (not ongoing or held >= 2 or ending or age >= ONGOING[crop][2]):
                        add((x,y), ["HARVEST"], held*prices[crop]*(1.45 if ongoing else 1.1))''')
    source = replace_once(source,
'''            qty = existing.get(product, 0) + deposits[product]
            if qty:
                sales.append(["SELL", product, qty])''',
'''            qty = existing.get(product, 0) + deposits[product]
            if product == "FERTILIZER" and remaining_days > 2:
                keep = min(4, sum(_fertilizer_window(p[2], day, step, turns, steps) is not None for p in plants))
                qty = max(0, qty - min(deposits[product], keep))
            if qty:
                sales.append(["SELL", product, qty])''')
    source = ("# FLORA KAG-PRODUCTION: integrated land/labor/crop/fertilizer policy.\n" +
              "# Generated from exact selected KAG-COMPOSE bytes; see build.py.\n" + source)
    ast.parse(source)
    return source


def generate(output: Path = HERE / "candidate.py") -> str:
    data = build(PARENT.read_text())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(data)
    return hashlib.sha256(data.encode()).hexdigest()


if __name__ == "__main__":
    print(generate())
