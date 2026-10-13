# SPDX-License-Identifier: Apache-2.0
"""Exact market subgame from an actual development admission and real slots.

These legal PASS-unit continuations isolate market receipts. They do not replay
the full producer or claim that its opportunities remain unchanged.
"""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from dependencies import official_engine
from recourse import choose_observed


def replay(ev,engine,case,stream,seat,adaptive):
    cfg=ev.Struct({k:v.get('default') if isinstance(v,dict) else v
                   for k,v in engine.specification['configuration'].items()})
    cfg.seed=0;env=ev.Struct(configuration=cfg,done=False,info={})
    state=[ev.Struct(observation=ev.Struct(),action={},status='ACTIVE',reward=0) for _ in range(2)]
    engine.interpreter(state,env)
    item=case['item'];market=state[0].observation.market
    market['inventory'][item]=case['inventory']
    if case['params'] is not None:market['params']=deepcopy(case['params'])
    engine._refresh_prices(market)
    state[0].observation.town['unlocked_shops']=case['shops']
    state[seat].observation.private['shed']={item:case['quantity']}
    _,rival,alignment=stream
    state[1-seat].observation.private['shed']={item:sum(q for _,q in rival)}
    for f in state[0].observation.farms:f['money']=0
    own_slot=case['own_slot'];rival_slot=own_slot+{'before':-1,'paired':0,'after':1}[alignment]
    assert rival_slot>=0
    policy=case['policy'];plan=dict(policy['plans'][0]['sales']);rival=dict(rival)
    rows=[];chosen=0
    for step in range(case['now'],case['end']+1):
        for s in state:s.observation.update(step=step,day=step//24,hour=step%24)
        if adaptive and step==policy['branch']:
            chosen=choose_observed(policy,state[seat].observation,item)
            assert chosen is not None
            plan=dict(policy['plans'][chosen]['sales'])
        for who,slot,orders in ((seat,own_slot,plan),(1-seat,rival_slot,rival)):
            queue=[[] for _ in range(slot)]+[['SELL',item,orders[step]]] if orders.get(step,0) else []
            state[who].action={'farmer':['PASS'],'hands':[],'market':queue}
        actions=deepcopy([s.action for s in state]);before=[f['money'] for f in state[0].observation.farms]
        engine.interpreter(state,env)
        rows.append({'step':step,'actions':actions,'cash_before':before,
            'cash_after':[f['money'] for f in state[0].observation.farms],
            'inventory_after':market['inventory'][item]})
    return {'cash':[state[0].observation.farms[s]['money'] for s in (seat,1-seat)],
            'chosen':chosen,'transitions':rows}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--engine-dir',required=True);a=p.parse_args()
    case=json.loads(gzip.decompress((HERE/'results/reached-scan.json.gz').read_bytes()))['findings'][0]
    ev,engine,hashes=official_engine(a.engine_dir);seats=[]
    for seat in (0,1):
        baseline=[replay(ev,engine,case,s,seat,False) for s in case['streams']]
        adaptive=[replay(ev,engine,case,s,seat,True) for s in case['streams']]
        deltas=[a['cash'][0]-a['cash'][1]-b['cash'][0]+b['cash'][1] for a,b in zip(adaptive,baseline)]
        assert deltas==case['policy']['causal_deltas']
        seats.append({'seat':seat,'deltas':deltas,'baseline':baseline,'adaptive':adaptive})
    r={'engine':hashes,'context':case,'seats':seats,'serialized_transitions':sum(len(r['transitions']) for s in seats for arm in ('baseline','adaptive') for r in s[arm])}
    (HERE/'results/reached-engine.json.gz').write_bytes(gzip.compress(json.dumps(r,indent=2).encode(),mtime=0))
    print(json.dumps({'reached_seed':9943001,'step':case['now'],'own_slot':case['own_slot'],
        'columns':len(case['streams']),'both_seats':True,'deltas':seats[0]['deltas'],
        'transitions':r['serialized_transitions']}))
