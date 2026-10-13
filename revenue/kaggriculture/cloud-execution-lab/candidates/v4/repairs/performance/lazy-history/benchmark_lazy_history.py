# SPDX-License-Identifier: Apache-2.0
"""Paired cold native initialization/entrypoint timings; no strength claim."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile

from build_lazy_history import compose

CHILD = r'''
import sys,json,time,importlib.util
from pathlib import Path
root=Path(sys.argv[1]); mode=sys.argv[2]
sys.dont_write_bytecode=True
sys.path.insert(0,str(root))
packet=json.loads(Path(sys.argv[3]).read_text())
t0=time.perf_counter(); c0=time.process_time()
import main
if mode=='init':
    actor=main._new_instance(root,json.loads((root/'TITAN-CONFIG.json').read_text()))
    actor._initialize()
    output={'route':actor.controller.cur,'ready':actor.ready}
    status='completed'
else:
    output=main.agent(packet['observation'],packet['configuration'])
    status=main._INSTANCE.diagnostics.get('status') if main._INSTANCE else 'no-instance'
wall=time.perf_counter()-t0; cpu=time.process_time()-c0
print(json.dumps({'wall_seconds':wall,'cpu_seconds':cpu,'output':output,'status':status}))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--pairs',type=int,default=12)
    parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args()
    if not 2<=args.pairs<=30:
        parser.error('choose 2..30 foreground paired runs')
    root=args.runtime.resolve()
    sys.path[:0]=[str(root),str(root/'checks')]
    from test_ordered_selected_sell import OrderedSelectedSellTests
    OrderedSelectedSellTests.setUpClass()
    obs,cfg,_state,_env=OrderedSelectedSellTests().fixture(0)
    results={}
    with tempfile.TemporaryDirectory(prefix='titan-lazy-history-') as temporary:
        temporary=Path(temporary)
        paths={name:temporary/name for name in ('eager','lazy')}
        for path in paths.values():
            shutil.copytree(root,path,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        target=paths['lazy']/'terminal_history_join.py'
        target.write_text(compose(target.read_text()))
        fixture=temporary/'constructed_step0.json'
        fixture.write_text(json.dumps({'observation':obs,'configuration':cfg}))
        for mode in ('init','entrypoint'):
            rows=[]
            for pair in range(args.pairs):
                order=('eager','lazy') if pair%2==0 else ('lazy','eager')
                result={}
                for variant in order:
                    process=subprocess.run([sys.executable,'-B','-c',CHILD,
                        str(paths[variant]),mode,str(fixture)],check=True,capture_output=True,
                        text=True,timeout=10,
                        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0'})
                    result[variant]=json.loads(process.stdout)
                if result['eager']['output']!=result['lazy']['output']:
                    raise RuntimeError('returned output mismatch in paired cold run')
                if any(row['status']!='completed' for row in result.values()):
                    raise RuntimeError('deadline fallback invalidates cold timing comparison')
                rows.append(result)
            summary={}
            for clock in ('wall_seconds','cpu_seconds'):
                medians={variant:statistics.median(row[variant][clock] for row in rows)
                         for variant in ('eager','lazy')}
                summary[clock]={**medians,'speedup':medians['eager']/medians['lazy'],
                    'saved_fraction':1-medians['lazy']/medians['eager'],
                    'paired_saved_median':statistics.median(row['eager'][clock]-row['lazy'][clock] for row in rows)}
            results[mode]={'pairs':args.pairs,'summary':summary,'rows':rows}
    receipt={'python':sys.version,'modes':results,'bytecode_cache':'absent; -B in each fresh interpreter',
        'fixture':'constructed official step-0 rich-state fixture; not a natural opening distribution',
        'limits':'Local paired microbenchmark; no full games, leaderboard, EV, loaded-worker or deadline-rate claim.',
        'full_games':0,'production_changed':False}
    args.receipt.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({mode:row['summary'] for mode,row in results.items()},indent=2))


if __name__=='__main__':
    main()
