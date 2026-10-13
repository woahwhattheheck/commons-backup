# SPDX-License-Identifier: Apache-2.0
"""Independent observation-reactive Kaggriculture benchmark challengers.

No TITAN imports, authored tapes, opponent private data, environment seed, clocks,
or persistent episode state. These are test opponents, not production overlays.
The small constants below follow the pinned Apache-2.0 Kaggle game specification.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import ceil

CROPS = {  # seed cost, first yield, last growth, ongoing
    'WHEAT': (10, 2, 4, False), 'CARROT': (20, 2, 3, False),
    'TOMATO': (50, 8, 8, True), 'STRAWBERRY': (100, 10, 10, True),
    'MELON': (80, 10, 12, False),
}
ANIMALS = {  # purchase cost, first yield, interval, product, structure
    'GOOSE': (300, 4, 1, 'EGG', 'COOP'),
    'COW': (400, 8, 2, 'MILK', 'PASTURE'),
    'SHEEP': (500, 6, 3, 'WOOL', 'PASTURE'),
}
PRODUCTS = tuple(CROPS) + ('EGG', 'MILK', 'WOOL', 'FERTILIZER')

@dataclass(frozen=True)
class Profile:
    name: str
    livestock: tuple[tuple[str, int], ...]
    crops: tuple[str, ...]
    hands: int = 9
    plant_limit: int = 10

PROFILES = {
    'dairy': Profile('dairy', (('COW', 18),), ('CARROT',), 10, 5),
    'poultry': Profile('poultry', (('GOOSE', 20),), ('WHEAT',), 10, 3),
    'fiber': Profile('fiber', (('SHEEP', 16),), ('CARROT',), 10, 5),
    'roots': Profile('roots', (), ('CARROT', 'WHEAT'), 8, 25),
    'orchard': Profile('orchard', (('COW', 6), ('SHEEP', 4), ('GOOSE', 4)),
                       ('STRAWBERRY', 'CARROT', 'WHEAT'), 10, 10),
}

def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def _move(pos, goal):
    if pos[0] != goal[0]:
        return ['EAST' if pos[0] < goal[0] else 'WEST']
    if pos[1] != goal[1]:
        return ['SOUTH' if pos[1] < goal[1] else 'NORTH']
    return ['PASS']

def _fib(n):
    a = b = 1
    for _ in range(n):
        a, b = b, a + b
    return a

def _project(farm, private, actor, action, day, tpd, capacity):
    """Only the legal unit subset this policy emits; no market/engine prediction.

    Shared seeds/shed/tile flags are reserved in actual farmer-then-hand order.
    A later unit never acts on a purchase or hire that has not executed yet.
    """
    pos = farm['farmer'] if actor == 0 else farm['hands'][actor - 1]
    inv = private['inventories'][actor]
    x, y = pos
    tile = farm['tiles'][y][x]
    op = action[0]
    if op in ('EAST', 'WEST', 'NORTH', 'SOUTH'):
        dx, dy = {'EAST': (1, 0), 'WEST': (-1, 0), 'NORTH': (0, -1), 'SOUTH': (0, 1)}[op]
        pos[:] = [x + dx, y + dy]
    elif op == 'PICKUP':
        item, n = action[1:]
        n = min(n, private['shed'].get(item, 0))
        private['shed'][item] = private['shed'].get(item, 0) - n
        if n:
            inv[item] = inv.get(item, 0) + n
    elif op == 'DROP':
        for item, n in list(inv.items()):
            take = min(n, max(0, capacity - sum(private['shed'].values())))
            private['shed'][item] = private['shed'].get(item, 0) + take
        inv.clear()
    elif op == 'DIG':
        farm['tiles'][y][x] = None
    elif op.startswith('BUILD_'):
        farm['tiles'][y][x] = {'kind': op[6:]}
    elif op == 'PLACE':
        item = action[1]
        inv[item] -= 1
        if not inv[item]:
            del inv[item]
        farm['tiles'][y][x] = {
            'kind': ANIMALS[item][4], 'animal': item, 'placed_day': day,
            'yield_units': 0, 'consecutive_unfed': 0, 'fed_today': False,
            'cared_today': False, 'fertilizer_available': False, 'pending_care_bonus': 0,
        }
    elif op == 'PLANT':
        crop = action[1]
        private['seeds'][crop] -= 1
        cd = CROPS[crop]
        farm['tiles'][y][x] = {
            'kind': 'PLANT', 'crop': crop, 'planted_day': day,
            'watered_today': False, 'consecutive_unwatered': 1,
            'yield_units': 0 if cd[3] else 1,
            'max_lifespan_step': -1 if cd[3] else (day + cd[2] + 1) * tpd,
            'fertilized_until_day': -1,
        }
    elif op == 'WATER':
        tile['watered_today'] = True
        cd = CROPS[tile['crop']]
        age = day - tile['planted_day']
        if not cd[3] and (cd[2] + 1) // 2 <= age <= cd[2]:
            bonus = 2 if tile.get('fertilized_until_day', -1) >= day else 1
            tile['yield_units'] = min(6 if tile['crop'] in ('WHEAT', 'MELON') else 4,
                                      tile['yield_units'] + bonus)
    elif op == 'FEED':
        inv['WHEAT'] -= 1
        if not inv['WHEAT']:
            del inv['WHEAT']
        tile['fed_today'] = True
    elif op == 'CARE':
        tile['cared_today'] = True
    elif op == 'COLLECT_FERTILIZER':
        tile['fertilizer_available'] = False
        inv['FERTILIZER'] = inv.get('FERTILIZER', 0) + 1
    elif op == 'HARVEST':
        item = tile['crop'] if tile['kind'] == 'PLANT' else ANIMALS[tile['animal']][3]
        inv[item] = inv.get(item, 0) + tile['yield_units']
        tile['yield_units'] = 0
        if tile['kind'] == 'PLANT' and not CROPS[tile['crop']][3]:
            farm['tiles'][y][x] = None


def act(observation, configuration=None, *, profile='orchard'):
    """Kaggle callable core. Unknown profiles raise; input objects are unchanged."""
    p = PROFILES[profile]
    cfg = configuration or {}
    tpd = max(1, int(cfg.get('turnsPerDay', 24)))
    last = int(cfg.get('episodeSteps', 720)) - 2
    step = int(observation.get('step', int(observation.get('day', 0)) * tpd
                               + int(observation.get('hour', 0))))
    if not observation.get('farms'):
        return {'farmer': ['PASS'], 'hands': [], 'market': []}
    day, hour = divmod(step, tpd)
    remaining = last - step
    season_days = remaining / tpd
    seat = int(observation['player'])
    farm = deepcopy(observation['farms'][seat])
    private = deepcopy(observation['private'])
    n = len(farm['tiles'])
    half = n // 2
    shed_tiles = ((half - 1, half - 1), (half, half - 1),
                  (half - 1, half), (half, half))
    capacity = int(cfg.get('shedCapacity', 100))
    quotes = observation['market']['prices']
    actor_count = len(farm['hands']) + 1
    while len(private['inventories']) < actor_count:
        private['inventories'].append({})
    animal_count = sum(isinstance(t, dict) and 'animal' in t for row in farm['tiles'] for t in row)
    plant_count = sum(isinstance(t, dict) and t.get('kind') == 'PLANT'
                      for row in farm['tiles'] for t in row)
    reserved = set()
    actions = []
    for idx in range(actor_count):
        pos = farm['farmer'] if idx == 0 else farm['hands'][idx - 1]
        inv = private['inventories'][idx]
        home = min(shed_tiles, key=lambda s: (distance(pos, s), s))
        dh = distance(pos, home)
        stock = private['shed']
        output = sum(v for k, v in inv.items() if k in PRODUCTS and k != 'WHEAT')
        carried = sum(sum(i.values()) for i in private['inventories'])
        terminal_return = remaining <= dh + 2 and any(inv.values())
        drop_pressure = (output >= 9 or (output and carried + sum(stock.values()) > capacity - 10))
        chosen = None
        if terminal_return or drop_pressure:
            chosen = ['DROP'] if dh == 0 else _move(pos, home)
        elif remaining <= dh + 1:
            chosen = ['PASS']
        if chosen is None and dh == 0:
            # Deliver outputs before repurposing an empty courier as a feeder.
            if output >= 3:
                chosen = ['DROP']
            elif not any(inv.get(a, 0) for a in ANIMALS):
                for animal, _ in p.livestock:
                    if stock.get(animal, 0) and hour < tpd - 5:
                        chosen = ['PICKUP', animal, 1]
                        break
            if chosen is None and animal_count and inv.get('WHEAT', 0) == 0 and stock.get('WHEAT', 0):
                unfed = sum(isinstance(t, dict) and 'animal' in t and not t['fed_today']
                            for row in farm['tiles'] for t in row)
                if unfed and remaining >= 3:
                    chosen = ['PICKUP', 'WHEAT', min(3, stock['WHEAT'], unfed)]
        jobs = []
        if chosen is None:
            for y, row in enumerate(farm['tiles']):
                for x, tile in enumerate(row):
                    target = (x, y)
                    if tile == 'LOCKED' or target in reserved:
                        continue
                    d = distance(pos, target)
                    if d + 1 > min(tpd - hour, remaining + 1):
                        continue
                    task, value = None, 0.0
                    if isinstance(tile, dict) and 'animal' in tile:
                        a = ANIMALS[tile['animal']]
                        # Protect survival first; bonus care cannot replace food.
                        if not tile['fed_today'] and inv.get('WHEAT', 0) and season_days >= 0.5:
                            task = ['FEED']
                            value = (650 if tile['consecutive_unfed'] else 220) + quotes[a[3]] / a[2]
                        if tile.get('yield_units', 0) and quotes[a[3]] * tile['yield_units'] > value:
                            task, value = ['HARVEST'], quotes[a[3]] * tile['yield_units']
                        if tile.get('fertilizer_available') and quotes['FERTILIZER'] * 1.2 > value:
                            task, value = ['COLLECT_FERTILIZER'], quotes['FERTILIZER'] * 1.2
                        care_value = quotes[a[3]] / a[2] + 45
                        if (tile['fed_today'] and not tile['cared_today'] and season_days >= 1.5
                                and tile.get('pending_care_bonus', 0) < 4 and care_value > value):
                            task, value = ['CARE'], care_value
                    elif isinstance(tile, dict) and tile.get('kind') == 'PLANT':
                        crop = tile['crop']; cd = CROPS[crop]; age = day - tile['planted_day']
                        due = cd[3] or age >= cd[2] or remaining < tpd
                        if not tile['watered_today'] and season_days >= 0.1:
                            task = ['WATER']; value = 150 + 180 * min(1, tile['consecutive_unwatered'])
                        if (tile.get('yield_units', 0) and age >= cd[1] and due
                                and (tile['watered_today'] or cd[3] or remaining < tpd)):
                            task, value = ['HARVEST'], quotes[crop] * tile['yield_units'] + 250
                    else:
                        held = next((a for a in ANIMALS if inv.get(a, 0)), None)
                        if held is not None and hour < tpd - d - 2:
                            structure = ANIMALS[held][4]
                            if tile is None:
                                task, value = ['BUILD_' + structure], 500
                            elif tile == {'kind': structure}:
                                task, value = ['PLACE', held], 700
                            elif isinstance(tile, dict) and tile.get('kind') == 'WEED':
                                task, value = ['DIG'], 350
                        elif plant_count < p.plant_limit and not any(inv.get(a, 0) for a in ANIMALS):
                            eligible = [c for c in p.crops if private['seeds'].get(c, 0)
                                        and season_days >= CROPS[c][1] + 1]
                            if eligible and hour < tpd - d - 2:
                                crop = max(eligible, key=lambda c: quotes[c] / (CROPS[c][1] + 2))
                                if tile is None:
                                    task, value = ['PLANT', crop], 100 + quotes[crop]
                                elif isinstance(tile, dict) and tile.get('kind') == 'WEED':
                                    task, value = ['DIG'], 90
                    if task is not None:
                        # Do not harvest into inventory that cannot reach the shed
                        # on the terminal partial day; EOD is not terminal liquidation.
                        home_after = min(distance(target, s) for s in shed_tiles)
                        if task[0] in ('HARVEST', 'COLLECT_FERTILIZER') and remaining < tpd - hour:
                            if d + 1 + home_after + 1 > remaining + 1:
                                continue
                        jobs.append((value / (d + 1.5), -d, -y, -x, target, task))
            # Get feed for otherwise unreachable animal-service obligations.
            needs_feed = any(isinstance(t, dict) and 'animal' in t and not t['fed_today']
                             for row in farm['tiles'] for t in row)
            if (needs_feed and not inv.get('WHEAT', 0) and stock.get('WHEAT', 0)
                    and season_days >= 0.5 and dh + 3 <= tpd - hour):
                jobs.append((250 / (dh + 1.5), -dh, -home[1], -home[0], home,
                             ['PICKUP', 'WHEAT', min(3, stock['WHEAT'])]))
            if jobs:
                _, _, _, _, target, task = max(jobs)
                reserved.add(target)
                chosen = task if tuple(pos) == target else _move(pos, target)
            else:
                chosen = ['PASS']
        if chosen[0] == 'PLANT':
            plant_count += 1
        elif chosen[0] == 'HARVEST':
            t = farm['tiles'][pos[1]][pos[0]]
            if isinstance(t, dict) and t.get('kind') == 'PLANT' and not CROPS[t['crop']][3]:
                plant_count -= 1
        _project(farm, private, idx, chosen, day, tpd, capacity)
        actions.append(chosen)
    # Only actual pre-market unit consequences are used here.
    market = []
    stock = private['shed']
    reserve_feed = animal_count if season_days >= 0.5 else 0
    for item in sorted(PRODUCTS, key=lambda k: (-quotes[k], k)):
        sell = max(0, stock.get(item, 0) - (reserve_feed if item == 'WHEAT' else 0))
        if sell:
            market.append(['SELL', item, sell])
    limit = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))
    # Procurement uses observed cash, never fictional credits from future sales.
    budget = max(0, farm['money'])
    space = max(0, capacity - sum(stock.values()))
    if season_days >= 0.5 and animal_count:
        target = animal_count + min(3, actor_count)
        feed = stock.get('WHEAT', 0) + sum(i.get('WHEAT', 0) for i in private['inventories'])
        unit_budget = max(1, ceil(quotes['WHEAT'] * 1.1) + 2)
        amount = min(max(0, target - feed), space, int(budget // unit_budget))
        if amount:
            market.append(['BUY_PRODUCT', 'WHEAT', amount]); budget -= amount * unit_budget; space -= amount
    board_animals = {a: sum(isinstance(t, dict) and t.get('animal') == a
                            for row in farm['tiles'] for t in row) for a in ANIMALS}
    for animal, target in p.livestock:
        owned = board_animals[animal] + stock.get(animal, 0) + sum(i.get(animal, 0) for i in private['inventories'])
        cost, first, *_ = ANIMALS[animal]
        amount = min(2, target - owned, space, int(max(0, budget - 200) // cost))
        if amount > 0 and season_days >= first + 4 and hour < tpd - 6:
            market.append(['BUY_ANIMAL', animal, amount]); budget -= amount * cost; space -= amount
    if plant_count < p.plant_limit and sum(private['seeds'].values()) < 5:
        eligible = [c for c in p.crops if season_days >= CROPS[c][1] + 2]
        if eligible:
            crop = max(eligible, key=lambda c: quotes[c] / (CROPS[c][1] + 2))
            amount = min(4, p.plant_limit - plant_count, int(max(0, budget - 50) // CROPS[crop][0]))
            if amount:
                market.append(['BUY_SEED', crop, amount]); budget -= amount * CROPS[crop][0]
    target_hands = min(p.hands, max(2, ceil((animal_count * 6 + plant_count * 2) / 18)))
    if day < 2:
        target_hands = max(target_hands, 5 if p.livestock else 4)
    hires = farm['hires_today']
    while len(farm['hands']) + sum(o[0] == 'HIRE' for o in market) < target_hands and hour <= 4 and remaining >= 12:
        cost = _fib(hires) * int(cfg.get('farmHandCostMult', 1))
        if budget < cost or len(market) >= limit:
            break
        market.append(['HIRE']); budget -= cost; hires += 1
    return {'farmer': actions[0], 'hands': actions[1:], 'market': market[:limit]}


def agent(observation, configuration=None):
    return act(observation, configuration, profile='orchard')

def dairy(observation, configuration=None):
    return act(observation, configuration, profile='dairy')

def poultry(observation, configuration=None):
    return act(observation, configuration, profile='poultry')

def fiber(observation, configuration=None):
    return act(observation, configuration, profile='fiber')

def roots(observation, configuration=None):
    return act(observation, configuration, profile='roots')
