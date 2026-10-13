# SPDX-License-Identifier: Apache-2.0
"""Saved-action correspondence and same-input conditional performance comparison.

No new environment seeds or full games. Actor restoration uses prior own/public
observations. Conditional tails use the same existing RILL/T04 evaluation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import random
import re
import statistics
import sys
from time import perf_counter

from state_copy import scheduler_class, fork_scheduler


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def signature(path):
    data=Path(path).read_bytes()
    return {'sha256':hashlib.sha256(data).hexdigest(),'size':len(data),
            'git_blob':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()}


def actor_fields(actor):
    return {**actor.__dict__,'controller':actor.controller.__dict__}


def read_trace(path, seat):
    with gzip.open(path,'rt',encoding='utf-8') as file:
        previous=json.loads(next(file))
        if previous['step']!=-1:raise ValueError('Missing original initialization row')
        for step,line in enumerate(file):
            current=json.loads(line)
            if current['step']!=step:raise ValueError('Non-contiguous original trace')
            observation=deepcopy(previous['observations'][seat])
            observation.update(step=step,remainingOverageTime=0)
            yield step,observation,current['actions'][seat]
            previous=current


def action_correspondence(scheduler,configuration,paths):
    Fast=scheduler_class(scheduler)
    rows=[]
    for path in paths:
        match=re.search(r'-p([01])-frozen_sell_control\.trace\.jsonl\.gz$',path.name)
        if not match:raise ValueError('Supply original frozen-SELL control traces')
        seat=int(match.group(1));random.seed(20260907)
        actor=Fast();digest=hashlib.sha256();count=0;started=perf_counter()
        for step,observation,expected in read_trace(path,seat):
            action=actor.act(observation,configuration)
            if action!=expected:raise AssertionError(f'{path.name}: action differs at{step}')
            digest.update(encoded({'step':step,'action':action})+b'\n');count+=1
        rows.append({'trace':path.name,'source':signature(path),'actions_matched':count,
                     'action_sha256':digest.hexdigest(),'wall_seconds':perf_counter()-started,
                     'seat':seat,'game_panels':0,'interpreter_transitions':0})
    return rows


def compare_tails(actor,observation,cfg,engine,physical,oracle,evaluate,scheduler,*,repeats):
    from functools import partial
    incumbent=actor.controller.cur
    route='7015cc00acfa4922'
    if incumbent==route:raise ValueError('This measurement uses the retained milk-exit577 checkpoint')
    before=deepcopy(actor_fields(actor));before_obs=deepcopy(observation)
    rows=[];reference=None
    for repeat in range(repeats):
        order=('original','copy_variant') if repeat%2==0 else ('copy_variant','original')
        for label in order:
            kwargs={'fork_scheduler':partial(fork_scheduler,scheduler=scheduler)} if label=='copy_variant' else {}
            result=evaluate(actor,(incumbent,route),observation,cfg,engine,
                replay_routes=physical.replay_routes,simulate_bundle=oracle.simulate_bundle,
                scenarios={'known':oracle.Scenario()},end_step=718,
                limits=physical.ReplayLimits(seconds=30,decisions=284),**kwargs)
            if not result['complete']:raise AssertionError('Incomplete timing pair')
            seconds=result['replay'].pop('wall_seconds')
            stable=encoded(result);digest=hashlib.sha256(stable).hexdigest()
            if reference is None:reference=stable
            elif stable!=reference:raise AssertionError('A recorded action/state/cash field changed')
            if actor_fields(actor)!=before or observation!=before_obs:
                raise AssertionError('Timing evaluation changed original inputs')
            rows.append({'repeat':repeat,'variant':label,'seconds':seconds,'result_sha256':digest,
                         'entire_report_equal_excluding_time':True})
    stats={}
    for label in ('original','copy_variant'):
        times=[r['seconds'] for r in rows if r['variant']==label]
        stats[label]={'minimum':min(times),'median':statistics.median(times),'maximum':max(times)}
    stats['median_reduction_fraction']=1-stats['copy_variant']['median']/stats['original']['median']
    return {'measurements':rows,'summary':stats,'original_actor_unchanged':True,'original_input_unchanged':True,
            'source_result':json.loads(reference),'accepted_tail_cases':2*len(rows),
            'scope':'Repeated conditional same-input timings, not independent samples or one-second runtime guarantees'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--value-root',type=Path,default=Path(__file__).resolve().parent.parent/'cloud-late-milk-value')
    p.add_argument('--engine-dir',type=Path,required=True)
    p.add_argument('--rill',type=Path,required=True)
    p.add_argument('--oracle',type=Path,required=True)
    p.add_argument('--trace-dir',type=Path,required=True)
    p.add_argument('--checkpoint-trace',type=Path,required=True)
    p.add_argument('--checkpoint-input',type=Path,required=True)
    p.add_argument('--part',choices=('actions','timing','all'),default='all')
    p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.repeats<1:raise ValueError('At least one timing repetition is required')
    sys.path.insert(0,str(args.value_root))
    from reached_case import load,restore_prefix
    from sell_tail_value import evaluate_sell_tails
    sell=args.source_root/'cloud-titan-composition/vendor/sell'
    sys.path.insert(0,str(sell))
    scheduler=load(sell/'scheduler.py','copy_measure_frozen')
    evaluator=load(args.source_root/'cloud-eval/evaluate.py','copy_measure_evaluator')
    engine,hashes=evaluator.get_engine(args.engine_dir,prepare=False)
    oracle=load(args.oracle,'copy_measure_oracle')
    physical=load(args.rill/'physical_replay.py','copy_measure_physical')
    cfg={k:v.get('default') if isinstance(v,dict) else v for k,v in engine.specification['configuration'].items()}
    cfg['seed']=None
    report={'schema':'titan.sell-state-copy.measurement.v1','sources':{
        'scheduler':signature(sell/'scheduler.py'),'value':signature(args.value_root/'sell_tail_value.py'),
        'physical':signature(args.rill/'physical_replay.py'),'oracle':signature(args.oracle),
        'runtime':signature(Path(__file__).with_name('state_copy.py')),
        'measurement':signature(__file__)},'engine_sha256':hashes,'configuration':cfg,
        'game_panels':0,'new_game_seeds':[]}
    if args.part in ('actions','all'):
        paths=sorted(args.trace_dir.glob('*-frozen_sell_control.trace.jsonl.gz'))
        if not paths:raise ValueError('No saved frozen-SELL control traces')
        report['action_correspondence']=action_correspondence(scheduler,cfg,paths)
    if args.part in ('timing','all'):
        random.seed(20260907);actor=scheduler.SellScheduler()
        observation,restore=restore_prefix(actor,args.checkpoint_trace,cfg)
        expected=json.loads(args.checkpoint_input.read_text())
        if observation!=expected['observation']:raise ValueError('Retained checkpoint mismatch')
        if signature(args.checkpoint_trace)['sha256']!=expected['source_trace_sha256']:
            raise ValueError('Checkpoint source trace mismatch')
        report['restored_prefix']=restore
        report['timing']=compare_tails(actor,observation,cfg,engine,physical,oracle,
                                      evaluate_sell_tails,scheduler,repeats=args.repeats)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(encoded(report)+b'\n')
    summary={'part':args.part,'matched_actions':sum(x['actions_matched'] for x in report.get('action_correspondence',[]))}
    if 'timing' in report:summary['timing']=report['timing']['summary']
    print(json.dumps(summary))


if __name__=='__main__':main()
