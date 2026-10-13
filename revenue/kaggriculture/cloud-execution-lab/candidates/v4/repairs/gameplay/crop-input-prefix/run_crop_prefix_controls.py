# SPDX-License-Identifier: Apache-2.0
"""Run deliberately broken repairs in isolated processes; require real failures."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

VARIANTS = ('original','wheat_tail','capacity_tail','cap9','cap11',
            'compact','truncate','allow_active_buy')


def run(runtime: Path) -> dict:
    checks=Path(__file__).with_name('check_crop_input_prefix.py')
    rows=[]
    with tempfile.TemporaryDirectory() as temporary:
        for variant in VARIANTS:
            receipt=Path(temporary)/(variant+'.json')
            command=[sys.executable,*(['-O'] if not __debug__ else []),str(checks),
                     '--runtime',str(runtime),'--variant',variant,'--output',str(receipt)]
            result=subprocess.run(command,capture_output=True,text=True,timeout=30)
            if not receipt.exists():
                raise RuntimeError(f'{variant}: no test receipt; not a semantic rejection: {result.stderr[-1000:]}')
            report=json.loads(receipt.read_text())
            # Import/syntax/infrastructure failures are not accepted substitutes
            # for assertion-killed bad logic. Extra assertion subcases are counted
            # separately by unittest but all sixteen test methods must execute.
            killed=(result.returncode==1 and report['tests']==16 and report['failures']>0
                    and not report['passed'] and report['skipped']==0)
            rows.append({'variant':variant,'killed':killed,'returncode':result.returncode,
                         'tests':report['tests'],'assertion_failures':report['failures'],
                         'errors':report['errors'],'test_blob':report['test_blob'],
                         'composer_blob':report['composer_blob']})
            if not killed: raise RuntimeError(f'{variant}: unsound repair survived: {report}')
    return {'optimized':not __debug__,'killed':sum(r['killed'] for r in rows),
            'total':len(rows),'controls':rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run(args.runtime.resolve())
    args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))


if __name__=='__main__': main()
