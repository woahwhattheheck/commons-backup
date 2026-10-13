#!/usr/bin/env python3
"""Run a supplied native solver on the preserved temporal-neighborhood witness.

This is a test consumer, not a solver. It records the actual binary, inputs,
outputs and resource settings and validates with exact rational ECMP.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import time
from native_screen import evaluate


def check(binary: Path, fixture: Path, output: Path, settings: dict[str, str], expect: str) -> dict:
    binary, fixture, output = binary.resolve(), fixture.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    names = ('net.json','tm.json','scenario.json','local-optimum.json','dp-escape.json')
    data = {n: json.loads((fixture/n).read_text()) for n in names}
    old = evaluate(data['net.json'],data['tm.json'],data['scenario.json'],data['local-optimum.json'])
    optimum = evaluate(data['net.json'],data['tm.json'],data['scenario.json'],data['dp-escape.json'])
    settings = {'SEDGE_SECONDS':'30','SEDGE_MAX_ROUNDS':'0',**settings,
                'CLOUD_INITIAL_SOLUTION':str(fixture/'local-optimum.json'),
                'SEDGE_STATS':str(output/'stats.json')}
    env = {k:v for k,v in os.environ.items() if not k.startswith(('SEDGE_','CLOUD_','FLEET_','KESTREL_','DOCK_'))}
    env.update(settings)
    command = [str(binary),*[str(fixture/n) for n in names[:3]],str(output/'solution.json')]
    started = time.perf_counter()
    process = subprocess.run(command, env=env, capture_output=True, timeout=35, check=False)
    elapsed = time.perf_counter()-started
    (output/'stdout.bin').write_bytes(process.stdout)
    (output/'stderr.bin').write_bytes(process.stderr)
    result = {'binary_sha256':sha256(binary.read_bytes()).hexdigest(),'binary':str(binary),
              'input_sha256':{n:sha256((fixture/n).read_bytes()).hexdigest() for n in names},
              'settings':settings,'command':command,'returncode':process.returncode,
              'wall_seconds':elapsed,'expectation':expect,
              'evaluator':'independent Python Fraction ECMP, not official Orange checker'}
    if process.returncode != 0:
        result.update(passed=False,reason='solver_nonzero')
    else:
        try:
            actual_solution = json.loads((output/'solution.json').read_text())
            actual = evaluate(data['net.json'],data['tm.json'],data['scenario.json'],actual_solution)
            stats=json.loads((output/'stats.json').read_text())
            native=[x['sat'] for x in stats['loads']]
            rational=[x for row in actual['loads'] for x in row]
            aligned=(len(native)==len(rational) and all(abs(x-y)<1e-8 for x,y in zip(native,rational)))
            unchanged=actual['vector']==old['vector']
            improved=actual['vector']<old['vector']
            best=actual['vector']==optimum['vector']
            passed=stats['resumed'] and aligned and stats['budget_used']==actual['used']
            passed=passed and {'unchanged':unchanged,'improved':improved,'optimum':best}[expect]
            result.update(passed=bool(passed),source_stats_agree=aligned,resumed=stats['resumed'],
                          incumbent_vector=old['vector'],actual_vector=actual['vector'],
                          expected_optimum_vector=optimum['vector'],budget_used=actual['used'],
                          solution_sha256=sha256((output/'solution.json').read_bytes()).hexdigest(),
                          full_expected_solution=actual_solution==data['dp-escape.json'])
        except (KeyError, ValueError, AssertionError, OSError) as exc:
            result.update(passed=False,reason=type(exc).__name__+': '+str(exc))
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['passed']:
        raise AssertionError('Native barrier expectation failed; see '+str(output/'result.json'))
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--binary',type=Path,required=True)
    ap.add_argument('--fixture',type=Path,default=Path(__file__).resolve().parent/'fixtures/barrier-094-two-segment')
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--env',action='append',default=[],metavar='NAME=VALUE')
    ap.add_argument('--expect',choices=('unchanged','improved','optimum'),default='optimum')
    args=ap.parse_args()
    settings={}
    for setting in args.env:
        k,sep,v=setting.partition('=')
        if not sep or not k or '=' in k or not all(c.isalnum() or c=='_' for c in k):
            ap.error('--env requires NAME=VALUE')
        settings[k]=v
    print(json.dumps(check(args.binary,args.fixture,args.output,settings,args.expect),indent=2))

if __name__=='__main__':main()
