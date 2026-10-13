# SPDX-License-Identifier: Apache-2.0
"""Alternating-order, fresh-model benchmark; not a whole-agent deadline test."""
import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import time

from test_score_schedule import core, compile_policy, original_scores, table_case


def benchmark(repeats=16):
    rows=[]
    for task in ('table','optimizer'):
        for quantity in (2,20,100):
            args,plans,streams=table_case(quantity)
            options=dict(item='EGG',quantity=quantity,inventory=9998,params=None,
                         shops=['BAKERY','BRUNCH_SPOT'],config={},now=241,
                         dates=[241,242,245,249],reference=((241,quantity),),rival_quantity=quantity)
            def execute():
                if task=='table':
                    return compile_policy(core.MarketPath(**args),plans,quantity,streams,242,core.absorption)
                return core.optimize_lot(**options)
            times={'reference':[],'candidate':[]}
            for attempt in range(repeats):
                order=('reference','candidate') if attempt%2==0 else ('candidate','reference')
                answers={}
                for arm in order:
                    gc.collect()
                    with original_scores() if arm=='reference' else nullcontext():
                        start=time.perf_counter_ns();answers[arm]=execute()
                        elapsed=time.perf_counter_ns()-start
                    times[arm].append(elapsed)
                if answers['reference']!=answers['candidate']:
                    raise AssertionError(f'Decision mismatch: {task}/{quantity}/{attempt}')
            old=statistics.median(times['reference']);new=statistics.median(times['candidate'])
            rows.append(dict(task=task,quantity=quantity,plans=len(plans) if task=='table' else answers['candidate'][1]['plans_evaluated'],
                             samples_ns=times,reference_median_ns=old,candidate_median_ns=new,
                             speedup=old/new,time_reduction_fraction=1-new/old,all_outputs_equal=True))
    here=Path(__file__).resolve().parent
    paths=[Path(core.__file__),here/'test_score_schedule.py',Path(__file__),
           here.parent/'cloud-market-game-theory/adaptive/recourse.py',here/'mechanics.py',here/'reference/decision/decision.py']
    return dict(schema='titan.score-schedule-benchmark.v1',created_utc=datetime.now(timezone.utc).isoformat(),
                python=platform.python_version(),platform=platform.platform(),visible_cpus=os.cpu_count(),
                cgroup_cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip() if Path('/sys/fs/cgroup/cpu.max').exists() else None,
                source_sha256={str(p.relative_to(here.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                original_core_blob='a743f3b2c1bd4a78cab7b84e5ec9668874116a83',
                repetitions=repeats,method='Alternating order; fresh model each sample; imports and pre-sample gc excluded; wall time.',
                scope='Constructed exact-model calls, not reached/full-agent/held timing; no game seeds consumed.',rows=rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats',type=int,default=16)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.repeats<2:parser.error('At least two alternating samples are required')
    report=benchmark(args.repeats)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    for row in report['rows']:
        print(f"{row['task']:9s} q={row['quantity']:3d}: {row['reference_median_ns']/1e6:.3f} -> {row['candidate_median_ns']/1e6:.3f} ms; {row['speedup']:.3f}x")
