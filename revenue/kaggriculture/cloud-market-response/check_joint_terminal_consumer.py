# SPDX-License-Identifier: MIT
"""Execute the new history-to-terminal consumer boundary using existing sources.

No source fetching, new game, policy controller, or historical outcome enters
these constructed cases. Supply the existing POLY source/dependency package.
"""
from copy import deepcopy
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch
from joint_terminal_history import build_joint_terminal_scenarios


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod
    spec.loader.exec_module(mod);return mod


def fixture(engine,seat,kind):
    farm={'money':100000.,'tiles':[[None for _ in range(10)] for _ in range(10)],
          'farmer':[4,4],'hands':[],'unlocked_quadrants':['NW'],'hires_today':0}
    farms=[deepcopy(farm),deepcopy(farm)];farms[seat]['money']+=33
    market={'inventory':{p:10000 for p in engine.PRODUCTS},'prices':{}}
    engine._refresh_prices(market)
    cfg=dict(episodeSteps=720,boardSize=10,turnsPerDay=24,shedCapacity=100,
             maxMarketOrdersPerTurn=10,farmHandCostMult=1)
    stock={'CARROT':3,'WOOL':4,'MILK':2,'WHEAT':2}
    obs={'step':718,'player':seat,'day':29,'hour':22,'farms':farms,'market':market,
         'town':{'unlocked_shops':[]},'private':{'shed':stock.copy(),'seeds':{},'inventories':[{}]}}
    action={'farmer':['PASS'],'hands':[],
            'market':[[],['SELL','CARROT',3],['SELL','WOOL',4],['SELL','MILK',2],['SELL','WHEAT',2]]}
    if kind=='drop':
        obs['private']['shed']={};obs['private']['inventories']=[stock.copy()];action['farmer']=['DROP']
    elif kind=='funding':
        farms[seat]['money']=0.;action['market'][0]=['HIRE']
        action['market'].insert(2,['BUY_SEED','CARROT',1])
    elif kind=='floor':
        market['inventory']['WOOL']=30000;engine._refresh_prices(market)
    return obs,cfg,action


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--poly-package',type=Path,required=True)
    parser.add_argument('--flow',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.poly_package
    sys.path.insert(0,str(root/'source'))
    ti=load(root/'source/terminal_inputs.py','terminal_inputs')
    cases=load(root/'source/terminal_input_cases.py','_joint_terminal_cases')
    deps=cases.dependencies(root/'dependencies/engine_loader.py',root/'engine',
                            root/'dependencies',root/'dependencies/full_support.py')
    flow=load(args.flow,'_joint_consumer_flow')
    products=list(deps.engine.PRODUCTS)
    h=flow.FlowHistory(minimum=3)
    for lag,lot in [(3,{'MILK':5}),(2,{'MILK':2,'WOOL':3,'CARROT':1}),
                    (1,{'WOOL':4,'CARROT':2})]:
        for p in products:
            if p in ('WHEAT','FERTILIZER'):continue
            q=lot.get(p,0);h.add(flow.FlowInterval(718-lag*24,p,q,q,q,q,'identified'))
    slot_templates=[{'id':'interior','origin':'constructed explicit interior pattern',
                     'slots':[None,'CARROT','EGG','FERTILIZER','WOOL','MILK','WHEAT','TOMATO','STRAWBERRY','MELON']},
                    {'id':'milk-first','origin':'constructed explicit alternative order',
                     'slots':['MILK','WOOL','CARROT','EGG','FERTILIZER','WHEAT','TOMATO','STRAWBERRY','MELON']}]
    completions=[{'id':'quiet-operating','origin':'explicit unobserved operating-stock hypothesis',
                  'stock':{'WHEAT':0,'FERTILIZER':0}},
                 {'id':'operating-lot','origin':'explicit unobserved operating-stock hypothesis',
                  'stock':{'WHEAT':3,'FERTILIZER':1}}]
    family=build_joint_terminal_scenarios(h,products,718,slot_templates=slot_templates,
                                        unobserved_lots=completions)
    assert family['ready'] and family['joint_support']==3
    assert len(family['scenarios'])==12
    records=[];native_calls=full_calls=unit_calls=selector_calls=0
    for seat in (0,1):
        for kind in ('plain','drop','funding','floor'):
            obs,cfg,action=fixture(deps.engine,seat,kind);original=deepcopy((obs,cfg,action,family))
            post=cases.own_unit_snapshot(deps.engine,obs,cfg,action);unit_calls+=1
            with patch.object(deps.engine,'_apply_unit_action',side_effect=AssertionError('repeated unit projection')):
                packet=ti.build_terminal_inputs(deps.engine,obs,cfg,action,post_unit_observation=post,
                                                scenarios=family['scenarios'])
            assert packet['complete'];native_calls+=packet['native_market_calls']
            assert packet['scenarios'][0]['origin']==family['scenarios'][0]['origin']
            assert (obs,cfg,action,family)==original
            plans={p['id']:p['action'] for p in packet['plans']}
            scenarios={r['id']:r for r in packet['scenarios']}
            for r in packet['document']['receipts']:
                state,env=cases.make_state(obs,cfg,plans[r['plan']],scenarios[r['scenario']])
                deps.engine.interpreter(state,env);full_calls+=1
                own=state[seat].observation.farms[seat]['money']
                rival=state[1-seat].observation.farms[1-seat]['money']
                assert (r['own_cash'],r['rival_cash'])==(own,rival)
                assert state[seat].status=='DONE'
            picked,actor=cases.choose(deps,obs,cfg,action,packet);selector_calls+=1
            assert picked in list(plans.values())
            assert picked['farmer']==action['farmer'] and picked['hands']==action['hands']
            if kind=='funding':
                assert all(p['market'][0]==['HIRE'] and p['market'][2]==['BUY_SEED','CARROT',1] for p in plans.values())
            partial=ti.build_terminal_inputs(deps.engine,obs,cfg,action,post_unit_observation=post,
                                             scenarios=family['scenarios'],max_cells=1)
            native_calls+=partial['native_market_calls']
            fallback,partial_actor=cases.choose(deps,obs,cfg,action,partial);selector_calls+=1
            assert fallback==action and partial_actor.draws==0
            records.append({'seat':seat,'case':kind,'packet':packet,'selected_action':picked,
                            'objective':actor.last_objective,'partial_fallback_preserved':True})
    # Fixed-slot negative control: removal of an empty rival slot changes paired
    # quotes even when its complete quantities and current public state match.
    gap=[]
    for seat in (0,1):
        obs,cfg,action=fixture(deps.engine,seat,'plain')
        action['market']=[[],['SELL','WOOL',4]]
        fixed={'id':'fixed','shed':{'WOOL':4},'market':[[],['SELL','WOOL',4]]}
        compact={'id':'compacted','shed':{'WOOL':4},'market':[['SELL','WOOL',4]]}
        outcomes=[]
        for s in (fixed,compact):
            state,env=cases.make_state(obs,cfg,action,s);deps.engine.interpreter(state,env);full_calls+=1
            outcomes.append([state[seat].observation.farms[seat]['money'],
                             state[1-seat].observation.farms[1-seat]['money']])
        assert outcomes[0]!=outcomes[1]
        gap.append({'seat':seat,'fixed_slot_cash':outcomes[0],'compacted_cash':outcomes[1]})
    sources={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob('*.py') if p.is_file()}
    report={'summary':{'constructed_cases':len(records),'joint_historical_lags':3,
                       'explicit_scenarios':12,'producer_native_market_calls':native_calls,
                       'independent_complete_terminal_interpreter_calls':full_calls,
                       'unit_boundary_captures':unit_calls,'actual_score_selector_calls':selector_calls,
                       'receipt_comparisons':full_calls-4,'full_games':0,'new_game_seeds':0},
            'slot_gap_discriminator':gap,'family':family,'cases':records,
            'dependencies_sha256':sources,'engine_hashes':deps.engine_hashes,
            'adapter_sha256':hashlib.sha256(Path(__file__).with_name('joint_terminal_history.py').read_bytes()).hexdigest()}
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report['summary'],indent=2));print(json.dumps(gap,indent=2))


if __name__=='__main__':main()
