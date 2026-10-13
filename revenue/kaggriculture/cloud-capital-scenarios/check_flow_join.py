# SPDX-License-Identifier: Apache-2.0
"""Join exact ROUTE-FLOW, DATE, HAZEL and Arlene sources without a new game panel.

The initial inventories, shops, funds and future scenarios are CONSTRUCTED.
This verifies the composed callable and conditional accounting, not a forecast.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from check_real_routes import load, blob, PARENT_SHA256, HAZEL_BLOB
from dated_scenarios import CashScenario, DatedSelector

FLOW_BLOB = 'dcb9250711e5f672a7adfa8a7ec3191895f4feea'


def run(arlene_path, hazel_path, mechanics_path, flow_path):
    assert hashlib.sha256(arlene_path.read_bytes()).hexdigest() == PARENT_SHA256
    assert blob(hazel_path) == HAZEL_BLOB
    assert blob(flow_path) == FLOW_BLOB
    arlene = load('flow_join_arlene', arlene_path)
    hazel = load('flow_join_hazel', hazel_path)
    mechanics = load('flow_join_mechanics', mechanics_path)
    flow = load('flow_join_producer', flow_path)
    inventory = {p: mechanics.MARKET_I0 for p in mechanics.PRODUCTS}
    # Use a mechanically consistent starting quote/inventory pair, not overwrite prices.
    for item, wanted in [('WOOL', 189), ('EGG', 51)]:
        inventory[item] = next(i for i in range(9000, 11001)
                               if mechanics.market_price(item, i) == wanted)
    prices = {p: mechanics.market_price(p, inventory[p]) for p in inventory}
    cfg = {}
    observation = {'step': 226, 'player': 0,
        'farms': [{'money': 10000, 'hires_today': 0, 'unlocked_quadrants': ['NW']}
                  for _ in range(2)],
        'market': {'inventory': inventory, 'prices': prices},
        'town': {'unlocked_shops': ['BAKERY', 'ICE_CREAM_SHOP']}}
    scenarios = [
        flow.Scenario('existing_shops_only'),
        flow.Scenario('hypothetical_yarn_first_active_288', shop_additions={288: ['YARN_STORE']}),
        flow.Scenario('declared_rival_wool_sales', rival_orders={
            406: [['PASS'], ['SELL', 'WOOL', 14]],
            430: [['SELL', 'WOOL', 12]]}),
        flow.Scenario('yarn_and_rival', shop_additions={288: ['YARN_STORE']}, rival_orders={
            406: [['PASS'], ['SELL', 'WOOL', 14]],
            430: [['SELL', 'WOOL', 12]]}),
    ]
    combined = []
    variable_rows = matched_rows = 0
    duration = []
    for player in (0, 1):
        ob = deepcopy(observation); ob['player'] = player
        ctrl = arlene.Agent()
        untouched = deepcopy((ob, cfg, ctrl.__dict__))
        cache = {}
        def callback(offers, current):
            t0 = time.perf_counter()
            receipt = flow.evaluate_scenarios(offers, current, cfg, mechanics, scenarios,
                                             seconds=None, retain_trace=False)
            assert receipt['complete'], receipt
            scenario_cash = flow.as_cash_scenarios(receipt, CashScenario)
            selector = DatedSelector(scenario_cash)
            chosen = selector(offers, current)
            duration.append(1000 * (time.perf_counter() - t0))
            cache.update(offers=offers, receipt=receipt, report=selector.last_report)
            return chosen
        outer = hazel.choose_before_action(ctrl, ob, cfg, mechanics, selector=callback)
        assert ob == untouched[0] and cfg == untouched[1]
        assert {k:v for k,v in ctrl.__dict__.items() if k!='cur'} == {
            k:v for k,v in untouched[2].items() if k!='cur'}
        receipt, report = cache['receipt'], cache['report']
        compact = []
        for group, result in zip(receipt['rows'], report['scenarios']):
            scenario_rows = []
            for row in group:
                other = result['routes'][row['route_id']]
                assert other['complete']
                assert other['final_nominal_cash'] == row['final_marked_cash']
                assert other['minimum_nominal_cash'] == row['minimum_marked_cash']
                assert other['first_negative'] == row['first_negative']
                offer = next(v for v in cache['offers'] if v.route_id==row['route_id'])
                expected = {(r['step'],r['slot']) for r in offer.orders
                            if r['order'][0] in ('SELL','BUY_PRODUCT')}
                keys = {(r['step'],r['slot']) for r in row['cash_flow_rows']}
                assert keys == expected
                assert len(keys) == len(row['cash_flow_rows'])
                variable_rows += len(keys); matched_rows += 1
                scenario_rows.append({k: row[k] for k in (
                    'route_id','final_marked_cash','minimum_marked_cash','first_negative',
                    'own_receipts','own_product_spend','fixed_costs','rival_receipts',
                    'rival_product_spend','final_market_inventory')})
            compact.append({'name': result['name'], 'routes': scenario_rows})
        combined.append({'player':player, 'outer_changed':outer['changed'],
                         'selected':ctrl.cur, 'conditional_rows':compact,
                         'date_report':report, 'unit_rounds':receipt['unit_rounds']})
    # A new incomplete result cannot be converted into a silently smaller scenario bank.
    ctrl = arlene.Agent()
    offers = [hazel.quote_program(k, ctrl.R[k], observation, cfg, mechanics)
              for k in (hazel.MAIN, hazel.SHEEP)]
    rejected = 0
    for kwargs in ({'max_units':0, 'seconds':None}, {'seconds':0}):
        incomplete = flow.evaluate_scenarios(offers, observation, cfg, mechanics, scenarios, **kwargs)
        assert not incomplete['complete'] and incomplete['rows']==[]
        try:
            flow.as_cash_scenarios(incomplete, CashScenario)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError('incomplete flow was consumable')
    assert rejected == 2
    return {'schema':'capital-flow-date-join.v1',
        'scope':'real_source_composition_on_constructed_market_and_declared_scenarios',
        'pins':{'arlene_sha256':PARENT_SHA256,'hazel_blob':HAZEL_BLOB,
                'flow_blob':FLOW_BLOB,'mechanics_blob':blob(mechanics_path)},
        'constructed_observation':observation,
        'joined_selector_calls':2, 'matched_route_scenario_rows':matched_rows,
        'matched_variable_cash_rows':variable_rows, 'incomplete_budget_controls':rejected,
        'results':combined, 'duration_ms':duration,
        'timing_scope':'single_join_per_seat_no_deadline_for_measurement_excludes_quoting_and_imports',
        'games':0, 'parent_action_calls':0, 'new_game_seeds':0,
        'limits':['Constructed market: not a saved reached state or an ex-ante prediction.',
                  'Quantities and fixed costs are conditional assumed execution, not physical feasibility.',
                  'No default policy, game results or calibrated scenario probabilities are changed.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('arlene','hazel','mechanics','flow','output'):
        p.add_argument('--'+name, type=Path, required=True)
    args = p.parse_args()
    result = run(args.arlene,args.hazel,args.mechanics,args.flow)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('joined_selector_calls','matched_route_scenario_rows',
        'matched_variable_cash_rows','incomplete_budget_controls','duration_ms','games')},indent=2))


if __name__=='__main__':
    main()
