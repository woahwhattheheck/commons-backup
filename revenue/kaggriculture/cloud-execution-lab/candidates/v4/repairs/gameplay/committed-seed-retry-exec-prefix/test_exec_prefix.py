#!/usr/bin/env python3
from __future__ import annotations
import copy, importlib.util, sys, types

checks = 0
def check(cond, label):
    global checks
    checks += 1
    if not cond:
        raise AssertionError(label)

class M:
    LAND_ORDER = ['NW','NE','SW','SE']
    CROPS = {'CARROT': {'seed': 2}}
    ANIMALS = {'COW': {'cost': 20}}

def spend(order, farm, inventory, params, hires, cfg):
    if not order: return 0, hires
    if order[0] == 'HIRE': return 7, hires + 1
    if order[0] == 'BUY_LAND': return 25, hires
    if len(order) < 3: return 0, hires
    if order[0] == 'BUY_SEED': return 2 * int(order[2]), hires
    if order[0] == 'BUY_ANIMAL': return 20 * int(order[2]), hires
    if order[0] == 'BUY_PRODUCT': return 11 * int(order[2]), hires
    return 0, hires

scheduler = types.ModuleType('scheduler')
scheduler._order_spend = spend
scheduler.m = M
sys.modules['scheduler'] = scheduler
HERE = __import__('pathlib').Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('exec_prefix', HERE/'exec_prefix.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class Runtime:
    def __init__(self, queue):
        route = [{'market': []} for _ in range(25)]
        route[11] = {'market': copy.deepcopy(queue)}
        self.controller = types.SimpleNamespace(R={'A': route}, cur='A')

def obs():
    farm = {'hires_today': 0, 'unlocked_quadrants': ['NW']}
    return {'step': 10, 'player': 0, 'farms': [farm, copy.deepcopy(farm)],
            'market': {'inventory': {'WHEAT': 100}, 'params': {}}}

cfg = {'maxMarketOrdersPerTurn': 10}
selected = {'market': []}

def main():
    # Dead row 11 cannot veto or reserve cash.
    dead_product = [[] for _ in range(10)] + [['BUY_PRODUCT','WHEAT',1]]
    check(not mod.has_dynamic_product_obligation([dead_product], cfg), 'dead BUY_PRODUCT veto')
    check(mod.prefix_cash_reserve(Runtime(dead_product), obs(), cfg, selected, 11) == 0,
          'dead BUY_PRODUCT reserve')

    # Same row inside the live prefix keeps old semantics.
    live_product = [[] for _ in range(9)] + [['BUY_PRODUCT','WHEAT',1], []]
    check(mod.has_dynamic_product_obligation([live_product], cfg), 'live BUY_PRODUCT missed')
    check(mod.prefix_cash_reserve(Runtime(live_product), obs(), cfg, selected, 11) == 11,
          'live BUY_PRODUCT spend missed')

    # Fixed-cost suffix rows are equally dead; live rows still reserve.
    dead_hire = [[] for _ in range(10)] + [['HIRE']]
    live_hire = [[] for _ in range(9)] + [['HIRE'], []]
    check(mod.prefix_cash_reserve(Runtime(dead_hire), obs(), cfg, selected, 11) == 0,
          'dead HIRE reserve')
    check(mod.prefix_cash_reserve(Runtime(live_hire), obs(), cfg, selected, 11) == 7,
          'live HIRE missing')
    dead_seed = [[] for _ in range(10)] + [['BUY_SEED','CARROT',3]]
    live_seed = [[] for _ in range(9)] + [['BUY_SEED','CARROT',3], []]
    check(mod.prefix_cash_reserve(Runtime(dead_seed), obs(), cfg, selected, 11) == 0,
          'dead BUY_SEED reserve')
    check(mod.prefix_cash_reserve(Runtime(live_seed), obs(), cfg, selected, 11) == 6,
          'live BUY_SEED missing')

    # Non-default limits are exact, not hard-coded 10.
    cfg12 = {'maxMarketOrdersPerTurn': 12}
    row11 = [[] for _ in range(10)] + [['BUY_PRODUCT','WHEAT',1], []]
    check(mod.has_dynamic_product_obligation([row11], cfg12), 'row11 not live at limit12')
    cfg3 = {'maxMarketOrdersPerTurn': 3}
    row4 = [[],[],[],['BUY_PRODUCT','WHEAT',1]]
    check(not mod.has_dynamic_product_obligation([row4], cfg3), 'row4 not dead at limit3')

    # Selected/current queue obeys the same prefix rule in reserve.
    current = {'market': [[] for _ in range(10)] + [['HIRE']]}
    check(mod.prefix_cash_reserve(Runtime([]), obs(), cfg, current, 10) == 0,
          'current dead suffix reserve')
    current = {'market': [[] for _ in range(9)] + [['HIRE'], []]}
    check(mod.prefix_cash_reserve(Runtime([]), obs(), cfg, current, 10) == 7,
          'current live HIRE missing')

    # Helper is non-mutating and fails closed on malformed limits/tapes.
    queue = [[], ['HIRE'], ['BUY_PRODUCT','WHEAT',1]]
    before = copy.deepcopy(queue)
    check(mod.active_market(queue, 2) == [[], ['HIRE']], 'prefix slice wrong')
    check(queue == before, 'prefix mutated queue')
    check(mod.market_limit({}) == 10, 'default limit changed')
    check(mod.market_limit({'maxMarketOrdersPerTurn': 1}) == 1, 'limit one rejected')
    for bad in (0, True, 2.5):
        try: mod.market_limit({'maxMarketOrdersPerTurn': bad})
        except ValueError: check(True, f'bad limit {bad!r} rejected')
        else: check(False, f'bad limit {bad!r} accepted')
    try: mod.active_market('bad', 10)
    except ValueError: check(True, 'bad tape rejected')
    else: check(False, 'bad tape accepted')

    # Cross-queue veto scans only active rows in every represented turn.
    mixed = [[['SELL','WHEAT',1]], dead_product, [[], ['BUY_PRODUCT','WHEAT',1]]]
    check(mod.has_dynamic_product_obligation(mixed, cfg), 'live later queue BUY_PRODUCT missed')
    mixed[-1] = [[], []]
    check(not mod.has_dynamic_product_obligation(mixed, cfg), 'dead suffix contaminated cross-queue scan')

    check(checks == 22, f'count mismatch {checks}')
    print('V4 committed-seed-retry executable-prefix donor OK (22 checks)')

if __name__ == '__main__': main()
