# SPDX-License-Identifier: Apache-2.0
"""Join existing Arlene + HAZEL route offers + ROUTE-FLOW + DATE, without games.

The checkpoint state is explicitly constructed, not a historical reached loss.
The entire existing route programs and peer implementations are used unchanged.
No hypothetical cash result is represented as a realized terminal score.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

from dated_flow import Scenario, evaluate_scenarios, as_cash_scenarios


def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('engine-dir','loader','arlene','capital','dated','output'):
        p.add_argument('--'+name,required=True,type=Path)
    args=p.parse_args()
    for name in ('kaggriculture.py','kaggriculture.json','utils.py'):
        if not (args.engine_dir/name).is_file():p.error('all cached engine files are required')
    loader=load(args.loader,'route_flow_existing_loader')
    engine,engine_hashes=loader.get_engine(args.engine_dir)
    arlene=load(args.arlene,'route_flow_existing_arlene')
    capital=load(args.capital,'route_flow_existing_capital')
    dated=load(args.dated,'route_flow_existing_dated')
    cfg=loader.Struct({k:v.get('default') if isinstance(v,dict) else v
                       for k,v in engine.specification['configuration'].items()})
    cfg.update(seed=71,startingMoney=20_000)
    env=loader.Struct(configuration=cfg,done=False,info={})
    state=[loader.Struct(observation=loader.Struct(),action={},status='ACTIVE',reward=0)for _ in range(2)]
    engine.interpreter(state,env)
    obs=copy.deepcopy(state[0].observation)
    obs.update(step=226,day=9,hour=10)
    obs['town']['unlocked_shops']=['BAKERY','PET_CAFE','PIZZA_SHOP']
    obs['market']['inventory']['WOOL']=10014
    engine._refresh_prices(obs['market'])
    controller=arlene.Agent()
    original_routes=copy.deepcopy(controller.R)
    offers=tuple(capital.quote_program(key,controller.R[key],obs,cfg,engine)
                 for key in (capital.MAIN,capital.SHEEP))
    # Declared route-independent future streams, not known hidden opponent orders.
    rival={step:[list(o) if o and o[0] in ('SELL','BUY_PRODUCT') else ['PASS']
                 for o in controller.R[capital.MAIN][step].get('market',[])]
           for step in range(226,719)}
    no_yarn={step:['SMOOTHIE_SHOP']for step in (288,360,432,504,576)}
    one_yarn=copy.deepcopy(no_yarn);one_yarn[288]=['YARN_STORE']
    scenarios=[Scenario('no_yarn_no_rival_flow',shop_additions=no_yarn),
               Scenario('one_future_yarn_no_rival_flow',shop_additions=one_yarn),
               Scenario('no_yarn_declared_main_flow',rival,no_yarn),
               Scenario('one_future_yarn_declared_main_flow',rival,one_yarn)]
    frozen_inputs=copy.deepcopy((obs,cfg,offers,scenarios))
    began=time.perf_counter()
    trajectory=evaluate_scenarios(offers,obs,cfg,engine,scenarios,seconds=1.0,retain_trace=True)
    elapsed=time.perf_counter()-began
    assert trajectory['complete'],trajectory
    cash_scenarios=as_cash_scenarios(trajectory,dated.CashScenario)
    selector=dated.DatedSelector(cash_scenarios)
    binding=capital.choose_before_action(controller,obs,cfg,engine,selector=selector)
    compared=selector.last_report
    reconciled=0
    for scenario_rows, comparison in zip(trajectory['rows'],compared['scenarios']):
        for row in scenario_rows:
            value=comparison['routes'][row['route_id']]
            assert value['complete']
            assert value['final_nominal_cash']==row['final_marked_cash']
            assert value['minimum_nominal_cash']==row['minimum_marked_cash']
            assert value['priced_variable_rows']==len(row['cash_flow_rows'])
            reconciled+=1
    assert controller.R==original_routes
    assert (obs,cfg,offers,scenarios)==frozen_inputs
    assert controller.cur==compared['selected']==binding['after']
    # Show that dynamic rows retain total settlement, never a unit quote.
    covered=sum(len(row['cash_flow_rows'])for rows in trajectory['rows']for row in rows)
    output={'scope':'constructed checkpoint, full actual route quotations; no policy call or full game',
            'state_kind':'synthetic_public_checkpoint_not_reached_historical_loss',
            'engine_ref':loader.ENGINE_REF,'engine_sha256':engine_hashes,
            'source_sha256':{name:hashlib.sha256(getattr(args,name).read_bytes()).hexdigest()
                             for name in ('arlene','capital','dated')},
            'runtime_sha256':hashlib.sha256(Path(__file__).with_name('dated_flow.py').read_bytes()).hexdigest(),
            'trajectory_seconds':elapsed,'route_scenario_pairs_reconciled':reconciled,
            'dynamic_rows_covered':covered,'route_programs_unchanged':True,
            'parent_calls':0,'binding':binding,'dated_comparison':compared,'trajectory':trajectory}
    args.output.write_text(json.dumps(output,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in output.items()if k not in ('trajectory','binding','dated_comparison')},indent=2))
    print(json.dumps({'selected':compared['selected'],'candidates':compared['candidates']},indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
