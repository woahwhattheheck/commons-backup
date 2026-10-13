#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Source-preserving build and finite-width controls; no public-instance runs."""
from __future__ import annotations
import argparse
from copy import deepcopy
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('cedar_builder',ROOT/'build_candidate.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
spec=importlib.util.spec_from_file_location('cedar_native',ROOT/'check_native.py')
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)
A=None
ROWS=[]

class Boundaries(unittest.TestCase):
    def test_01_exact_base_and_additive_source(self):
        raw=A.base_source.read_bytes();generated=B.generate(raw,ROOT)
        self.assertEqual(B.blob(raw),B.BASE_BLOB)
        self.assertEqual(generated,B.generate(raw,ROOT))
        # Every original source line stays in order: only additive code/hook/stat lines.
        ops=difflib.SequenceMatcher(None,raw.splitlines(keepends=True),generated.splitlines(keepends=True),autojunk=False).get_opcodes()
        self.assertFalse(any(tag in ('delete','replace') for tag,*_ in ops))
        self.assertIn(b'!contributing.empty()',generated)

    def test_02_changed_input_is_not_silently_rebound(self):
        with self.assertRaises(ValueError):B.generate(A.base_source.read_bytes()+b'\n',ROOT)

    def test_03_ambiguous_anchor_is_not_patched(self):
        for text in ('nothing','anchor anchor'):
            with self.assertRaises(ValueError):B.once(text,'anchor','replacement')

    def test_04_existing_output_and_base_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'untouched.cpp';target.write_bytes(b'prior-output\n')
            raw=A.base_source.read_bytes()
            r=subprocess.run([sys.executable,str(ROOT/'build_candidate.py'),'--base',str(A.base_source),'--output',str(target)],capture_output=True,timeout=10)
            self.assertNotEqual(r.returncode,0)
            self.assertEqual(target.read_bytes(),b'prior-output\n')
            self.assertEqual(A.base_source.read_bytes(),raw)

    def test_05_zero_trials_and_stop_cannot_report_a_gain(self):
        # The compiled header's distinct controls are run with assertions enabled.
        binary=A.output/'pairs-boundary-unit'
        c=subprocess.run(['g++','-O2','-std=c++20','-Wall','-Wextra','-Werror',str(ROOT/'test_ordered_pairs.cpp'),'-o',str(binary)],capture_output=True,timeout=30)
        self.assertEqual(c.returncode,0,c.stderr.decode(errors='replace'))
        r=subprocess.run([str(binary)],capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr.decode(errors='replace'))
        obj=json.loads(r.stdout);self.assertIs(obj['passed'],True)
        (A.output/'header-properties.json').write_bytes(r.stdout)

    def test_06_large_pool_width_and_work_limits_are_explicit(self):
        folder,paths,_=N.fixture(A.output,'width-limited')
        net=json.loads(paths[0].read_text())
        for node in range(4,40):
            net['nodes'].append({'id':node,'name':f'n{node}'})
            for source,target in ((0,node),(node,0)):
                net['links'].append({'id':len(net['links']),'from':source,'to':target,'metric':100,'capacity':1000})
        N.write(paths[0],net)
        def run(label,binary,width=16,trials=4096,enabled=True):
            output=folder/(label+'.solution.json');stats=folder/(label+'.stats.json')
            env={k:v for k,v in os.environ.items() if not k.startswith(('SEDGE_','FLEET_','CEDAR_','CLOUD_INITIAL_'))}
            env.update(SEDGE_SECONDS='15',SEDGE_MAX_ROUNDS='100',SEDGE_STATS=str(stats),
                       CEDAR_PAIR_WIDTH=str(width),CEDAR_PAIR_TRIALS=str(trials),CEDAR_PAIRS='1' if enabled else '0')
            start=time.perf_counter()
            result=subprocess.run([str(binary),*map(str,paths),str(output)],capture_output=True,env=env,timeout=20)
            elapsed=time.perf_counter()-start
            (folder/(label+'.stderr')).write_bytes(result.stderr)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            checked=subprocess.run([str(A.checker),'--net',str(paths[0]),'--tm',str(paths[1]),'--scenario',str(paths[2]),'--srpaths',str(output)],capture_output=True,timeout=20)
            (folder/(label+'.checker.json')).write_bytes(checked.stdout)
            self.assertEqual(checked.returncode,0,checked.stderr.decode(errors='replace'))
            report=json.loads(checked.stdout);self.assertIs(report['valid'],True)
            s=json.loads(stats.read_text())
            row={'label':label,'width':width,'trials':trials,'solution_sha256':N.digest(output),
                 'vector':N.vector(report),'wall_seconds':elapsed,
                 'pair_checks':s.get('cedar_pair_checks',0),'pair_accepted':s.get('cedar_pair_accepted',0)}
            ROWS.append(row);return row
        baseline=run('baseline',A.baseline)
        narrow=run('width16',A.candidate)
        capped=run('trials1',A.candidate,width=128,trials=1)
        broad=run('width128',A.candidate,width=128)
        disabled=run('disabled',A.candidate,width=128,enabled=False)
        self.assertEqual(narrow['vector'],baseline['vector'])
        self.assertEqual(capped['vector'],baseline['vector'])
        self.assertEqual(disabled['solution_sha256'],baseline['solution_sha256'])
        self.assertLess(broad['vector'],baseline['vector'])
        self.assertGreater(broad['pair_accepted'],0)
        self.assertEqual(broad['vector'][0],100_000)


def main():
    global A
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-source',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--checker',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    A=p.parse_args();A.output.mkdir(parents=True,exist_ok=True)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Boundaries))
    summary={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful(),
             'official_checker_calls':len(ROWS),'cases':ROWS,
             'binaries':{name:N.digest(getattr(A,name)) for name in ('baseline','candidate','checker')},
             'base_blob':B.blob(A.base_source.read_bytes()),'public_instances':0}
    N.write(A.output/'summary.json',summary)
    raise SystemExit(0 if result.wasSuccessful() else 1)
if __name__=='__main__':main()
