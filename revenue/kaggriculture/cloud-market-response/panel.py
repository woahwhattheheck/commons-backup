# SPDX-License-Identifier: MIT
"""Bounded concurrent execution of explicit paired panels. No network or uploads."""
import argparse
import concurrent.futures
import itertools
import json
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--seeds',required=True);p.add_argument('--arms',default='arlene,sell,response')
    p.add_argument('--opponents',default='arlene,apex')
    p.add_argument('--engine-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=2);p.add_argument('--freeze',type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if a.freeze:
        import hashlib
        expected=json.loads(a.freeze.read_text())['runtime']
        for path,digest in expected.items():
            assert hashlib.sha256((HERE/path).read_bytes()).hexdigest()==digest, 'Runtime changed after freeze: '+path
    cases=list(itertools.product(map(int,a.seeds.split(',')),(0,1),a.arms.split(','),a.opponents.split(',')))
    def run(case):
        seed,seat,arm,rival=case;stem=f'{arm}-{rival}-{seed}-{seat}'
        # Never silently treat an old result as this run's frozen execution.
        if (a.output/(stem+'.json')).exists():raise FileExistsError(stem)
        with (a.output/(stem+'.log')).open('w') as log:
            result=subprocess.run([sys.executable,str(HERE/'measure.py'),'--seed',str(seed),'--seat',str(seat),
                '--arm',arm,'--opponent',rival,'--engine-dir',str(a.engine_dir),'--output',str(a.output)],
                stdout=log,stderr=subprocess.STDOUT,timeout=180)
        if result.returncode:raise RuntimeError(stem+' failed; read its log')
        row=json.loads((a.output/(stem+'.json')).read_text())
        print(json.dumps({k:row[k] for k in ('seed','seat','arm','opponent','margin','interventions')}),flush=True)
        return row
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,a.workers)) as pool:rows=list(pool.map(run,cases))
    if a.freeze:
        for path,digest in expected.items():
            assert hashlib.sha256((HERE/path).read_bytes()).hexdigest()==digest, 'Runtime changed during panel: '+path
    (a.output/'panel.json').write_text(json.dumps({'complete':True,'games':len(rows),'cases':[list(c) for c in cases]},indent=2)+'\n')
if __name__=='__main__':main()
