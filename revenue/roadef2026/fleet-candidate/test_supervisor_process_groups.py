#!/usr/bin/env python3
"""Linux process-group shutdown, using real subprocesses and isolated reaping.

The portfolio probes use synthetic solver/checker executables to exercise the
real supervisor. They do not measure official feasibility or solver strength.
"""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import supervisor


CHILD = r'''
import json, os, signal, sys, time
from pathlib import Path
ready, mode = Path(sys.argv[1]), sys.argv[2]
def finish(signum, frame):
    ready.with_suffix('.term').write_text('TERM', encoding='utf-8')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN if mode == 'ignore' else finish)
ready.write_text(json.dumps({'pid': os.getpid(), 'pgid': os.getpgrp()}), encoding='utf-8')
time.sleep(15)
'''
PARENT = r'''
import subprocess, sys, time
from pathlib import Path
child, ready, mode, remain = sys.argv[1:]
subprocess.Popen([sys.executable, '-c', child, ready, mode])
limit = time.monotonic() + 3
while not Path(ready).exists() and time.monotonic() < limit:
    time.sleep(.005)
if not Path(ready).exists():
    raise SystemExit(9)
if remain == 'yes':
    time.sleep(15)
'''


def until(predicate, seconds=1.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(.01)
    return bool(predicate())


def probe(mode):
    # This fresh subprocess, not the unittest host, adopts its own orphaned
    # descendants so even a failing baseline leaves no running/zombie children.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER, Linux.
        raise OSError(ctypes.get_errno(), 'test subreaper unavailable')
    parents, children, statuses = [], [], {}
    temporary = tempfile.TemporaryDirectory(prefix='portfolio-group-control-')
    root = Path(temporary.name)

    def child_exited(pid):
        if pid in statuses:
            return True
        reaped, status = os.waitpid(pid, os.WNOHANG)
        if reaped:
            statuses[pid] = status
            return True
        return False

    def start(name, ignore=False, remain=False):
        ready = root / (name + '.json')
        parent = supervisor.launch(
            [sys.executable, '-c', PARENT, CHILD, str(ready),
             'ignore' if ignore else 'cooperate', 'yes' if remain else 'no'],
            dict(os.environ), subprocess.DEVNULL, subprocess.DEVNULL)
        parents.append(parent)
        assert until(ready.exists, 3), 'child readiness not observed'
        record = json.loads(ready.read_text(encoding='utf-8'))
        children.append(record['pid'])
        assert record['pgid'] == parent.pid, 'launch did not create the expected isolated group'
        if not remain:
            assert parent.wait(timeout=3) == 0
        return parent, record['pid'], ready

    try:
        if mode in ('orphan_term', 'orphan_force', 'live_term', 'escalate'):
            force = mode in ('orphan_force', 'escalate')
            remain = mode in ('live_term', 'escalate')
            parent, pid, ready = start('target', ignore=force, remain=remain)
            if mode == 'escalate':
                supervisor.stop_process(parent)
                assert parent.wait(timeout=2) == -signal.SIGTERM
                assert not child_exited(pid), 'TERM-ignoring child should require escalation'
            supervisor.stop_process(parent, force=force)
            parent.wait(timeout=2)
            assert until(lambda: child_exited(pid)), 'child survived requested group shutdown'
            if force:
                assert os.WIFSIGNALED(statuses[pid]) and os.WTERMSIG(statuses[pid]) == signal.SIGKILL
            else:
                assert ready.with_suffix('.term').read_text() == 'TERM'
                assert os.WIFEXITED(statuses[pid]) and os.WEXITSTATUS(statuses[pid]) == 0
        elif mode == 'idempotent':
            parent = supervisor.launch([sys.executable, '-c', 'pass'], dict(os.environ),
                                       subprocess.DEVNULL, subprocess.DEVNULL)
            parents.append(parent)
            assert parent.wait(timeout=2) == 0
            supervisor.stop_process(None)
            for force in (False, True, False):
                supervisor.stop_process(parent, force=force)
        elif mode == 'isolation':
            target, pid, _ = start('target', ignore=True)
            other, other_pid, _ = start('unrelated', ignore=True, remain=True)
            supervisor.stop_process(target, force=True)
            assert until(lambda: child_exited(pid)), 'target group survived'
            assert other.poll() is None, 'unrelated group leader was stopped'
            os.kill(other_pid, 0)
        elif mode == 'begin_stop':
            parent, pid, ready = start('target')
            with patch.dict(os.environ, {'PORTFOLIO_SECONDS': '3',
                                       'PORTFOLIO_ARTIFACTS': str(root),
                                       'PORTFOLIO_RECEIPT': str(root / 'receipt.json')}):
                engine = supervisor.Supervisor([], root / 'selected.json')
            engine.lanes = [{'process': parent}]
            engine.begin_stop('test')
            assert until(lambda: child_exited(pid)), 'begin_stop left descendant alive'
            assert ready.with_suffix('.term').exists()
            first = engine.stopping_at
            engine.begin_stop('test-again')
            assert engine.stopping_at == first
        elif mode in ('runner_complete', 'runner_exception'):
            checker = root / 'checker'
            checker.write_text('#!' + sys.executable + '\n' +
                "import json,sys\nfrom pathlib import Path\n"
                "source=Path(sys.argv[sys.argv.index('--srpaths')+1])\n"
                "x=json.loads(source.read_text())\n"
                "print(json.dumps({'valid':True,'total_cost':0,'saturations':"
                "[{'t':0,'from':1,'to':2,'sat':x.get('score',9)}]}))\n", encoding='utf-8')
            checker.chmod(0o700)
            solver = root / 'solver'
            solver.write_text('#!' + sys.executable + '\n' +
                'import json, subprocess, sys, time\nfrom pathlib import Path\n' +
                'child=' + repr(CHILD) + '\n' +
                "out=Path(sys.argv[-1]);ready=out.with_suffix('.child.json')\n"
                "subprocess.Popen([sys.executable,'-c',child,str(ready),'ignore'])\n"
                "limit=time.monotonic()+3\n"
                "while not ready.exists() and time.monotonic()<limit:time.sleep(.005)\n"
                "score={'sedge':5,'flora':4,'candidate':3}[out.stem]\n"
                "out.write_text(json.dumps({'srpaths':[],'score':score}))\n", encoding='utf-8')
            solver.chmod(0o700)
            inputs = [root / name for name in ('net.json', 'tm.json', 'scenario.json')]
            for path in inputs:
                path.write_text('{}', encoding='utf-8')
            env = {'PORTFOLIO_SECONDS': '10', 'PORTFOLIO_CHECK_INTERVAL': '.05',
                   'PORTFOLIO_ARTIFACTS': str(root), 'PORTFOLIO_CHECKER': str(checker),
                   'PORTFOLIO_RECEIPT': str(root / 'receipt.json'),
                   **{'PORTFOLIO_' + name: str(solver) for name in ('SEDGE', 'FLORA', 'CANDIDATE')}}
            with patch.dict(os.environ, env):
                engine = supervisor.Supervisor(inputs, root / 'selected.json')
                original_start = engine.start_lanes
                def registered_start():
                    original_start()
                    for lane in engine.lanes:
                        parent = lane['process']
                        parents.append(parent)
                        assert parent.wait(timeout=3) == 0
                        ready = lane['solution'].with_suffix('.child.json')
                        record = json.loads(ready.read_text())
                        children.append(record['pid'])
                        assert record['pgid'] == parent.pid
                engine.start_lanes = registered_start
                if mode == 'runner_exception':
                    def fail_sampling():
                        raise RuntimeError('controlled stop after child startup')
                    engine.sample_rss = fail_sampling
                    try:
                        engine.run()
                    except RuntimeError as error:
                        assert str(error) == 'controlled stop after child startup'
                    else:
                        raise AssertionError('expected controlled runtime error')
                else:
                    assert engine.run() == 0
                    assert json.loads(engine.output.read_text()) == {'srpaths': [], 'score': 3}
                    receipt = json.loads(engine.receipt.read_text())
                    assert receipt['validated'] and receipt['selected_lane'] == 'candidate'
                    assert receipt['maximum_load'] == '3'
                    assert receipt['status'] == 'complete'
            assert until(lambda: all(child_exited(pid) for pid in children)), 'runner cleanup leaked a lane descendant'
        else:
            raise AssertionError('unknown probe: ' + mode)
        print(json.dumps({'probe': mode, 'passed': True, 'children': len(children)}))
    finally:
        # Cleanup does not use the function under test. Even original failures
        # are force-stopped and reaped before this short-lived probe returns.
        for parent in parents:
            try:
                os.killpg(parent.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for parent in parents:
            parent.wait(timeout=3)
        for pid in children:
            if pid not in statuses:
                try:
                    os.waitpid(pid, 0)
                except ChildProcessError:
                    pass
        temporary.cleanup()


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux isolated process-group controls')
class NativeProcessGroups(unittest.TestCase):
    def check_probe(self, mode):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--probe', mode],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record['probe'], mode)
        self.assertTrue(record['passed'])

    def test_exited_leader_does_not_suppress_term(self):
        self.check_probe('orphan_term')

    def test_exited_leader_does_not_suppress_kill(self):
        self.check_probe('orphan_force')

    def test_live_group_receives_term(self):
        self.check_probe('live_term')

    def test_term_then_kill_reaches_surviving_child(self):
        self.check_probe('escalate')

    def test_missing_group_and_none_are_idempotent(self):
        self.check_probe('idempotent')

    def test_unrelated_group_remains_alive(self):
        self.check_probe('isolation')

    def test_begin_stop_reaches_exited_lane_group(self):
        self.check_probe('begin_stop')

    def test_completed_portfolio_reaps_lane_groups_and_keeps_best(self):
        self.check_probe('runner_complete')

    def test_exception_cleanup_reaches_exited_lane_groups(self):
        self.check_probe('runner_exception')


class NonPosixControls(unittest.TestCase):
    def test_finished_non_posix_process_is_untouched(self):
        process = Mock()
        process.poll.return_value = 0
        with patch.object(supervisor.os, 'name', 'nt'):
            supervisor.stop_process(process)
            supervisor.stop_process(process, force=True)
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_live_non_posix_termination_is_unchanged(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(supervisor.os, 'name', 'nt'):
            supervisor.stop_process(process)
            supervisor.stop_process(process, force=True)
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--probe':
        probe(sys.argv[2])
    else:
        unittest.main()
