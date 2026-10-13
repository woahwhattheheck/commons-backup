"""Reuse the existing runner, branch only its reached final action, retain all traces."""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from terminal_admission import RivalScenario, optimize_terminal_admission


def sale_stress(observation, config, products):
    """Finite uncalibrated hypotheses from public capacity, never private rival data."""
    capacity = int(config.get('shedCapacity',100))
    return [RivalScenario('idle',{},[],'no-sale stress hypothesis')] + [
        RivalScenario('full-'+item,{item:capacity},[['SELL',item,capacity]],
                      'public capacity upper-bound stress; no probability assigned')
        for item in products]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo-root',type=Path,required=True)
    ap.add_argument('--engine-dir',type=Path,required=True)
    ap.add_argument('--seeds',type=int,nargs='+',required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--candidate', type=Path, help='Existing complete agent entrypoint; default is frozen SELL')
    ap.add_argument('--seats', type=int, choices=[0,1], nargs='+', default=[0,1])
    ap.add_argument('--opponent',choices=['arlene','apex'],action='append')
    args=ap.parse_args()
    r=args.repo_root/'revenue/kaggriculture'
    spec=importlib.util.spec_from_file_location('admission_existing_eval',r/'cloud-eval/evaluate.py')
    ev=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ev;spec.loader.exec_module(ev)
    engine,hashes=ev.get_engine(args.engine_dir)
    original_interpreter=engine.interpreter
    candidate=str((args.candidate or r/'cloud-titan-composition/arms/sell.py').resolve())
    if not Path(candidate).is_file():
        ap.error(f'Candidate entrypoint does not exist: {candidate}')
    candidate_identity={'entrypoint':candidate, 'entrypoint_sha256':hashlib.sha256(Path(candidate).read_bytes()).hexdigest()}
    candidate_manifest=Path(candidate).with_name('SOURCE.json')
    if candidate_manifest.is_file():
        candidate_identity['source_manifest']=json.loads(candidate_manifest.read_text())
    opponents={'arlene':str(r/'cloud-frontier-policy/next-panel/vendor/arlene.py'),
               'apex':str(r/'cloud-frontier-policy/next-panel/vendor/apex/main.py')}
    rows=[];records=[]
    for seed in args.seeds:
        for opponent,opp_spec in opponents.items():
            if args.opponent and opponent not in args.opponent: continue
            for player in dict.fromkeys(args.seats):
                capture={};trace=[]
                def observed_interpreter(states,env):
                    initialized=bool(states[0].observation.get('farms'))
                    if initialized:
                        step=int(states[0].observation.get('step',0))
                        actions=copy.deepcopy([s.action for s in states])
                        if step==env.configuration.episodeSteps-2:
                            capture['states'],capture['env']=copy.deepcopy((states,env))
                    output=original_interpreter(states,env)
                    if initialized:
                        trace.append({'step':step,'actions':actions,
                                      'bank':[f['money'] for f in states[0].observation.farms]})
                    return output
                engine.interpreter=observed_interpreter
                specs=[opp_spec,opp_spec];specs[player]=candidate
                result=ev.play(engine,specs,args.engine_dir,ev.LOADER,seed,player)
                engine.interpreter=original_interpreter
                row={'seed':seed,'player':player,'opponent':opponent,'original_run':result}
                record={'seed':seed,'player':player,'opponent':opponent,'trace':trace}
                if result['status']=='complete' and capture:
                    states,env=capture['states'],capture['env']
                    observation=copy.deepcopy(states[player].observation)
                    selected=copy.deepcopy(states[player].action)
                    # Actual rival action/private state is NOT passed to the policy.
                    source_sc=sale_stress(observation,env.configuration,engine.PRODUCTS)
                    action,report=optimize_terminal_admission(engine,observation,env.configuration,
                        selected,source_sc,max_states=32,max_candidates=32,time_budget_s=.15)
                    outcomes={}
                    for label,choice in [('original',selected),
                            ('liquidation',report.get('same_workers_liquidation_action',selected)),
                            ('admission',action)]:
                        trial,e=copy.deepcopy((states,env));trial[player].action=choice
                        original_interpreter(trial,e)
                        if not all(s.status=='DONE' for s in trial):raise AssertionError('terminal branch did not finish')
                        outcomes[label]={'own':trial[player].reward,'rival':trial[1-player].reward,
                                         'margin':trial[player].reward-trial[1-player].reward}
                    expected=[outcomes['original']['own'],outcomes['original']['rival']]
                    if expected != [result['scores'][player],result['scores'][1-player]]:
                        raise AssertionError('original terminal branch drift')
                    row.update(outcomes=outcomes,report=report)
                    record.update(final_states=states,final_env=env,selected_action=action,report=report)
                rows.append(row);records.append(record)
                print(json.dumps({'seed':seed,'player':player,'opponent':opponent,
                    'status':result['status'],'changed':row.get('report',{}).get('changed'),
                    'reason':row.get('report',{}).get('reason'),
                    'outcomes':row.get('outcomes'),'elapsed_s':row.get('report',{}).get('elapsed_s')}),flush=True)
                args.out.mkdir(parents=True,exist_ok=True)
                (args.out/'games.json').write_text(json.dumps(rows,indent=2)+'\n')
                packed=gzip.compress(json.dumps(records,separators=(',',':')).encode(),mtime=0)
                (args.out/'traces.json.gz').write_bytes(packed)
    summary={'kind':'new development; exact shared prefix with terminal-only branches',
             'engine_hashes':hashes,'candidate':candidate_identity,'seeds':args.seeds,'seats':args.seats,'games':len(rows),
             'complete':sum(r['original_run']['status']=='complete' for r in rows),
             'changed':sum(r.get('report',{}).get('changed',False) for r in rows),
             'budget_exhausted':sum(r.get('report',{}).get('budget_exhausted',False) for r in rows),
             'trace_sha256':hashlib.sha256((args.out/'traces.json.gz').read_bytes()).hexdigest(),
             'source_sha256':hashlib.sha256(Path(__file__).with_name('terminal_admission.py').read_bytes()).hexdigest()}
    for arm in ['original','liquidation','admission']:
        vals=[r['outcomes'][arm] for r in rows if 'outcomes' in r]
        summary[arm]={'wins':sum(v['margin']>0 for v in vals),'ties':sum(v['margin']==0 for v in vals),
                      'losses':sum(v['margin']<0 for v in vals),
                      'mean_own':sum(v['own'] for v in vals)/len(vals) if vals else None}
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
