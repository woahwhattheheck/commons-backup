# SPDX-License-Identifier: Apache-2.0
"""Interleaved whole-optimizer timing, including construction and result creation.

Run with TITAN_SIEVE_RUNTIME pointing to the unchanged extracted current archive.
This is a deterministic microbenchmark, not game strength or whole-agent speed.
"""
from __future__ import annotations
import argparse
import gc
import hashlib
import json
import platform
import statistics
import sys
import time
from test_selected_incumbent import ROOT, authenticate, cases, example, load_source
from patch_selected_incumbent import git_blob, transform


def run(rounds=10):
    if rounds < 2:raise ValueError('at least two interleaved rounds required')
    authenticate()
    source=(ROOT/'selected_sell_core.py').read_bytes()
    modules=[load_source(source,'sieve_timing_base'),
             load_source(transform(source),'sieve_timing_candidate')]
    panels={'mixed_160':list(cases(160))}
    panels['high_prune_40']=[example(item='CARROT',quantity=24,inventory=10000,
        shops=list(modules[0].m.SHOPS),now=710,dates=[710,711,713,715],
        reference=((710,19),(715,5)),rival_quantity=0) for _ in range(40)]
    # No opportunity to build a positive incumbent: includes added-bound cost.
    panels['floor_control_160']=[example(item='MILK',quantity=48,inventory=10100,
        shops=[],now=4,dates=[4,5,7],reference=((4,48),),rival_quantity=0)
        for _ in range(160)]
    output={}
    for name,panel in panels.items():
        answers=[[m.optimize_lot(**kw) for kw in panel] for m in modules]
        if answers[0]!=answers[1]:raise RuntimeError('output mismatch in '+name)
        dig=hashlib.sha256(json.dumps(answers[0],sort_keys=True).encode()).hexdigest()
        samples=[[],[]]
        for r in range(rounds):
            for arm in ((0,1) if r%2==0 else (1,0)):
                gc.collect();enabled=gc.isenabled();gc.disable()
                try:
                    start=time.perf_counter()
                    actual=[modules[arm].optimize_lot(**kw) for kw in panel]
                    elapsed=time.perf_counter()-start
                finally:
                    if enabled:gc.enable()
                if actual!=answers[arm]:raise RuntimeError('nonrepeatable results')
                samples[arm].append(elapsed)
        medians=[statistics.median(x) for x in samples]
        output[name]={'input_count':len(panel),'output_sha256':dig,
            'base_seconds':samples[0],'candidate_seconds':samples[1],
            'base_median_seconds':medians[0],'candidate_median_seconds':medians[1],
            'median_ratio_candidate_over_base':medians[1]/medians[0],
            'paired_ratios':[b/a for a,b in zip(*samples)]}
    return {'kind':'interleaved_complete_optimizer_microbenchmark','rounds':rounds,
        'python':sys.version,'platform':platform.platform(),'optimized':not __debug__,
        'source_blob':git_blob(source),'candidate_blob':git_blob(transform(source)),
        'panels':output,'qualification':'Synthetic inputs; no game-strength or full-agent-speed claim.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rounds',type=int,default=10)
    args=p.parse_args();print(json.dumps(run(args.rounds),sort_keys=True))
