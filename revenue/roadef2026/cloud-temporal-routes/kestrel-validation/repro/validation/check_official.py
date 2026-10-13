#!/usr/bin/env python3
"""Run the unmodified official checker on a supplied barrier solution, then compare every coordinate."""
from __future__ import annotations
import argparse
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from native_screen import evaluate


def validate(checker: Path, fixture: Path, solution: Path, output: Path) -> dict:
    output.mkdir(parents=True,exist_ok=False)
    net,tm,scenario=[json.loads((fixture/n).read_text()) for n in ('net.json','tm.json','scenario.json')]
    exact=evaluate(net,tm,scenario,json.loads(solution.read_text()))
    evidence=[]
    for places in (6,12):
        command=[str(checker.resolve()),'--net',str((fixture/'net.json').resolve()),'--tm',str((fixture/'tm.json').resolve()),
                 '--scenario',str((fixture/'scenario.json').resolve()),'--srpaths',str(solution.resolve()),
                 '--max-decimal-places',str(places)]
        result=subprocess.run(command,capture_output=True,timeout=30)
        (output/f'checker-{places}.stdout').write_bytes(result.stdout)
        (output/f'checker-{places}.stderr').write_bytes(result.stderr)
        if result.returncode:raise AssertionError(f'Official checker returned {result.returncode}')
        document=json.loads(result.stdout,parse_float=Decimal)
        assert document['valid'] is True
        assert document['total_cost']==sum(exact['used'])
        slots=tm['num_time_slots'];links=net['links'];observed={}
        for row in document['saturations']:
            key=(row['t'],row['from'],row['to']);assert key not in observed
            observed[key]=Decimal(row['sat'])
        assert len(observed)==slots*len(links)
        errors=[]
        for t in range(slots):
            for e,link in enumerate(links):
                reported=observed[t,link['from'],link['to']]
                expected=Decimal(str(exact['loads'][t][e]))
                errors.append(abs(reported-expected))
        tolerance=Decimal(1).scaleb(-places)+Decimal('1e-14')
        assert max(errors,default=Decimal(0))<=tolerance,(places,max(errors))
        vector=sorted((int(x*1000000) for x in observed.values()),reverse=True)
        if places==6:assert vector==exact['vector']
        evidence.append({'decimal_places':places,'valid':True,'coordinates':len(observed),
                         'total_cost':document['total_cost'],'maximum_coordinate_error':str(max(errors)),
                         'six_decimal_vector':vector,'stdout_sha256':sha256(result.stdout).hexdigest(),
                         'returncode':result.returncode,'command':command})
    receipt={'schema':'kestrel.official-barrier-check.v1','checker_binary_sha256':sha256(checker.read_bytes()).hexdigest(),
             'solution_sha256':sha256(solution.read_bytes()).hexdigest(),
             'input_sha256':{n:sha256((fixture/n).read_bytes()).hexdigest() for n in ('net.json','tm.json','scenario.json')},
             'runs':evidence,'all_passed':True,
             'scope':'Official checker1.2.2 on one constructed development fixture; not a set-B or contest-rank result.'}
    (output/'RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checker',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--solution',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(validate(args.checker,args.fixture,args.solution,args.output),indent=2))

if __name__=='__main__':main()
