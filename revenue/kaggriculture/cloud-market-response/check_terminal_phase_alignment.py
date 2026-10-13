# SPDX-License-Identifier: MIT
"""Offline same-hour versus ordinary-final-market reference experiment.

Consumes old input and analysis artifacts; it creates no actor or complete game.
Runtime adapter, source, selection defaults and original receipts remain intact.
"""
from collections import Counter
from copy import deepcopy
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

from check_joint_terminal_consumer import load
from check_joint_retained_prefix import decode_input
from joint_terminal_history import build_joint_terminal_scenarios


def training_steps(now, period, hour, window):
    if any(type(v) is not int for v in (now, period, hour, window)):
        raise ValueError('Integer time fields required')
    if now < 0 or period <= 0 or window < 1 or not 0 <= hour < period:
        raise ValueError('Invalid reference phase')
    reference = now - now % period + hour
    steps = sorted(reference - lag * period for lag in range(1, window + 1))
    if any(t < 0 or t + 1 > now for t in steps):
        raise ValueError('Every complete training pair must precede the decision')
    return reference, steps


def map_reference_family(family, now, reference):
    """Label the hypothesis transfer; never fabricate training timestamps."""
    output = deepcopy(family)
    output['reference_step'] = reference
    output['now'] = now
    output['phase_transfer'] = 'prior ordinary last-market hour projected to the current final market; uncalibrated hypothesis'
    for scenario in output['scenarios']:
        origin = scenario['origin']
        if origin['now'] != reference:
            raise ValueError('Mismatched reference-family origin')
        origin['reference_step'] = origin.pop('now')
        origin['target_step'] = now
        origin['phase_transfer'] = output['phase_transfer']
        for witness in origin['witnesses']:
            if not witness['training_start'] <= witness['training_end'] < now:
                raise ValueError('Noncausal training witness')
    return output


