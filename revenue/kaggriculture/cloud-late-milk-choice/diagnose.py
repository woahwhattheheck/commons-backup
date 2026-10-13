# SPDX-License-Identifier: Apache-2.0
"""Replay an existing complete panel trace through its original pinned engine.

Records actual successful per-unit/atomic cash transfers. No agents are called,
no new scenario is generated, and each reproduced full transition must equal
its retained counterpart. This is diagnosis, not an independent game sample.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def encoded(value): return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def replay(evaluator, engine_dir, loader, trace, seed, start=577):
    engine, hashes=evaluator.get_engine(engine_dir,loader=loader,prepare=False)
    rows=[json.loads(line) for line in gzip.open(trace,'rt',encoding='utf-8')]
    cfg=evaluator.Struct({k:v.get('default') if isinstance(v,dict) else v
                          for k,v in engine.specification['configuration'].items()})
    cfg.seed=seed
    env=evaluator.Struct(configuration=cfg,done=False,info={})
    state=[evaluator.Struct(observation=evaluator.Struct(),action={},status='ACTIVE',reward=0) for _ in range(2)]
    receipts=[]; current=-1
    unit,hire,land=engine._commit_unit,engine._do_hire,engine._do_buy_land
    def position(farm):
        return next(i for i,f in enumerate(state[0].observation.farms) if f is farm)
    def record(farm,op,item,before,quantity,ok):
        if current>=start:
            receipts.append({'step':current,'player':position(farm),'operation':op,'item':item,
                             'filled':quantity,'cash_delta':farm['money']-before,'success':bool(ok)})
    def commit(op,item,price,farm,private,market,shed_capacity=100):
        before=farm['money'];ok=unit(op,item,price,farm,private,market,shed_capacity)
        record(farm,op,item,before,int(bool(ok)),ok)
        return ok
    def do_hire(farm,private,board_size,mult=1):
        before=farm['money'];n=len(farm['hands']);out=hire(farm,private,board_size,mult)
        q=len(farm['hands'])-n;record(farm,'HIRE',None,before,q,q>0);return out
    def do_land(farm,board_size):
        before=farm['money'];n=len(farm['unlocked_quadrants']);out=land(farm,board_size)
        q=len(farm['unlocked_quadrants'])-n;record(farm,'BUY_LAND',None,before,q,q>0);return out
    engine._commit_unit,engine._do_hire,engine._do_buy_land=commit,do_hire,do_land
    digest=hashlib.sha256();opening=None
    try:
        for expected in rows:
            current=expected['step']
            if current>=0:
                for player in (0,1):
                    state[player].observation.step=current
                    state[player].observation.remainingOverageTime=0
                    state[player].action=deepcopy(expected['actions'][player])
            if current==start: opening=[f['money'] for f in state[0].observation.farms]
            actions=deepcopy([s.action for s in state])
            engine.interpreter(state,env)
            actual={'step':current,'actions':actions,'observations':[s.observation for s in state],
                    'status':[s.status for s in state],'rewards':[s.reward for s in state]}
            if actual!=expected:
                raise ValueError(f'Retained transition differs at {current}; diagnosis is not admitted as exact')
            digest.update(encoded(actual)+b'\n')
    finally:
        engine._commit_unit,engine._do_hire,engine._do_buy_land=unit,hire,land
    totals=defaultdict(lambda:{'filled':0,'cash_delta':0,'failed_attempts':0})
    for row in receipts:
        key=(row['player'],row['operation'],row['item'])
        total=totals[key];total['filled']+=row['filled'];total['cash_delta']+=row['cash_delta']
        total['failed_attempts']+=not row['success']
    closing=[s.reward for s in state]
    residuals=[closing[i]-opening[i]-sum(r['cash_delta'] for r in receipts if r['player']==i) for i in (0,1)]
    if any(residuals):raise ValueError('Cash bridge does not close')
    return {'trace_file':trace.name,'trace_sha256':hashlib.sha256(trace.read_bytes()).hexdigest(),
            'full_transition_sha256':digest.hexdigest(),'transitions_matched':len(rows),
            'source_engine_hashes':hashes,'seed':seed,'start':start,'opening_cash':opening,
            'terminal_cash':closing,'cash_residuals':residuals,'agent_calls':0,
            'totals':[dict(player=k[0],operation=k[1],item=k[2],**v) for k,v in sorted(totals.items(),key=lambda kv:str(kv[0]))],
            'receipts':receipts}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluator',type=Path,required=True)
    parser.add_argument('--loader',type=Path,required=True)
    parser.add_argument('--engine-dir',type=Path,required=True)
    parser.add_argument('--trace',type=Path,required=True)
    parser.add_argument('--seed',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('prism_replay_evaluator',args.evaluator)
    evaluator=importlib.util.module_from_spec(spec);sys.modules[spec.name]=evaluator;spec.loader.exec_module(evaluator)
    result=replay(evaluator,args.engine_dir,args.loader,args.trace,args.seed)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='receipts'},indent=2))

if __name__=='__main__':main()
