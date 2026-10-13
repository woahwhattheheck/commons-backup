#!/usr/bin/env python3
"""Linux process-group regression tests for the real portfolio supervisor.

The child programs/checker reports are explicit lifecycle fixtures, not solver
or official-checker evidence. Only groups created by these tests are signaled.
Run with --supervisor to compare an exact old source; --report retains results.
"""
import argparse
import contextlib
import ctypes
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

SUPERVISOR = Path(__file__).with_name('supervisor.py')
RECORDS = []

# Fork and handshake before the leader exits or returns a report. Child ignores
# TERM when requested; the same process group is inherited, never escaped.
FIXTURE = r'''import json,os,signal,sys,time
from pathlib import Path
root=Path(os.environ['TEST_GROUP_ROOT'])
def publish(path,value):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value));temporary.replace(path)
role=os.environ.get('TEST_GROUP_ROLE','plain')
read,write=os.pipe()
child=os.fork()
if child==0:
    os.close(read)
    if os.environ.get('TEST_IGNORE_TERM')=='1':signal.signal(signal.SIGTERM,signal.SIG_IGN)
    p=root/(str(os.getpid())+'.child.json')
    publish(p,{'pid':os.getpid(),'pgid':os.getpgrp()})
    os.write(write,b'1');os.close(write)
    time.sleep(30)
    os._exit(0)
os.close(write);os.read(read,1);os.close(read)
publish(root/(str(os.getpid())+'.leader.json'),{'pid':os.getpid(),'pgid':os.getpgrp(),'child':child})
if '--srpaths' in sys.argv:
    source=Path(sys.argv[sys.argv.index('--srpaths')+1])
    v=json.loads(source.read_text())
    mode=os.environ.get('TEST_CHECKER_MODE','valid')
    if mode=='malformed':print('{broken',flush=True)
    elif mode!='timeout':
        print(json.dumps({'valid':mode!='invalid','total_cost':0,'saturations':[{'t':0,'from':1,'to':2,'sat':v.get('score',50)}]}),flush=True)
    if mode=='timeout':time.sleep(30)
else:
    if role=='lane':
        out=Path(sys.argv[-1]);tmp=out.with_suffix('.tmp')
        tmp.write_text(json.dumps({'srpaths':[],'score':{'sedge':9,'flora':8,'candidate':7}[out.stem]}))
        tmp.replace(out)
    if os.environ.get('TEST_LEADER_WAIT')=='1':time.sleep(30)
sys.exit(int(os.environ.get('TEST_LEADER_EXIT','0')))
'''


def state(pid):
    try:
        return Path('/proc', str(pid), 'stat').read_text().rsplit(') ', 1)[1][0]
    except FileNotFoundError:
        return None


def running(pid):
    return state(pid) not in (None, 'Z', 'X')


