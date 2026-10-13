# SPDX-License-Identifier: Apache-2.0
"""Real-process missing/changed dependency and non-overwrite gate controls."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=None
COUNTS={'missing_input_rejections':0,'changed_input_rejections':0,'real_cli_processes':0}


def run(*args):
    COUNTS['real_cli_processes']+=1
    optimization=['-O'] if not __debug__ else []
    return subprocess.run([sys.executable,*optimization,*map(str,args)],
                          capture_output=True,text=True,timeout=45)


class GateCLI(unittest.TestCase):
    def test_required_input_rejections(self):
        names=['SOURCE.json','frozen_selected.py','scheduler.py','mechanics.py',
               'checks/reference/engine/kaggriculture.py',
               'checks/reference/evaluator/loader.py']
        with tempfile.TemporaryDirectory(prefix='funding-input-controls-') as directory:
            target=Path(directory)/'runtime'
            shutil.copytree(ROOT,target)
            for name in names:
                path=target/name;original=path.read_bytes()
                for mode in ('missing','changed'):
                    if mode=='missing':path.unlink()
                    else:path.write_bytes(original+b'\n# input custody poison\n')
                    result=run(HERE/'check_funding_replay.py','--runtime',target)
                    self.assertNotEqual(result.returncode,0,(name,mode,result.stdout))
                    self.assertIn('missing or changed',result.stderr)
                    self.assertNotIn('test_01_',result.stderr)
                    COUNTS[mode+'_input_rejections']+=1
                    path.write_bytes(original)

    def test_in_place_source_write_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.py';source.write_bytes((ROOT/'frozen_selected.py').read_bytes())
            before=source.read_bytes()
            result=run(HERE/'apply_funding_replay.py',source,source)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('separate composition output',result.stderr)
            self.assertEqual(source.read_bytes(),before)

    def test_changed_input_never_overwrites_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.py';output=Path(directory)/'result.py'
            source.write_text((ROOT/'frozen_selected.py').read_text().replace(
                '    original=copy.deepcopy(orders)','    original=list(orders)',1))
            output.write_text('sentinel\n')
            result=run(HERE/'apply_funding_replay.py',source,output)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('funding source changed',result.stderr)
            self.assertEqual(output.read_text(),'sentinel\n')

    def test_valid_output_and_idempotent_second_pass(self):
        pins=json.loads((HERE/'INPUTS.json').read_text())
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            first=Path(directory)/'first.py';second=Path(directory)/'second.py'
            for source,target in ((ROOT/'frozen_selected.py',first),(first,second)):
                result=run(HERE/'apply_funding_replay.py',source,target)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),pins['composed_sha256'])
            self.assertEqual(first.read_bytes(),second.read_bytes())


def main():
    global ROOT
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path)
    args=p.parse_args();ROOT=args.runtime.resolve()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(GateCLI)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    COUNTS.update(tests=result.testsRun,success=result.wasSuccessful(),optimized=not __debug__)
    text=json.dumps(COUNTS,indent=2,sort_keys=True)+'\n'
    if args.output:args.output.write_text(text)
    print(text)
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':main()
