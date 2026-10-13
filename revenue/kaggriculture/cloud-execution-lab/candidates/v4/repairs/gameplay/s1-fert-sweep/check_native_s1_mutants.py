# SPDX-License-Identifier: Apache-2.0
"""Run real S1 behavioral controls; errors are not accepted as mutation kills."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
MUTATIONS = {
    'truncated-day-admitted': ("len(tape) < end", "len(tape) <= step"),
    'ignore-alternative-routes': ("for tape in tapes:\n", "for tape in tapes[:1]:\n"),
    'cardinality-only-hire': ("farm['hires_today'] == p.hires_today+1", "True"),
    'short-vector-shift': ("max(0, index-len(rows))", "0"),
    'ghost-vector-truncation': ("rows = result.get('hands', [])", "rows = result.get('hands', [])\n    if isinstance(rows, list): rows = rows[:index]"),
    'wrong-private-actor': ("del result['private']['inventories'][index+1]", "del result['private']['inventories'][index]"),
    'headroom-bypass': ("if total+n > 88:", "if False:"),
    'steal-dynamic-parent-fertilizer': ("command = ['PASS']  # Dynamic native collectors keep first claim.", "command = command  # deliberately broken"),
    'request-is-hire-credit': ("self.report['admissions'] += 1", "self.report['admissions'] += 1\n        self.report['confirmed_hires'] += 1"),
    'se-worker-territory': ("if x >= 5 and y >= 5:", "if False:"),
}


def run(tmp, optimized):
    cmd = [sys.executable]+(['-O'] if optimized else [])+[str(tmp/'test_native_s1_experiment.py')]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=tmp,
                            env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'})
    try:
        data = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError('test process did not return its execution receipt\n'+result.stderr) from exc
    data['returncode'] = result.returncode
    data['stdout_sha256'] = hashlib.sha256(result.stdout.encode()).hexdigest()
    data['stderr_sha256'] = hashlib.sha256(result.stderr.encode()).hexdigest()
    data['failed_test_names'] = [line for line in result.stderr.splitlines() if line.startswith('FAIL:')]
    return data


def main(out):
    original=(HERE/'native_s1_experiment.py').read_text()
    result={'method':'isolated processes; all controls executed; only assertion failures count',
            'source_sha256':hashlib.sha256(original.encode()).hexdigest(),'modes':{}}
    with tempfile.TemporaryDirectory(prefix='s1-mutants-') as td:
        tmp=Path(td)
        for name in ('run_native_experiment.py','test_native_s1_experiment.py'):
            (tmp/name).write_bytes((HERE/name).read_bytes())
        for optimized in (False,True):
            mode='optimized' if optimized else 'normal'
            path=tmp/'native_s1_experiment.py';path.write_text(original)
            control=run(tmp,optimized)
            if control['returncode'] or control['tests']!=28 or any(control[k] for k in ('errors','failures','skips')):
                raise RuntimeError(('control failed',mode,control))
            rows={}
            for name,(before,after) in MUTATIONS.items():
                if original.count(before)!=1:
                    raise ValueError('source mutation anchor drift: '+name)
                path.write_text(original.replace(before,after))
                row=run(tmp,optimized)
                if row['returncode']==0 or row['tests']!=28 or row['failures']==0 or row['errors'] or row['skips']:
                    raise RuntimeError(('nonbehavioral rejection or survivor',mode,name,row))
                rows[name]=row
            result['modes'][mode]={'control':control,'mutants':rows}
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({mode:{'tests':v['control']['tests'],'assertion_rejected':len(v['mutants'])}
                      for mode,v in result['modes'].items()},sort_keys=True))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    main(args.out)
