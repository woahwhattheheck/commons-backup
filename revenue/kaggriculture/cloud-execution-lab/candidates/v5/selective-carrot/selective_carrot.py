# SPDX-License-Identifier: Apache-2.0
"""Conditional age-three carrot production over an unchanged movement tape.

The WF1 leader census motivates looking at crop output; this intervention
instead changes the crop on wheat sites whose authored harvest occurs before
carrot expiry. It uses visible town demand and prices, never replay futures.
"""
from copy import deepcopy

MOVES = {'NORTH': (0, -1), 'SOUTH': (0, 1), 'EAST': (1, 0), 'WEST': (-1, 0)}
SHOPS = {'BAKERY': ('EGG', 'WHEAT'), 'PIZZA_SHOP': ('MILK', 'TOMATO', 'WHEAT'),
         'BRUNCH_SPOT': ('EGG', 'WHEAT', 'STRAWBERRY'), 'YARN_STORE': ('WOOL',),
         'ICE_CREAM_SHOP': ('STRAWBERRY', 'MILK', 'WHEAT'), 'PET_CAFE': ('CARROT',),
         'SMOOTHIE_SHOP': ('STRAWBERRY', 'MILK'),
         'FARMERS_MARKET': ('WHEAT', 'CARROT', 'TOMATO', 'STRAWBERRY')}


def unit(row, i):
    return row.get('farmer', ['PASS']) if i == 0 else (row.get('hands', [])[i-1]
        if i <= len(row.get('hands', [])) else ['PASS'])


def set_unit(row, i, action):
    if i == 0:
        row['farmer'] = action
    else:
        row['hands'][i-1] = action


def move(pos, action):
    dx, dy = MOVES.get(action[0] if action else '', (0, 0))
    q = (pos[0]+dx, pos[1]+dy)
    return q if 0 <= q[0] < 10 and 0 <= q[1] < 10 else pos


def absorption(item, start, end, shops, cfg):
    amount = 0
    for t in range(start, end):
        if t % max(1, int(cfg.get('townShopSellInterval', 4))) == 0:
            for shop in shops:
                products = SHOPS.get(shop, ())
                if item in products:
                    amount += 2 if len(products) == 1 else 1
        if t % max(1, int(cfg.get('townCenterSellInterval', 24))) == 0:
            amount += 1
    return amount


def schedule(obs, selected, route, stop):
    """Position-only authored schedule, starting from actual own positions.

    Future hires are conditional on the tape being funded. The planting itself
    is admitted later against actual position, seed inventory and returned row.
    """
    now = int(obs['step'])
    farm = obs['farms'][obs['player']]
    positions = [tuple(farm['farmer']), *map(tuple, farm['hands'])]
    shed = ((4, 4), (5, 4), (4, 5), (5, 5))
    out = []
    for t in range(now, min(stop, len(route), 719)):
        row = selected if t == now else route[t]
        events = [(i, p, list(unit(row, i))) for i, p in enumerate(positions)]
        out.append((t, events))
        positions = [move(p, a) for _, p, a in events]
        for order in row.get('market', [])[:10]:
            if order and order[0] == 'HIRE':
                positions.append(min(shed, key=lambda p: (positions.count(p), shed.index(p))))
        if (t+1) % 24 == 0:
            positions = [(4, 4)]
    return out


