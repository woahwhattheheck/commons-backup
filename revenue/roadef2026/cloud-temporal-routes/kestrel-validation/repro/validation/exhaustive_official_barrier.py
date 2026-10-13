#!/usr/bin/env python3
"""Enumerate the entire legal one-waypoint interval neighborhood using Orange's checker.

Also enumerates every complete route schedule for demand zero at the same cap.
The checker is injected as an unchanged existing executable; no search is run.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import subprocess
from native_screen import evaluate
from verify_barrier import solution


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checker',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    net,tm,scenario,incumbent,expected=[json.loads((args.fixture/n).read_text()) for n in
        ('net.json','tm.json','scenario.json','local-optimum.json','dp-escape.json')]
    assert scenario['max_segments']==2
    base=evaluate(net,tm,scenario,incumbent); optimum=evaluate(net,tm,scenario,expected)
    h=tm['num_time_slots']; ids=[n['id'] for n in net['nodes']]
    results=[];counts={'interval':0,'schedule':0};feasible={'interval':0,'schedule':0};improving=[];best=None;best_paths=[]
    def check(kind,choice,routes):
        number=len(results); out=args.output/f'{number:03d}'
        out.mkdir(); proposal=solution(routes)
        (out/'solution.json').write_text(json.dumps(proposal,sort_keys=True)+'\n')
        try:
            rational=evaluate(net,tm,scenario,proposal)
        except (ValueError,AssertionError):rational=None
        command=[str(args.checker.resolve()),'--net',str((args.fixture/'net.json').resolve()),
            '--tm',str((args.fixture/'tm.json').resolve()),'--scenario',str((args.fixture/'scenario.json').resolve()),
            '--srpaths',str((out/'solution.json').resolve()),'--max-decimal-places','6']
        process=subprocess.run(command,capture_output=True,timeout=10)
        (out/'stdout').write_bytes(process.stdout);(out/'stderr').write_bytes(process.stderr)
        observed=json.loads(process.stdout,parse_float=Decimal)
        valid=observed['valid'];assert valid == (rational is not None),(number,'validity mismatch')
        row={'kind':kind,'choice':choice,'valid':valid,'returncode':process.returncode,
            'stdout_sha256':sha256(process.stdout).hexdigest(),
            'solution_sha256':sha256((out/'solution.json').read_bytes()).hexdigest()}
        counts[kind]+=1
        if valid:
            assert process.returncode==0
            feasible[kind]+=1
            vector=sorted((int(Decimal(x['sat'])*1000000) for x in observed['saturations']),reverse=True)
            assert vector==rational['vector'],(number,'vector mismatch')
            assert observed['total_cost']==sum(rational['used']),(number,'cost mismatch')
            row.update(vector=vector,total_cost=observed['total_cost'])
        else:assert process.returncode!=0
        results.append(row)
        return row
    for d,demand in enumerate(tm['demands']):
        pool=[[]]+[[v] for v in ids if v not in (demand['s'],demand['t'])]
        for a in range(h):
            for b in range(a,h):
                for path in pool:
                    routes=deepcopy(base['routes']);routes[d][a:b+1]=[path]*(b-a+1)
                    row=check('interval',[d,a,b,path],routes)
                    if row['valid'] and row['vector']<base['vector']:improving.append(row)
    pool=[[]]+[[v] for v in ids if v not in (tm['demands'][0]['s'],tm['demands'][0]['t'])]
    for path in product(range(len(pool)),repeat=h):
        routes=deepcopy(base['routes']);routes[0]=[pool[k] for k in path]
        row=check('schedule',path,routes)
        if row['valid']:
            if best is None or row['vector']<best:best=row['vector'];best_paths=[path]
            elif row['vector']==best:best_paths.append(path)
    assert not improving
    assert best==optimum['vector']<base['vector']
    report={'schema':'kestrel.official-complete-neighborhood.v1','checker_version':'1.2.2',
        'checker_binary_sha256':sha256(args.checker.read_bytes()).hexdigest(),
        'input_sha256':{n:sha256((args.fixture/n).read_bytes()).hexdigest() for n in ('net.json','tm.json','scenario.json','local-optimum.json','dp-escape.json')},
        'proposal_checks':counts,'feasible_proposals':feasible,'improving_constant_intervals':len(improving),
        'all_complete_optimal_paths':best_paths,'waypoint_pool':pool,
        'incumbent_vector':base['vector'],'best_vector':best,
        'rational_official_validity_vector_cost_mismatches':0,
        'scope':'One constructed cap-two-segment fixture. Complete interval neighborhood, all demands. Complete schedule neighborhood for demand0 only. Not a public-B or joint-demand optimum.'}
    (args.output/'PROPOSALS.json').write_text(json.dumps(results,indent=2)+'\n')
    (args.output/'SUMMARY.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
