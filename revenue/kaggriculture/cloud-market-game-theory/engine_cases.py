# SPDX-License-Identifier: Apache-2.0
"""Replay conditional complete-sale tables through the pinned official engine."""
import argparse
import copy
import json
from pathlib import Path

from dependencies import official_engine
from solver import solve_table


def execute(ev, engine, context, plan, stream, *, seat=0, own_slot=1):
    cfg = ev.Struct({k: v.get('default') if isinstance(v,dict) else v
                     for k,v in engine.specification['configuration'].items()})
    cfg.seed=0
    env=ev.Struct(configuration=cfg,done=False,info={})
    state=[ev.Struct(observation=ev.Struct(),action={},status='ACTIVE',reward=0) for _ in range(2)]
    engine.interpreter(state,env)
    item=context['item']; market=state[0].observation.market
    market['inventory'][item]=context['inventory']
    engine._refresh_prices(market)
    state[0].observation.town['unlocked_shops']=list(context['shops'])
    state[seat].observation.private['shed']={item:context['quantity']}
    _, rival, alignment=stream
    rival_slot={'before':0,'paired':1,'after':2}[alignment]
    state[1-seat].observation.private['shed']={item:sum(q for _,q in rival)}
    for farm in state[0].observation.farms:
        farm['money']=0
    now,end=context['now'],context['end']
    plan,rival=dict(plan),dict(rival)
    rows=[]
    for step in range(now,end+1):
        for who,slot,orders in ((seat,own_slot,plan),(1-seat,rival_slot,rival)):
            obs=state[who].observation
            obs['step']=step;obs['day']=step//cfg.turnsPerDay;obs['hour']=step%cfg.turnsPerDay
            queue=[[]]*slot+[['SELL',item,orders[step]]] if orders.get(step,0) else []
            state[who].action={'farmer':['PASS'],'hands':[],'market':queue}
        before=[f['money'] for f in state[0].observation.farms]
        actions=copy.deepcopy([s.action for s in state])
        engine.interpreter(state,env)
        after=[f['money'] for f in state[0].observation.farms]
        rows.append({'step':step,'actions':actions,'cash_before':before,'cash_after':after,
                     'market_inventory_after':market['inventory'][item]})
    cash=[state[0].observation.farms[i]['money'] for i in (seat,1-seat)]
    return {'cash':cash,'remaining':[state[i].observation.private['shed'].get(item,0) for i in (seat,1-seat)],
            'market_inventory':market['inventory'][item],'transitions':rows}


def verify_table(ev,engine,context):
    seats=[]
    for seat in (0,1):
        receipts=[[execute(ev,engine,context,plan,stream,seat=seat) for stream in context['streams']]
                  for plan in context['plans']]
        baseline=[r['cash'][0]-r['cash'][1] for r in receipts[0]]
        table=[[r['cash'][0]-r['cash'][1]-b for r,b in zip(row,baseline)] for row in receipts]
        assert table==context['table'], (seat,table,context['table'])
        assert all(r['remaining']==[0,0] for row in receipts for r in row)
        seats.append({'seat':seat,'table':table,'solution':solve_table(table),'receipts':receipts})
    return {'context':context,'verified_seats':seats}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine-dir',type=Path,required=True)
    p.add_argument('--scan',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();ev,engine,hashes=official_engine(a.engine_dir)
    source=json.loads(a.scan.read_text())
    cases=[verify_table(ev,engine,x) for x in source['findings']]
    a.output.write_text(json.dumps({'engine_sha256':hashes,'cases':cases},indent=2)+'\n')
    print(json.dumps({'tables':len(cases),'both_seats':True,'official_transitions':sum(len(r['transitions']) for c in cases for s in c['verified_seats'] for row in s['receipts'] for r in row)}))
