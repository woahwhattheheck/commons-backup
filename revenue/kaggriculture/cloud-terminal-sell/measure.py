# SPDX-License-Identifier: MIT
"""Official-engine paired measurement; no copied game or opponent logic.

Use in isolated cloud compute. Passive final-day records stay outside actor
processes. Runtime receives only player-visible observations and public config.
"""
from __future__ import annotations
import argparse, copy, hashlib, importlib.util, json, sys
from pathlib import Path

def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod
    spec.loader.exec_module(mod);return mod

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def outcome(m):return 'W' if m>0 else 'L' if m<0 else 'T'

def compare(control, candidate):
    """Join by seed/opponent/seat, not order; failed/missing rows stay unresolved."""
    def index(rows):
        out={}
        for row in rows:
            key=(row['seed'],row['opponent'],row['candidate_seat'])
            if key in out:raise ValueError(f'Duplicate paired key: {key}')
            out[key]=row
        return out
    left,right=index(control),index(candidate);pairs=[];unresolved=[]
    for key in sorted(left.keys()|right.keys()):
        a,b=left.get(key),right.get(key)
        if a is None or b is None or a['status']!='complete' or b['status']!='complete':
            unresolved.append({'key':list(key),'control':None if a is None else a['status'],'candidate':None if b is None else b['status']});continue
        seat=key[2];am=a['scores'][seat]-a['scores'][1-seat];bm=b['scores'][seat]-b['scores'][1-seat]
        pairs.append({'seed':key[0],'opponent':key[1],'candidate_seat':seat,
            'control_cash':a['scores'][seat],'candidate_cash':b['scores'][seat],
            'own_cash_delta':b['scores'][seat]-a['scores'][seat],
            'rival_cash_delta':b['scores'][1-seat]-a['scores'][1-seat],
            'margin_delta':bm-am,'flip':outcome(am)+'>'+outcome(bm),
            'same_pre698_observations_and_actions':bool(a.get('pre698_sha256')) and a.get('pre698_sha256')==b.get('pre698_sha256')})
    return {'pairs':pairs,'unresolved':unresolved,'flips':{f:sum(r['flip']==f for r in pairs) for f in sorted({r['flip'] for r in pairs})}}

def play_one(repo,engine_dir,runtime,arm,opponent,seed,seat):
    base=repo/'revenue/kaggriculture'
    ev=load(base/'cloud-eval/evaluate.py','_osprey_evaluator')
    engine,hashes=ev.get_engine(engine_dir)
    native,native_commit=engine.interpreter,engine._commit_unit
    prefix=hashlib.sha256();final_day=[];receipts=[];terminal={};step=[-1];farm_ids={}
    def commit(op,item,price,farm,private,*args,**kwargs):
        result=native_commit(op,item,price,farm,private,*args,**kwargs)
        if result and step[0]>=696:receipts.append({'step':step[0],'player':farm_ids.get(id(farm)),'op':op,'item':item,'cash':price})
        return result
    def interpreter(state,env):
        obs=state[seat].observation
        if obs.get('farms'):
            step[0]=int(obs.get('step',0));farm_ids.update({id(f):i for i,f in enumerate(state[0].observation.farms)})
            if step[0]<698:prefix.update(ev.encoded({'observation':obs,'action':state[seat].action}))
            if step[0]>=696:final_day.append({'step':step[0],'observation':copy.deepcopy(obs),'configuration':copy.deepcopy(env.configuration),'actions':[copy.deepcopy(s.action) for s in state]})
        result=native(state,env)
        farm_ids.update({id(f):i for i,f in enumerate(state[0].observation.farms)})
        if all(s.status=='DONE' for s in state):terminal.update(farms=copy.deepcopy(state[0].observation.farms),private=[copy.deepcopy(s.observation.private) for s in state])
        return result
    engine.interpreter,engine._commit_unit=interpreter,commit
    candidate=(runtime/(arm+'-adapter.py')).resolve();rival=(runtime/(opponent+'-adapter.py')).resolve()
    pair=[str(candidate),str(rival)] if seat==0 else [str(rival),str(candidate)]
    try:game=ev.play(engine,pair,engine_dir,ev.LOADER,seed,seat)
    finally:engine.interpreter,engine._commit_unit=native,native_commit
    game.update(arm=arm,opponent=opponent,pre698_sha256=prefix.hexdigest(),final_day=final_day,final_day_receipts=receipts,terminal=terminal,
        provenance={'engine_ref':ev.ENGINE_REF,'engine_sha256':hashes,'evaluator_sha256':sha(ev.__file__),'measurement_sha256':sha(__file__),'candidate_adapter_sha256':sha(candidate),'opponent_adapter_sha256':sha(rival)},
        method='Existing cloud-eval.play; full official engine; native file-agent adapters; passive final-day capture. Not hosted rating.')
    return game

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['repo','engine-dir','runtime','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--arm',required=True);p.add_argument('--opponent',choices=['baseline','apex'],required=True)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--seat',type=int,choices=[0,1],required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Output exists; preserve it and choose a new file')
    g=play_one(a.repo.resolve(),a.engine_dir.resolve(),a.runtime.resolve(),a.arm,a.opponent,a.seed,a.seat)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(g,separators=(',',':'),allow_nan=False)+'\n')
    print(json.dumps({k:g[k] for k in ['arm','opponent','seed','candidate_seat','status','scores','failure','wall_seconds']}),flush=True)
    return int(g['status']!='complete')
if __name__=='__main__':raise SystemExit(main())
