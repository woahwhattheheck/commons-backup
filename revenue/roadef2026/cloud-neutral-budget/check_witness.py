#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run three constructed stages and independently check with the official checker.

No public instance or timed benchmark panel is run. DATE's operator is external;
this directory supplies the test input and a consumer of the original kernel.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native(binary: Path, fixture: Path, output: Path, mode: str) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    for key in tuple(env):
        if key.startswith(('SEDGE_', 'FLEET_', 'CLOUD_')): del env[key]
    env.update(SEDGE_SECONDS='60', SEDGE_MAX_ROUNDS='100',
               SEDGE_STATS=str(output/'stats.json'))
    inputs = [fixture/name for name in ('network.json','traffic.json','scenario.json','incumbent.json')]
    command=[str(binary.resolve()), *map(str, inputs), str(output/'solution.json'), mode]
    proc=subprocess.run(command,env=env,capture_output=True,timeout=90)
    (output/'stdout.txt').write_bytes(proc.stdout)
    (output/'stderr.txt').write_bytes(proc.stderr)
    (output/'invocation.json').write_text(json.dumps({'command':command,'exit':proc.returncode,
        'inputs':{p.name:sha(p) for p in inputs},'mode':mode},indent=2)+'\n')
    proc.check_returncode()
    return json.loads((output/'stats.json').read_bytes())


def official(checker: Path, fixture: Path, solution: Path, output: Path, decimals: int):
    command=[str(checker.resolve()), '--net',str(fixture/'network.json'),
             '--tm',str(fixture/'traffic.json'),'--scenario',str(fixture/'scenario.json'),
             '--srpaths',str(solution),'--max-decimal-places',str(decimals)]
    proc=subprocess.run(command,capture_output=True,timeout=30)
    (output/f'checker-{decimals}.json').write_bytes(proc.stdout)
    (output/f'checker-{decimals}.stderr').write_bytes(proc.stderr)
    proc.check_returncode()
    report=json.loads(proc.stdout)
    if report.get('valid') is not True: raise ValueError('Official checker did not validate output')
    return report


def run(binary: Path, checker: Path, output: Path, fixture: Path = HERE/'fixtures') -> dict:
    fixture,output=fixture.resolve(),output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    rows=[]; vectors={}; checked_values=0
    for mode in ('original','release-only','release'):
        folder=output/mode
        stats=native(binary,fixture,folder,mode)
        six=official(checker,fixture,folder/'solution.json',folder,6)
        twelve=official(checker,fixture,folder/'solution.json',folder,12)
        predicted={(x['t'],x['from'],x['to']):x['sat'] for x in stats['loads']}
        actual={(x['t'],x['from'],x['to']):x['sat'] for x in twelve['saturations']}
        if predicted.keys()!=actual.keys(): raise ValueError('Native/checker load identities differ')
        error=max(abs(predicted[k]-actual[k]) for k in predicted)
        if error>2e-9: raise ValueError(f'Native/checker load mismatch: {error}')
        if sum(stats['budget_used'])!=twelve['total_cost']: raise ValueError('Boundary cost mismatch')
        checked_values+=len(actual)
        vectors[mode]=sorted((x['sat'] for x in six['saturations']),reverse=True)
        rows.append({'mode':mode,'peak_6':vectors[mode][0],'budget_used':stats['budget_used'],
                     'total_cost':twelve['total_cost'],'strict_accepts':stats['accepted'],
                     'attempts':stats['attempted'],'max_load_error':error,
                     'native_seconds':stats['seconds'],'solution_sha256':sha(folder/'solution.json')})
    if vectors['original']!=vectors['release-only']: raise ValueError('Neutral stage changed ranked objective')
    if not vectors['release']<vectors['original']: raise ValueError('No unlocked lexicographic improvement')
    if [r['total_cost'] for r in rows]!=[3,0,3]: raise ValueError('Unexpected budget stages')
    if [r['peak_6'] for r in rows]!=[1.6,1.6,1.0]: raise ValueError('Unexpected ranked peaks')
    original=json.loads((output/'original/stats.json').read_bytes())['loads']
    neutral=json.loads((output/'release-only/stats.json').read_bytes())['loads']
    if original!=neutral: raise ValueError('Per-link load vector changed during release')
    report={'scope':'constructed independent official-checker discriminator, not public-instance performance',
            'binary_sha256':sha(binary),'checker_sha256':sha(checker),
            'fixture_sha256':{p.name:sha(p) for p in sorted(fixture.glob('*.json'))},
            'rows':rows,'vectors_6':vectors,'checker_invocations':6,
            'native_checker_load_comparisons_12':checked_values,
            'neutral_link_loads_identical':True,'unlocked_strict_gain':True,
            'budgets_never_exceeded':True,'submission_actions':0}
    (output/'RESULTS.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--checker',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--fixture',type=Path,default=HERE/'fixtures')
    a=p.parse_args();print(json.dumps(run(a.binary,a.checker,a.output,a.fixture),indent=2))
