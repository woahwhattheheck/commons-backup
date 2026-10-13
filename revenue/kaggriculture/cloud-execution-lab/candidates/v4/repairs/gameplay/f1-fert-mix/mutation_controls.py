# SPDX-License-Identifier: Apache-2.0
"""Isolated behavioral negative controls; assertion failures only earn credit."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

MUTANTS = {
    'tail_boundary': ('if prefix <= room_upper:', 'if prefix < room_upper:'),
    'ignore_sell_space': ('release += quantity', 'release += 0'),
    'compact_raw_slots': ('for order in orders[:max_orders]:',
                          'for order in [o for o in orders if o][:max_orders]:'),
    'sort_inventory_keys': ('for key, value in inv.items():\n            prefix += value',
                            'for key, value in sorted(inv.items()):\n            prefix += value'),
    'ignore_prior_workers': ('prefix = sum(sum(v.values()) for v in inventories[:actor])',
                             'prefix = 0'),
    'skip_unit_collateral': ('if arm_farm != expected_farm or arm_private != expected_private:',
                             'if False:'),
    'leave_stale_snapshot': ('return arm, snapshot', 'return arm, post'),
    'reject_ignored_actors': ("if len(private['inventories']) != len(positions):",
                              "if len(commands) > len(positions) or len(private['inventories']) != len(positions):"),
}


def run(native, output):
    root=Path(__file__).resolve().parent
    original=(root/'f1_spill.py').read_text()
    receipts=[]
    with tempfile.TemporaryDirectory(prefix='f1-negative-') as temp:
        target=Path(temp)
        for name in ('test_f1_spill.py','compose_native.py'):
            shutil.copyfile(root/name,target/name)
        for label,(old,new) in MUTANTS.items():
            if original.count(old)!=1:
                raise ValueError('ambiguous mutation: '+label)
            text=original.replace(old,new,1)
            compile(text,'f1_spill.py','exec')
            (target/'f1_spill.py').write_text(text)
            for optimized in (False,True):
                command=[sys.executable,'-B']+(['-O'] if optimized else [])+[
                    str(target/'test_f1_spill.py'),'--native',str(Path(native).resolve())]
                completed=subprocess.run(command,capture_output=True,text=True,timeout=45)
                log=completed.stdout+completed.stderr
                failures=[line for line in log.splitlines() if line.startswith('FAIL: ')]
                errors=[line for line in log.splitlines() if line.startswith('ERROR: ')]
                caught=completed.returncode==1 and bool(failures) and not errors
                receipts.append({'mutant':label,'optimized':optimized,'caught_by_assertion':caught,
                                 'returncode':completed.returncode,'failures':failures,'errors':errors,
                                 'log_sha256':hashlib.sha256(log.encode()).hexdigest()})
                if not caught:
                    raise AssertionError(label+' did not fail behaviorally: '+log)
    output=Path(output);output.write_text(json.dumps(receipts,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'variants':len(MUTANTS),'modes':2,'behavioral_rejections':len(receipts)}))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--native',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    run(args.native,args.output)
