# SPDX-License-Identifier: Apache-2.0
"""Process-isolated actual main.agent controls; preserves raw actions and config."""
from __future__ import annotations
import argparse,collections,copy,hashlib,json,shutil,statistics,subprocess,sys,tempfile,time
from pathlib import Path
import check_funding_capacity as check
import compose_funding_capacity as compose

def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()

def run_one(args):
    check.authenticate(args.runtime,args.unitflow,args.funding_perf,args.town_funding)
    unit=check.load(args.unitflow,'_captrace_game_unit');perf=check.load(args.funding_perf,'_captrace_game_perf')
    town=check.load(args.town_funding,'_captrace_game_town')
    with tempfile.TemporaryDirectory(prefix='captrace-native-') as tmp:
        root=Path(tmp)/'native';shutil.copytree(args.runtime,root)
        sc=(root/'scheduler.py').read_text();fr=(root/'frozen_selected.py').read_text()
        if args.foundation=='town-unit-perf':fr=town.apply(fr)
        if args.foundation in ('unit-perf','town-unit-perf'):sc,fr=unit.compose_sources(sc,fr);fr=perf.apply(fr)
        if args.repair:fr=compose.apply(fr)
        (root/'scheduler.py').write_text(sc);(root/'frozen_selected.py').write_text(fr)
        manifest=json.loads((args.runtime/'SOURCE.json').read_text())['runtime']
        changed={'scheduler.py':sc.encode(),'frozen_selected.py':fr.encode()}
        for name,meta in manifest.items():
            expected=hashlib.sha256(changed[name]).hexdigest() if name in changed else meta['sha256']
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:raise ValueError('scratch pin: '+name)
        sys.path.insert(0,str(root))
        loader=check.load(root/'checks/reference/evaluator/loader.py','_captrace_game_loader')
        engine,_=loader.get_engine(root/'checks/reference/engine');S=loader.Struct
        import main
        import frozen_selected
        minima=[];original=frozen_selected.funded_minimum_now
        def observe(*a,**kw):
            out=original(*a,**kw)
            minima.append({'step':a[0]['step'],'end':a[6],'item':a[9],'minimum':out[0],
                'funding_turn':out[1].get('funding_turn'),'boundary':out[1].get('funding_boundary'),
                'fallback':out[1].get('fallback')})
            return out
        if not args.uninstrumented:frozen_selected.funded_minimum_now=observe
        cfg=S({k:v.get('default') if isinstance(v,dict) else v for k,v in engine.specification['configuration'].items()})
        cfg.seed=args.seed;env=S(configuration=cfg,done=False,info={})
        state=[S(observation=S(),action={},status='ACTIVE',reward=0) for _ in range(2)];engine.interpreter(state,env)
        frames=[];timings=[];statuses=collections.Counter();ah=hashlib.sha256();sh=hashlib.sha256()
        for step in range(cfg.episodeSteps):
            for seat,st in enumerate(state):
                st.observation.step=step
                if seat==args.seat:
                    start=time.perf_counter();st.action=main.agent(copy.deepcopy(st.observation),cfg);timings.append(time.perf_counter()-start)
                    d=main._INSTANCE.diagnostics if main._INSTANCE is not None else {};statuses[d.get('status','missing')]+=1
                else:st.action=engine.starter_agent(copy.deepcopy(st.observation))
            action=copy.deepcopy(state[args.seat].action);ah.update(encoded(action)+b'\n')
            engine.interpreter(state,env);raw=encoded([dict(st) for st in state]);sh.update(raw+b'\n')
            frames.append({'step':step,'action':action,'state_sha256':hashlib.sha256(raw).hexdigest()})
            if any(st.status=='DONE' for st in state):break
        if len(frames)!=719 or statuses!={'completed':719}:raise AssertionError('incomplete/fallback: '+str(statuses))
        own,rival=state[args.seat].reward,state[1-args.seat].reward
        return {'foundation':args.foundation,'repair':args.repair,'seed':args.seed,'seat':args.seat,
            'uninstrumented':args.uninstrumented,'score':own,'rival':rival,'margin':own-rival,'callbacks':len(frames),
            'status':dict(statuses),'max_seconds':max(timings),'median_seconds':statistics.median(timings),
            'total_seconds':sum(timings),'action_sha256':ah.hexdigest(),'state_sha256':sh.hexdigest(),
            'scheduler_blob':check.blob(sc.encode()),'frozen_blob':check.blob(fr.encode()),'minima':minima,'frames':frames}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',type=Path,required=True);p.add_argument('--unitflow',type=Path,required=True)
    p.add_argument('--funding-perf',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--town-funding',type=Path,required=True)
    p.add_argument('--one',action='store_true');p.add_argument('--foundation',choices=['native','unit-perf','town-unit-perf'],default='native')
    p.add_argument('--repair',action='store_true');p.add_argument('--uninstrumented',action='store_true')
    p.add_argument('--foundations',default='native,unit-perf,town-unit-perf')
    p.add_argument('--seed',type=int,default=9922999);p.add_argument('--seat',type=int,choices=[0,1],default=0)
    a=p.parse_args()
    if a.one:a.output.write_text(json.dumps(run_one(a),separators=(',',':'))+'\n');return
    check.authenticate(a.runtime,a.unitflow,a.funding_perf,a.town_funding);games=[];comparisons=[];parity=[]
    foundations=a.foundations.split(',')
    if not foundations or any(f not in ('native','unit-perf','town-unit-perf') for f in foundations):p.error('invalid foundation list')
    # Retain each complete child result even if the parent process is interrupted.
    tmp=tempfile.mkdtemp(prefix=a.output.stem+'-parts-',dir=a.output.parent)
    if True:
        for foundation in foundations:
            for seat in [0,1]:
                pair=[]
                for repair in [False,True]:
                    out=Path(tmp)/f'{foundation}-seat{seat}-repair{int(repair)}.json'
                    cmd=[sys.executable]+(['-O'] if not __debug__ else [])+[__file__,'--one','--runtime',str(a.runtime),
                        '--unitflow',str(a.unitflow),'--funding-perf',str(a.funding_perf),'--town-funding',str(a.town_funding),'--output',str(out),
                        '--foundation',foundation,'--seat',str(seat),'--seed',str(a.seed)]+(['--repair'] if repair else [])
                    done=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
                    if done.returncode:raise RuntimeError(done.stderr)
                    result=json.loads(out.read_text());pair.append(result)
                    print(json.dumps({k:result[k] for k in ['foundation','repair','seat','score','rival','callbacks','status','total_seconds']}),flush=True)
                    if foundation=='town-unit-perf' and seat==0 and repair:
                        plainout=Path(tmp)/f'{foundation}-seat{seat}-plain.json'
                        plaincmd=cmd.copy();plaincmd[plaincmd.index('--output')+1]=str(plainout)
                        done=subprocess.run(plaincmd+['--uninstrumented'],capture_output=True,text=True,timeout=120)
                        if done.returncode:raise RuntimeError(done.stderr)
                        plain=json.loads(plainout.read_text())
                        if (plain['action_sha256'],plain['state_sha256'],plain['score'])!=(result['action_sha256'],result['state_sha256'],result['score']):raise AssertionError('instrumentation changed episode')
                        parity.append({k:v for k,v in plain.items() if k not in ('frames','minima')})
                old,new=pair
                changes=[{'step':x['step'],'before':x['action'],'after':y['action']} for x,y in zip(old['frames'],new['frames']) if x['action']!=y['action']]
                comparisons.append({'foundation':foundation,'seat':seat,'delta_own':new['score']-old['score'],
                    'delta_rival':new['rival']-old['rival'],'delta_margin':new['margin']-old['margin'],
                    'changed_actions':len(changes),'action_changes':changes,
                    'changed_state_frames':sum(x['state_sha256']!=y['state_sha256'] for x,y in zip(old['frames'],new['frames']))})
                for result in pair:result.pop('frames');games.append(result)
                a.output.write_text(json.dumps({'status':'PARTIAL','games':games,'comparisons':comparisons,'parts_directory':str(tmp)},indent=2)+'\n')
    report={'status':'COMPLETE','parts_directory':str(tmp),'python':sys.version,'optimized':not __debug__,'runtime_members':109,'source_sha256':check.SOURCE_SHA,
        'opponent':'official_starter','seed':a.seed,'games':games,'comparisons':comparisons,'uninstrumented_parity_games':parity,
        'release_authorized':False,'scope':'Checked-archive component plus UNITFLOW+PERF, not current-HEAD whole V4 or field promotion.'}
    a.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
