# SPDX-License-Identifier: Apache-2.0
"""Reproducible isolated behavioral mutation checks for the local oracle only."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from runtime_support import HERE, identity

# Deliberately broken changes to distinct invariants. Never modifies repository
# inputs or the implementation on disk. Each child imports its local mutant.
MUTATIONS = [
 ('paired_only', 'ALIGNMENTS = ("before", "paired", "after")', 'ALIGNMENTS = ("paired",)',
  'OracleTests.test_named_green_witnesses_are_negative'),
 ('whole_budget_pulses_only', 'range(rival_budget - used + 1)', 'sorted({0, rival_budget-used})',
  'OracleTests.test_named_green_witnesses_are_negative'),
 ('reverse_margin_delta', 'delta + (c_cash - c_rival) - (b_cash - b_rival)', 'delta - (c_cash - c_rival) + (b_cash - b_rival)',
  'OracleTests.test_named_green_witnesses_are_negative'),
 ('ignore_carry', "delta += model.single(inv_c, rem_c)[0] - model.single(inv_b, rem_b)[0]", 'delta += 0',
  'OracleTests.test_named_green_witnesses_are_negative'),
 ('omit_town_consumption', 'c_inv - consumption[step], b_inv - consumption[step]', 'c_inv, b_inv',
  'OracleTests.test_named_green_witnesses_are_negative'),
 ('partial_search_false_certificate', 'return Audit(False, None, (), transitions, max_frontier,', 'return Audit(True, 0.0, (), transitions, max_frontier,',
  'OracleTests.test_partial_search_never_certifies'),
 ('disable_optional_screen', 'if not enabled:', 'if True:',
  'AdapterTests.test_reject_counterexamples'),
 ('lose_forced_rescue_exception', 'if not reference_feasible:', 'if False:',
  'AdapterTests.test_physical_reference_infeasible_preserves_original_rescue'),
]

CHILD = '''
from pathlib import Path
import importlib.util, sys, unittest
sys.path.insert(0,sys.argv[1])
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
load(Path(sys.argv[2]),'market_response')
m=load(Path(sys.argv[1])/'test_market_response.py','test_market_response')
suite=unittest.defaultTestLoader.loadTestsFromName(sys.argv[3],m)
r=unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(0 if r.wasSuccessful() else 1)
'''


def main() -> int:
    if not os.environ.get('TITAN_RUNTIME_ROOT'):
        print('TITAN_RUNTIME_ROOT is required',file=sys.stderr);return 2
    source=(HERE/'market_response.py').read_text()
    records=[]
    with tempfile.TemporaryDirectory(prefix='titan-market-mutants-') as t:
        root=Path(t);child=root/'child.py';child.write_text(CHILD)
        # A baseline must pass each targeted assertion; otherwise a failure could
        # merely be an environment or import problem instead of mutation rejection.
        for mode in (0,1):
            for name,old,new,test in MUTATIONS:
                if source.count(old)!=1:
                    raise ValueError(f'Mutation anchor drifted: {name}')
                candidate=root/(name+'.py');candidate.write_text(source.replace(old,new))
                command=[sys.executable,*(['-O'] if mode else []),str(child),str(HERE)]
                baseline=subprocess.run(command+[str(HERE/'market_response.py'),test],capture_output=True,text=True,timeout=15)
                mutant=subprocess.run(command+[str(candidate),test],capture_output=True,text=True,timeout=15)
                # Require an assertion FAILURE, not only an import/syntax ERROR.
                rejected=(baseline.returncode==0 and mutant.returncode==1 and 'FAIL:' in mutant.stderr)
                records.append({'mutation':name,'optimization_mode':mode,'test':test,
                                'baseline_exit':baseline.returncode,'mutant_exit':mutant.returncode,
                                'rejected_by_behavioral_assertion':rejected,
                                'mutant_sha256':identity(candidate)['sha256'],
                                'stdout':mutant.stdout,'stderr':mutant.stderr})
    report={'schema':'titan-market-response-mutations/v1',
            'generated_utc':datetime.now(timezone.utc).isoformat(),
            'source':identity(HERE/'market_response.py'),
            'tests':identity(HERE/'test_market_response.py'),
            'all_rejected':all(r['rejected_by_behavioral_assertion'] for r in records),
            'records':records}
    (HERE/'MUTATIONS.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"Rejected {sum(r['rejected_by_behavioral_assertion'] for r in records)}/{len(records)} mutations across normal/-O")
    return 0 if report['all_rejected'] else 1

if __name__=='__main__':
    raise SystemExit(main())
