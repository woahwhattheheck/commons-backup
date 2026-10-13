# SPDX-License-Identifier: Apache-2.0
"""Run six explicit negative controls against the isolated boundary proof."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
source=(HERE/'check_native_terminal_boundary.py').read_text()
MUTATIONS={
 'last_trial_snapshot':("pair = projections.get(_unit_key(candidate))", "pair = list(projections.values())[-1] if projections else None"),
 'swallow_cancellation':('except Exception:\n            return selected, post','except BaseException:\n            return selected, post'),
 'wrong_seat_snapshot':("matching_post['farms'][seat], matching_post['private']", "matching_post['farms'][1-seat], matching_post['private']"),
 'discard_fresh_post':('returned, post = boundary(self, obs, cfg or {}, returned, post)', 'returned, ignored_post = boundary(self, obs, cfg or {}, returned, post)'),
 'after_receipt_boundary':("SOURCE.replace(ANCHOR, ANCHOR+INSERT, 1)", "SOURCE.replace('        return returned\\n', INSERT+'        return returned\\n', 1)"),
 'enable_default':('project_units: Callable, *, enabled=False','project_units: Callable, *, enabled=True'),
}
results={}
for name,(old,new) in MUTATIONS.items():
    if source.count(old)!=1:
        raise RuntimeError('mutation anchor is not unique: '+name)
    with tempfile.NamedTemporaryFile('w',suffix='.py',prefix='_negative_',dir=HERE,delete=False) as f:
        path=Path(f.name);f.write(source.replace(old,new,1))
    try:
        flags=['-O'] if not __debug__ else []
        r=subprocess.run([sys.executable,*flags,str(path)],text=True,capture_output=True,timeout=30)
        # A broken fixture/import is not a detected semantic regression.
        detected=(r.returncode!=0 and 'Ran 23 tests' in r.stderr
                  and 'FAILED (failures=' in r.stderr)
        results[name]={'exit_code':r.returncode,'detected':detected,
                       'summary':r.stderr[r.stderr.rfind('Ran 23 tests'):].strip()}
    finally:
        path.unlink(missing_ok=True)
print(json.dumps(results,indent=2))
if not all(r['detected'] for r in results.values()):
    raise SystemExit('surviving or invalid negative control')
