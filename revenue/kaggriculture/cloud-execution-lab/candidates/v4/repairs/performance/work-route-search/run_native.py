# SPDX-License-Identifier: Apache-2.0
"""Source-authenticated four-arm full-game route-search parity, offline only.

Both default config and the pre-existing spatial_pathing=True experiment run
before/after. Does not write to input runtime, archive, workflow or config.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import compose_work_route as composer

# This wrapper calls the unmodified main.py::agent and rejects its fallback.
# Only helper invocation counts and terminal diagnostics are written externally.
WRAPPER = '''import collections,json
from pathlib import Path
import spatial_tempo as spatial
import main as native
COUNTS=collections.Counter()
if hasattr(spatial,'_minimum_work_trial'):
    original=spatial._minimum_work_trial
    def counted(origin,goal,groups,length):
        COUNTS[len(groups)]+=1
        return original(origin,goal,groups,length)
    spatial._minimum_work_trial=counted
else:
    original=spatial.permutations
    def counted(values):
        values=tuple(values);COUNTS[len(values)]+=1
        return original(values)
    spatial.permutations=counted
CALLS=0
EVENTS=0
def agent(observation,configuration=None):
    global CALLS,EVENTS
    action=native.agent(observation,configuration)
    diagnostics=getattr(native._INSTANCE,'diagnostics',{})
    if diagnostics.get('status')!='completed':
        raise RuntimeError('native non-completion: '+str(diagnostics.get('status')))
    CALLS+=1
    EVENTS=len(getattr(getattr(native._INSTANCE,'spatial',None),'events',[]))
    if observation['step']==718:
        Path(__file__).with_name('engagement.json').write_text(json.dumps({'callbacks':CALLS,'searches_by_group_count':dict(COUNTS),'spatial_events_final':EVENTS,'last_status':diagnostics['status']},sort_keys=True))
    return action
'''


def sha(data): return hashlib.sha256(data).hexdigest()

def authenticate(root,manifest):
    records=json.loads(manifest.read_text())['runtime']
    if not records: raise ValueError('empty runtime manifest')
    for name,record in records.items():
        path=(root/name).resolve()
        if not path.is_relative_to(root.resolve()): raise ValueError('outside runtime path')
        data=path.read_bytes()
        if len(data)!=record['bytes'] or sha(data)!=record['sha256']:
            raise ValueError('runtime authentication mismatch: '+name)
    return records


def run(root,manifest,seeds,seats):
    records=authenticate(root,manifest)
    source=(root/'spatial_tempo.py').read_text()
    if composer.blob(source.encode())!=composer.SOURCE_BLOB: raise ValueError('wrong source')
    composed=composer.compose(source)
    eval_path=root/'checks/reference/evaluator/evaluate.py'
    loader=root/'checks/reference/evaluator/loader.py'
    spec=importlib.util.spec_from_file_location('_wayfinder_evaluator',eval_path)
    ev=importlib.util.module_from_spec(spec);spec.loader.exec_module(ev)
    engine,hashes=ev.get_engine(root/'checks/reference/engine',loader)
    report={'python':sys.version,'source_blob':composer.SOURCE_BLOB,'candidate_blob':composer.blob(composed.encode()),
            'manifest_sha256':sha(manifest.read_bytes()),'runtime_members':len(records),
            'evaluator_sha256':sha(eval_path.read_bytes()),'loader_sha256':sha(loader.read_bytes()),
            'engine_sha256':hashes,'wrapper_sha256':sha(WRAPPER.encode()),'seeds':seeds,
            'scope':'Pinned published native artifact; only spatial source delta. Not final composed V4. Default key remains OFF.',
            'games':[],'comparisons':[]}
    with tempfile.TemporaryDirectory(prefix='wayfinder-native-') as temp:
        roots={}
        for enabled in (False,True):
            for changed in (False,True):
                key=('on' if enabled else 'off')+('_candidate' if changed else '_baseline')
                target=Path(temp)/key
                shutil.copytree(root,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
                if changed: (target/'spatial_tempo.py').write_text(composed)
                if enabled:
                    cfg=json.loads((target/'TITAN-CONFIG.json').read_text());cfg['spatial_pathing']=True
                    (target/'TITAN-CONFIG.json').write_text(json.dumps(cfg,indent=2)+'\n')
                (target/'wayfinder_entry.py').write_text(WRAPPER)
                roots[key]=target
        # Pair before/after immediately; alternate execution order by seed/seat.
        for seed in seeds:
            for seat in seats:
                for enabled in (False,True):
                    pair_results={}
                    for changed in ((False,True) if (seeds.index(seed)+seat)%2==0 else (True,False)):
                        key=('on' if enabled else 'off')+('_candidate' if changed else '_baseline')
                        target=roots[key];entry=str(target/'wayfinder_entry.py')
                        specs=[entry,'official_starter'] if seat==0 else ['official_starter',entry]
                        (target/'engagement.json').unlink(missing_ok=True)
                        result=ev.play(engine,specs,root/'checks/reference/engine',loader,seed,seat,
                                       action_timeout=2.,startup_timeout=15.,game_timeout=90.)
                        result['arm']=key
                        if result['status']!='complete' or result['steps']!=719:
                            raise RuntimeError('incomplete game '+json.dumps(result))
                        result['engagement']=json.loads((target/'engagement.json').read_text())
                        if result['engagement']['callbacks']!=719: raise RuntimeError('callback coverage loss')
                        report['games'].append(result);pair_results[changed]=result
                        print(json.dumps({'arm':key,'seed':seed,'seat':seat,'scores':result['scores'],'engagement':result['engagement']}),flush=True)
                    before,after=pair_results[False],pair_results[True]
                    equality={field:before[field]==after[field] for field in ('trace_sha256','scores','daily_bank','engagement')}
                    report['comparisons'].append({'seed':seed,'seat':seat,'pathing':enabled,'equality':equality})
                    if not all(equality.values()): raise RuntimeError('native parity mismatch '+json.dumps(report['comparisons'][-1]))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--seeds',default='2027,6607')
    parser.add_argument('--seats',default='0,1')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();seeds=[int(s) for s in args.seeds.split(',')]
    if not seeds or len(set(seeds))!=len(seeds): raise ValueError('seeds must be nonempty and unique')
    seats=[int(s) for s in args.seats.split(',')]
    if not seats or len(set(seats))!=len(seats) or any(s not in (0,1) for s in seats): raise ValueError('seats must be distinct 0/1')
    result=run(args.root.resolve(),args.manifest.resolve(),seeds,seats)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')

if __name__=='__main__': main()
