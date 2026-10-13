# SPDX-License-Identifier: Apache-2.0
"""Deliberately broken ledgers must fail assertions, not crash or skip tests."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
MUTANTS={
 'phantom_hire':("len(farm['hands']) > before['hands']", 'True'),
 'requested_is_filled':("row['status'] = (", "row['filled'] = row['requested'] or 0\n            row['status'] = ("),
 'erase_raw_position':("'slot': slot, 'raw':", "'slot': 0, 'raw':"),
 'erase_failed_attempt':("row['attempts'] += 1", "row['attempts'] += int(filled)"),
 'invert_cash_and_counts':("result[key] = after[key] - value", "result[key] = value - after[key]"),
 'zero_cost_hire_is_failure':("len(farm['hands']) > before['hands']", "farm['money'] < before['cash']"),
 'floor_sale_supplies_market':("delta = _delta(before, self._snap(seat))", "delta = _delta(before, self._snap(seat))\n        if filled and price == 1 and row['parsed']['type'] == 'SELL':\n            delta['market'][row['parsed']['item']] = 1"),
 'discard_market_hand_counts':("totals = [_empty_delta(), _empty_delta()]", "for row in rows:\n            row['delta']['hands'] = 0\n        totals = [_empty_delta(), _empty_delta()]"),
 'skip_full_state_parity':("if baseline != candidate or env_b != env_c:", 'if False:'),
}

def run():
    source=(HERE/'realized_market_ledger.py').read_text()
    results=[]
    harness="""import json,unittest
import test_realized_market_ledger as t
suite=unittest.defaultTestLoader.loadTestsFromTestCase(t.LedgerTests)
r=unittest.TextTestRunner(verbosity=0).run(suite)
print(json.dumps({'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped)}))
"""
    for name,(before,after) in MUTANTS.items():
        if source.count(before)!=1: raise ValueError(f'ambiguous mutant {name}')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'realized_market_ledger.py').write_text(source.replace(before,after))
            shutil.copyfile(HERE/'test_realized_market_ledger.py',root/'test_realized_market_ledger.py')
            cmd=[sys.executable]+(['-O'] if not __debug__ else [])+['-B','-c',harness]
            done=subprocess.run(cmd,cwd=root,env=os.environ.copy(),text=True,capture_output=True,timeout=20)
            if done.returncode: raise RuntimeError(f'mutant process error: {name}: {done.stderr[-500:]}')
            result=json.loads(done.stdout.strip().splitlines()[-1])
            if result['tests']!=21 or result['failures']<1 or result['errors'] or result['skipped']:
                raise AssertionError(f'mutant not assertion-rejected: {name}: {result}\n{done.stderr[-2000:]}')
            result['name']=name; results.append(result)
    print(json.dumps({'mode':'normal' if __debug__ else 'optimized','rejected':results},indent=2))

if __name__=='__main__': run()
