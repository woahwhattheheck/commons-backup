#!/usr/bin/env python3
"""Check any implementation's JSONL results against the independent finite-menu bank.

Result rows: {case_id, status, route_indices, descending_loads}. A different
optimal tie path is accepted. Runtime deadlines are tested separately; these
inputs request complete deterministic finite-menu solutions.
"""
from __future__ import annotations
import argparse
import gzip
from hashlib import sha256
import itertools
import json
from pathlib import Path
from typing import Iterable


def read_jsonl(path: Path) -> list[dict]:
    raw = path.read_bytes()
    if path.suffix=='.gz':raw=gzip.decompress(raw)
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def validate(bank: Iterable[dict], outputs: Iterable[dict]) -> dict:
    expected={}
    for row in bank:
        key=row.get('case_id')
        if type(key)is not int or key in expected:raise ValueError('Invalid or repeated input case ID')
        expected[key]=row
    seen=set()
    for output in outputs:
        if not isinstance(output,dict):raise ValueError('Output row must be an object')
        key=output.get('case_id')
        if type(key)is not int or key not in expected or key in seen:
            raise ValueError('Missing, foreign or repeated output case ID')
        seen.add(key);case=expected[key]
        if output.get('status')!=case['expected_status']:raise ValueError(f'Case {key}: status differs')
        path=output.get('route_indices');score=output.get('descending_loads')
        if not isinstance(path,list) or not isinstance(score,list):raise ValueError('Path and score must be lists')
        if case['expected_status']=='infeasible':
            if path or score:raise ValueError('An infeasible result must not expose a chosen path or score')
            continue
        if len(path)!=len(case['available']):raise ValueError(f'Case {key}: wrong horizon')
        k=len(case['transition_costs'])
        if any(type(p)is not int or not 0<=p<k for p in path):raise ValueError('Invalid route index')
        if any(not case['available'][t][p] for t,p in enumerate(path)):raise ValueError('Unavailable route used')
        if any(case['transition_costs'][path[t-1]][path[t]]>case['residual_budgets'][t] for t in range(1,len(path))):
            raise ValueError('A transition exceeds its own residual budget')
        actual=sorted(itertools.chain.from_iterable(case['descending_loads'][t][p] for t,p in enumerate(path)),reverse=True)
        if any(type(x)is not int for x in score):raise ValueError('Score entries must be integers')
        if score!=actual or score!=case['expected_descending_loads']:
            raise ValueError(f'Case {key}: score does not equal the feasible optimum')
    if seen!=set(expected):raise ValueError('One complete result per input case is required')
    return {'cases':len(expected),'matched':len(seen),'mismatches':0,
            'scope':'Exact finite-pool output/path correspondence; not a graph benchmark or whole-solver result.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank',type=Path,required=True)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=validate(read_jsonl(args.bank),read_jsonl(args.results))
    report.update(bank_file_sha256=sha256(args.bank.read_bytes()).hexdigest(),results_file_sha256=sha256(args.results.read_bytes()).hexdigest())
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