def evaluate_phase(rows, deps, cases, ti, flow, fills, hour):
    indexed = {r['step']: r for r in rows}
    if len(indexed) != len(rows):
        raise ValueError('Duplicate input steps')
    now = max(indexed)
    final = indexed[now]
    cfg = final['configuration']
    if now != cfg['episodeSteps'] - 2:
        raise ValueError('Requires the retained final actionable observation')
    h = flow.FlowHistory(period=cfg['turnsPerDay'])
    reference, steps = training_steps(now, h.period, hour, h.window)
    training = []
    native_units = native_town = 0
    for step in steps:
        if step not in indexed or step+1 not in indexed:
            training.append({'step': step, 'status': 'missing_adjacent_input'})
            continue
        prev, nxt = indexed[step], indexed[step+1]
        obs, action, old_cfg = prev['observation'], prev['expected_action'], prev['configuration']
        current = nxt['observation']
        if obs['step'] != step or current['step'] != step+1 or obs['player'] != current['player']:
            raise ValueError('Mismatched player/time boundary')
        if old_cfg.get('seed') is not None:
            raise ValueError('No seed belongs in runtime input')
        post = cases.own_unit_snapshot(deps.engine, obs, old_cfg, action)
        native_units += 1
        ledger = fills.ObservedFillLedger()
        ledger.record(obs, old_cfg, action,
                      post_unit_shed=post['private']['shed'],
                      post_unit_inventories=post['private']['inventories'])
        quantities = ledger.observe(current)
        market = deepcopy(obs['market'])
        state = [NS(observation=NS(market=market, town=deepcopy(obs['town'])))]
        deps.engine._town_consume(NS(configuration=NS(**old_cfg)), state, step)
        native_town += 1
        absorbed = {p:obs['market']['inventory'][p]-market['inventory'][p] for p in deps.engine.PRODUCTS}
        own = {}; intervals = {}
        if quantities['status'] in ('reconciled', 'ambiguous'):
            for p in deps.engine.PRODUCTS:
                sales = [o for o in quantities['orders'] if o['kind']=='sell' and o['item']==p]
                if any(o['fill_min'] != o['fill_max'] for o in sales):
                    intervals[p] = {'status':'unknown_own_fill'}
                    continue
                own[p] = sum(o['fill_min'] for o in sales)
                interval = flow.infer_flow(obs, current, own, p, old_cfg, deps.engine,
                                          lambda item, t, shops, c:absorbed[item])
                h.add(interval)
                intervals[p] = interval.as_dict() if interval else {'status':'unidentified'}
        training.append({'step':step, 'next_observation_step':step+1,
                         'status':quantities['status'], 'own_fills':quantities,
                         'intervals':intervals, 'own_sales':own, 'absorption':absorbed})
    # Same two patterns and operating-stock hypotheses as PR10119. No look-up
    # of recorded rival actions or outcomes chooses a family, template or tie.
    products = list(deps.engine.PRODUCTS)
    templates = [{'id':'canonical-with-gap','origin':'fixed engine-product ordering hypothesis, not inferred',
                  'slots':[None,*products]},
                 {'id':'reverse','origin':'fixed reverse product ordering hypothesis, not inferred',
                  'slots':list(reversed(products))}]
    completions = [{'id':'quiet-operating','origin':'explicit unknown operating-lot hypothesis',
                    'stock':{'WHEAT':0,'FERTILIZER':0}},
                   {'id':'five-each','origin':'explicit unknown operating-lot hypothesis',
                    'stock':{'WHEAT':5,'FERTILIZER':5}}]
    raw_family = build_joint_terminal_scenarios(h, products, reference,
        slot_templates=templates, unobserved_lots=completions,
        capacity=cfg['shedCapacity'], max_orders=cfg['maxMarketOrdersPerTurn'])
    family = map_reference_family(raw_family, now, reference)
    original = deepcopy(final['expected_action']); output = deepcopy(original)
    packet = objective = None; selector_calls = 0
    if family['ready']:
        post = cases.own_unit_snapshot(deps.engine, final['observation'], cfg, original)
        native_units += 1
        packet = ti.build_terminal_inputs(deps.engine, final['observation'], cfg, original,
            post_unit_observation=post, scenarios=family['scenarios'])
        output, actor = cases.choose(deps, final['observation'], cfg, original, packet)
        selector_calls = 1; objective = actor.last_objective
    counts = Counter(v.get('reason',v.get('status')) for r in training for v in r.get('intervals',{}).values())
    return {'summary':{'reference_hour':hour, 'actual_decision_hour':now%h.period,
        'training_steps':steps, 'prior_pairs':len(training),
        'fill_statuses':dict(Counter(r['status'] for r in training)),
        'flow_statuses':dict(counts), 'joint_support':family['joint_support'],
        'family_status':family['status'], 'included_scenarios':len(family['scenarios']),
        'action_changed':output!=original, 'unit_boundary_captures':native_units,
        'native_town_consumption_calls':native_town,
        'conditional_market_calls':packet['native_market_calls'] if packet else 0,
        'score_selector_calls':selector_calls, 'actor_calls':0, 'full_games':0, 'new_seeds':0},
        'training':training, 'family':family, 'packet':packet, 'objective':objective,
        'original_action':original, 'output_action':output}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, nargs='+', required=True)
    p.add_argument('--baseline', type=Path, nargs='+', required=True,
                   help='Original PR10119 saved analyses; consumed without repeating native execution')
    p.add_argument('--poly-package', type=Path, required=True)
    p.add_argument('--flow', type=Path, required=True)
    p.add_argument('--observed-fills', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args=p.parse_args(); root=args.poly_package
    sys.path.insert(0,str(root/'source'))
    ti=load(root/'source/terminal_inputs.py','terminal_inputs')
    cases=load(root/'source/terminal_input_cases.py','_phase_cases')
    deps=cases.dependencies(root/'dependencies/engine_loader.py',root/'engine',root/'dependencies',root/'dependencies/full_support.py')
    flow=load(args.flow,'_phase_flow'); fills=load(args.observed_fills,'_phase_fills')
    baseline={}
    for source in args.baseline:
        doc=json.loads(source.read_text())
        for r in doc.get('reports',[doc]):
            key=r['input_decoded_sha256']
            if key in baseline: raise ValueError('Duplicate baseline input')
            baseline[key]=r
    reports=[]
    for source in args.input:
        compressed=source.read_bytes(); raw=gzip.decompress(compressed)
        key=hashlib.sha256(raw).hexdigest()
        if key not in baseline: raise ValueError('Input lacks an exact prior baseline receipt')
        rows=decode_input(raw)
        result=evaluate_phase(rows,deps,cases,ti,flow,fills,rows[-1]['configuration']['turnsPerDay']-1)
        result['input_decoded_sha256']=key
        result['input_compressed_sha256']=hashlib.sha256(compressed).hexdigest()
        result['original_same_hour_summary']=baseline[key]['summary']
        result['original_same_hour_action']=baseline[key]['output_action']
        result['action_differs_from_same_hour']=result['output_action']!=baseline[key]['output_action']
        reports.append(result)
    summary={'inputs':len(reports), 'changed_from_original_action':sum(r['summary']['action_changed'] for r in reports),
        'changed_from_same_hour_action':sum(r['action_differs_from_same_hour'] for r in reports),
        'baseline_family_statuses':dict(Counter(r['original_same_hour_summary']['family_status'] for r in reports)),
        'reference_family_statuses':dict(Counter(r['summary']['family_status'] for r in reports)),
        'old_new_joint_support':[[r['original_same_hour_summary']['joint_support'],r['summary']['joint_support']] for r in reports],
        'unit_boundary_captures':sum(r['summary']['unit_boundary_captures'] for r in reports),
        'native_town_consumption_calls':sum(r['summary']['native_town_consumption_calls'] for r in reports),
        'conditional_market_calls':sum(r['summary']['conditional_market_calls'] for r in reports),
        'score_selector_calls':sum(r['summary']['score_selector_calls'] for r in reports),
        'actor_calls':0,'full_games':0,'new_seeds':0,'runtime_changes':0,
        'recorded_rival_actions_or_outcomes_consumed':False}
    source_paths=[Path(__file__),args.flow,args.observed_fills,*[root/'source'/s for s in ('terminal_inputs.py','terminal_input_cases.py')]]
    out={'summary':summary,'reports':reports,
         'source_sha256':{str(v):hashlib.sha256(v.read_bytes()).hexdigest() for v in source_paths},
         'baseline_receipts_sha256':{str(v):hashlib.sha256(v.read_bytes()).hexdigest() for v in args.baseline}}
    args.output.write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
