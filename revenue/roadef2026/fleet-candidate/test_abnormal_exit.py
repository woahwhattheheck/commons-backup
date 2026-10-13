#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Supervisor termination receipts, using real subprocesses and synthetic checker results.

No challenge benchmark or solver quality is measured. The test checker implements
only this fixture protocol; production scheduling, validation, publication and
cleanup run unchanged. A real directory/file collision supplies the I/O failure.
"""
import contextlib
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
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
TARGET = Path(os.environ.get('JOINT_SUPERVISOR', HERE / 'supervisor.py')).resolve()
sys.path.insert(0, str(TARGET.parent))
spec = importlib.util.spec_from_file_location('joint_supervisor_under_test', TARGET)
SUP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SUP)
BASELINE = b'{"srpaths":[]}\n'
BETTER = b'{"srpaths":[],"fixture_rank":"better"}\n'


@unittest.skipUnless(os.name == "posix", "requires executable POSIX subprocess fixtures")
class AbnormalExitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='joint-termination-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inputs = [self.root / (key + '.json') for key in ('net', 'tm', 'scenario')]
        for path in self.inputs:
            path.write_text('{}\n')
        self.output = self.root / 'output.json'
        self.checker = self.script('checker', '''import json, sys
from pathlib import Path
value = json.loads(Path(sys.argv[sys.argv.index('--srpaths') + 1]).read_text())
print(json.dumps({'valid': True, 'saturations': [{'t': 0, 'from': 0, 'to': 1,
    'sat': '1.000000' if value.get('fixture_rank') == 'better' else '2.000000'}]}))
''')
        self.solver = self.script('solver', f'''import sys, time
from pathlib import Path
Path(sys.argv[-1]).write_bytes({BETTER!r})
time.sleep(30)
''')
        env = {'PORTFOLIO_SECONDS': '2', 'PORTFOLIO_CHECK_INTERVAL': '0.05',
               'PORTFOLIO_CHECK_TIMEOUT': '1', 'PORTFOLIO_ARTIFACTS': str(self.root),
               'PORTFOLIO_RECEIPT': str(self.output) + '.portfolio.json',
               'PORTFOLIO_CHECKER': str(self.checker)}
        env.update({'PORTFOLIO_' + key: str(self.solver) for key in ('SEDGE', 'FLORA', 'CANDIDATE')})
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.handlers = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
        self.addCleanup(self.restore_signals)
        self.subject = SUP.Supervisor(self.inputs, self.output)
        self.addCleanup(self.force_cleanup)

    def script(self, name, body):
        path = self.root / name
        path.write_text('#!' + sys.executable + ' -S\n' + body)
        path.chmod(0o700)
        return path

    def restore_signals(self):
        for sig, handler in self.handlers.items():
            signal.signal(sig, handler)

    def force_cleanup(self):
        for lane in self.subject.lanes:
            p = lane.get('process')
            SUP.stop_process(p, force=True)
            if p is not None:
                p.wait(timeout=2)
        check = self.subject.check
        if check is not None:
            SUP.stop_process(check['process'], force=True)
            check['process'].wait(timeout=2)

    def run_quiet(self):
        with contextlib.redirect_stderr(io.StringIO()):
            return self.subject.run()

    def receipt(self):
        return json.loads(self.subject.receipt.read_text())

    def require_error_receipt(self, validated):
        report = self.receipt()
        self.assertEqual(report['status'], 'error')
        self.assertIs(report['validated'], validated)
        self.assertEqual(report['solution_sha256'], self.subject.best_digest)
        for lane in self.subject.lanes:
            if lane.get('process'):
                self.assertIsNotNone(lane['process'].poll())
        return report

    def inject_after_best(self, error, better=True):
        sample = self.subject.sample_rss
        def boundary():
            sample()
            if self.subject.best and (not better or self.subject.best['vector'][0] == 1):
                raise error
        self.subject.sample_rss = boundary

    def test_real_checkpoint_io_failure_is_error_after_validated_baseline(self):
        schedule = self.subject.schedule_check
        def with_collision():
            if self.subject.best:
                digest = hashlib.sha256(BETTER).hexdigest()
                collision = self.subject.work / (digest + '.solution.json')
                collision.mkdir(exist_ok=True)
            schedule()
        self.subject.schedule_check = with_collision
        with self.assertRaises(IsADirectoryError):
            self.run_quiet()
        self.require_error_receipt(True)
        self.assertEqual(self.output.read_bytes(), BASELINE)

    def test_runtime_error_preserves_better_checked_solution_and_exception(self):
        error = RuntimeError('deliberate post-validation boundary')
        self.inject_after_best(error)
        try:
            self.run_quiet()
        except RuntimeError as raised:
            self.assertIs(raised, error)
        else:
            self.fail('original error was swallowed')
        report = self.require_error_receipt(True)
        self.assertEqual(self.output.read_bytes(), BETTER)
        self.assertEqual(report['maximum_load'], '1.000000')

    def test_keyboard_interrupt_stays_abnormal_and_propagates(self):
        error = KeyboardInterrupt('fixture interruption')
        self.inject_after_best(error)
        with self.assertRaises(KeyboardInterrupt) as got:
            self.run_quiet()
        self.assertIs(got.exception, error)
        self.require_error_receipt(True)
        self.assertEqual(self.output.read_bytes(), BETTER)

    def test_system_exit_keeps_original_code_and_validated_output(self):
        error = SystemExit(17)
        self.inject_after_best(error)
        with self.assertRaises(SystemExit) as got:
            self.run_quiet()
        self.assertIs(got.exception, error)
        self.assertEqual(got.exception.code, 17)
        self.require_error_receipt(True)

    def test_before_first_check_error_does_not_invent_validation(self):
        error = RuntimeError('fixture startup')
        def fail_start():
            raise error
        self.subject.start_lanes = fail_start
        with self.assertRaises(RuntimeError) as got:
            self.run_quiet()
        self.assertIs(got.exception, error)
        report = self.require_error_receipt(False)
        self.assertIsNone(report['solution_sha256'])
        self.assertEqual(self.output.read_bytes(), BASELINE)

    def test_error_receipt_identifies_original_exception_type(self):
        error = RuntimeError('fixture type evidence')
        self.inject_after_best(error)
        with self.assertRaises(RuntimeError):
            self.run_quiet()
        report = self.require_error_receipt(True)
        failures = [row for row in report['events'] if row['event'] == 'supervisor_failed']
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]['error_type'], 'RuntimeError')

    def test_failed_final_receipt_preserves_original_error_and_old_atomic_bytes(self):
        error = RuntimeError('original search fault')
        save = self.subject.save_receipt
        saved = []
        def final_io_fault(status):
            if status in ('complete', 'no_validated_solution', 'error'):
                raise OSError('deliberate final-receipt write failure')
            save(status)
            saved[:] = [self.subject.receipt.read_bytes()]
        self.subject.save_receipt = final_io_fault
        self.inject_after_best(error)
        try:
            self.run_quiet()
        except BaseException as got:
            self.assertIs(got, error)
        else:
            self.fail('original search fault disappeared')
        self.assertEqual(self.subject.receipt.read_bytes(), saved[0])
        self.assertEqual(self.receipt()['status'], 'running')
        self.assertEqual(self.output.read_bytes(), BETTER)

    def test_failed_failure_event_does_not_prevent_error_receipt(self):
        error = KeyboardInterrupt('original interruption')
        emit = self.subject.emit
        def closed_log(event, **fields):
            if event == 'supervisor_failed':
                raise BrokenPipeError('closed diagnostics stream')
            return emit(event, **fields)
        self.subject.emit = closed_log
        self.inject_after_best(error)
        with self.assertRaises(KeyboardInterrupt) as got:
            self.run_quiet()
        self.assertIs(got.exception, error)
        self.require_error_receipt(True)

    def test_normal_final_receipt_failure_is_not_swallowed(self):
        self.solver.write_text('#!' + sys.executable + ' -S\nfrom pathlib import Path\nimport sys\n'
                               + f'Path(sys.argv[-1]).write_bytes({BETTER!r})\n')
        error = OSError('normal final-receipt fault')
        save = self.subject.save_receipt
        def fail_complete(status):
            if status == 'complete':
                raise error
            return save(status)
        self.subject.save_receipt = fail_complete
        with self.assertRaises(OSError) as got:
            self.run_quiet()
        self.assertIs(got.exception, error)
        self.assertEqual(self.receipt()['status'], 'running')
        self.assertEqual(self.output.read_bytes(), BETTER)

    def test_normal_finished_search_retains_complete(self):
        self.solver.write_text('#!' + sys.executable + ' -S\nfrom pathlib import Path\nimport sys\n'
                               + f'Path(sys.argv[-1]).write_bytes({BETTER!r})\n')
        self.assertEqual(self.run_quiet(), 0)
        self.assertEqual(self.receipt()['status'], 'complete')
        self.assertTrue(self.receipt()['validated'])
        self.assertEqual(self.output.read_bytes(), BETTER)

    def test_normal_invalid_run_retains_no_validated_solution(self):
        self.checker.write_text('#!' + sys.executable + ' -S\nprint(\'{"valid":false}\')\n')
        self.solver.write_text('#!' + sys.executable + ' -S\nfrom pathlib import Path\nimport sys\n'
                               + f'Path(sys.argv[-1]).write_bytes({BETTER!r})\n')
        self.assertEqual(self.run_quiet(), 1)
        self.assertEqual(self.receipt()['status'], 'no_validated_solution')
        self.assertFalse(self.receipt()['validated'])
        self.assertEqual(self.output.read_bytes(), BASELINE)

    def test_handled_termination_keeps_existing_signal_semantics(self):
        sample = self.subject.sample_rss
        def request_stop():
            sample()
            if self.subject.best and self.subject.best['vector'][0] == 1:
                self.subject.signal_handler(signal.SIGTERM, None)
        self.subject.sample_rss = request_stop
        self.assertEqual(self.run_quiet(), 0)
        self.assertEqual(self.receipt()['status'], 'complete')
        self.assertEqual(self.receipt()['signal_received'], signal.SIGTERM)
        self.assertEqual(self.output.read_bytes(), BETTER)


if __name__ == '__main__':
    unittest.main(verbosity=2)
