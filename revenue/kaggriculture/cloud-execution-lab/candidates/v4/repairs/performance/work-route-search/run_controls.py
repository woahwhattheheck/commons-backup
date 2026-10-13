# SPDX-License-Identifier: Apache-2.0
"""Run behavioral source mutations; count assertion rejection, never error credit."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import compose_work_route as composer

MUTATIONS = {
    'ignore_goal_cost': ('finish=[distance(p,goal) for p in sites]', 'finish=[0 for p in sites]'),
    'reverse_winner_tie': ('    if cost+sum', '    order=tuple(reversed(order))\n    if cost+sum'),
    'over_budget_one': ('for _,acts in groups)>length:', 'for _,acts in groups)>length+1:'),
    'reverse_site_work': ('trial+=path(q,pos)+acts;q=pos', 'trial+=path(q,pos)+list(reversed(acts));q=pos'),
    'omit_goal_path': ('    trial+=path(q,goal)\n    return trial', '    trial+=[]\n    return trial'),
    'longest_dp_prefix': ('incumbent is None or proposal<incumbent', 'incumbent is None or proposal>incumbent'),
    'bypass_state_veto': ('if saved>0 and self._same_work_state(obs,i,sequence,trial):best=trial', 'if saved>0:best=trial'),
    'excess_padding': ("trial+= [['PASS']]*(length-len(trial))", "trial+= [['PASS']]*(length-len(trial)+1)"),
}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mutants',default=','.join(MUTATIONS))
    args=p.parse_args()
    source=(args.root/'spatial_tempo.py').read_text()
    if composer.blob(source.encode())!=composer.SOURCE_BLOB:
        raise ValueError('unexpected parent source')
    composed=composer.compose(source)
    code="""import json,sys,unittest
import test_work_route
suite=unittest.defaultTestLoader.loadTestsFromModule(test_work_route)
result=unittest.TextTestRunner(verbosity=0).run(suite)
print(json.dumps({'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'failure_tests':[str(t) for t,_ in result.failures]}))
"""
    output={'mode':'optimized' if sys.flags.optimize else 'normal','controls':{},'mutants':{}}
    with tempfile.TemporaryDirectory(prefix='wayfinder-controls-') as tmp:
        for name,replacement in [('unchanged',None),*[(key,MUTATIONS[key]) for key in args.mutants.split(',')]]:
            candidate=composed
            if replacement:
                a,b=replacement
                if candidate.count(a)!=1:
                    raise ValueError('ambiguous mutation '+name)
                candidate=candidate.replace(a,b,1)
            path=Path(tmp)/(name+'.py');path.write_text(candidate)
            env=dict(os.environ,TITAN_ROOT=str(args.root.resolve()),WAYFINDER_CANDIDATE=str(path),PYTHONPATH=str(Path(__file__).resolve().parent))
            result=subprocess.run([sys.executable,*(['-O'] if sys.flags.optimize else []),'-c',code],env=env,capture_output=True,text=True,timeout=45)
            if result.returncode:
                raise RuntimeError(f'{name}: infrastructure error\n'+result.stderr)
            counts=json.loads(result.stdout.strip().splitlines()[-1])
            if counts['errors'] or counts['skipped'] or counts['tests']!=17:
                raise RuntimeError(f'{name}: errors/skips/coverage loss {counts}')
            expected=counts['failures']==0 if replacement is None else counts['failures']>0
            if not expected:
                raise RuntimeError(f'{name}: did not meet discrimination requirement {counts}')
            output['controls' if replacement is None else 'mutants'][name]=counts
            print(name,json.dumps(counts),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2)+'\n')

if __name__=='__main__': main()
