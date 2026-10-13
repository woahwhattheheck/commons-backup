# SPDX-License-Identifier: MIT
"""Run the actual benchmark CLI against explicit local protocol fixtures.

No official solver, checker, instance or competition measurement is invoked.
Select a source with --benchmark; all children run in temporary directories.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BENCHMARK = None
REPORT = None
RECORDS = []
SOLVER = r'''#!/usr/bin/env python3
import json,math,os,sys
from pathlib import Path
with Path(os.environ['ARGUMENT_TEST_CALLS']).open('a') as out:
    out.write(json.dumps({'role':'solver','seconds':os.environ['SEDGE_SECONDS'],
        'rounds':os.environ.get('SEDGE_MAX_ROUNDS'),
        'resume':os.environ.get('CLOUD_INITIAL_SOLUTION')})+'\n')
seconds=float(os.environ['SEDGE_SECONDS'])
rounds=float(os.environ.get('SEDGE_MAX_ROUNDS','1000000'))
if not math.isfinite(seconds) or seconds<0 or not math.isfinite(rounds) or rounds<0:
    print('fixture solver: unusable search setting',file=sys.stderr)
    raise SystemExit(64)
Path(sys.argv[-1]).write_text('{"srpaths":[]}\n')
Path(os.environ['SEDGE_STATS']).write_text(json.dumps({'loads':[
    {'t':0,'from':0,'to':1,'sat':0.5}], 'budget_used':[0], 'accepted':0, 'attempted':0}))
'''
CHECKER = r'''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
with Path(os.environ['ARGUMENT_TEST_CALLS']).open('a') as out:
    out.write(json.dumps({'role':'checker','precision':sys.argv[-1]})+'\n')
print(json.dumps({'valid':True,'total_cost':0,'saturations':[
    {'t':0,'from':0,'to':1,'sat':0.5}]}))
'''

class ArgumentTests(unittest.TestCase):
    def setUp(self):
        if BENCHMARK is None:
            self.skipTest('Use --benchmark to select the actual CLI source')
        self.temporary = tempfile.TemporaryDirectory(prefix='roadef-arg-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root/'data'; (self.data/'setB').mkdir(parents=True)
        for suffix in ('net','tm','scenario'):
            (self.data/'setB'/f'setB-01-{suffix}.json').write_text('{}\n')
        self.solver = self.root/'solver'; self.solver.write_text(SOLVER.replace('#!/usr/bin/env python3', '#!' + sys.executable + ' -S', 1)); self.solver.chmod(0o700)
        self.checker = self.root/'checker'; self.checker.write_text(CHECKER.replace('#!/usr/bin/env python3', '#!' + sys.executable + ' -S', 1)); self.checker.chmod(0o700)
        self.calls = self.root/'calls.jsonl'; self.output = self.root/'evidence'
        self.env = dict(os.environ, ARGUMENT_TEST_CALLS=str(self.calls),
                        SEDGE_MAX_ROUNDS='234', CLOUD_INITIAL_SOLUTION='/unused/inherited.json')

    def invoke(self, *flags, output=None, data=True, checker=None, solver=None):
        destination = self.output if output is None else output
        command = [sys.executable,'-B','-S',str(BENCHMARK),'--solver',f'test={solver or self.solver}',
                   '--checker',str(checker or self.checker),'--instances','setB-01',
                   '--output',str(destination)]
        if data: command += ['--data',str(self.data)]
        command += list(flags)
        result = subprocess.run(command,env=self.env,capture_output=True,timeout=10)
        produced = sorted(str(p.relative_to(destination)) for p in destination.rglob('*')) if destination.exists() else []
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        RECORDS.append({'test':self.id().split('.')[-1], 'flags':list(flags),
            'returncode':result.returncode, 'stdout':result.stdout.decode('utf-8','backslashreplace'),
            'stderr':result.stderr.decode('utf-8','backslashreplace'), 'calls':calls,
            'output_entries':produced,'fixture_kind':'synthetic subprocess protocol; no official solver/checker'})
        return result, calls

    def invalid(self, option, value):
        self.calls.unlink(missing_ok=True)
        output=self.root/f'bad-{len(RECORDS)}'
        result,calls=self.invoke(f'{option}={value}',output=output)
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertIn(option.encode(),result.stderr)
        self.assertNotIn(b'Traceback',result.stderr)
        self.assertEqual(calls,[])
        self.assertFalse(output.exists(),RECORDS[-1])

    def valid(self, *flags):
        result,calls=self.invoke(*flags)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual([r['role'] for r in calls],['solver','checker','checker'])
        self.assertEqual([r['precision'] for r in calls if r['role']=='checker'],['6','12'])
        metadata=json.loads((self.output/'summary.json').read_text())
        row=metadata['results'][0][0]
        self.assertTrue(row['valid']); self.assertEqual(row['mlu_6'],0.5)
        self.assertEqual(row['max_load_error'],0); self.assertEqual(row['total_cost'],0)
        return metadata,calls[0]

    def test_seconds_nan_rejected_before_work(self): self.invalid('--seconds','nan')
    def test_seconds_positive_infinity_rejected(self): self.invalid('--seconds','inf')
    def test_seconds_negative_infinity_rejected(self): self.invalid('--seconds','-inf')
    def test_seconds_overflow_to_infinity_rejected(self): self.invalid('--seconds','1e309')
    def test_seconds_negative_rejected(self): self.invalid('--seconds','-1')
    def test_rounds_negative_rejected(self): self.invalid('--rounds','-1')
    def test_workers_zero_rejected(self): self.invalid('--workers','0')
    def test_workers_negative_rejected(self): self.invalid('--workers','-2')

    def test_invalid_settings_precede_input_discovery(self):
        for flag in ('--seconds=nan','--rounds=-1','--workers=0'):
            with self.subTest(flag=flag):
                result,calls=self.invoke(flag,data=False,solver=self.root/'absent-solver',checker=self.root/'absent-checker')
                self.assertEqual(result.returncode,2,result.stderr)
                self.assertIn(flag.split('=')[0].encode(),result.stderr)
                self.assertNotIn(b'Traceback',result.stderr)
                self.assertFalse(self.output.exists()); self.assertEqual(calls,[])

    def test_invalid_settings_preserve_existing_files(self):
        self.output.mkdir(); existing=self.output/'keep.bin'; existing.write_bytes(b'previous\x00result\xff')
        for flag in ('--seconds=nan','--rounds=-1','--workers=0'):
            with self.subTest(flag=flag):
                result,calls=self.invoke(flag)
                self.assertEqual(result.returncode,2,result.stderr)
                self.assertEqual(existing.read_bytes(),b'previous\x00result\xff')
                self.assertEqual(list(self.output.iterdir()),[existing]); self.assertEqual(calls,[])

    def test_same_output_can_be_used_after_rejected_seconds(self):
        result,_=self.invoke('--seconds=nan')
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertFalse(self.output.exists())
        self.valid('--seconds=0','--workers=1')

    def test_same_output_can_be_used_after_rejected_workers(self):
        result,_=self.invoke('--workers=0')
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertFalse(self.output.exists())
        self.valid('--seconds=0','--workers=1')

    def test_default_settings_unchanged(self):
        metadata,call=self.valid()
        self.assertEqual(metadata['seconds_per_solver'],30)
        self.assertEqual(metadata['workers'],2); self.assertIsNone(metadata['rounds'])
        self.assertEqual(call['seconds'],'30'); self.assertIsNone(call['rounds']); self.assertIsNone(call['resume'])

    def test_zero_seconds_preserves_no_search_mode(self):
        metadata,call=self.valid('--seconds=0','--workers=1')
        self.assertEqual(metadata['seconds_per_solver'],0); self.assertEqual(call['seconds'],'0.0')

    def test_negative_zero_seconds_is_valid(self):
        metadata,call=self.valid('--seconds=-0.0')
        self.assertEqual(metadata['seconds_per_solver'],0); self.assertEqual(call['seconds'],'-0.0')

    def test_fractional_seconds_forwarded_unchanged(self):
        metadata,call=self.valid('--seconds=0.125')
        self.assertEqual(metadata['seconds_per_solver'],0.125); self.assertEqual(call['seconds'],'0.125')

    def test_smallest_positive_float_preserved(self):
        metadata,call=self.valid('--seconds=5e-324')
        self.assertEqual(metadata['seconds_per_solver'],5e-324); self.assertEqual(call['seconds'],'5e-324')

    def test_zero_rounds_preserves_no_search_mode(self):
        metadata,call=self.valid('--rounds=0')
        self.assertEqual(metadata['rounds'],0); self.assertEqual(call['rounds'],'0')

    def test_positive_round_limit_forwarded_once(self):
        metadata,call=self.valid('--rounds=1000001','--workers=1')
        self.assertEqual(metadata['rounds'],1000001); self.assertEqual(call['rounds'],'1000001')

    def test_explicit_resume_path_preserved(self):
        resume=self.root/'resume'; resume.mkdir()
        metadata,call=self.valid('--resume-dir',str(resume),'--rounds=0')
        self.assertEqual(call['resume'],str(resume/'setB-01'/'solution.json'))

    def test_existing_completed_output_protection_preserved(self):
        self.valid('--seconds=0','--workers=1')
        before={str(p.relative_to(self.output)):p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        first_calls=self.calls.read_bytes()
        result,_=self.invoke('--seconds=0','--workers=1')
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'preserve existing benchmark evidence',result.stderr)
        self.assertEqual(self.calls.read_bytes(),first_calls)
        self.assertEqual(before,{str(p.relative_to(self.output)):p.read_bytes() for p in self.output.rglob('*') if p.is_file()})

    def test_existing_parser_type_rejections_preserved(self):
        for option,value in (('--seconds','nope'),('--workers','1.5'),('--rounds','1.5')):
            with self.subTest(option=option): self.invalid(option,value)

    def test_multiple_valid_workers_keep_instance_outputs(self):
        for suffix in ('net','tm','scenario'):
            (self.data/'setB'/f'setB-02-{suffix}.json').write_text('{}\n')
        result,calls=self.invoke('--instances','setB-01','setB-02','--workers=2','--seconds=0')
        self.assertEqual(result.returncode,0,result.stderr)
        doc=json.loads((self.output/'summary.json').read_text())
        self.assertEqual([rows[0]['instance'] for rows in doc['results']],['setB-01','setB-02'])
        self.assertEqual(sum(c['role']=='solver' for c in calls),2)
        self.assertEqual(sum(c['role']=='checker' for c in calls),4)


def main():
    global BENCHMARK,REPORT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark',type=Path,required=True)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args(); BENCHMARK=args.benchmark.resolve(); REPORT=args.report
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ArgumentTests))
    source=BENCHMARK.read_bytes()
    document={'schema':'roadef.benchmark.arguments.validation.v1','source_sha256':hashlib.sha256(source).hexdigest(),
        'source_git_blob':hashlib.sha1(b'blob '+str(len(source)).encode()+b'\0'+source).hexdigest(),
        'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'skipped':len(result.skipped),'successful':result.wasSuccessful(), 'executions':RECORDS,
        'failure_details':[{'test':str(test),'detail':text} for test,text in result.failures+result.errors],
        'scope':'Actual benchmark CLI and real local subprocess fixtures. No official solvers, checker, instances, scores or timing panel.'}
    if REPORT:
        REPORT.parent.mkdir(parents=True,exist_ok=True); REPORT.write_text(json.dumps(document,indent=2,allow_nan=False)+'\n')
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__': raise SystemExit(main())
