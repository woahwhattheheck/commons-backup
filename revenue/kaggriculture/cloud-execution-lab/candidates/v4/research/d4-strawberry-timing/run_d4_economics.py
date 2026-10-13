# SPDX-License-Identifier: Apache-2.0
"""Constructed both-seat native SELL lifecycle paths, with full engine settlement.

These are declared 23-transition fixtures, not ladder games or field EV.
Opponents do not read candidate-private state. Terminal cleanup is common and
explicit; asset/market differences are reported rather than valued as cash.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import test_native_d4 as tests


def run(unanchored=False):
    cls=tests.NativeEngineTests;cls.setUpClass();fixture=cls()
    rows=[]
    for seat in (0,1):
        for quantity,inventory in ((80,10000),(80,10020),(30,10050),(4,0)):
            for rival_plan in ('pass','now','before_due','same_due'):
                arms=[]
                for active in (False,True):
                    state,env,route=fixture.world(seat,quantity,inventory)
                    state[1-seat].observation.private['shed']['STRAWBERRY']=20
                    c=fixture.consumer((tests.unanchored_control() if unanchored else tests.candidate).FrozenSelected if active else tests.baseline.FrozenSelected,route,active)
                    chosen=[];actions=[];extensions=0
                    for now in range(361,384):
                        for s in state:
                            s.observation.step=now
                            s.observation.day=now//24;s.observation.hour=now%24
                        out=c.transform(copy.deepcopy(state[seat].observation),env.configuration,copy.deepcopy(route[now]))
                        d4=c.diagnostics.get('d4') or {}
                        extensions+=d4.get('due') is not None
                        if c.diagnostics.get('chosen'):
                            chosen.append({'step':now,'chosen':c.diagnostics['chosen']})
                        if now==383:
                            # Explicit identical liquidation rule in both arms.
                            out=copy.deepcopy(out)
                            out['market']=[['SELL','STRAWBERRY',state[seat].observation.private['shed'].get('STRAWBERRY',0)]]
                        rival=copy.deepcopy(tests.PASS)
                        due={'pass':-1,'now':361,'before_due':375,'same_due':376}[rival_plan]
                        if now==due:rival['market']=[['SELL','STRAWBERRY',20]]
                        actions.append(out)
                        fixture.step(state,env,seat,now,out,rival)
                    farms=copy.deepcopy(state[seat].observation.farms)
                    cash=[f.pop('money')for f in farms]
                    arms.append(dict(active=active,cash=cash,private=[s.observation.private for s in state],
                        physical_farms=farms,market=state[seat].observation.market,actions=actions,
                        chosen=chosen,extensions=extensions))
                a,b=arms
                rows.append(dict(seat=seat,quantity=quantity,inventory=inventory,rival_plan=rival_plan,
                    delta_own=b['cash'][seat]-a['cash'][seat],delta_rival=b['cash'][1-seat]-a['cash'][1-seat],
                    delta_margin=(b['cash'][seat]-b['cash'][1-seat])-(a['cash'][seat]-a['cash'][1-seat]),
                    same_physical=(a['physical_farms']==b['physical_farms'] and a['private']==b['private']),
                    same_market=a['market']==b['market'],
                    changed_actions=sum(x!=y for x,y in zip(a['actions'],b['actions'])),
                    baseline=a,candidate=b))
    return dict(kind='constructed_23_transition_native_sell_lifecycle',unanchored_control=unanchored,rows=rows,
        engine_calls=tests.REPORT['engine_calls'],engine_sha256=tests.REPORT['engine_sha256'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--unanchored-control',action='store_true');a=p.parse_args();result=run(a.unanchored_control);a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'cells':len(result['rows']),'engine_calls':result['engine_calls'],
        'summary':[{k:r[k]for k in ('seat','quantity','inventory','rival_plan','delta_own','delta_rival','delta_margin','same_physical','same_market','changed_actions')}for r in result['rows']]},sort_keys=True))
