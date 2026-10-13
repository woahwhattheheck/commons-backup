"""Paired T04 panel over existing process-isolated cloud-eval and exact parents."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys

HERE=Path(__file__).resolve().parent
PANELS={'development':[9740001,9740019], 'held':[9740101,9740119]}

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
    return m

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--engine-dir',type=Path,required=True)
    p.add_argument('--panel',choices=PANELS,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-new-games',type=int,default=16)
    args=p.parse_args()
    root=args.source_root.resolve(); cache=args.engine_dir.resolve()
    parent_dir=root/'cloud-frontier-policy/next-panel'
    ev=load(root/'cloud-eval/evaluate.py','t04_process_eval')
    engine,engine_hashes=ev.get_engine(cache)
    arlene=parent_dir/'vendor/arlene.py';apex=parent_dir/'vendor/apex'
    pins=json.loads((parent_dir/'UPSTREAM.json').read_text())['files']
    for name,pin in pins.items():
        if name=='vendor/arlene.py' or name.startswith('vendor/apex/'):
            assert digest(parent_dir/name)==pin['sha256'],name
    freeze={'own_files':{n:digest(HERE/n) for n in ['oracle.py','policy.py','benchmark.py','test_oracle.py']},
            'engine_ref':ev.ENGINE_REF,'engine':engine_hashes,
            'evaluator':digest(ev.__file__),'loader':digest(ev.LOADER),
            'parent_files':{n:x['sha256'] for n,x in pins.items() if n=='vendor/arlene.py' or n.startswith('vendor/apex/')},
            'panels':PANELS,'mechanism':'CARE versus HARVEST on full fed animals; isolated parent continuation; fixed worker/capital plans with counterfactual SELL refresh; final day unchanged'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    freeze_path=args.output.parent/'FREEZE.json'
    if freeze_path.exists():
        assert json.loads(freeze_path.read_text())==freeze,'Source freeze changed; use a distinct experiment directory'
    else:
        freeze_path.write_text(json.dumps(freeze,indent=2)+'\n')
    compile_command=['g++','-O3','-std=c++17','-Wall','-Wextra','-pedantic','-shared','-fPIC','-Isource/include','-o','agent.so','source/policy.cpp','submission_bridge.cpp']
    if not (apex/'agent.so').exists():subprocess.run(compile_command,cwd=apex,check=True)
    adapter=args.output.parent/'candidate-adapter.py'
    adapter.write_text('import copy, importlib.util, sys\n'
        +f'sys.path.insert(0,{str(HERE)!r})\nfrom policy import make_policy\n'
        +'def load(path,name):\n s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m\n'
        +f'ev=load({str(Path(ev.__file__).resolve())!r},"t04_ev")\n'
        +f'engine,_=ev.get_engine({str(cache)!r})\n'
        +f'ar=load({str(arlene)!r},"t04_arlene")\n'
        +'agent=make_policy(ar.agent,engine,fork_parent=lambda:copy.copy(ar._A).act)\n')
    report=json.loads(args.output.read_text()) if args.output.exists() else {
        'panel':args.panel,'freeze_sha256':digest(freeze_path),'games':[],
        'compile_command':compile_command,'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
        'method':'Unchanged cloud-eval.play; 719 real official-engine decisions; fresh process per player per game; paired same seed/opponent/seat; not leaderboard results'}
    assert report['freeze_sha256']==digest(freeze_path)
    assert report['panel']==args.panel
    completed={(g['seed'],g['opponent'],g['candidate_seat'],g['arm']) for g in report['games']}
    count=0
    for seed in PANELS[args.panel]:
        for opponent,spec in [('arlene',arlene),('apex',apex/'main.py')]:
            for seat in [0,1]:
                for arm,candidate in [('control',arlene),('service',adapter.resolve())]:
                    key=(seed,opponent,seat,arm)
                    if key in completed:continue
                    if count>=args.max_new_games:return
                    ref=load(arlene,'passive_arlene').Agent()
                    original=engine.interpreter
                    differences=[]; difference_count=[0];terminal={}
                    def traced(state,env):
                        obs=state[seat].observation
                        if obs.get('farms'):
                            expected=ref.act(copy.deepcopy(obs))
                            actual=state[seat].action
                            if expected!=actual:
                                difference_count[0]+=1
                                if len(differences)<12:
                                    differences.append({'step':obs.step,'actual':copy.deepcopy(actual),'intact_parent_same_observation':expected,
                                                        'own_farm':copy.deepcopy(obs.farms[seat]),'own_private':copy.deepcopy(obs.private)})
                        result=original(state,env)
                        if all(s.status=='DONE' for s in state):
                            terminal.update(own_farm=copy.deepcopy(state[seat].observation.farms[seat]),own_private=copy.deepcopy(state[seat].observation.private))
                        return result
                    engine.interpreter=traced
                    pair=[str(candidate),str(spec)] if seat==0 else [str(spec),str(candidate)]
                    try:g=ev.play(engine,pair,cache,ev.LOADER,seed,seat)
                    finally:engine.interpreter=original
                    g.update(opponent=opponent,arm=arm,service_overrides=difference_count[0],differences=differences,terminal=terminal)
                    report['games'].append(g);count+=1
                    report['summary']={a:ev.summarize([g for g in report['games'] if g['arm']==a]) for a in ['control','service']}
                    pairs=[]
                    for cand in report['games']:
                        if cand['arm']!='service' or cand['status']!='complete':continue
                        ctrl=next((c for c in report['games'] if c['arm']=='control' and c['seed']==cand['seed'] and c['opponent']==cand['opponent'] and c['candidate_seat']==cand['candidate_seat'] and c['status']=='complete'),None)
                        if ctrl:
                            s=cand['candidate_seat'];cm=cand['scores'][s]-cand['scores'][1-s];bm=ctrl['scores'][s]-ctrl['scores'][1-s]
                            pairs.append(dict(seed=cand['seed'],opponent=cand['opponent'],seat=s,own_cash_delta=cand['scores'][s]-ctrl['scores'][s],margin_delta=cm-bm,control_result=(bm>0)-(bm<0),candidate_result=(cm>0)-(cm<0),overrides=cand['service_overrides']))
                    report['paired']=pairs
                    args.output.write_text(json.dumps(report,indent=2)+'\n')
                    print(json.dumps({k:g[k] for k in ['seed','opponent','candidate_seat','arm','status','scores','failure','service_overrides','wall_seconds']}),flush=True)
                    if g['status']!='complete':return

if __name__=='__main__':main()