def crop_lot(timeline, plant_step, worker, site):
    """Require living carrot and wheat with equal output at an age-three harvest."""
    planted_day = plant_step // 24
    plants = {p: {'yield': 1, 'watered': False, 'dry': 1, 'fert': -1}
              for p in ('WHEAT', 'CARROT')}
    begun = False
    for t, events in timeline:
        if t < plant_step:
            continue
        day = t // 24
        if day >= planted_day + 4:
            return None
        for i, pos, action in events:
            if pos != site:
                continue
            op = action[0] if action else 'PASS'
            if t == plant_step and i == worker and action == ['PLANT', 'WHEAT']:
                begun = True
                continue
            if not begun:
                continue
            if op in ('DIG', 'PLANT'):
                return None
            if op == 'FERTILIZE':
                return None  # existing fertilization owns this site's crop economics
            if op == 'WATER':
                for crop, p in plants.items():
                    if not p['watered']:
                        p['watered'] = True
                        if 2 <= day-planted_day <= (4 if crop == 'WHEAT' else 3):
                            p['yield'] = min(6 if crop == 'WHEAT' else 4, p['yield']+1)
            if op == 'HARVEST':
                if day-planted_day != 3 or plants['CARROT']['yield'] != plants['WHEAT']['yield']:
                    return None
                # Some wheat is fed directly from the harvesting hand. A shed
                # purchase cannot replace that carried input without extra
                # travel, so those crop sites remain wheat.
                delivered = False
                sale_step = (t//24+1)*24
                for u, later in timeline:
                    if u <= t:
                        continue
                    if u//24 != t//24:
                        break
                    for j, later_pos, cmd in later:
                        if j != i:
                            continue
                        if cmd and cmd[0] == 'FEED' and not delivered:
                            return None
                        if cmd == ['DROP'] or cmd[:2] == ['PLACE', 'WHEAT']:
                            delivered = True
                        if cmd == ['DROP'] and later_pos in ((4,4), (5,4), (4,5), (5,5)):
                            sale_step = min(sale_step, u)
                return {'plant_step': plant_step, 'worker': worker, 'site': list(site),
                        'planted_day': planted_day, 'harvest_step': t,
                        'harvest_worker': i, 'quantity': plants['CARROT']['yield'],
                        'sale_step': sale_step}
        if begun and (t+1) % 24 == 0:
            for p in plants.values():
                p['dry'] = 0 if p['watered'] else p['dry']+1
                p['watered'] = False
                if p['dry'] >= 2:
                    return None
    return None


class CropChoice:
    def __init__(self, quote, *, max_active=4, margin=12, receipt_discount=0.8):
        self.quote = quote
        self.max_active, self.margin, self.discount = max_active, margin, receipt_discount
        self.pending = None
        self.lots = []
        self.credit = 0
        self.previous = None
        self.last_step = -1
        self.report = {}

    def observe(self, obs):
        now = int(obs['step'])
        if now <= self.last_step:
            if now == self.last_step:
                return
            self.pending = None; self.lots = []; self.credit = 0; self.previous = None
        self.last_step = now
        self.report = {'prepared': 0, 'planted': 0, 'harvested': 0, 'extra_sales': 0,
                       'replacement_wheat': 0}
        farm = obs['farms'][obs['player']]
        for lot in self.lots:
            x, y = lot['site']; tile = farm['tiles'][y][x]
            same = isinstance(tile, dict) and tile.get('crop') == 'CARROT' and tile.get('planted_day') == lot['planted_day']
            if lot['status'] == 'plant_returned':
                lot['status'] = 'growing' if same else 'lost'
            elif lot['status'] == 'harvest_returned':
                if not same:
                    self.credit += lot['actual_quantity']
                    self.report['harvested'] += lot['actual_quantity']
                    lot['status'] = 'harvested'
                else:
                    lot['status'] = 'growing'
            elif lot['status'] == 'growing' and not same:
                lot['status'] = 'lost'
        # The prior actual returned sale was bounded by post-unit shed stock.
        # CARROT cannot be purchased, so the lockstep engine executes all such
        # units regardless of rival ordering. EOD deposits do not mask fills.
        if self.previous and self.previous['step'] == now-1:
            old = self.previous
            sold = old['extra_sale']
            self.credit = max(0, self.credit-sold)
        self.lots = [x for x in self.lots if x['status'] not in ('lost', 'harvested')]

    def commit(self, obs, returned):
        """Bind receipts to main.agent's actual return, including fallback."""
        farm = obs['farms'][obs['player']]
        positions = [farm['farmer'], *farm['hands']]
        for lot in self.lots:
            if lot['status'] == 'plant_returned' and unit(returned, lot['worker']) != ['PLANT', 'CARROT']:
                lot['status'] = 'lost'
            if lot['status'] == 'harvest_returned' and not any(
                    pos == lot['site'] and unit(returned, i) == ['HARVEST'] for i, pos in enumerate(positions)):
                lot['status'] = 'growing'
        if self.previous:
            q = self.previous['extra_sale']
            if not q or returned.get('market', [])[-1:] != [['SELL', 'CARROT', q]]:
                # A seed buy may follow the sale; retain its exact recorded slot.
                slot = self.previous.get('sale_slot')
                if slot is None or returned.get('market', [])[slot:slot+1] != [['SELL', 'CARROT', q]]:
                    self.previous['extra_sale'] = 0

    def units(self, obs, cfg, selected, route_id):
        self.observe(obs)
        out = selected
        farm = obs['farms'][obs['player']]
        positions = [farm['farmer'], *farm['hands']]
        p = self.pending
        if p and int(obs['step']) >= p['plant_step']:
            self.pending = None
            if (int(obs['step']) == p['plant_step'] and route_id == p['route']
                    and obs['private']['seeds'].get('CARROT', 0) >= p['seed_floor']+len(p['lots'])):
                demand = sum(unit(selected, i) == ['PLANT', 'CARROT'] for i in range(len(positions)))
                wheat_demand = sum(unit(selected, i) == ['PLANT', 'WHEAT'] for i in range(len(positions)))
                eligible = []
                for lot in p['lots']:
                    i = lot['worker']; x, y = lot['site']
                    if (i < len(positions) and positions[i] == lot['site'] and farm['tiles'][y][x] is None
                            and unit(selected, i) == ['PLANT', 'WHEAT']):
                        eligible.append(lot)
                if (eligible and obs['private']['seeds'].get('CARROT', 0) >= demand+len(eligible)
                        and obs['private']['seeds'].get('WHEAT', 0) >= wheat_demand):
                    out = deepcopy(selected)
                    for lot in eligible:
                        set_unit(out, lot['worker'], ['PLANT', 'CARROT'])
                        self.lots.append(dict(lot, status='plant_returned'))
                    self.report['planted'] = len(eligible)
        for lot in self.lots:
            if lot['status'] != 'growing':
                continue
            x, y = lot['site']; tile = farm['tiles'][y][x]
            if any(pos == lot['site'] and unit(out, i) == ['HARVEST'] for i, pos in enumerate(positions)):
                lot['status'] = 'harvest_returned'
                lot['actual_quantity'] = tile.get('yield_units', 0)
        return out

    def value(self, obs, cfg, lot, extra_supply=0):
        now = int(obs['step']); end = lot['sale_step']; q = lot['quantity']
        market = obs['market']; shops = obs['town']['unlocked_shops']; params = market.get('params')
        supply = obs['private']['shed'].get('CARROT', 0)
        supply += sum(i.get('CARROT', 0) for i in obs['private']['inventories'])
        # Both farms' visible carrot plants are counted at their full possible
        # lot capacity, even if their actual release occurs after this horizon.
        supply += sum(4 for f in obs['farms'] for row in f['tiles'] for tile in row
                      if isinstance(tile, dict) and tile.get('crop') == 'CARROT')
        supply += sum(x['quantity'] for x in self.lots if x['status'] == 'plant_returned')
        carrot_inv = market['inventory']['CARROT']-absorption('CARROT', now, end, shops, cfg)+supply+extra_supply
        wheat_inv = market['inventory']['WHEAT']-absorption('WHEAT', now, end, shops, cfg)
        # Full replacement-feed cost prices all removed wheat units; it is not
        # added again as foregone revenue. Existing wheat seed buys stay intact.
        carrot_receipt = sum(self.quote('CARROT', carrot_inv+k, params) for k in range(q))
        wheat_replacement = sum(self.quote('WHEAT', wheat_inv-1-k, params) for k in range(q))
        edge = self.discount*carrot_receipt-wheat_replacement-20
        return {'edge': round(edge, 4), 'carrot_receipt': carrot_receipt,
                'wheat_replacement': wheat_replacement, 'extra_seed_cost': 20,
                'carrot_inventory': carrot_inv, 'wheat_inventory': wheat_inv,
                'visible_carrot_supply_bound': supply+extra_supply}

    def market(self, obs, cfg, selected, route, route_id, post):
        now = int(obs['step']); out = selected
        # Feed replacement has priority over the optional incremental outlet.
        replace = sum(x['actual_quantity'] for x in self.lots if x['status'] == 'harvest_returned')
        if replace and len(out.get('market', [])) < 10:
            out = deepcopy(out)
            out.setdefault('market', []).append(['BUY_PRODUCT', 'WHEAT', replace])
            self.report['replacement_wheat'] = replace
        if self.credit:
            planned = sum(max(0, int(o[2])) for o in out.get('market', [])[:10]
                          if len(o) >= 3 and o[:2] == ['SELL', 'CARROT'])
            q = min(self.credit, max(0, post['private']['shed'].get('CARROT', 0)-planned))
            if q and len(out.get('market', [])) < 10:
                out = deepcopy(out); out.setdefault('market', []).append(['SELL', 'CARROT', q])
                self.report['extra_sales'] = q
        self.previous = {'step': now, 'extra_sale': self.report['extra_sales'],
                         'post_shed_carrot': post['private']['shed'].get('CARROT', 0),
                         'sale_slot': len(out.get('market', []))-1 if self.report['extra_sales'] else None}
        if (self.pending or len(self.lots) >= self.max_active or now < 240 or now >= 648
                or now % 24 == 23 or len(out.get('market', [])) >= 10):
            return out
        # Keep the known singleton crop_release site's preparation separate.
        if now == 372:
            return out
        farm = obs['farms'][obs['player']]
        if not any(unit(route[now+1], i) == ['PLANT', 'WHEAT']
                   for i in range(1+len(farm['hands']))):
            return out
        timeline = schedule(obs, out, route, min(719, ((now+1)//24+4)*24))
        if len(timeline) < 2:
            return out
        lots = []
        for i, site, action in timeline[1][1]:
            if action != ['PLANT', 'WHEAT'] or i >= 1+len(farm['hands']):
                continue
            x, y = site
            if post['farms'][obs['player']]['tiles'][y][x] is not None:
                continue
            lot = crop_lot(timeline, now+1, i, site)
            if lot is None or lot['sale_step'] > 718:
                continue
            # A not-yet-resolved branch can change the crop's service schedule.
            if any(now < checkpoint <= lot['harvest_step'] for checkpoint in (226, 360, 433)):
                continue
            receipt = self.value(obs, cfg, lot, sum(x['quantity'] for x in lots))
            if receipt['edge'] >= self.margin:
                lots.append(dict(lot, estimate=receipt))
            if len(lots)+len(self.lots) >= self.max_active or len(lots) >= 2:
                break
        if not lots:
            return out
        # Spending screen does not credit future sales or change fixed buys.
        # Keep $1000 above the literal requested current spend for input repair.
        spend = 0; hires = int(farm.get('hires_today', 0)); land = len(farm['unlocked_quadrants'])
        seeds = {'WHEAT':10, 'CARROT':20, 'TOMATO':50, 'STRAWBERRY':100, 'MELON':80}
        animals = {'GOOSE':300, 'COW':400, 'SHEEP':500}
        for o in out.get('market', [])[:10]:
            if not o:
                continue
            if o[0] == 'HIRE':
                a, b = 1, 1
                for _ in range(hires): a, b = b, a+b
                spend += a*cfg.get('farmHandCostMult', 1); hires += 1
            elif o[0] == 'BUY_LAND':
                spend += (1000, 2000, 4000, 0)[min(max(land-1, 0), 3)]; land += 1
            elif len(o) >= 3 and o[0] == 'BUY_SEED':
                spend += seeds.get(o[1], 1000)*max(0, int(o[2]))
            elif len(o) >= 3 and o[0] == 'BUY_ANIMAL':
                spend += animals.get(o[1], 1000)*max(0, int(o[2]))
            elif len(o) >= 3 and o[0] == 'BUY_PRODUCT':
                q = max(0, int(o[2])); inv = obs['market']['inventory'].get(o[1], 0)
                spend += sum(self.quote(o[1], inv-101-k, obs['market'].get('params')) for k in range(q))
        if farm['money'] < spend+1000+20*len(lots):
            return out
        seed_floor = post['private']['seeds'].get('CARROT', 0)+sum(max(0, int(o[2]))
                     for o in out.get('market', [])[:10] if len(o) >= 3 and o[:2] == ['BUY_SEED','CARROT'])
        out = deepcopy(out); out.setdefault('market', []).append(['BUY_SEED', 'CARROT', len(lots)])
        self.pending = {'plant_step': now+1, 'route': route_id, 'seed_floor': seed_floor, 'lots': lots}
        self.report['prepared'] = len(lots)
        self.report['estimates'] = [x['estimate'] for x in lots]
        return out
