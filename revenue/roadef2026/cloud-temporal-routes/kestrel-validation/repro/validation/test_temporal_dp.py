#!/usr/bin/env python3
"""Exhaustive independent finite-pool controls for the compiled production DP."""
from __future__ import annotations
import argparse
import itertools
import json
from pathlib import Path
import random
import subprocess
import time


def cases(seed=41821, n=4000):
    rng = random.Random(seed)
    result = []
    for _ in range(n):
        t, k, width = rng.randint(1, 5), rng.randint(1, 4), rng.randint(1, 5)
        rows = [[(rng.random() > .2, sorted([rng.randint(0, 25) for _ in range(width)], reverse=True))
                 for _ in range(k)] for _ in range(t)]
        costs = [[0 if a == b else rng.randint(1, 6) for b in range(k)] for a in range(k)]
        budget = [0] + [rng.randint(0, 6) for _ in range(t-1)]
        result.append({'rows': rows, 'costs': costs, 'budget': budget,
                       'cancel_at': -1, 'max_cells': 2000000})
    return result


def exhaustive(c):
    rows, costs, budget = c['rows'], c['costs'], c['budget']
    best, seen = None, 0
    for path in itertools.product(range(len(costs)), repeat=len(rows)):
        seen += 1
        if not all(rows[t][r][0] for t, r in enumerate(path)): continue
        if any(costs[path[t-1]][path[t]] > budget[t] for t in range(1, len(path))): continue
        score = sorted(itertools.chain.from_iterable(rows[t][r][1] for t, r in enumerate(path)), reverse=True)
        if best is None or score < best: best = score
    return best, seen


def encode(bank):
    lines = [str(len(bank))]
    for c in bank:
        rows = c['rows']; t, k, width = len(rows), len(c['costs']), len(rows[0][0][1])
        lines.append(f"{t} {k} {width} {c['cancel_at']} {c['max_cells']}")
        lines.append(' '.join(map(str, c['budget'])))
        for row in c['costs']: lines.append(' '.join(map(str, row)))
        for row in rows:
            for available, values in row:
                lines.append(' '.join(map(str, [int(available), *values])))
    return '\n'.join(lines) + '\n'


def run(binary, bank):
    result = subprocess.run([str(Path(binary).resolve())], input=encode(bank), text=True,
                            capture_output=True, check=True, timeout=30)
    lines = result.stdout.splitlines()
    if len(lines) != len(bank): raise AssertionError('One result required per input')
    return lines


def check(c, line):
    if line == 'error': raise AssertionError('Unexpected invalid input')
    values = list(map(int, line.split())); status, count = values[:2]
    path = values[2:2+count]; width = values[2+count]; score = values[3+count:]
    if len(score) != width: raise AssertionError('Malformed result')
    best, paths = exhaustive(c)
    if best is None:
        assert status == 1 and not path and not score
    else:
        assert status == 0 and len(path) == len(c['rows'])
        assert all(c['rows'][t][r][0] for t,r in enumerate(path))
        assert all(c['costs'][path[t-1]][path[t]] <= c['budget'][t] for t in range(1,len(path)))
        actual = sorted(itertools.chain.from_iterable(c['rows'][t][r][1] for t,r in enumerate(path)), reverse=True)
        assert score == actual == best, (score, best)
    return paths


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--binary',required=True)
    ap.add_argument('--output',type=Path,required=True); args=ap.parse_args()
    start = time.perf_counter(); bank = cases(); results=run(args.binary,bank)
    enumerated=sum(check(c,line) for c,line in zip(bank,results))
    dense = {'rows': [[(True,[k+t,0]) for k in range(4)] for t in range(5)],
             'costs': [[0]*4 for _ in range(4)], 'budget': [0]*5,
             'cancel_at': -1, 'max_cells': 2000000}
    cancellation = [dict(dense,cancel_at=i) for i in (0,1,3,12,23,30,60,85,90)]
    for line in run(args.binary,cancellation):
        assert line == '2 0 0', line
    limited=run(args.binary,[dict(dense,max_cells=0),dict(dense,max_cells=39),
        dict(dense,max_cells=40)])
    assert limited[:2]==['3 0 0','3 0 0']; check(dense,limited[2])
    invalid=[dict(dense,costs=[[-1]*4 for _ in range(4)]),dict(dense,budget=[0,-1,0,0,0]),
             dict(dense,rows=[[(True,[0,1])]*4]*5),dict(dense,rows=[[(True,[1,-1])]*4]*5)]
    assert run(args.binary,invalid)==['error']*4
    report={'finite_pool_cases':len(bank),'enumerated_paths':enumerated,'mismatches':0,
            'cancellation_cases':len(cancellation),'cell_bound_cases':3,'invalid_cases':4,
            'generator_seed':41821,'wall_seconds':time.perf_counter()-start,
            'scope':'Independent exhaustive synthetic finite-pool optimum; not benchmark-network strength'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
