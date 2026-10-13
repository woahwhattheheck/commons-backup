# SPDX-License-Identifier: Apache-2.0
"""Independent, deterministic T04 oracle / official interpreter comparisons.

No game, policy, hosted replay, reserved seed or rival private state is consumed.
The comparison is conditional on a PASS rival, no new shops and no weeds.
External market scenarios and adversarial rival behavior are not covered.
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
import urllib.request

ORACLE_BLOB = '49640c27862d3d132c828fbafc6a8b4957527736'
ENGINE_SHA256 = {'kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e', 'kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867', 'utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b'}
LOADER_SHA256 = 'cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e'

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def git_blob(path):
    data = Path(path).read_bytes()
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def differences(a, b, path=''):
    if isinstance(a, dict) and isinstance(b, dict):
        return [d for k in sorted(a.keys() | b.keys()) for d in (
            [f'{path}/{k}: key missing'] if k not in a or k not in b
            else differences(a[k], b[k], f'{path}/{k}'))]
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b): return [f'{path}: lengths {len(a)} != {len(b)}']
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x,y,f'{path}/{i}')]
    return [] if a == b else [f'{path}: {a!r} != {b!r}']

def fixture(engine, Struct, seat, step, kind, capacity, money, market_offset):
    cfg = Struct({k: v.get('default') if isinstance(v, dict) else v
                  for k, v in engine.specification['configuration'].items()})
    cfg.update(weedSpawnChance=0, townShopUnlockInterval=100000,
               shedCapacity=capacity)
    farms = [engine._new_farm(10, money) for _ in range(2)]
    privates = [engine._new_private() for _ in range(2)]
    own, private = farms[seat], privates[seat]
    own['farmer'] = [4,4]
    own['hands'] = [[4,4], [5,4], [0,0]]
    own['hires_today'] = 3
    private['inventories'] = [
        {'WHEAT': 3, 'FERTILIZER': 2, 'EGG': 4, 'GOOSE': 1},
        {'WHEAT': 2, 'FERTILIZER': 1, 'MILK': 6, 'COW': 1},
        {'EGG': 5, 'WOOL': 3},
        {'FERTILIZER': 1, 'WHEAT': 1},
    ]
    for k in private['seeds']: private['seeds'][k] = 1
    private['shed'].update(WHEAT=min(3,capacity), STRAWBERRY=max(0, capacity-4))
    day = step // 24
    if kind.startswith('plant:'):
        crop = kind.split(':')[1]
        tile = engine._new_plant(crop, max(0,day-engine.CROPS[crop]['first_yield_day']),24)
        tile.update(yield_units=3, watered_today=False, consecutive_unwatered=1)
        if engine.CROPS[crop]['ongoing']:
            tile.update(production_count=3)
        own['tiles'][4][4] = tile
    elif kind.startswith('animal:'):
        animal = kind.split(':')[1]
        tile = engine._new_animal(animal, max(0,day-engine.ANIMALS[animal]['first_yield_day']))
        tile.update(yield_units=engine.ANIMALS[animal]['max_held'], fed_today=False,
                    cared_today=False, pending_care_bonus=3, fertilizer_available=True,
                    consecutive_unfed=1)
        own['tiles'][4][4] = tile
    elif kind != 'empty': own['tiles'][4][4] = {'kind':kind}
    market = engine._new_market()
    for product in engine.PRODUCTS: market['inventory'][product] += market_offset
    engine._refresh_prices(market)
    town = {'unlocked_shops':['BAKERY','PIZZA_SHOP','PIZZA_SHOP']}
    # Validate actual shop names instead of inventing a named fixture.
    town['unlocked_shops'] = [x for x in town['unlocked_shops'] if x in engine.SHOPS]
    state = [Struct(observation=Struct(farms=farms, private=privates[i], market=market,
               town=town, player=i, step=step, day=day, hour=step%24),
               action={}, status='ACTIVE', reward=0) for i in range(2)]
    return state, Struct(configuration=cfg,done=False,info={})

def compare(engine, oracle, state, env, seat, start, plan, end):
    obs = copy.deepcopy(state[seat].observation)
    cfg = copy.deepcopy(env.configuration)
    untouched = copy.deepcopy((obs,cfg,plan))
    result = oracle.simulate_bundle(engine,obs,cfg,plan,end_step=end,record_actions=True)
    if (obs,cfg,plan) != untouched:
        return ['oracle mutated input observation/configuration/plan']
    initial = obs['farms'][seat]['money']
    for step in range(start,end+1):
        for s in state:
            s.observation.step=step
            s.action={}
        state[seat].action=copy.deepcopy(plan(copy.deepcopy(state[seat].observation)) if callable(plan) else plan.get(step,{}))
        engine.interpreter(state,env)
    expected = dict(farm=state[seat].observation.farms[seat],
                    private=state[seat].observation.private,
                    market=state[seat].observation.market,
                    town=state[seat].observation.town,
                    cash_gain=state[seat].observation.farms[seat]['money']-initial)
    return differences({k:result[k] for k in expected},expected)

def run(args):
    start_time=time.perf_counter()
    if git_blob(args.oracle) != ORACLE_BLOB: raise ValueError('Unexpected oracle blob; review pin explicitly')
    for name, expected in ENGINE_SHA256.items():
        if hashlib.sha256((args.engine/name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Unexpected engine bytes: {name}')
    if hashlib.sha256(args.loader.read_bytes()).hexdigest() != LOADER_SHA256:
        raise ValueError('Unexpected official-loader source')
    # Fail closed on any missing cache or accidental network access.
    old=urllib.request.urlopen
    def offline(*a,**kw): raise RuntimeError('Network disabled for conformance review')
    urllib.request.urlopen=offline
    try:
        loader=load('atlas_official_loader',args.loader)
        engine,hashes=loader.get_engine(args.engine)
        oracle=load('atlas_t04_oracle',args.oracle)
        S=loader.Struct
        # Single-step joint-action tests at mid-day, day boundary and final sale.
        kinds=['empty','WEED','COOP','PASTURE']+[f'plant:{x}' for x in engine.CROPS]+[f'animal:{x}' for x in engine.ANIMALS]
        units=[['PASS'],['NORTH'],['SOUTH'],['EAST'],['WEST'],['DROP'],['PICKUP','WHEAT',3],
               ['PLACE','EGG',4],['PLACE','GOOSE'],['PLACE','COW'],['PLANT','WHEAT'],
               ['WATER'],['HARVEST'],['FERTILIZE'],['FEED'],['CARE'],
               ['COLLECT_FERTILIZER'],['DIG'],['BUILD_COOP'],['BUILD_PASTURE']]
        markets=[[],[['SELL','STRAWBERRY',8]],
                 [['BUY_PRODUCT','WHEAT',3],['SELL','WHEAT',4]],
                 [['SELL','STRAWBERRY',8],['HIRE'],['BUY_ANIMAL','GOOSE',1]],
                 [['BUY_SEED','WHEAT',2],['BUY_LAND'],['HIRE']]]
        failures=[]; count=0; transitions=0; scopes={}
        for seat in (0,1):
            for step in (240,263,592,718):
                for ki,kind in enumerate(kinds):
                    for ai,unit in enumerate(units):
                        scenario_id=f'joint-seat{seat}-step{step}-{kind}-action{ai}'
                        capacity=(4,20,100)[(ki+ai)%3]
                        money=(0,5,3000)[(ki+ai//3)%3]
                        offset=(0,400,10000)[(ki+ai//2)%3]
                        state,env=fixture(engine,S,seat,step,kind,capacity,money,offset)
                        # Two workers share the tile, plus a locked shed access and a remote hand.
                        action=dict(farmer=unit, hands=[units[(ai+3)%len(units)],
                            ['DROP'],['PLANT','WHEAT']], market=markets[ai%len(markets)])
                        if ai==10: action['hands'][0]=['PLANT','WHEAT']
                        ds=compare(engine,oracle,state,env,seat,step,{step:action},step)
                        count+=1; transitions+=1
                        if ds: failures.append(dict(case=scenario_id,differences=ds[:10]))
        scopes['single_step_joint_cases']=count
        # Stateful sequences across deposits, production, despawn/re-hire and market timing.
        for seat in (0,1):
            for kind in kinds:
                for boundary in (263,599,718):
                    step=boundary-2
                    state,env=fixture(engine,S,seat,step,kind,20,3000,400)
                    end=min(718,boundary+3)
                    plan={step:dict(farmer=['FEED'],hands=[['FERTILIZE'],['PICKUP','WHEAT',3]],market=[['BUY_PRODUCT','FERTILIZER',2]]),
                        step+1:dict(farmer=['CARE'],hands=[['WATER'],['DROP']],market=[['SELL','STRAWBERRY',5]]),
                        boundary:dict(farmer=['HARVEST'],hands=[['DROP'],['DROP']],market=[['SELL','EGG',99],['HIRE']]),
                        boundary+1:dict(farmer=['PICKUP','EGG',9],hands=[['DROP']],market=[['HIRE'],['HIRE']]),
                        boundary+2:dict(farmer=['DROP'],hands=[['PICKUP','WHEAT',1]],market=[['SELL','EGG',99],['SELL','MILK',99],['SELL','WOOL',99]]),
                        boundary+3:dict(farmer=['PASS'],hands=[['DROP']],market=[['SELL','WHEAT',99]])}
                    ds=compare(engine,oracle,state,env,seat,step,plan,end)
                    count+=1;transitions+=end-step+1
                    if ds: failures.append(dict(case=f'sequence-{seat}-{boundary}-{kind}',differences=ds[:10]))
        scopes['multi_step_cases']=count-scopes['single_step_joint_cases']
        # Supported top-level normalization (not arbitrary ill-typed unit payloads).
        for seat in (0,1):
            for i,action in enumerate([None,[],{}, {'hands':None}, {'farmer':None,'hands':'x','market':'x'},
                {'farmer':[], 'hands':[None,[],['PASS']], 'market':[None,[],['SELL','EGG','bad']]},
                {'farmer':['PLANT','WHEAT'],'hands':[['PASS']]*3+[['PLANT','WHEAT']]}]):
                state,env=fixture(engine,S,seat,592,'empty',100,3000,0)
                ds=compare(engine,oracle,state,env,seat,592,{592:action},592)
                count+=1;transitions+=1
                if ds: failures.append(dict(case=f'normalization-{seat}-{i}',differences=ds[:10]))
        scopes['normalization_cases']=14
        # A pure observation-driven callable reprojects from each actual own state.
        def observed_plan(obs):
            private=obs['private']; own=obs['farms'][obs['player']]
            return dict(farmer=['DROP'], hands=[['DROP'] for _ in own['hands']],
                market=[['SELL',item,n] for item,n in private['shed'].items()
                        if item in engine.PRODUCTS and n>0][:10])
        for seat in (0,1):
            for kind in kinds:
                state,env=fixture(engine,S,seat,261,kind,20,3000,400)
                ds=compare(engine,oracle,state,env,seat,261,observed_plan,266)
                count+=1;transitions+=6
                if ds: failures.append(dict(case=f'callable-{seat}-{kind}',differences=ds[:10]))
        scopes['callable_cases']=24
        # Negative controls test the comparator, not the real oracle. No file edits.
        from types import SimpleNamespace
        negative_controls=[]
        for name in ('wrong_cash','omitted_market','omitted_farmer_action','input_mutation','invented_liquidation'):
            state,env=fixture(engine,S,1,592,'empty',100,3000,0)
            plan={592:dict(farmer=['PICKUP','WHEAT',3],
                           hands=[['PICKUP','WHEAT',3],['DROP']],
                           market=[['SELL','STRAWBERRY',8]])}
            def defective(eng,obs,cfg,actions,*,end_step,record_actions=False, defect=name):
                modified=copy.deepcopy(actions)
                if defect=='omitted_market': modified[592]['market']=[]
                if defect=='omitted_farmer_action':
                    modified[592]['farmer']=['PASS']
                result=oracle.simulate_bundle(eng,obs,cfg,modified,end_step=end_step,
                                               record_actions=record_actions)
                if defect=='wrong_cash': result['cash_gain']+=1
                if defect=='input_mutation': obs['private']['shed']['EGG']+=1
                if defect=='invented_liquidation':
                    result['farm']['money']+=sum(result['private']['shed'].values())
                return result
            ds=compare(engine,SimpleNamespace(simulate_bundle=defective),state,env,1,592,plan,592)
            negative_controls.append(dict(defect=name,detected=bool(ds),first_difference=ds[:1]))
            if not ds: failures.append(dict(case='negative-control-'+name,differences=['Not detected']))
        report=dict(oracle_git_blob=git_blob(args.oracle),engine_sha256=hashes,
            loader_sha256=LOADER_SHA256,source_git_blobs={p.name:git_blob(p) for p in Path(args.engine).iterdir() if p.suffix in ('.py','.json')},
            harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            cases=count,executed_steps_per_arm=transitions,coverage=scopes,
            mismatches=len(failures),failures=failures,seconds=time.perf_counter()-start_time,
            input_immutability_checked=True,negative_controls=negative_controls,
            scope='Exact own farm/private, market, town and cash; PASS rival, zero weed spawning and no new shop unlocks. Synthetic states, not games or held-panel runs.',
            excluded=['simultaneous rival orders','unknown future shop/weed scenarios','policy controller cloning','runtime policy strength','hosted leaderboard behavior'])
        Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
        return 1 if failures else 0
    finally: urllib.request.urlopen=old

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--oracle',type=Path,required=True)
    p.add_argument('--loader',type=Path,required=True)
    p.add_argument('--engine',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    raise SystemExit(run(p.parse_args()))