def until(predicate, timeout=2):
    end=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>=end:return False
        time.sleep(.01)
    return True


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux /proc and subreaper test harness')
class GroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Adopt only descendants of this isolated test process so teardown can
        # reap orphan fixtures even on containers whose PID 1 does not reap.
        cls.libc=ctypes.CDLL(None, use_errno=True)
        old=ctypes.c_int()
        if cls.libc.prctl(37, ctypes.byref(old), 0, 0, 0)!=0:
            raise OSError(ctypes.get_errno(), 'PR_GET_CHILD_SUBREAPER')
        cls.old_subreaper=old.value
        if cls.libc.prctl(36, 1, 0, 0, 0)!=0:
            raise OSError(ctypes.get_errno(), 'PR_SET_CHILD_SUBREAPER')
        sys.path.insert(0,str(SUPERVISOR.resolve().parent))
        spec=importlib.util.spec_from_file_location('group_test_supervisor',SUPERVISOR)
        cls.s=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.s)

    @classmethod
    def tearDownClass(cls):
        cls.libc.prctl(36, cls.old_subreaper, 0, 0, 0)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='roadef-group-test-')
        self.root=Path(self.tmp.name)
        self.fixture=self.root/'child fixture.py'
        self.fixture.write_text('#!'+sys.executable+'\n'+FIXTURE)
        self.fixture.chmod(0o700)
        self.processes=[];self.engine=None;self.environment=None
        self.started=time.monotonic();self.extra={}

    def tearDown(self):
        if self.engine and self.engine.check:
            p=self.engine.check['process'];self.processes.append(p)
            self.engine.check['stdout'].close();self.engine.check['stderr'].close()
        # Independently clean the groups, even when testing the failing source.
        # Never use broad process-name searches or signal unrelated workers.
        groups={p.pid for p in self.processes}
        children=[]
        for path in self.root.glob('*.child.json'):
            value=json.loads(path.read_text());groups.add(value['pgid']);children.append(value['pid'])
        for group in groups:
            if group==os.getpgrp():raise AssertionError('fixture group not isolated')
            try:os.killpg(group,signal.SIGKILL)
            except ProcessLookupError:pass
        for p in self.processes:
            try:p.wait(timeout=2)
            except subprocess.TimeoutExpired:pass
        for pid in children:
            try:os.waitpid(pid,0)
            except ChildProcessError:pass
        if self.environment:self.environment.stop()
        RECORDS.append({'test':self._testMethodName,'elapsed_seconds':time.monotonic()-self.started,
                        'fixture_groups':len(groups),'fixture_children':len(children),
                        'remaining_running_children':sum(running(p) for p in children),**self.extra})
        self.tmp.cleanup()

    def spawn(self, *, wait=False, ignore=False, code=0):
        env=dict(os.environ,TEST_GROUP_ROOT=str(self.root),TEST_LEADER_WAIT=str(int(wait)),
                 TEST_IGNORE_TERM=str(int(ignore)),TEST_LEADER_EXIT=str(code))
        p=self.s.launch([sys.executable,str(self.fixture)],env,subprocess.DEVNULL,subprocess.DEVNULL)
        self.processes.append(p)
        marker=self.root/(str(p.pid)+'.leader.json')
        self.assertTrue(until(marker.exists),'fixture handshake absent')
        child=json.loads(marker.read_text())['child']
        self.assertEqual(os.getpgid(child),p.pid)
        self.assertNotEqual(p.pid,os.getpgrp())
        return p,child

    def assert_stopped(self,child):
        self.assertTrue(until(lambda:not running(child),.4),'descendant survived group cleanup')

    def test_none(self):
        self.s.stop_process(None);self.s.stop_process(None,force=True)

    def test_live_group_term(self):
        p,child=self.spawn(wait=True)
        self.s.stop_process(p);p.wait(timeout=2);self.assert_stopped(child)

    def test_exited_leader_term(self):
        p,child=self.spawn();self.assertEqual(p.wait(timeout=2),0)
        self.s.stop_process(p);self.assert_stopped(child);self.assertEqual(p.returncode,0)

    def test_failed_leader_force(self):
        p,child=self.spawn(ignore=True,code=7);self.assertEqual(p.wait(timeout=2),7)
        self.s.stop_process(p,force=True);self.assert_stopped(child);self.assertEqual(p.returncode,7)

    def test_term_then_force_after_leader_exits(self):
        p,child=self.spawn(wait=True,ignore=True)
        self.s.stop_process(p);p.wait(timeout=2);self.assertTrue(running(child))
        self.s.stop_process(p,force=True);self.assert_stopped(child)

    def test_unrelated_group_untouched(self):
        target,a=self.spawn(ignore=True);sentinel,b=self.spawn(wait=True,ignore=True)
        target.wait(timeout=2);self.s.stop_process(target,force=True);self.assert_stopped(a)
        self.assertTrue(running(b));self.assertIsNone(sentinel.poll())

    def test_force_retirement_not_signaled_twice(self):
        p,child=self.spawn(ignore=True);p.wait(timeout=2)
        self.s.stop_process(p,force=True);self.assert_stopped(child)
        with patch.object(self.s.os,'killpg',side_effect=AssertionError('retired group signaled')):
            self.s.stop_process(p);self.s.stop_process(p,force=True)

    def test_absent_group_retirement(self):
        p=self.s.launch([sys.executable,'-c','pass'],dict(os.environ),subprocess.DEVNULL,subprocess.DEVNULL)
        self.processes.append(p);p.wait(timeout=2);self.s.stop_process(p)
        self.assertTrue(getattr(p,'_portfolio_group_closed',False))
        with patch.object(self.s.os,'killpg',side_effect=AssertionError('absent group re-signaled')):
            self.s.stop_process(p,force=True)

    def test_nonposix_live_and_exited(self):
        calls=[]
        p=types.SimpleNamespace(poll=lambda:None,kill=lambda:calls.append('kill'),terminate=lambda:calls.append('term'))
        with patch.object(self.s,'os',types.SimpleNamespace(name='nt')):
            self.s.stop_process(p);self.s.stop_process(p,force=True)
            p.poll=lambda:0;self.s.stop_process(p);self.s.stop_process(p,force=True)
        self.assertEqual(calls,['term','kill'])

    def setup_engine(self,mode='valid',wait=False):
        inputs=[self.root/n for n in ('net.json','tm.json','scenario.json')]
        for p in inputs:p.write_text('{}')
        self.environment=patch.dict(os.environ,PORTFOLIO_CHECKER=str(self.fixture),
            PORTFOLIO_SECONDS='2',PORTFOLIO_ARTIFACTS=str(self.root),
            TEST_GROUP_ROOT=str(self.root),TEST_IGNORE_TERM='1',TEST_CHECKER_MODE=mode,
            TEST_LEADER_WAIT=str(int(wait)),TEST_GROUP_ROLE='lane')
        self.environment.start()
        self.engine=self.s.Supervisor(inputs,self.root/'best.json')
        return self.engine

    def checker_case(self,mode):
        engine=self.setup_engine(mode)
        solution=self.root/'candidate.json';solution.write_text('{"score":7}')
        self.assertTrue(engine.enqueue(solution,'fixture'))
        process=engine.check['process'];self.processes.append(process)
        marker=self.root/(str(process.pid)+'.leader.json');self.assertTrue(until(marker.exists))
        child=json.loads(marker.read_text())['child']
        if mode=='timeout':
            engine.check_timeout=.1;time.sleep(.15)
        else:process.wait(timeout=2)
        engine.poll_checker();self.assertIsNone(engine.check);self.assert_stopped(child)
        return engine

    def test_returned_checker_group(self):
        engine=self.checker_case('valid')
        self.assertEqual(json.loads(engine.output.read_text()),{'score':7})
        self.assertEqual(engine.best['vector'][0],7)
        self.assertEqual(len(engine.failed_checks),0)

    def test_invalid_checker_group(self):
        engine=self.checker_case('invalid');self.assertIsNone(engine.best)
        self.assertTrue(any(e['event']=='candidate_invalid' for e in engine.events))

    def test_malformed_checker_group_retry(self):
        engine=self.checker_case('malformed');self.assertIsNone(engine.best)
        self.assertEqual(list(engine.failed_checks.values()),[1])
        self.assertTrue(any(e['event']=='check_retry_queued' for e in engine.events))

    def test_timed_out_checker_group_retry(self):
        engine=self.checker_case('timeout');self.assertIsNone(engine.best)
        self.assertEqual(list(engine.failed_checks.values()),[1])
        self.assertTrue(any(e.get('error')=='checker timeout' for e in engine.events))

    def test_whole_cli_cleanup_and_checkpoint(self):
        engine=self.setup_engine()
        env=dict(os.environ,PORTFOLIO_SECONDS='8',PORTFOLIO_CHECK_INTERVAL='0.05',
                 PORTFOLIO_SEDGE=str(self.fixture),PORTFOLIO_FLORA=str(self.fixture),
                 PORTFOLIO_CANDIDATE=str(self.fixture))
        with (self.root/'cli.log').open('wb') as log:
            p=self.s.launch([sys.executable,str(SUPERVISOR),*map(str,engine.inputs),str(engine.output)],env,log,log)
            self.processes.append(p);self.assertEqual(p.wait(timeout=10),0)
        self.extra['cli_log']=(self.root/'cli.log').read_text()
        self.extra['cli_receipt']=json.loads(Path(str(engine.output)+'.portfolio.json').read_text())
        self.assertEqual(json.loads(engine.output.read_text())['score'],7)
        receipt=json.loads(Path(str(engine.output)+'.portfolio.json').read_text())
        self.assertTrue(receipt['validated']);self.assertEqual(receipt['selected_lane'],'candidate')
        self.assertEqual(receipt['status'],'complete')
        children=[json.loads(f.read_text())['pid'] for f in self.root.glob('*.child.json')]
        self.assertGreaterEqual(len(children),4)
        for child in children:self.assert_stopped(child)

    def test_cli_term_retains_checkpoint_and_kills_descendants(self):
        engine=self.setup_engine(wait=True)
        env=dict(os.environ,PORTFOLIO_SECONDS='15',PORTFOLIO_SEDGE=str(self.fixture),
                 PORTFOLIO_FLORA=str(self.fixture),PORTFOLIO_CANDIDATE=str(self.fixture))
        with (self.root/'signal-cli.log').open('wb') as log:
            p=self.s.launch([sys.executable,str(SUPERVISOR),*map(str,engine.inputs),str(engine.output)],env,log,log)
            self.processes.append(p)
            receipt_path=Path(str(engine.output)+'.portfolio.json')
            def valid():
                try:return json.loads(receipt_path.read_text()).get('validated')
                except (OSError,ValueError):return False
            self.assertTrue(until(valid,3));before=engine.output.read_bytes()
            start=time.monotonic();p.send_signal(signal.SIGTERM);self.assertEqual(p.wait(timeout=5),0)
        self.assertLess(time.monotonic()-start,5)
        receipt=json.loads(receipt_path.read_text());self.assertTrue(receipt['validated'])
        self.assertEqual(receipt['signal_received'],signal.SIGTERM)
        self.assertTrue(engine.output.exists())
        for path in self.root.glob('*.child.json'):self.assert_stopped(json.loads(path.read_text())['pid'])

    def test_exception_finally_cleans_exited_lane(self):
        engine=self.setup_engine()
        p,child=self.spawn(ignore=True);p.wait(timeout=2)
        engine.lanes=[{'name':'x','executable':self.fixture,'process':p,'log':None}]
        old={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
        try:
            with patch.object(engine,'start_lanes'),patch.object(engine,'poll_checker',side_effect=RuntimeError('diagnostic')):
                with self.assertRaisesRegex(RuntimeError,'diagnostic'):engine.run()
            self.assert_stopped(child)
        finally:
            for sig,handler in old.items():signal.signal(sig,handler)


def main():
    global SUPERVISOR
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--supervisor',type=Path,default=SUPERVISOR)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();SUPERVISOR=args.supervisor.resolve()
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(GroupTests)
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    log=stream.getvalue();print(log,end='')
    report={'schema':'roadef.process-group-tests.v1','supervisor_sha256':hashlib.sha256(SUPERVISOR.read_bytes()).hexdigest(),
        'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'python':sys.version,'platform':sys.platform,
        'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'successful':result.wasSuccessful(),'cases':RECORDS,'log':log,
        'scope':'Actual Linux processes and complete supervisor with synthetic solver/checker fixtures; no algorithm, official checker, Docker, or full-budget claim.'}
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':sys.exit(main())
