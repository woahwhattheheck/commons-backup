# SPDX-License-Identifier: Apache-2.0
"""Opt-in seed-capital admission over pinned Kaggriculture mechanics.

This is a *direct crop-revenue upper bound*, not a proof of whole-game dominance:
market externalities, route changes and cash reallocation still need paired games.
It uses public observations only. WHEAT is deliberately excluded: animal feed has
an operating value that crop-sale revenue alone cannot bound.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

CASH_CROPS = frozenset(('CARROT', 'TOMATO', 'STRAWBERRY', 'MELON'))
MAX_SHOP_INSTANCES = 8  # pinned official engine; acceptance suite verifies this.
SHAPES = frozenset(('linear', 'sq', 'sqrt', 'log', 'log10', 'hinge'))


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return value


def _interval(config: dict, name: str, default: int) -> int:
    return _integer(config.get(name, default), name, 1)


def _params(mechanics: Any, obs: dict, crop: str) -> dict:
    # An initialized official observation carries resolved overrides in market.
    params = obs['market'].get('params') or mechanics.MARKET_PARAMS
    p = params[crop]
    for name in ('base', 'I0', 'T', 'below_target', 'above_target'):
        v = p[name]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f'unsupported nonfinite/nonnumeric price parameter {name}')
        if name != 'I0' and (v < 0 or (name == 'T' and v == 0)):
            raise ValueError(f'unsupported nonmonotone price parameter {name}')
    if p['below_func'] not in SHAPES or p['above_func'] not in SHAPES:
        raise ValueError('unsupported price shape')
    return params


def consumption_ceiling(mechanics: Any, obs: dict, config: dict, crop: str) -> dict:
    """Maximal public-town removal before the final market executes.

    Current-step town demand is AFTER the current market, but affects a later
    sale. Final-step town demand is AFTER the final market and cannot help it.
    Every still-unknown shop is assigned the most helpful legal shop for *this*
    crop. Unlocks occur after consumption on the end-of-day transition.
    """
    now = _integer(obs['step'], 'step')
    last = _integer(config.get('episodeSteps', 720), 'episodeSteps', 2) - 2
    tpd = _interval(config, 'turnsPerDay', 24)
    tick = _interval(config, 'townShopSellInterval', 4)
    center = _interval(config, 'townCenterSellInterval', 24)
    unlock = _interval(config, 'townShopUnlockInterval', 3)
    shops = obs['town']['unlocked_shops']
    if not isinstance(shops, list) or len(shops) > MAX_SHOP_INSTANCES:
        raise ValueError('unsupported shop list')
    known = 0
    for shop in shops:
        products = mechanics.SHOPS[shop]
        if crop in products:
            known += 2 if len(products) == 1 else 1
    best = max((2 if len(products) == 1 else 1
                for products in mechanics.SHOPS.values() if crop in products), default=0)
    count, unknown, removed = len(shops), 0, 0
    for step in range(now, last):
        if step % tick == 0:
            removed += known + unknown * best
        if step % center == 0 and crop in mechanics.TOWN_CENTER_PRODUCTS:
            removed += 1
        if ((step + 1) % tpd == 0 and ((step + 1) // tpd) % unlock == 0
                and count < MAX_SHOP_INSTANCES):
            unknown += 1
            count += 1
    return {'max_town_removal_before_final_market': removed,
            'known_shop_rate': known, 'max_rate_per_future_shop': best,
            'max_future_shop_instances': unknown, 'last_market_step': last}


def crop_revenue_ceiling(mechanics: Any, obs: dict, config: dict, crop: str) -> dict:
    if crop not in CASH_CROPS:
        raise ValueError('crop has operating-input value or is unsupported')
    now = _integer(obs['step'], 'step')
    tpd = _interval(config, 'turnsPerDay', 24)
    info = mechanics.CROPS[crop]
    seed_cost = _integer(info['seed'], 'seed cost', 1)
    max_yield = _integer(info['max_yield'], 'max yield', 1)
    first = _integer(info['first_yield_day'], 'first yield day')
    demand = consumption_ceiling(mechanics, obs, config, crop)
    last = demand['last_market_step']
    # Market BUY_SEED is too late for today's unit stage. The earliest PLANT is
    # the next callback, which may be the next *day* at an EOD purchase.
    plant_day = (now + 1) // tpd
    first_harvest_step = (plant_day + first) * tpd
    if now + 1 > last or first_harvest_step > last:
        yield_cap = 0
        production_events = 0
    elif info['ongoing']:
        interval = _integer(info['interval'], 'crop interval', 1)
        production_events = min(max_yield, (last // tpd - plant_day - first) // interval + 1)
        # Each ongoing production event can yield TWO with fertilization.
        # Ignore held-yield clipping, fertilizer cost, watering and all transport
        # time: every relaxation makes this an optimistic ceiling.
        yield_cap = 2 * production_events
    else:
        production_events = 1
        yield_cap = max_yield
    inventory = obs['market']['inventory'][crop]
    if isinstance(inventory, bool) or not isinstance(inventory, int):
        raise ValueError('unsupported noninteger inventory')
    params = _params(mechanics, obs, crop)
    lower_inventory = inventory - demand['max_town_removal_before_final_market']
    price_cap = mechanics.market_price(crop, lower_inventory, params)
    if isinstance(price_cap, bool) or not isinstance(price_cap, int) or price_cap < 1:
        raise ValueError('unsupported quote')
    revenue_cap = yield_cap * price_cap
    return {'crop': crop, 'step': now, 'seed_cost': seed_cost,
            'earliest_plant_day': plant_day, 'earliest_harvest_step': first_harvest_step,
            'max_production_events': production_events, 'yield_units_ceiling': yield_cap,
            'inventory_lower_bound': lower_inventory, 'unit_price_ceiling': price_cap,
            'direct_revenue_ceiling': revenue_cap,
            'reject_new_seed': revenue_cap < seed_cost,
            'scope': 'direct-crop-revenue-only-not-whole-game-EV', **demand}


def apply_seed_regime(action: dict, obs: dict, config: dict, mechanics: Any,
                      *, enabled: bool = False) -> tuple[dict, dict]:
    """Blank unpayable BUY_SEED slots, without compacting or changing units.

    Disabled and no-edit paths return the original object. Malformed/unsupported
    rows or contexts are retained with explicit reasons, never silently pruned.
    Existing seeds, PLANT commands, operational WHEAT and non-seed orders survive.
    """
    if not enabled:
        return action, {'enabled': False, 'changed': False, 'rows': []}
    report = {'enabled': True, 'changed': False, 'rows': [],
              'scope': 'direct-crop-revenue-only-not-whole-game-EV'}
    rows = action.get('market', [])
    if not isinstance(rows, list):
        report['unsupported'] = 'market is not a list'
        return action, report
    try:
        limit = _interval(config, 'maxMarketOrdersPerTurn', 10)
    except ValueError as error:
        report['unsupported'] = str(error)
        return action, report
    cache = {}
    edits = []
    for index, order in enumerate(rows[:limit]):
        if not (isinstance(order, list) and len(order) >= 3 and order[0] == 'BUY_SEED'):
            continue
        crop = order[1]
        if not isinstance(crop, str) or crop not in CASH_CROPS:
            continue
        try:
            quantity = _integer(order[2], 'quantity', 1)
            if crop not in cache:
                cache[crop] = crop_revenue_ceiling(mechanics, obs, config, crop)
            witness = dict(cache[crop], slot=index, requested=quantity)
            if witness['reject_new_seed']:
                edits.append(index)
            report['rows'].append(witness)
        except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError) as error:
            report['rows'].append({'slot': index, 'crop': crop, 'retained': True,
                                   'unsupported': f'{type(error).__name__}: {error}'})
    if not edits:
        return action, report
    result = deepcopy(action)
    for index in edits:
        result['market'][index] = []
    report.update(changed=True, removed_slots=edits)
    return result, report
