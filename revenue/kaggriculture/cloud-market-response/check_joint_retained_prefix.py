# SPDX-License-Identifier: MIT
"""Use a retained public/own input prefix, without actor or game replay.

Only five prior same-hour transitions train this one-turn history adapter.
Existing observed-fill reconciliation supplies own quantities; native own-unit
capture and native town consumption preserve exact mechanics. No rival current
queue, private state, terminal result, hidden seed, or future outcome is read.
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
from joint_terminal_history import build_joint_terminal_scenarios


def evaluate(rows, deps, cases, ti, flow, fills):
    indexed={r['step']:r for r in rows}
    if len(indexed)!=len(rows):raise ValueError('Duplicate steps in one input prefix')
    now=max(indexed)
    final=indexed[now]
    if now!=final['configuration']['episodeSteps']-2:
        raise ValueError('Retained final actionable observation required')
    period=final['configuration']['turnsPerDay'];h=flow.FlowHistory(period=period)
    training=[];unit_captures=0;consumption_calls=0
    for step in sorted(now-lag*period for lag in range(1,h.window+1)):
        if step not in indexed or step+1 not in indexed:
            training.append({'step':step,'status':'missing_adjacent_input'});continue
        prev,nxt=indexed[step],indexed[step+1]
        obs,cfg,action=prev['observation'],prev['configuration'],prev['expected_action']
        current=nxt['observation']
        if obs['player']!=current['player'] or obs['step']!=step or current['step']!=step+1:
            raise ValueError('Mismatched player/step boundary')
        if cfg.get('seed') is not None:raise ValueError('This input road uses no runtime seed')
        post=cases.own_unit_snapshot(deps.engine,obs,cfg,action);unit_captures+=1
        ledger=fills.ObservedFillLedger()
        ledger.record(obs,cfg,action,post_unit_shed=post['private']['shed'],
                      post_unit_inventories=post['private']['inventories'])
        quantity=ledger.observe(current)
        # Execute the exact native town stage on a detached public book once;
        # its total per-product subtraction supplies T12's absorption callback.
        market=deepcopy(obs['market'])
        state=[NS(observation=NS(market=market,town=deepcopy(obs['town'])))]
        deps.engine._town_consume(NS(configuration=NS(**cfg)),state,step);consumption_calls+=1
        absorption={p:obs['market']['inventory'][p]-market['inventory'][p] for p in deps.engine.PRODUCTS}
        own={};intervals={}
        if quantity['status'] in ('reconciled','ambiguous'):
            for p in deps.engine.PRODUCTS:
                sale_rows=[r for r in quantity['orders'] if r['kind']=='sell' and r['item']==p]
                if any(r['fill_min']!=r['fill_max'] for r in sale_rows):
                    intervals[p]={'status':'unknown_own_fill'};continue
                own[p]=sum(r['fill_min'] for r in sale_rows)
                interval=flow.infer_flow(obs,current,own,p,cfg,deps.engine,
                                        lambda item,step,shops,cfg:absorption[item])
                h.add(interval)
                intervals[p]=interval.as_dict() if interval else {'status':'unidentified'}
        training.append({'step':step,'status':quantity['status'],'own_fills':quantity,
                         'own_sales':own,'intervals':intervals,'absorption':absorption})
    # Fixed BEFORE observing any current rival action or terminal outcome.
    # These are uncalibrated public-source-order stress templates, not a fit.
    products=list(deps.engine.PRODUCTS)
    templates=[{'id':'canonical-with-gap','origin':'fixed engine-product ordering hypothesis, not inferred',
                'slots':[None,*products]},
               {'id':'reverse','origin':'fixed reverse product ordering hypothesis, not inferred',
                'slots':list(reversed(products))}]
    completions=[{'id':'quiet-operating','origin':'explicit unknown operating-lot hypothesis',
                  'stock':{'WHEAT':0,'FERTILIZER':0}},
                 {'id':'five-each','origin':'explicit unknown operating-lot hypothesis',
                  'stock':{'WHEAT':5,'FERTILIZER':5}}]
    family=build_joint_terminal_scenarios(h,products,now,slot_templates=templates,
        unobserved_lots=completions,capacity=final['configuration']['shedCapacity'],
        max_orders=final['configuration']['maxMarketOrdersPerTurn'])
    original=deepcopy(final['expected_action']);output=deepcopy(original);packet=None;objective=None
    selector_calls=0
    if family['ready']:
        post=cases.own_unit_snapshot(deps.engine,final['observation'],final['configuration'],original)
        unit_captures+=1
        packet=ti.build_terminal_inputs(deps.engine,final['observation'],final['configuration'],original,
                                       post_unit_observation=post,scenarios=family['scenarios'])
        output,actor=cases.choose(deps,final['observation'],final['configuration'],original,packet)
        selector_calls=1;objective=actor.last_objective
    counts=Counter(i.get('reason',i.get('status')) for r in training for i in r.get('intervals',{}).values())
    return {'summary':{'retained_input_rows':len(rows),'prior_pairs':len(training),
                      'fill_statuses':dict(Counter(r['status'] for r in training)),
                      'flow_statuses':dict(counts),'joint_support':family['joint_support'],
                      'family_status':family['status'],'included_scenarios':len(family['scenarios']),
                      'action_changed':output!=original,'unit_boundary_captures':unit_captures,
                      'native_town_consumption_calls':consumption_calls,
                      'conditional_market_calls':packet['native_market_calls'] if packet else 0,
                      'score_selector_calls':selector_calls,'full_games':0,'policy_actor_calls':0,
                      'new_game_seeds':0,'realized_outcome_evaluation':False},
            'family':family,'training':training,'packet':packet,'objective':objective,
            'original_action':original,'output_action':output,
            'runtime_scope':'Public/own retained observations and already-selected own actions; no recorded current rival queue or terminal outcome.'}


def decode_input(raw):
    """Normalize the two existing input contracts, never evaluator indexes."""
    try:
        payload=json.loads(raw)
    except json.JSONDecodeError:
        rows=[json.loads(line) for line in raw.splitlines() if line.strip()]
        if not rows:raise ValueError('Empty input stream')
        return rows
    if isinstance(payload,dict) and payload.get('schema')=='titan.public-own-history.v1':
        cfg=payload['configuration'];final=payload['observation']
        prefix=payload['history'];now=final['step'];seat=final['player']
        if not isinstance(prefix,list) or len(prefix)!=now:
            raise ValueError('Complete chronological public/own prefix required')
        rows=[]
        for step,entry in enumerate(prefix):
            obs=entry['observation']
            if obs['step']!=step or obs['player']!=seat:
                raise ValueError('Inconsistent history observation boundary')
            rows.append({'step':step,'seat':seat,'observation':obs,
                         'configuration':cfg,'expected_action':entry['own_action']})
        rows.append({'step':now,'seat':seat,'observation':final,
                     'configuration':cfg,'expected_action':payload['selected_action']})
        return rows
    if isinstance(payload,dict) and {'step','observation','configuration','expected_action'}<=set(payload):
        return [payload]
    raise ValueError('Expected recorded input JSONL or public-own-history.v1, not an offline index')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,nargs='+',required=True)
    parser.add_argument('--poly-package',type=Path,required=True)
    parser.add_argument('--flow',type=Path,required=True)
    parser.add_argument('--observed-fills',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.poly_package
    sys.path.insert(0,str(root/'source'))
    ti=load(root/'source/terminal_inputs.py','terminal_inputs')
    cases=load(root/'source/terminal_input_cases.py','_retained_joint_cases')
    deps=cases.dependencies(root/'dependencies/engine_loader.py',root/'engine',root/'dependencies',root/'dependencies/full_support.py')
    flow=load(args.flow,'_retained_joint_flow');fills=load(args.observed_fills,'_retained_joint_fills')
    reports=[]
    for source in args.input:
        compressed=source.read_bytes();raw=gzip.decompress(compressed)
        rows=decode_input(raw)
        report=evaluate(rows,deps,cases,ti,flow,fills)
        report['input_compressed_sha256']=hashlib.sha256(compressed).hexdigest()
        report['input_decoded_sha256']=hashlib.sha256(raw).hexdigest()
        report['source_sha256']={str(p.name):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [args.flow,args.observed_fills,Path(__file__),Path(__file__).with_name('joint_terminal_history.py')]}
        reports.append(report)
    if len(reports)==1:
        report=reports[0]
    else:
        report={'reports':reports,'summary':{'unique_inputs':len(reports),
            'ready_inputs':sum(r['family']['ready'] for r in reports),
            'changed_actions':sum(r['summary']['action_changed'] for r in reports),
            'family_statuses':dict(Counter(r['family']['status'] for r in reports)),
            'prior_pairs':sum(r['summary']['prior_pairs'] for r in reports),
            'unit_boundary_captures':sum(r['summary']['unit_boundary_captures'] for r in reports),
            'conditional_market_calls':sum(r['summary']['conditional_market_calls'] for r in reports),
            'score_selector_calls':sum(r['summary']['score_selector_calls'] for r in reports),
            'full_games':0,'policy_actor_calls':0,'new_game_seeds':0}}
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report['summary'],indent=2))


if __name__=='__main__':main()
