# SPDX-License-Identifier: MIT OR CC-BY-4.0
"""Evaluate current-observation fixtures, never feed later replay labels to policy."""
import gzip
import hashlib
import json
from pathlib import Path
import platform
import time
import forecast

HERE=Path(__file__).resolve().parent


def run():
    cases=[]
    for name in ['leader-day9','leader-day17']:
        path=HERE/'fixtures'/f'{name}.json'
        case=json.loads(path.read_text());o=case['observation'];cfg=case['configuration']
        # Candidate planting horizons are derived from public crop first-yield rules;
        # one further action for DROP+SELL assumes an available depot and worker.
        horizons=[o['step'],(o['day']+8)*cfg['turnsPerDay']+1,(o['day']+10)*cfg['turnsPerDay']+1]
        started=time.perf_counter()
        result=forecast.forecast_market(o,cfg,horizons)
        elapsed=time.perf_counter()-started
        cases.append({'case':name,'fixture_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'input_source':case['source'],'horizon_assumption':'hypothetical planting today: first tomato/strawberry event + one DROP/SELL action; not a purchase/plant recommendation',
                      'wall_seconds':elapsed,'result':result})
    report={'python':platform.python_version(),'forecast_sha256':hashlib.sha256((HERE/'forecast.py').read_bytes()).hexdigest(),
            'case_count':len(cases),'games_run':0,'cases':cases}
    (HERE/'results').mkdir(exist_ok=True)
    raw=(json.dumps(report,indent=2,sort_keys=True)+'\n').encode()
    (HERE/'results/actual-state-cases.json.gz').write_bytes(gzip.compress(raw,mtime=0))
    summary={**report,'cases':[{**c,'result':{k:v for k,v in c['result'].items() if k!='crop_witnesses'}} for c in cases]}
    (HERE/'results/summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    for c in cases:
        print(c['case'],f"{c['wall_seconds']:.6f}s")
        for frame in c['result']['frames']:
            print(frame['realization_step'],{p:frame['products'][p]['scenario_price_range'] for p in ('TOMATO','STRAWBERRY')})
    return report


if __name__=='__main__':run()
