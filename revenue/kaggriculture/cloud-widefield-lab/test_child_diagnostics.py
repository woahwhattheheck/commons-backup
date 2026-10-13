# SPDX-License-Identifier: Apache-2.0
"""Preserve failed child diagnostics using real fixture subprocesses; no games."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
TEST_SOURCE = Path(os.environ.get('TITAN_REUSE_TEST_SOURCE', HERE/'test_report_reuse.py')).resolve()
spec = importlib.util.spec_from_file_location('diagnostic_reuse_fixtures', TEST_SOURCE)
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
P = R.P
WITNESSES = []

class ChildDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.f = R.ReportReuseTests('test_exact_report_reused_without_launch_or_writes')
        self.f.setUp();self.addCleanup(self.f.doCleanups)

    def fixture(self, emitted, *, stderr=False, exit_code=7):
        f=self.f
        source=f.evaluator.read_text()
        stream='stderr' if stderr else 'stdout'
        source=source.replace("print('fixture evaluator only; no policy or engine')",
                              f"sys.{stream}.buffer.write({emitted!r});sys.{stream}.buffer.flush()")
        f.evaluator.write_text(source);f.report['evaluator_sha256']=R.sha(f.evaluator)
        f.fixture(exit=exit_code)

    def invoke(self):
        f=self.f
        return P.run_job(f.job,f.evaluator,f.engine,f.opponents,f.out)

    def check_failed_bytes(self, emitted, **kwargs):
        self.fixture(emitted,**kwargs)
        with self.assertRaises(UnicodeDecodeError) as caught:self.invoke()
        f=self.f
        self.assertTrue(f.target.exists())
        self.assertTrue(f.log.exists(),'decoding failure lost the diagnostic log')
        self.assertEqual(f.log.read_text(encoding='utf-8'),emitted.decode(caught.exception.encoding,errors='backslashreplace'))
        self.assertEqual((f.evaluator.parent/'launches.txt').read_text(),'one\n')
        return caught.exception

    def test_failed_stdout_is_retained_and_original_failure_stays(self):
        e=self.check_failed_bytes(b'original\xffstdout\n')
        WITNESSES.append({'case':'stdout','error':type(e).__name__,'display_log':self.f.log.read_text(),'report_retained':True,'fixture_exit':7})

    def test_failed_stderr_is_retained_in_existing_combined_log(self):
        self.check_failed_bytes(b'original\xfestderr\n',stderr=True)

    def test_zero_exit_with_undecodable_output_is_not_promoted(self):
        self.check_failed_bytes(b'\xffinvalid despite exit zero\n',exit_code=0)

    def test_valid_unicode_output_and_status_are_unchanged(self):
        self.fixture('plain unicode λ\n'.encode(),exit_code=0)
        result=self.invoke()
        self.assertEqual(result['status'],'complete')
        self.assertEqual(self.f.log.read_text(),'plain unicode λ\n')

    def test_log_write_failure_keeps_original_exception_identity(self):
        f=self.f
        original=UnicodeDecodeError('utf-8',b'\xffdiagnostic',0,1,'invalid byte')
        secondary=OSError('injected log write failure')
        with patch.object(P.subprocess,'run',side_effect=original),patch.object(Path,'write_text',side_effect=secondary):
            with self.assertRaises(UnicodeDecodeError) as caught:self.invoke()
        self.assertIs(caught.exception,original)
        self.assertIs(caught.exception.__cause__,secondary)

    def test_cancellation_is_not_converted_to_decoding_failure(self):
        original=KeyboardInterrupt('fixture interruption')
        with patch.object(P.subprocess,'run',side_effect=original):
            with self.assertRaises(KeyboardInterrupt) as caught:self.invoke()
        self.assertIs(caught.exception,original)
        self.assertFalse(self.f.log.exists())

    def test_prior_log_preservation_still_prevents_new_launch(self):
        f=self.f;f.log.parent.mkdir(parents=True);f.log.write_text('retained previous attempt\n')
        with patch.object(P.subprocess,'run',side_effect=AssertionError('prior log overwritten')):
            result=self.invoke()
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['reason'],'existing_evidence_not_reusable')
        self.assertEqual(f.log.read_text(),'retained previous attempt\n')

    def test_actual_cli_keeps_bad_log_and_successful_sibling(self):
        f=self.f
        good=f.root/'good.py';good.write_text('# fixture only, never imported\n')
        s=f.evaluator.read_text().replace('import json,sys','import json,sys,hashlib')
        s=s.replace("target.write_text(json.dumps(data['report']))",'''candidate=Path(sys.argv[sys.argv.index('--candidate')+1])
report=data['report']
report['candidate']={'entry':candidate.name,'callable':'agent','sha256':hashlib.sha256(candidate.read_bytes()).hexdigest()}
target.write_text(json.dumps(report))''')
        s=s.replace("print('fixture evaluator only; no policy or engine')",'''if candidate.name == 'candidate.py':
    sys.stdout.buffer.write(b'\\xffretained failed-child diagnostic\\n');sys.stdout.buffer.flush()
else:
    print('successful sibling fixture')''')
        f.evaluator.write_text(s);f.report['evaluator_sha256']=R.sha(f.evaluator);f.fixture()
        cfg=f.root/'config.json';cfg.write_text(json.dumps({'evaluator':str(f.evaluator),'engine':str(f.engine),
            'seeds':{'first':12,'last':12,'shard_size':1},'arms':{'bad':str(f.candidate),'good':str(good)},'opponents':f.opponents}))
        proc=subprocess.run([sys.executable,'-B',str(R.TARGET),'--config',str(cfg),'--output',str(f.out),'--jobs','2'],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(proc.returncode,0)
        self.assertIn('UnicodeDecodeError',proc.stderr)
        records=json.loads((f.out/'run-state.json').read_text());self.assertEqual(len(records),2)
        rows={r['arm']:r for r in records}
        self.assertEqual(rows['bad']['failure']['type'],'UnicodeDecodeError')
        self.assertEqual(rows['good']['status'],'complete')
        log=f.out/'logs/bad/12-12.log'
        self.assertTrue(log.exists(),'checkpoint survives but diagnostic file was lost')
        self.assertEqual(log.read_text(),'\\xffretained failed-child diagnostic\n')
        self.assertTrue((f.out/'raw/bad/12-12.json').exists())
        WITNESSES.append({'case':'actual_cli_two_workers','exit':proc.returncode,'bad_error':rows['bad']['failure']['type'],'good_status':rows['good']['status'],'bad_log':log.read_text(),'raw_reports_retained':2})

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path);a=ap.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ChildDiagnosticTests))
    if a.report:
        a.report.parent.mkdir(parents=True,exist_ok=True)
        a.report.write_text(json.dumps({'scope':'fixture subprocess/CLI and diagnostic exception handling','source_sha256':R.sha(R.TARGET),'test_sha256':R.sha(Path(__file__)),'fixture_helper_sha256':R.sha(TEST_SOURCE),'python':sys.version,'tests':{'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'successful':result.wasSuccessful()},'witnesses':WITNESSES,'official_games':0,'policy_calls':0,'game_seeds':[],'failures':[{'test':str(t),'traceback':m} for t,m in result.failures],'errors':[{'test':str(t),'traceback':m} for t,m in result.errors]},indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
