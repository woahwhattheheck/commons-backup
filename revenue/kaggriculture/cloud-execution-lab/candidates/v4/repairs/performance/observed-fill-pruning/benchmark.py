# SPDX-License-Identifier: Apache-2.0
"""Controlled reconciler workload measurements, not game-score evidence."""
from __future__ import annotations

import argparse
import gc
import importlib.util
import json
from pathlib import Path
import statistics
import tempfile
import time

from repair_observed_fill_pruning import repair, git_blob
from test_observed_fill_pruning import case, load_file, semantic


def workload():
    return {
        'unique_two_buys': case(market=[['BUY_PRODUCT','WHEAT',100], ['BUY_PRODUCT','FERTILIZER',100]],
                               after={'WHEAT':50,'FERTILIZER':50}),
        'unique_one_buy': case(market=[['BUY_PRODUCT','WHEAT',100]], after={'WHEAT':50}),
        'unique_three_buys': case(market=[['BUY_PRODUCT','WHEAT',100], ['BUY_PRODUCT','FERTILIZER',100],
                                        ['BUY_ANIMAL','COW',100]], after={'WHEAT':20,'FERTILIZER':30,'COW':50}),
        'genuine_buy_sell_ambiguity': case(market=[['BUY_PRODUCT','WHEAT',100], ['SELL','WHEAT',100]]),
        'sale_only': case(before={'WHEAT':50,'FERTILIZER':50}, market=[['SELL','WHEAT',50],['SELL','FERTILIZER',50]]),
        'saturated_deposit_ambiguity': case(market=[['BUY_PRODUCT','WHEAT',100]], after={'WHEAT':100}, deposits=[{'WHEAT':100}]),
        'both_buys_zero_fill': case(market=[['BUY_PRODUCT','WHEAT',100], ['BUY_PRODUCT','FERTILIZER',100]]),
        'buy_sell_buy_correlated': case(market=[['BUY_PRODUCT','WHEAT',100], ['SELL','WHEAT',50], ['BUY_PRODUCT','FERTILIZER',100]],
                                       after={'WHEAT':20,'FERTILIZER':80}),
    }


def measure(function, data):
    samples=[]
    for _ in range(7):
        start=time.perf_counter_ns()
        for _ in range(20):
            result=function(**data)
        samples.append((time.perf_counter_ns()-start)/20/1000)
    return round(statistics.median(samples),3), result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args()
    source=args.baseline.read_bytes(); output=repair(source)
    rows=[]
    with tempfile.TemporaryDirectory() as work:
        target=Path(work)/'candidate.py'; target.write_bytes(output)
        original=load_file('_bench_original_fills',args.baseline)
        candidate=load_file('_bench_candidate_fills',target)
        was_enabled=gc.isenabled(); gc.disable()
        try:
            for name,data in workload().items():
                old_us,old=measure(original.reconcile_shed_fills,data)
                new_us,new=measure(candidate.reconcile_shed_fills,data)
                if old['status'] in ('reconciled','ambiguous') and semantic(old)!=semantic(new):
                    raise ValueError('semantic regression in '+name)
                rows.append({'workload':name,'input':data,'baseline':old,'candidate':new,
                             'baseline_median_us':old_us,'candidate_median_us':new_us,
                             'baseline_over_candidate_time':round(old_us/new_us,3)})
        finally:
            if was_enabled:gc.enable()
    receipt={'baseline_blob':git_blob(source),'candidate_blob':git_blob(output),'workloads':rows,
             'method':'Median of 7 blocks of 20 calls, garbage collection disabled; this local process only.',
             'boundary':'Synthetic inference workloads. No game, official-interpreter, deadline-SLA, score or leaderboard claim.'}
    args.receipt.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    for r in rows:
        print(r['workload'], r['baseline']['status'],r['baseline'].get('transitions'),
              '->',r['candidate']['status'],r['candidate'].get('transitions'),
              'time ratio',r['baseline_over_candidate_time'])


if __name__=='__main__':main()
