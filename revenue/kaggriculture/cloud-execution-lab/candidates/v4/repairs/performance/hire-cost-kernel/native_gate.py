# SPDX-License-Identifier: Apache-2.0
"""Actual-entrypoint differential games in separate processes, offline only.

The reference interpreter is unmodified. Raw actions, including extra hand rows,
are never truncated. Each worker writes an exclusive-create evidence file.
"""
from __future__ import annotations
import argparse, copy, hashlib, importlib.util, json, sys, time
from pathlib import Path
from collections import Counter
NAMES=('_decay_plants','_daily_refresh_plants','_daily_refresh_animals','_fib')
ENGINE_SHA='bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj)
    return obj


def compact(obj):
    return json.dumps(obj,separators=(',',':'),sort_keys=True,allow_nan=False).encode()


MAP_SHA='e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
MECHANICS_SHA=('579965e589237d1e5bbcc8b8448188f91b173d4480430d34b3a7f0e07e0c48d3',
               '74de5bbe1408be4393d5b7123b695b2a2af1a77ed0a39e3fa12aeca936069822')


def authenticate(root, source_map):
    raw=source_map.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=MAP_SHA:raise ValueError('source map drift')
    runtime=json.loads(raw)['runtime']
    for name, record in runtime.items():
        path=root/name
        if not path.resolve().is_relative_to(root):raise ValueError('invalid manifest path')
        content=path.read_bytes();sha=hashlib.sha256(content).hexdigest()
        if name=='mechanics.py':
            if sha not in MECHANICS_SHA:raise ValueError('untested mechanics')
        elif sha!=record['sha256'] or len(content)!=record['bytes']:
            raise ValueError('runtime source drift: '+name)
    return len(runtime)


def worker(args):
    root=args.runtime.resolve();sys.path.insert(0,str(root))
    authenticated_files=authenticate(root,args.source_map)
    enginepath=root/'checks/reference/engine'
    if hashlib.sha256((enginepath/'kaggriculture.py').read_bytes()).hexdigest()!=ENGINE_SHA:
        raise ValueError('engine source drift')
    for name in ('kaggriculture.py','kaggriculture.json','utils.py'):
        if not (enginepath/name).is_file():raise ValueError('offline engine cache incomplete')
    loader=load('hire_cost_game_loader',root/'checks/reference/evaluator/loader.py')
    engine,engine_hashes=loader.get_engine(enginepath)
    import mechanics
    calls=Counter();fib_arguments=Counter();samples={name:[] for name in NAMES}
    for name in NAMES:
        fn=getattr(mechanics,name)
        def observe(farm,*params,_name=name,_fn=fn):
            calls[_name]+=1
            if _name=="_fib":fib_arguments[str(farm)]+=1
            # Both arms use identical instrumentation and bounded input capture.
            if len(samples[_name])<8 and (calls[_name]-1)%37==0:
                samples[_name].append({'input':copy.deepcopy(farm),'args':params})
            return _fn(farm,*params)
        setattr(mechanics,name,observe)
    main=load('hire_cost_actual_entrypoint',root/'main.py')
    S=loader.Struct
    cfg=S({k:v.get('default') if isinstance(v,dict) else v for k,v in engine.specification['configuration'].items()})
    cfg.seed=args.seed;env=S(configuration=cfg,done=False,info={})
    state=[S(observation=S(),action={},status='ACTIVE',reward=0) for _ in range(2)]
    engine.interpreter(state,env)
    statuses=Counter();parents=Counter();actions=hashlib.sha256();states=hashlib.sha256()
    frames=[];durations=[];raw_extra_hands=0
    for step in range(int(cfg.episodeSteps)):
        for i,s in enumerate(state):
            s.observation.step=step;observation=copy.deepcopy(s.observation)
            if i==args.seat:
                before=time.perf_counter();action=main.agent(observation,cfg)
                durations.append(time.perf_counter()-before)
                inst=main._INSTANCE;diag=getattr(inst,'diagnostics',{}) if inst is not None else {}
                statuses[str(diag.get('status','missing_instance'))]+=1
                parents[str(diag.get('parent_calls','missing'))]+=1
                raw_extra_hands+=max(0,len(action.get('hands',[]))-len(observation.farms[i]['hands']))
            elif args.opponent=='starter':action=engine.starter_agent(observation)
            else:action={'farmer':['PASS'],'hands':[],'market':[]}
            if not isinstance(action,dict):raise TypeError('native return is not a dict')
            s.action=action
        raw=compact([s.action for s in state]);actions.update(raw+b'\n')
        engine.interpreter(state,env);after=compact(state);states.update(after+b'\n')
        frames.append({'step':step,'actions_sha256':hashlib.sha256(raw).hexdigest(),
                       'state_sha256':hashlib.sha256(after).hexdigest()})
        if any(s.status=='DONE' for s in state):break
    report={'schema':'titan.v4.hire-cost.native-game.v1','seed':args.seed,'seat':args.seat,
            'opponent':args.opponent,'authenticated_files':authenticated_files,'source_map_sha256':MAP_SHA,'steps':step+1,'native_callbacks':len(durations),
            'status':dict(statuses),'parent_calls':dict(parents),'final_status':[s.status for s in state],
            'scores':[s.reward for s in state],'raw_extra_hand_rows':raw_extra_hands,
            'kernel_calls':dict(calls),'fib_argument_histogram':dict(fib_arguments),'action_tape_sha256':actions.hexdigest(),
            'state_tape_sha256':states.hexdigest(),'frames':frames,'call_samples':samples,
            'max_call_seconds':max(durations),'sum_native_call_seconds':sum(durations),
            'engine_sha256':engine_hashes,'mechanics_sha256':hashlib.sha256((root/'mechanics.py').read_bytes()).hexdigest(),
            'entrypoint_sha256':hashlib.sha256((root/'main.py').read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('frames','call_samples','engine_sha256')},sort_keys=True))
    if report['final_status']!=['DONE','DONE'] or statuses!={'completed':step+1}:
        raise RuntimeError('incomplete native gate; inspect saved evidence')


def compare(paths):
    a,b=(json.loads(p.read_text()) for p in paths)
    keys=('seed','seat','opponent','authenticated_files','source_map_sha256','steps','native_callbacks','status','parent_calls','final_status','scores',
          'raw_extra_hand_rows','kernel_calls','fib_argument_histogram','action_tape_sha256','state_tape_sha256','frames','call_samples',
          'engine_sha256','entrypoint_sha256')
    failures=[key for key in keys if a[key]!=b[key]]
    if failures:raise RuntimeError('native differential mismatch: '+', '.join(failures))
    print(json.dumps({'equal':True,'seed':a['seed'],'seat':a['seat'],'opponent':a['opponent'],
                      'frames':a['steps'],'scores':a['scores'],'kernel_calls':a['kernel_calls']},sort_keys=True))


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('worker');p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--source-map',type=Path,required=True)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--seat',type=int,choices=(0,1),required=True)
    p.add_argument('--opponent',choices=('starter','pass'),required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('compare');p.add_argument('reports',type=Path,nargs=2)
    args=parser.parse_args()
    if args.cmd=='worker':worker(args)
    else:compare(args.reports)
if __name__=='__main__':main()
