# SPDX-License-Identifier: Apache-2.0
"""One foreground native game per process. Preserve atomic ghost actor rows."""
from collections import Counter
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import compose_native as C
import test_discarded_fertilizer as E


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def run(package, seed, seat):
    package=Path(package).resolve()
    if type(seed) is not int or type(seat) is not int or seat not in (0,1):
        raise ValueError('plain integer seed and seat required')
    manifest=json.loads((package/'SOURCE.json').read_text())
    for name,row in manifest['runtime'].items():
        if C.digest(package/name)!=row['sha256']:
            raise ValueError('runtime member mismatch: '+name)
    if C.digest(package/'main.py')!='c4c22d0f2b1071cadf6a9f74effccc8cb20ea9f4d10ca1cf9f1fe57351709dc1':
        raise ValueError('unrecognized entrypoint')
    if C.digest(package/'titan_runtime.py') not in (
            C.RUNTIME_SHA,'c61d54ef269cb04a24288def47b5f06db5a4cfd61d2d97986f11a8e004d11241'):
        raise ValueError('unrecognized native runtime; revalidate this runner')
    sys.path.insert(0,str(package))
    main=E.load(package/'main.py','census_native_main')
    engine,S,hashes=E.authenticated_engine(package)
    cfg=S({k:v.get('default') if isinstance(v,dict) else v
           for k,v in engine.specification['configuration'].items()})
    cfg.seed=seed
    env=S(configuration=cfg,done=False,info={})
    state=[S(observation=S(),action={},status='ACTIVE',reward=0) for _ in range(2)]
    engine.interpreter(state,env)
    actions_hash=hashlib.sha256();world_hash=hashlib.sha256()
    statuses=Counter();reasons=Counter();shadow=Counter()
    max_call=0.0;total_call=0.0;tomato_callbacks=0;tomato_eod=0;proposals=0;ghost_rows=0
    trace=[]
    for step in range(720):
        for s in state:s.observation.step=step
        obs=state[seat].observation
        plants=sum(isinstance(t,dict) and t.get('crop')=='TOMATO'
                   for row in obs.farms[seat]['tiles'] for t in row)
        tomato_callbacks+=bool(plants)
        tomato_eod+=bool(plants) and step%24==23
        start=time.perf_counter()
        own=main.agent(deepcopy(obs),deepcopy(cfg))
        elapsed=time.perf_counter()-start
        max_call=max(max_call,elapsed);total_call+=elapsed
        if (not isinstance(own,dict) or not isinstance(own.get('farmer'),list)
                or not isinstance(own.get('hands'),list) or not isinstance(own.get('market'),list)):
            raise ValueError('invalid native action shape')
        ghost_rows+=max(0,len(own['hands'])-len(obs.farms[seat]['hands']))
        diag=dict(getattr(main._INSTANCE,'diagnostics',{}) or {})
        statuses[diag.get('status','no_instance')]+=1
        rep=diag.get('tomato_discard_salvage',{})
        reasons[rep.get('reason','not_called')]+=1
        proposals+=bool(rep.get('changed'))
        _,potential=E.H.apply_discarded_fertilizer(obs,own,cfg,enabled=True)
        shadow[potential['reason']]+=1
        state[seat].action=own
        state[1-seat].action=engine.starter_agent(deepcopy(state[1-seat].observation))
        actions_hash.update(encode([s.action for s in state])+b'\n')
        engine.interpreter(state,env)
        world_hash.update(encode({'state':state,'env':env})+b'\n')
        if rep.get('changed'):
            trace.append({'step':step,'proposal':rep,'action':own})
        if any(s.status=='DONE' for s in state):
            env.done=True;break
    final=[s.reward for s in state]
    complete=step==718 and all(s.status=='DONE' for s in state)
    report={'seed':seed,'seat':seat,'steps':step+1,'native_games':1,
        'complete':complete,'scores':final,'own_score':final[seat],'rival_score':final[1-seat],
        'margin':final[seat]-final[1-seat],'native_statuses':dict(statuses),
        'max_call_seconds':max_call,'total_call_seconds':total_call,
        'tomato_visible_callbacks':tomato_callbacks,'tomato_visible_eod_callbacks':tomato_eod,
        'candidate_proposal_callbacks':proposals,'candidate_reasons':dict(reasons),
        'shadow_reasons':dict(shadow),'ghost_hand_rows_preserved':ghost_rows,'proposal_trace':trace,
        'action_trace_sha256':actions_hash.hexdigest(),'state_env_trace_sha256':world_hash.hexdigest(),
        'runtime_sha256':C.digest(package/'titan_runtime.py'),'entrypoint_sha256':C.digest(package/'main.py'),
        'config':json.loads((package/'TITAN-CONFIG.json').read_text()),'engine_sha256':hashes,
        'source_manifest_sha256':C.digest(package/'SOURCE.json'),
        'opponent':'pinned official starter_agent','scope':'actual native main.py::agent full game; activation/parity census, NOT a promotion gate',
        'disposition':'NEEDS_ENGAGED_PAIRED_FIELD_GATE' if proposals else 'NO_OPPORTUNITY_IS_NOT_A_KILL'}
    if not complete:raise RuntimeError('incomplete native game')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('package',type=Path);p.add_argument('--seed',type=int,default=17)
    p.add_argument('--seat',type=int,choices=(0,1),default=0);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();r=run(a.package,a.seed,a.seat)
    a.report.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
    print(json.dumps(r,sort_keys=True))
