# SPDX-License-Identifier: Apache-2.0
"""Reject broken NATIVE W2 wiring, not duplicate mutations of SECONDHELP policy."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from native_support import sha


def run(package, baseline, manifest, output):
    runtime=(package/'titan_runtime.py').read_text()
    checkpoint="""                    parent_checkpoint = (deepcopy(selected), self.controller.cur)
                    fallback = parent_checkpoint[0]
                    selected_checkpoint = parent_checkpoint
                    self.selected = parent_checkpoint[0]
"""
    variants={
        'disabled_hook':runtime.replace('if self.features.r04_dead_feed_care:', 'if False:'),
        'force_on':runtime.replace('if self.features.r04_dead_feed_care:', 'if True:'),
        'missing_parent_checkpoint':runtime.replace(checkpoint,''),
        'aliased_selected_checkpoint':runtime.replace('self.selected = deepcopy(selected)', 'self.selected = selected'),
        'discard_rewrite':runtime.replace('selected = care.apply_dead_feed_care(', 'discarded = care.apply_dead_feed_care('),
    }
    output.mkdir(parents=True,exist_ok=True)
    results=[]
    for name,text in [('unchanged',runtime),*variants.items()]:
        if name!='unchanged' and text==runtime:
            raise AssertionError('mutation missed its source: '+name)
        with tempfile.TemporaryDirectory(prefix='w2-native-fault-') as tmp:
            dest=Path(tmp)/'native'
            shutil.copytree(package,dest,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            (dest/'titan_runtime.py').write_text(text)
            receipt=output/(name+'.json')
            command=[sys.executable,*(['-O'] if not __debug__ else []),'-B',
                     str(Path(__file__).with_name('check_native.py')),
                     '--package',str(dest),'--baseline',str(baseline),
                     '--manifest',str(manifest),'--runtime-sha256',sha(dest/'titan_runtime.py'),
                     '--output',str(receipt)]
            completed=subprocess.run(command,capture_output=True,text=True,timeout=45)
            (output/(name+'.log')).write_text(completed.stdout+completed.stderr)
            if not receipt.is_file():
                raise AssertionError('runner did not execute: '+name)
            report=json.loads(receipt.read_text())
            if name=='unchanged':
                passed=completed.returncode==0 and report['failures']==report['errors']==report['skips']==0
            else:
                passed=(completed.returncode!=0 and report['failures']>0
                        and report['errors']==0 and report['skips']==0)
            if not passed:
                raise AssertionError('not a clean assertion-rejection/control: '+name+' '+str(report))
            results.append({'variant':name,'returncode':completed.returncode,
                            'tests':report['tests'],'failures':report['failures'],
                            'errors':report['errors'],'native_calls':report['counts']['fixture_native_calls'],
                            'log_sha256':sha(output/(name+'.log'))})
    result={'optimized':not __debug__,'variants':results,'rejected_mutants':len(variants)}
    (output/'SUMMARY.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('package','baseline','manifest','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.package,a.baseline,a.manifest,a.output)
