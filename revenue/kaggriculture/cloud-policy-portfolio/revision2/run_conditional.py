# SPDX-License-Identifier: Apache-2.0
"""Complete only the frozen intake's selected family/seed pairs."""
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
from run_panel import run_game


if __name__ == '__main__':
    here = Path(__file__).resolve().parent
    intake = json.loads((here/'results/conditional-intake.json').read_text())
    if not intake['complete']:
        raise ValueError('Intake is incomplete')
    out = here/'results/conditional-validation';out.mkdir(exist_ok=True)
    jobs = [(arm,rival,seed,seat,str(out),'validation')
        for rival,seed in intake['selected'].items() for seat in (0,1)
        for arm in ('sell','carrot_sell','staged','economic')]
    rows = []
    with ProcessPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(run_game,job) for job in jobs]):
            row = f.result();rows.append(row)
            print(json.dumps({k:row.get(k) for k in ('id','status','outcome','own_cash','rival_cash','failure')}),flush=True)
    report = {'panel':'conditional_validation','count':len(rows),'games':sorted(rows,key=lambda x:x['id']),
        'complete':all(x['status']=='complete' for x in rows),
        'intake_sha256':hashlib.sha256((here/'results/conditional-intake.json').read_bytes()).hexdigest(),
        'conditional_freeze_sha256':hashlib.sha256((here/'CONDITIONAL-FREEZE.json').read_bytes()).hexdigest(),
        'interpretation':'Source early-YARN condition, not an unconditional population estimate.'}
    (out/'panel.json').write_text(json.dumps(report,indent=2)+'\n')
