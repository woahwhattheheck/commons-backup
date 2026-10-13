# SPDX-License-Identifier: Apache-2.0
"""Authenticated native parity, official-engine fixtures and alternating timing.
No network, package writes, feature changes, or hosted execution are performed.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import tarfile
import tempfile
import time
from compose_feedpath import compose, digest

ARCHIVE_SHA='b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9'
ENGINE_PINS={
 'kaggriculture.py':'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
 'kaggriculture.json':'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
 'utils.py':'537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
}
LOADER_SHA='cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e'
TEST_PINS={
 'test_feed_stock.py':'670dd0a4977466998653766c0446f361bd55b2193bc61b1ad493185b284a1b7d',
 'test_operating_stock.py':'29c2da02cb493c16ba475d409892bd660e32d4ed121b62d4d8c47faa4db44377',
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def authenticate(root, archive):
    require(digest(archive.read_bytes())==ARCHIVE_SHA,'archive hash mismatch')
    members={}
    with tarfile.open(archive) as tar:
        for entry in tar.getmembers():
            if not entry.isfile():
                continue
            name=entry.name.removeprefix('./')
            require(not Path(name).is_absolute() and '..' not in Path(name).parts,'unsafe archive member')
            data=tar.extractfile(entry).read()
            require((root/name).read_bytes()==data,'native member mismatch: '+name)
            members[name]=digest(data)
    for name, pin in ENGINE_PINS.items():
        require(digest((root/'checks/reference/engine'/name).read_bytes())==pin,'engine hash mismatch: '+name)
    require(digest((root/'checks/reference/evaluator/loader.py').read_bytes())==LOADER_SHA,'loader hash mismatch')
    for name,pin in TEST_PINS.items():
        require(digest((root/'checks'/name).read_bytes())==pin,'fixture hash mismatch: '+name)
    return members


def initialize(loader, engine, seed):
    cfg=loader.Struct({k:v.get('default') if isinstance(v,dict) else v
                       for k,v in engine.specification['configuration'].items()})
    cfg.seed=seed
    env=loader.Struct(configuration=cfg,done=False,info={})
    state=[loader.Struct(observation=loader.Struct(),action={},status='ACTIVE',reward=0) for _ in range(2)]
    engine.interpreter(state,env)
    return cfg,env,state


def json_bytes(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def game(root, loader, engine, seed, seat, profile):
    main=load('feedpath_native_main',root/'main.py')
    import operating_stock as stock
    calls=Counter();widths=Counter();changes=Counter()
    if profile:
        for name in ('_action','_feed_window','_bonus_water_service','protect_feed_stock','protect_operating_stock'):
            original=getattr(stock,name)
            def wrapper(*args,_name=name,_fn=original,**kwargs):
                calls[_name]+=1
                if _name=='_action':
                    widths[len(args[0].get('hands') or [])]+=1
                result=_fn(*args,**kwargs)
                if _name.startswith('protect_'):
                    changes[_name]+=int(result[1].get('changed',False))
                return result
            setattr(stock,name,wrapper)
    cfg,env,state=initialize(loader,engine,seed)
    actions=hashlib.sha256();states=hashlib.sha256();records=[];times=[];statuses=Counter();raw_excess=Counter()
    for step in range(cfg.episodeSteps):
        returned=[]
        for player,s in enumerate(state):
            s.observation.step=step
            obs=deepcopy(s.observation)
            start=time.perf_counter()
            action=main.agent(obs,cfg) if player==seat else engine.starter_agent(obs)
            if player==seat:
                times.append(time.perf_counter()-start)
                statuses[getattr(main._INSTANCE,'diagnostics',{}).get('status','missing')]+=1
            require(isinstance(action,dict),'non-dict action')
            # The full interpreter, not a stricter local convention, owns
            # ghost-worker and raw-market-tail admission. Preserve all rows.
            if player==seat:
                raw_excess['hands']+=max(0,len(action.get('hands',[]))-len(s.observation.farms[player]['hands']))
                raw_excess['market']+=max(0,len(action.get('market',[]))-cfg.maxMarketOrdersPerTurn)
            s.action=action;returned.append(action)
        action_data=json_bytes(returned);actions.update(action_data+b'\n')
        engine.interpreter(state,env)
        state_data=json_bytes([state,env]);states.update(state_data+b'\n')
        records.append([step,digest(action_data),digest(state_data)])
        if any(s.status=='DONE' for s in state):
            break
    require(step+1==719 and all(s.status=='DONE' for s in state),'incomplete native game')
    require(statuses=={'completed':719},'native fallback or incomplete callback: '+str(statuses))
    return {'seed':seed,'seat':seat,'opponent':'official_starter','profiled':profile,
            'steps':step+1,'rewards':[s.reward for s in state],'callback_status':dict(statuses),
            'action_trace_sha256':actions.hexdigest(),'state_trace_sha256':states.hexdigest(),
            'calls':dict(calls),'lookup_hands_histogram':dict(widths),'changed_proposals':dict(changes),
            'raw_excess_rows':dict(raw_excess),'callback_seconds':times,'trace':records}


def component_work(root, loader, engine, benchmark):
    os.environ['TITAN_NATIVE']=str(root)
    import check_feedpath as check
    if benchmark:
        output=[]
        for kind in ('feed','fert'):
            key='protect_feed_stock' if kind=='feed' else 'protect_operating_stock'
            for width in (1,4,8,11,12,16,32,64,128):
                f=check.fixture(kind,width);args=check.arguments(f)
                require(getattr(check.BASE,key)(*args)==getattr(check.CAND,key)(*args),'consumer mismatch')
                rounds=[]
                for repetition in range(9):
                    times={}
                    for label in (('baseline','candidate') if repetition%2==0 else ('candidate','baseline')):
                        fn=getattr(check.BASE if label=='baseline' else check.CAND,key)
                        start=time.perf_counter_ns()
                        for _ in range(80):fn(*args)
                        times[label]=(time.perf_counter_ns()-start)/80
                    rounds.append(times)
                output.append({'consumer':key,'hands':width,'rounds_ns':rounds,
                               'median_ratio':statistics.median(r['baseline'] for r in rounds)/
                                              statistics.median(r['candidate'] for r in rounds)})
        return {'scope':'constructed full-consumer calls, not whole-agent speed','cases':output,
                'candidate_source_sha256':digest(check.CANDIDATE.encode())}
    results=[];calls=0
    for kind in ('feed','fert'):
        key='protect_feed_stock' if kind=='feed' else 'protect_operating_stock'
        for width in (1,8,32):
            for carried in (0,1,2):
                for seat in (0,1):
                    f=check.fixture(kind,width,carried,seat)
                    candidate=getattr(check.CAND,key)(*check.arguments(f))
                    baseline=getattr(check.BASE,key)(*check.arguments(f))
                    require(candidate==baseline,'proposal/report mismatch')
                    snapshots=[]
                    for action in (baseline[0],candidate[0]):
                        cfg,env,state=initialize(loader,engine,91241);calls+=1
                        farm=state[0].observation.farms[seat]
                        farm.update(deepcopy(f.farm))
                        for player,s in enumerate(state):
                            s.observation.step=460;s.observation.day=19;s.observation.hour=4
                            if player==seat:s.observation.private=loader.Struct(deepcopy(f.private))
                            s.action=deepcopy(action) if player==seat else {'farmer':['PASS'],'hands':[],'market':[]}
                        engine.interpreter(state,env);calls+=1
                        snapshots.append(json_bytes([state,env]))
                    require(snapshots[0]==snapshots[1],'official transition mismatch')
                    results.append({'kind':kind,'hands':width,'carried':carried,'seat':seat,
                                    'changed':candidate[1]['changed'],'state_sha256':digest(snapshots[0])})
    return {'cases':results,'candidate_source_sha256':digest(check.CANDIDATE.encode()),
            'full_interpreter_calls_including_initialization':calls,
            'completed_transitions':len(results)*2}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--variant',choices=('baseline','candidate'),default='baseline')
    parser.add_argument('--task',choices=('game','engine','benchmark'),default='game')
    parser.add_argument('--seed',type=int,default=17)
    parser.add_argument('--seat',type=int,choices=(0,1),default=0)
    parser.add_argument('--profile',action='store_true')
    args=parser.parse_args();root=args.root.resolve()
    if args.task!='game' and args.variant!='baseline':
        parser.error('component work compares both variants and requires original baseline root')
    members=authenticate(root,args.archive.resolve())
    with tempfile.TemporaryDirectory(prefix='feedpath-native-') as directory:
        if args.variant=='candidate':
            scratch=Path(directory)/'runtime';shutil.copytree(root,scratch,ignore=shutil.ignore_patterns('__pycache__'))
            (scratch/'operating_stock.py').write_text(compose((root/'operating_stock.py').read_text()))
            root=scratch
        sys.path.insert(0,str(root))
        loader=load('feedpath_official_loader',root/'checks/reference/evaluator/loader.py')
        engine,hashes=loader.get_engine(root/'checks/reference/engine')
        result=(game(root,loader,engine,args.seed,args.seat,args.profile) if args.task=='game'
                else component_work(root,loader,engine,args.task=='benchmark'))
        result.update(task=args.task,variant=args.variant,python=sys.version,optimized=bool(sys.flags.optimize),
                      archive_sha256=ARCHIVE_SHA,runtime_member_sha256=members,
                      runtime_members_authenticated=len(members),engine_sha256=hashes,
                      operating_stock_sha256=digest((root/'operating_stock.py').read_bytes()),
                      production_or_default_changed=False)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k not in
                          ('trace','callback_seconds','runtime_member_sha256','cases')},sort_keys=True))


if __name__=='__main__':main()
