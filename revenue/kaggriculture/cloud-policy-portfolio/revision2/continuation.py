# SPDX-License-Identifier: Apache-2.0
"""Bounded economic projections of complete source-frozen route continuations.

No controller is constructed or called here. Scenarios are explicit conditional
streams, not probabilities or predictions of hidden state. Reported value is a
relative-cash proxy; only subsequent complete games measure winning strength.
"""
import ast
from collections import Counter, defaultdict
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time

ROOT = Path(__file__).resolve().parents[1]
ENGINE_SHA = 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def market_kernel(mechanics):
    """Execute unchanged pinned market queue definitions over supplied state."""
    path = ROOT / 'vendor/engine/kaggriculture.py'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ENGINE_SHA:
        raise ValueError('Pinned market source differs')
    names = {'_parse_order', '_process_market', '_refresh_prices'}
    nodes = [n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in nodes} != names:
        raise ValueError('Missing pinned market functions')
    namespace = dict(mechanics.__dict__)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def compatible(routes, current, target, step):
    return (target in routes and len(routes[current]) >= step and len(routes[target]) >= step
            and routes[current][:step] == routes[target][:step])


def _unit_phase(m, farm, private, action, step, config, repair=None):
    acts = [list(action.get('farmer', ['PASS'])), *[list(a) for a in action.get('hands', [])]]
    positions = [farm['farmer'], *farm['hands']]
    # Retain the exact parent's deterministic weed/no-op repair, without an Agent.
    if repair:
        for i, a in enumerate(acts[:len(positions)]):
            x, y = positions[i]
            tile = farm['tiles'][y][x]
            inv = private['inventories'][i] if i < len(private['inventories']) else {}
            if isinstance(tile, dict) and tile.get('kind') == 'WEED' and repair(a, tile, inv, private['seeds'], x, y, len(farm['tiles'])):
                acts[i] = ['DIG']
    demand = Counter(a[1] for a in acts if len(a) > 1 and a[0] == 'PLANT')
    blocked = {p for p, q in demand.items() if q > private['seeds'].get(p, 0)}
    for i, a in enumerate(acts):
        if len(a) > 1 and a[0] == 'PLANT' and a[1] in blocked:
            a = ['PASS']
        m._apply_unit_action(farm, private, i, a, len(farm['tiles']), step // 24, 24, config.get('shedCapacity', 100))
    return len(blocked)


def scenario_windows(history, now, end, products, capacity=100):
    """Repeat whole prior days jointly across products; include unknown stresses.

    Repetition is a scenario assumption, not a forecast confidence statement.
    Operating-product buys/sales remain unidentified and receive separate shocks.
    """
    cases = []
    for lag in (1, 2, 3):
        start = now - 24 * lag
        if start < 0 or not all(t in history.records[p] and history.records[p][t].exact
                               for p in products for t in range(start, start + 24)):
            continue
        day = [[['SELL', p, history.records[p][start+h].lower]
                for p in products if history.records[p][start+h].lower] for h in range(24)]
        cases.append({'id': 'prior_day_' + str(lag), 'day_orders': day,
                      'training_start': start, 'training_end': start+23,
                      'future_shops': [], 'operating_buy': 0})
    # Explicit unknown branch; no fictional probability is attached.
    cases.append({'id': 'unknown_zero_supply', 'day_orders': [[] for _ in range(24)],
                  'training_start': None, 'training_end': None, 'future_shops': [], 'operating_buy': 0})
    if cases and cases[0]['training_start'] is not None:
        shock = deepcopy(cases[0])
        shock.update(id='unknown_shifted_double_supply', operating_buy=8)
        # Allowed but unknown shop draws: stress the rival's milk/strawberry
        # receipts at the source's next unlock dates. These are never seed draws.
        shock['future_shops'] = [(t, 'SMOOTHIE_SHOP') for t in range((now//72+1)*72, end+1, 72)]
        day = [[] for _ in range(24)]
        for h, orders in enumerate(shock['day_orders']):
            available = capacity
            for op, product, quantity in orders:
                quantity = min(available, quantity * 2)
                available -= quantity
                if quantity:
                    day[(h+1) % 24].append([op, product, quantity])
        shock['day_orders'] = day
        cases.append(shock)
    return cases


def project(observation, config, route, scenario, mechanics, kernel, *, repair=None,
            end=718, deadline=None, keep_curve=False):
    """Exact conditional owned unit/cost transitions under a bounded sale rule.

    Future market SELL timing uses the supplied route, clamped by physical stock,
    with route-dead stock and capacity liquidated. It is a projection, not a second
    SELL scheduler. Unobserved new weeds and shop draws are scenario assumptions.
    """
    now = int(observation['step'])
    own = int(observation['player'])
    rival = 1-own
    m = mechanics
    farm = deepcopy(observation['farms'][own])
    other = deepcopy(observation['farms'][rival])
    private = deepcopy(observation['private'])
    other_private = {'shed': {}, 'seeds': {}, 'inventories': [{}]}
    market = deepcopy(observation['market'])
    shops = list(observation.get('town', {}).get('unlocked_shops', []))
    farms = [None, None]; farms[own], farms[rival] = farm, other
    privates = [None, None]; privates[own], privates[rival] = private, other_private
    opening = [f['money'] for f in farms]
    low = farm['money']; failures = 0; blocked_plants = 0
    totals = defaultdict(float); fills = defaultdict(int); curve = []
    # Price values are exact and cached only within this projected parameter set.
    original_quote = m.market_price
    params = market.get('params')
    quote = lru_cache(maxsize=8192)(lambda item, inv: original_quote(item, inv, params))
    ns = dict(kernel)
    # Function globals are rebuilt so simultaneous projections share no hooks.
    from types import FunctionType
    for name in ('_process_market', '_parse_order', '_refresh_prices'):
        ns[name] = FunctionType(kernel[name].__code__, ns, name)
    ns['market_price'] = lambda item, inv, _params=None: quote(item, inv)
    step = now
    def committed(op, item, price, f, p, mk, cap=100):
        nonlocal failures, low
        before = f['money']
        result = m._commit_unit(op, item, price, f, p, mk, cap)
        who = 'own' if f is farm else 'rival'
        if result:
            totals[who+':'+op+':'+item] += f['money']-before
            fills[who+':'+op+':'+item] += 1
        elif f is farm and op.startswith('BUY') and f['money'] < price:
            failures += 1
        low = min(low, farm['money'])
        return result
    ns['_commit_unit'] = committed
    def hired(f, p, board, mult=1):
        nonlocal failures, low
        before = f['money']; count = len(f['hands'])
        result = m._do_hire(f, p, board, mult)
        totals['own:HIRE'] += f['money']-before
        if f is farm and len(f['hands']) == count:
            failures += 1
        low = min(low, farm['money'])
        return result
    ns['_do_hire'] = hired
    # Future request counts ensure only route-dead stock is added to sale queues.
    future = Counter()
    remaining = {}
    for t in range(end, now-1, -1):
        remaining[t] = future.copy()
        for order in route[t].get('market', []):
            if len(order) > 2 and order[0] == 'SELL':
                future[order[1]] += int(order[2])
    for step in range(now, end+1):
        if deadline is not None and step % 16 == 0 and time.perf_counter() >= deadline:
            raise TimeoutError('Continuation budget exhausted')
        for date, shop in scenario.get('future_shops', []):
            if date == step and len(shops) < 8:
                shops.append(shop)
        action = route[step]
        blocked_plants += _unit_phase(m, farm, private, action, step, config, repair)
        orders = deepcopy(action.get('market', []))
        # Clamp each source lot, preserving source slot positions in this model.
        stock = dict(private['shed'])
        for i, order in enumerate(orders):
            if len(order) > 2 and order[0] == 'SELL':
                p = order[1]; q = min(max(0, int(order[2])), stock.get(p, 0))
                orders[i] = ['SELL', p, q] if q else []
                stock[p] = stock.get(p, 0)-q
        candidates = []
        for p in m.PRODUCTS:
            surplus = max(0, stock.get(p, 0)-remaining[step][p])
            if surplus and quote(p, market['inventory'][p]) > 1:
                candidates.append(['SELL', p, surplus])
        candidates.sort(key=lambda x: -quote(x[1], market['inventory'][x[1]])*x[2])
        orders = (orders+candidates)[:config.get('maxMarketOrdersPerTurn', 10)]
        rival_orders = deepcopy(scenario['day_orders'][(step-now) % 24])
        # Each scenario has an explicit per-turn arrival, never hidden actual stock.
        other_private['shed'] = {}
        room = config.get('shedCapacity', 100)
        for i, order in enumerate(rival_orders):
            p = order[1]; q = min(room, max(0, int(order[2]))); room -= q
            order[2] = q
            other_private['shed'][p] = other_private['shed'].get(p, 0)+q
        if scenario.get('operating_buy') and step % 24 == 0:
            rival_orders.append(['BUY_PRODUCT', 'FERTILIZER', scenario['operating_buy']])
        actions = [None, None]; actions[own] = {'market': orders}; actions[rival] = {'market': rival_orders}
        state = [SimpleNamespace(action=actions[i], observation=SimpleNamespace(
            farms=farms, market=market, private=privates[i])) for i in (0, 1)]
        ns['_process_market'](state, SimpleNamespace(configuration=config))
        for p in m.PRODUCTS:
            consumed = 0
            if step % config.get('townShopSellInterval', 4) == 0:
                consumed += sum((2 if len(m.SHOPS.get(s, ())) == 1 else 1)
                                for s in shops if p in m.SHOPS.get(s, ()))
            if p != 'FERTILIZER' and step % config.get('townCenterSellInterval', 24) == 0:
                consumed += 1
            market['inventory'][p] -= consumed
        m._decay_plants(farm, step)
        if (step+1) % 24 == 0:
            m._daily_refresh_plants(farm, step // 24, 24)
            m._daily_refresh_animals(farm, step // 24)
            m._drop_inventories_to_shed(private, config.get('shedCapacity', 100))
            farm['farmer'] = list(m._default_spawn(len(farm['tiles'])))
            farm['hands'] = []; farm['hires_today'] = 0; private['inventories'] = [{}]
        if keep_curve:
            curve.append({'step': step, 'own_cash': farm['money'], 'rival_cash': other['money']})
    return {'own_cash_change': farm['money']-opening[own], 'rival_cash_change': other['money']-opening[rival],
            'relative_cash_change': farm['money']-opening[own]-other['money']+opening[rival],
            'cash_trough': low, 'unfunded_orders': failures, 'blocked_plant_turns': blocked_plants,
            'cash_components': dict(totals), 'filled_units': dict(fills), 'cash_curve': curve,
            'entry_state_sha256': digest({'farm': observation['farms'][own], 'private': observation['private']}),
            'exit_state_sha256': digest({'farm': farm, 'private': private}),
            'exit_state': {'farm': farm, 'private': private},
            'assumptions': 'Source route market timing; no new weeds; explicit conditional rival arrivals and shop scenarios.'}


def evaluate_continuations(observation, configuration, plans, scenarios, *, baseline,
                           mechanics, kernel, repair=None, budget_seconds=0.65, keep_curve=False):
    """Return a relative-cash selection plus every conditional economic receipt."""
    started = time.perf_counter(); deadline = started+budget_seconds
    evaluations = {}
    try:
        for name, route in plans.items():
            evaluations[name] = {scenario['id']: project(observation, configuration, route, scenario,
                mechanics, kernel, repair=repair, deadline=deadline, keep_curve=keep_curve)
                for scenario in scenarios}
    except TimeoutError:
        return {'selected': baseline, 'reason': 'deadline', 'evaluations': evaluations,
                'elapsed_seconds': time.perf_counter()-started}
    best, best_key = baseline, (0, 0)
    scores = {}
    for name, rows in evaluations.items():
        deltas = [r['relative_cash_change']-evaluations[baseline][sid]['relative_cash_change'] for sid, r in rows.items()]
        funded = all(r['unfunded_orders'] == 0 and r['cash_trough'] >= 0
                     for sid, r in rows.items())
        key = (min(deltas), sum(deltas))
        scores[name] = {'worst_relative_delta': key[0], 'sum_relative_delta': key[1], 'funding_supported': funded}
        if funded and key[0] > 0 and key > best_key:
            best, best_key = name, key
    return {'selected': best, 'reason': 'relative_cash_proxy', 'baseline': baseline,
            'scores': scores, 'evaluations': evaluations, 'elapsed_seconds': time.perf_counter()-started,
            'probabilities': None, 'selection_scope': 'robust conditional margin proxy, not validated win probability'}
