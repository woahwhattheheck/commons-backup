"""Development-only joint-route diagnostic, using actual official transitions."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent

def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m


def main(output, cache, seed):
    ev=load(ROOT/'cloud-eval/evaluate.py','ev_probe')
    arlene=load(ROOT/'cloud-frontier-policy/next-panel/vendor/arlene.py','arlene_probe')
    oracle=load(ROOT/'cloud-service-value/oracle.py','oracle_probe')
    from policy import RollingAgent, Continuation, fork_parent
    from scheduler import decode_day, remaining, capital_signature, outstanding_stock
    engine,_=ev.get_engine(cache)
    cfg=ev.Struct({k:v.get('default') if isinstance(v,dict) else v for k,v in engine.specification['configuration'].items()})
    cfg.seed=seed;env=ev.Struct(configuration=cfg,done=False,info={})
    state=[ev.Struct(observation=ev.Struct(),action={},status='ACTIVE',reward=0) for _ in range(2)]
    engine.interpreter(state,env)
    assert cfg.get('seed') is None
    agents=[arlene.Agent(),arlene.Agent()]
    snapshots={}
    for step in range(719):
        for s in state:s.observation.step=step
        if step in (458,482,602,650,674,698):
            snapshots[step]=(deepcopy(state[0].observation),fork_parent(agents[0]))
        for i in range(2):state[i].action=agents[i].act(state[i].observation)
        engine.interpreter(state,env)
    rows=[]
    output.mkdir(parents=True,exist_ok=True)
    for step,(obs,parent) in snapshots.items():
        day=step//24
        jobs=remaining(decode_day(parent.R[parent.cur],day),step,1+len(obs['farms'][0]['hands']))
        controller=Continuation(parent,{},jobs,step)
        horizon=min((day+1)*24+1,718)
        t=time.perf_counter();reference=oracle.simulate_bundle(engine,obs,cfg,parent.act,end_step=horizon,record_actions=True);ref_seconds=time.perf_counter()-t
        t=time.perf_counter();translated=oracle.simulate_bundle(engine,obs,cfg,controller,end_step=horizon,record_actions=True);seconds=time.perf_counter()-t
        a,b=outstanding_stock(reference),outstanding_stock(translated)
        row={'step':step,'workers':1+len(obs['farms'][0]['hands']),'reference_cash':reference['cash_gain'],'translated_cash':translated['cash_gain'],
             'same_capital':capital_signature(reference['farm'],reference['private'])==capital_signature(translated['farm'],translated['private']),
             'stock_delta':{k:b[k]-a[k] for k in a|b if a[k]!=b[k]},'missed':controller.missed,'reference_seconds':ref_seconds,'translated_seconds':seconds}
        rows.append(row);print(json.dumps(row),flush=True)
        (output/f'frame-{step}.json').write_text(json.dumps({'observation':obs,'configuration':cfg,'route':parent.cur},indent=2))
        (output/f'compare-{step}.json').write_text(json.dumps({'reference':reference,'translated':translated},indent=2))
    result={'seed':seed,'control_scores':[s.reward for s in state],'steps':719,'rows':rows}
    (output/'probe.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--engine-dir',type=Path,required=True);p.add_argument('--seed',type=int,required=True);a=p.parse_args();main(a.output,a.engine_dir,a.seed)
