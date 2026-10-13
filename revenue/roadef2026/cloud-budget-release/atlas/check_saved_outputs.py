#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Official-checker comparison of saved constructed invariant inputs/outputs only."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from test_native_invariants import budget_usage


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checker',type=Path,required=True)
    p.add_argument('--evidence-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    cases=sorted(args.evidence_dir.glob('case-*'))
    if not cases:raise ValueError('no saved fixture cases')
    results=[]
    for case in cases:
        row={}; destination=args.output/case.name;destination.mkdir()
        for name in ('incumbent','output'):
            command=[str(args.checker.resolve()),'--net',str(case/'net.json'),
                     '--tm',str(case/'tm.json'),'--scenario',str(case/'scenario.json'),
                     '--srpaths',str(case/(name+'.json'))]
            run=subprocess.run(command,capture_output=True,timeout=15)
            (destination/(name+'.stdout.json')).write_bytes(run.stdout)
            (destination/(name+'.stderr.log')).write_bytes(run.stderr)
            if run.returncode:raise RuntimeError(f'checker failed: {case.name} / {name}')
            value=json.loads(run.stdout)
            if value.get('valid') is not True:raise ValueError(f'invalid fixture route: {case.name} / {name}')
            row[name]=value
        before,after=row['incumbent'],row['output']
        def saturation(r):
            result={(s['t'],s['from'],s['to']):s['sat'] for s in r['saturations']}
            if len(result)!=len(r['saturations']):raise ValueError('duplicate saturation key')
            return result
        if saturation(before)!=saturation(after) or before['objectives']!=after['objectives']:
            raise ValueError('official load/objective output changed')
        tm=json.loads((case/'tm.json').read_bytes())
        old=budget_usage(tm,json.loads((case/'incumbent.json').read_bytes()))
        new=budget_usage(tm,json.loads((case/'output.json').read_bytes()))
        if before['total_cost']!=sum(old) or after['total_cost']!=sum(new):
            raise ValueError('official transition total differs from segment-set oracle')
        if any(b>a for a,b in zip(old,new)):raise ValueError('individual boundary increased')
        results.append(dict(case=case.name,budget_before=old,budget_after=new,
            exact_saturations_equal=True,objectives_equal=True,
            checker_before_sha256=sha(destination/'incumbent.stdout.json'),
            checker_after_sha256=sha(destination/'output.stdout.json'),
            inputs={name:sha(case/(name+'.json')) for name in ('net','tm','scenario','incumbent','output')}))
    report=dict(schema='roadef.atlas-date-official-invariants.v1',successful=True,
        checker_sha256=sha(args.checker),case_count=len(results),checker_invocations=2*len(results),
        cases_with_budget_release=sum(r['budget_after']!=r['budget_before'] for r in results),
        total_released=sum(sum(r['budget_before'])-sum(r['budget_after']) for r in results),
        cases=results,scope='saved constructed invariant fixtures only; no search/contest instance/strength measurement')
    (args.output/'summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'},indent=2))
if __name__=='__main__':main()
