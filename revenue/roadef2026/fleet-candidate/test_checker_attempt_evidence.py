#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Retain each actual checker attempt's raw streams without changing selection.

These checkers are protocol fixtures, not route validators. No solver benchmark
or official contest score is measured. ROADEF_TEST_SOURCE selects the complete
supervisor/comparator pair; ROADEF_ATTEMPT_EVIDENCE retains temporary run files.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE = Path(os.environ.get('ROADEF_TEST_SOURCE', Path(__file__).resolve().parent))
sys.path.insert(0, str(SOURCE))
SPEC = importlib.util.spec_from_file_location('checker_attempt_subject', SOURCE/'supervisor.py')
SUBJECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUBJECT)

CHECKER = r'''import json,os,sys,time
from pathlib import Path
p=Path(sys.argv[sys.argv.index('--srpaths')+1])
x=json.loads(p.read_text()); marker=p.with_suffix('.attempt-count')
n=int(marker.read_text())+1 if marker.exists() else 1
marker.write_text(str(n))
fault=x.get('fault',''); first=n==1
if fault=='binary' and first:
 os.write(1,b'first stdout\x00\xff\n');os.write(2,b'first stderr\x00\xfe\n');sys.exit(7)
if fault=='malformed' and first:
 os.write(1,b'null\n');os.write(2,b'malformed first\n');sys.exit(0)
if fault=='permanent':
 os.write(1,('bad attempt '+str(n)+'\n').encode())
 os.write(2,('diagnostic attempt '+str(n)+'\n').encode());sys.exit(7)
if fault=='timeout' and first:
 os.write(1,b'partial before timeout\x00\xff\n');os.write(2,b'timeout diagnostic\n')
 p.with_suffix('.ready').write_text('ready');time.sleep(10)
if fault=='invalid':
 os.write(1,b'{"valid":false}\n');os.write(2,b'conclusive invalid\n');sys.exit(2)
print(json.dumps({'valid':True,'total_cost':x.get('cost',0),'saturations':[
 {'t':0,'from':1,'to':2,'sat':x.get('score',10)}]}),flush=True)
os.write(2,('successful attempt '+str(n)+'\n').encode())
'''
SOLVER = '''import json,sys
from pathlib import Path
Path(sys.argv[-1]).write_text(json.dumps({'srpaths':[],'score':3,'fault':'binary'}))
'''


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CheckerAttemptEvidence(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='roadef-attempt-evidence-')
        self.root = Path(self.temporary.name)
        self.inputs = [self.root/name for name in ('net.json','traffic.json','scenario.json')]
        for path in self.inputs:
            path.write_text('{}', encoding='utf-8')
        self.checker = self.root/'checker with spaces.py'
        self.checker.write_text(CHECKER, encoding='utf-8')
        self.env = patch.dict(os.environ, {
            'PORTFOLIO_CHECKER': str(self.checker), 'PORTFOLIO_SECONDS':'10',
            'PORTFOLIO_CHECK_TIMEOUT':'0.5', 'PORTFOLIO_ARTIFACTS':str(self.root),
            'PORTFOLIO_RECEIPT':str(self.root/'receipt.json')})
        self.env.start()
        self.events = io.StringIO()
        self.stderr = contextlib.redirect_stderr(self.events);self.stderr.__enter__()
        self.subject = SUBJECT.Supervisor(self.inputs,self.root/'selected solution.json')
        self.subject.pending_baseline = None
        self.real_launch = SUBJECT.launch
        self.calls = []
        def launch(command, env, stdout, stderr):
            self.calls.append(list(command))
            return self.real_launch([sys.executable,*command],env,stdout,stderr)
        self.launch = patch.object(SUBJECT,'launch',side_effect=launch)
        self.launch.start()

    def tearDown(self):
        try:
            if self.subject.check is not None:
                current=self.subject.check
                SUBJECT.stop_process(current['process'],force=True)
                current['process'].wait(timeout=2)
                current['stdout'].close();current['stderr'].close()
            (self.root/'events.jsonl').write_text(self.events.getvalue(),encoding='utf-8')
            (self.root/'test-source.json').write_text(json.dumps({
                'supervisor_sha256':digest(SOURCE/'supervisor.py'),
                'comparator_sha256':digest(SOURCE/'compare_checker.py'),
                'launches':self.calls},indent=2)+'\n')
            evidence=os.environ.get('ROADEF_ATTEMPT_EVIDENCE')
            if evidence:
                target=Path(evidence)/self._testMethodName
                shutil.copytree(self.root,target)
        finally:
            self.launch.stop();self.stderr.__exit__(None,None,None);self.env.stop()
            self.temporary.cleanup()

    def lane(self, *, fault='', score=3, name='fixture', cost=0):
        path=self.root/(name+'.json')
        path.write_text(json.dumps({'srpaths':[],'score':score,'cost':cost,'fault':fault}))
        return {'name':name,'process':None,'solution':path,'executable':self.checker,
                'last_digest':None,'next_check':0,'final_checked':False,
                'retry_snapshot':None,'read_failures':0}

    def begin(self, lane, *, retry=False):
        path=lane['retry_snapshot'] if retry else lane['solution']
        self.assertTrue(self.subject.enqueue(path,lane))
        return self.subject.check

    def finish(self):
        check=self.subject.check
        check['process'].wait(timeout=3)
        self.subject.poll_checker()
        self.assertIsNone(self.subject.check)
        return check

    def retained(self, first, expected_out, expected_err, second):
        self.assertNotEqual(first['result'],second['result'])
        self.assertNotEqual(first['stderr'].name,second['stderr'].name)
        self.assertEqual(first['result'].read_bytes(),expected_out)
        self.assertEqual(Path(first['stderr'].name).read_bytes(),expected_err)
        self.assertEqual(first['snapshot'],second['snapshot'])
        self.assertEqual(first['digest'],second['digest'])
        self.assertEqual(second['result'].name,first['digest']+'.attempt-2.checker-6.json')
        self.assertEqual(Path(second['stderr'].name).name,first['digest']+'.attempt-2.checker.log')

    def test_first_success_keeps_original_paths_and_exact_selection(self):
        lane=self.lane();first=self.begin(lane);self.finish()
        self.assertEqual(first['result'].name,first['digest']+'.checker-6.json')
        self.assertEqual(Path(first['stderr'].name).name,first['digest']+'.checker.log')
        self.assertEqual(self.subject.output.read_bytes(),lane['solution'].read_bytes())
        self.assertEqual(self.subject.best['path'],str(first['result'].resolve()))
        self.assertEqual(len(self.calls),1)

    def test_binary_failure_then_success_retains_both_raw_streams(self):
        lane=self.lane(fault='binary');first=self.begin(lane);self.finish()
        second=self.begin(lane,retry=True);self.finish()
        self.retained(first,b'first stdout\x00\xff\n',b'first stderr\x00\xfe\n',second)
        self.assertEqual(self.subject.output.read_bytes(),lane['solution'].read_bytes())
        self.assertEqual(self.subject.best['sha256'],digest(second['result']))
        self.assertEqual(self.subject.failed_checks[first['digest']],1)
        self.assertEqual(len(self.calls),2)

    def test_zero_exit_malformed_report_is_retained_after_recovery(self):
        lane=self.lane(fault='malformed');first=self.begin(lane);self.finish()
        second=self.begin(lane,retry=True);self.finish()
        self.retained(first,b'null\n',b'malformed first\n',second)
        self.assertEqual(self.subject.best['vector'][0],3)
        self.assertEqual(first['process'].returncode,0)

    def test_two_failures_stay_separate_and_no_third_attempt_runs(self):
        lane=self.lane(fault='permanent');first=self.begin(lane);self.finish()
        second=self.begin(lane,retry=True);self.finish()
        self.retained(first,b'bad attempt 1\n',b'diagnostic attempt 1\n',second)
        self.assertEqual(second['result'].read_bytes(),b'bad attempt 2\n')
        self.assertEqual(Path(second['stderr'].name).read_bytes(),b'diagnostic attempt 2\n')
        self.assertIn(first['digest'],self.subject.exhausted_checks)
        self.assertFalse(self.subject.enqueue(lane['solution'],lane))
        self.assertEqual(len(self.calls),2)
        self.assertIsNone(self.subject.best)

    def test_partial_timeout_streams_survive_successful_retry(self):
        lane=self.lane(fault='timeout');first=self.begin(lane)
        deadline=time.monotonic()+3
        marker=first['snapshot'].with_suffix('.ready')
        while not marker.exists() and time.monotonic()<deadline:
            time.sleep(0.01)
        self.assertTrue(marker.exists(),'checker did not emit its partial output')
        # Force only the observer's elapsed-time condition; the actual child is
        # stopped by the production timeout/cleanup implementation.
        first['started']=time.monotonic()-self.subject.check_timeout-1
        self.subject.poll_checker();self.assertIsNone(self.subject.check)
        second=self.begin(lane,retry=True);self.finish()
        self.retained(first,b'partial before timeout\x00\xff\n',b'timeout diagnostic\n',second)
        self.assertEqual(self.subject.best['vector'][0],3)
        self.assertNotEqual(first['process'].returncode,0)

    def test_launch_failure_preserves_empty_first_artifacts(self):
        lane=self.lane()
        with patch.object(SUBJECT,'launch',side_effect=OSError('fixture launch failure')):
            self.assertFalse(self.subject.enqueue(lane['solution'],lane))
        sha=digest(lane['solution'])
        first_out=self.subject.work/(sha+'.checker-6.json')
        first_err=self.subject.work/(sha+'.checker.log')
        self.assertEqual(first_out.read_bytes(),b'');self.assertEqual(first_err.read_bytes(),b'')
        second=self.begin(lane,retry=True);self.finish()
        self.assertNotEqual(second['result'],first_out)
        self.assertEqual(first_out.read_bytes(),b'');self.assertEqual(first_err.read_bytes(),b'')
        self.assertEqual(self.subject.best['vector'][0],3)
        self.assertEqual(len(self.calls),1)

    def test_exited_lane_scheduler_finishes_retry_and_retains_failures(self):
        lane=self.lane(fault='binary');self.subject.lanes=[lane]
        self.subject.schedule_check();first=self.subject.check;self.finish()
        self.subject.schedule_check();second=self.subject.check;self.finish()
        self.subject.schedule_check()
        self.assertTrue(lane['final_checked']);self.assertIsNone(self.subject.check)
        self.retained(first,b'first stdout\x00\xff\n',b'first stderr\x00\xfe\n',second)
        self.assertEqual(len(self.calls),2)

    def test_cache_reuse_does_not_reopen_or_mutate_attempt_files(self):
        lane=self.lane(fault='binary');self.begin(lane);self.finish()
        self.begin(lane,retry=True);self.finish()
        paths=[p for p in self.subject.work.iterdir() if '.checker' in p.name]
        before={p.name:p.read_bytes() for p in paths}
        self.assertFalse(self.subject.enqueue(lane['solution'],lane))
        self.assertEqual({p.name:p.read_bytes() for p in paths},before)
        self.assertEqual(len(self.calls),2)

    def test_distinct_solution_digests_each_have_their_own_attempts(self):
        paths=[]
        for number in (5,3):
            lane=self.lane(fault='binary',score=number,name='lane'+str(number))
            first=self.begin(lane);self.finish()
            second=self.begin(lane,retry=True);self.finish()
            self.retained(first,b'first stdout\x00\xff\n',b'first stderr\x00\xfe\n',second)
            paths.extend((first['result'],second['result']))
        self.assertEqual(len(set(paths)),4)
        self.assertEqual(self.subject.best['vector'][0],3)
        self.assertEqual(len(self.calls),4)

    def test_live_checkpoint_update_does_not_change_frozen_retry(self):
        lane=self.lane(fault='binary');original=lane['solution'].read_bytes()
        first=self.begin(lane);self.finish()
        lane['solution'].write_text('{"srpaths":[],"score":1}')
        second=self.begin(lane,retry=True);self.finish()
        self.retained(first,b'first stdout\x00\xff\n',b'first stderr\x00\xfe\n',second)
        self.assertEqual(self.subject.output.read_bytes(),original)
        self.begin(lane);self.finish()
        self.assertEqual(self.subject.best['vector'][0],1)
        self.assertEqual(len(self.calls),3)

    def test_invalid_report_is_conclusive_without_retry(self):
        lane=self.lane(fault='invalid');first=self.begin(lane);self.finish()
        self.assertIn(first['digest'],self.subject.cache)
        self.assertNotIn(first['digest'],self.subject.failed_checks)
        self.assertIsNone(lane['retry_snapshot'])
        self.assertIsNone(self.subject.best)
        self.assertEqual(first['result'].read_bytes(),b'{"valid":false}\n')
        self.assertEqual(len(self.calls),1)

    def test_recovered_equal_vector_keeps_existing_incumbent(self):
        lane=self.lane(score=3,name='incumbent',cost=100)
        self.begin(lane);self.finish();before=self.subject.output.read_bytes()
        other=self.lane(score=3,fault='binary',name='equal-cheaper',cost=0)
        first=self.begin(other);self.finish();second=self.begin(other,retry=True);self.finish()
        self.retained(first,b'first stdout\x00\xff\n',b'first stderr\x00\xfe\n',second)
        self.assertEqual(self.subject.output.read_bytes(),before)
        self.assertEqual(self.subject.best['lane'],'incumbent')

    @unittest.skipUnless(os.name=='posix','CLI fixtures use local POSIX shebangs')
    def test_complete_cli_retains_failed_bytes_and_correct_validated_receipt(self):
        source=self.root/'cli';source.mkdir()
        for name in ('supervisor.py','compare_checker.py'):
            shutil.copy2(SOURCE/name,source/name)
        for name,code in (('checker',CHECKER),('solver',SOLVER)):
            path=source/name;path.write_text('#!'+sys.executable+'\n'+code);path.chmod(0o755)
        out=source/'out.json';receipt=source/'receipt.json'
        env=dict(os.environ,PORTFOLIO_SECONDS='4',PORTFOLIO_CHECK_INTERVAL='0.05',
                 PORTFOLIO_CHECK_TIMEOUT='1',PORTFOLIO_ARTIFACTS=str(source),
                 PORTFOLIO_RECEIPT=str(receipt),PORTFOLIO_CHECKER=str(source/'checker'))
        env.update({ 'PORTFOLIO_'+lane:str(source/'solver') for lane in ('SEDGE','FLORA','CANDIDATE')})
        done=subprocess.run([sys.executable,'-B',str(source/'supervisor.py'),
                            *map(str,self.inputs),str(out)],env=env,capture_output=True,timeout=8)
        (source/'supervisor.stdout').write_bytes(done.stdout)
        (source/'supervisor.stderr').write_bytes(done.stderr)
        self.assertEqual(done.returncode,0,done.stderr)
        recorded=json.loads(receipt.read_text());sha=digest(out)
        self.assertTrue(recorded['validated']);self.assertEqual(recorded['status'],'complete')
        self.assertEqual(recorded['solution_sha256'],sha)
        self.assertEqual(recorded['maximum_load'],'3')
        directory=Path(recorded['artifacts'])
        self.assertEqual((directory/(sha+'.checker-6.json')).read_bytes(),b'first stdout\x00\xff\n')
        self.assertEqual((directory/(sha+'.checker.log')).read_bytes(),b'first stderr\x00\xfe\n')
        second=directory/(sha+'.attempt-2.checker-6.json')
        self.assertEqual(recorded['selected_checker_sha256'],digest(second))
        self.assertEqual(sum(e['event']=='check_retry_queued' for e in recorded['events']),1)
        self.assertEqual(sum(e['event']=='check_retries_exhausted' for e in recorded['events']),0)


if __name__=='__main__':
    unittest.main(verbosity=2)
