# SPDX-License-Identifier: Apache-2.0
"""Run-state publication tests; synthetic jobs, never policy games.

Set TRIAD_PANEL_SOURCE to test a separate source file. A legacy writer fallback
is only used to exercise the exact pre-change main() write expression.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SOURCE = Path(os.environ.get('TRIAD_PANEL_SOURCE', Path(__file__).with_name('run_panel.py'))).resolve()
spec = importlib.util.spec_from_file_location('triad_run_state_target', SOURCE)
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)


def write_state(path, records):
    if hasattr(panel, 'write_run_state'):
        return panel.write_run_state(path, records)
    # Exact original run_panel.main expression, not a replacement implementation.
    return path.write_text(json.dumps(records, indent=2) + '\n')


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / 'output'
        self.out.mkdir()
        self.state = self.out / 'run-state.json'
        self.prior = b'[{"prior": "intact"}]\n'
        self.state.write_bytes(self.prior)

    def invoke(self, arms, worker, jobs=2, printer=None):
        cfg = self.root / 'config.json'
        cfg.write_text(json.dumps({'seeds': {'first': 12, 'last': 12, 'shard_size': 1},
                                   'arms': {arm: arm + '.py' for arm in arms},
                                   'evaluator': 'fixture.py', 'engine': 'fixture-engine',
                                   'opponents': ['fixture-opponent']}))
        argv = [str(SOURCE), '--config', str(cfg), '--output', str(self.out), '--jobs', str(jobs)]
        with patch.object(sys, 'argv', argv), patch.object(panel, 'run_job', side_effect=worker):
            with contextlib.redirect_stdout(io.StringIO()):
                if printer is not None:
                    with patch('builtins.print', side_effect=printer):
                        return panel.main()
                return panel.main()

    def rows(self):
        return json.loads(self.state.read_text())

    def test_success_shape_and_exact_returned_values(self):
        def worker(job, *args):
            return {**job, 'status': 'complete', 'returncode': 0, 'custom': {'kept': True}}
        self.assertEqual(self.invoke(['a', 'b'], worker), 0)
        self.assertEqual({r['arm'] for r in self.rows()}, {'a', 'b'})
        self.assertTrue(all(r['custom'] == {'kept': True} for r in self.rows()))

    def test_failed_then_successful_sibling_is_recorded(self):
        error = ValueError('fixture worker failure')
        def worker(job, *args):
            if job['arm'] == 'bad':
                raise error
            time.sleep(.04)
            return {**job, 'status': 'complete', 'custom': 'returned'}
        with self.assertRaises(ValueError) as caught:
            self.invoke(['bad', 'good'], worker)
        self.assertIs(caught.exception, error)
        rows = {r.get('arm'): r for r in self.rows()}
        self.assertEqual(set(rows), {'bad', 'good'})
        self.assertEqual(rows['good']['custom'], 'returned')
        self.assertEqual(rows['bad']['failure'], {'kind': 'runner_exception',
                                                 'type': 'ValueError', 'message': str(error)})
        self.assertNotIn('games', rows['bad'])

    def test_success_then_failed_sibling_is_recorded(self):
        def worker(job, *args):
            if job['arm'] == 'bad':
                time.sleep(.04)
                raise OSError('fixture io failure')
            return {**job, 'status': 'complete'}
        with self.assertRaises(OSError):
            self.invoke(['good', 'bad'], worker)
        self.assertEqual({r.get('arm') for r in self.rows()}, {'good', 'bad'})

    def test_multiple_failures_keep_first_exception_and_no_retries(self):
        calls = []; lock = threading.Lock(); error = ValueError('first worker failure')
        def worker(job, *args):
            with lock:
                calls.append(job['arm'])
            if job['arm'] == 'first':
                raise error
            if job['arm'] == 'second':
                time.sleep(.04)
                raise OSError('second worker failure')
            time.sleep(.08)
            return {**job, 'status': 'complete'}
        with self.assertRaises(ValueError) as caught:
            self.invoke(['first', 'second', 'good'], worker, jobs=3)
        self.assertIs(caught.exception, error)
        self.assertCountEqual(calls, ['first', 'second', 'good'])
        self.assertEqual(len(self.rows()), 3)
        self.assertEqual(sum(r.get('status') == 'failed' for r in self.rows()), 2)

    def test_returned_failure_keeps_existing_nonzero_contract(self):
        record = {'arm': 'a', 'status': 'failed', 'returncode': 7, 'report': 'existing.json'}
        self.assertEqual(self.invoke(['a'], lambda *args: record), 1)
        self.assertEqual(self.rows(), [record])

    def test_reused_report_is_not_changed_or_rerun(self):
        record = {'arm': 'a', 'status': 'reused-complete', 'report': 'old.json', 'sha256': 'retained'}
        calls = []
        def worker(*args):
            calls.append(1); return record
        self.assertEqual(self.invoke(['a'], worker), 0)
        self.assertEqual(calls, [1]); self.assertEqual(self.rows(), [record])

    def test_baseexception_is_not_converted_to_a_completed_attempt(self):
        for error in (KeyboardInterrupt('interrupt'), SystemExit(6)):
            with self.subTest(kind=type(error).__name__):
                self.state.write_bytes(self.prior)
                def worker(*args):
                    raise error
                with self.assertRaises(type(error)) as caught:
                    self.invoke(['a'], worker, jobs=1)
                self.assertIs(caught.exception, error)
                self.assertEqual(self.state.read_bytes(), self.prior)

    def test_checkpoint_precedes_stdout_notification(self):
        record = {'arm': 'a', 'status': 'complete'}
        with self.assertRaises(BrokenPipeError):
            self.invoke(['a'], lambda *args: record, printer=BrokenPipeError('fixture pipe'))
        self.assertEqual(self.rows(), [record])

    def test_serialization_failure_leaves_previous_checkpoint(self):
        with self.assertRaises(TypeError):
            write_state(self.state, [{'not_json': object()}])
        self.assertEqual(self.state.read_bytes(), self.prior)
        self.assertEqual(list(self.out.glob('.run-state.json.*')), [])

    def test_exact_utf8_success_bytes_and_no_stage_leftovers(self):
        rows = [{'name': 'café 日本語', 'status': 'complete'}]
        write_state(self.state, rows)
        self.assertEqual(self.state.read_bytes(), (json.dumps(rows, indent=2) + '\n').encode('utf-8'))
        self.assertEqual(list(self.out.glob('.run-state.json.*')), [])

    def test_replace_failure_preserves_previous_bytes(self):
        if not hasattr(panel, 'write_run_state'):
            self.fail('Legacy main writes in place without an atomic replacement')
        with patch.object(panel.os, 'replace', side_effect=OSError('replace failed')):
            with self.assertRaisesRegex(OSError, 'replace failed'):
                write_state(self.state, [{'new': True}])
        self.assertEqual(self.state.read_bytes(), self.prior)
        self.assertEqual(list(self.out.glob('.run-state.json.*')), [])

    def test_fsync_failure_preserves_previous_bytes(self):
        if not hasattr(panel, 'write_run_state'):
            self.fail('Legacy main replaces contents before complete staging')
        with patch.object(panel.os, 'fsync', side_effect=OSError('fsync failed')):
            with self.assertRaisesRegex(OSError, 'fsync failed'):
                write_state(self.state, [{'new': True}])
        self.assertEqual(self.state.read_bytes(), self.prior)

    def test_short_write_detected_and_previous_preserved(self):
        if not hasattr(panel, 'write_run_state'):
            self.fail('Legacy main has no complete staged-write check')
        original = panel.tempfile.NamedTemporaryFile
        class ShortWriter:
            def __init__(self, *a, **kw):
                self.stream = original(*a, **kw)
                self.name = self.stream.name
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def write(self, body): return self.stream.write(body[:7])
        with patch.object(panel.tempfile, 'NamedTemporaryFile', ShortWriter):
            with self.assertRaisesRegex(OSError, 'Short run-state'):
                write_state(self.state, [{'long': 'x' * 200}])
        self.assertEqual(self.state.read_bytes(), self.prior)
        self.assertEqual(list(self.out.glob('.run-state.json.*')), [])

    def test_secondary_checkpoint_failure_keeps_original_worker_exception(self):
        error = ValueError('primary worker error')
        def worker(*args): raise error
        if not hasattr(panel, 'write_run_state'):
            with self.assertRaises(ValueError) as caught:
                self.invoke(['a'], worker)
            self.assertIs(caught.exception, error)
            return
        with patch.object(panel, 'write_run_state', side_effect=OSError('secondary write error')):
            with self.assertRaises(ValueError) as caught:
                self.invoke(['a'], worker)
        self.assertIs(caught.exception, error)
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertEqual(self.state.read_bytes(), self.prior)

    def test_checkpoint_error_without_worker_error_propagates(self):
        def worker(job, *args): return {**job, 'status': 'complete'}
        if not hasattr(panel, 'write_run_state'):
            self.fail('Legacy main has no atomic checkpoint boundary')
        error = OSError('publication failed')
        with patch.object(panel, 'write_run_state', side_effect=error):
            with self.assertRaises(OSError) as caught:
                self.invoke(['a'], worker)
        self.assertIs(caught.exception, error)
        self.assertEqual(self.state.read_bytes(), self.prior)

    def test_cleanup_failure_does_not_hide_original_write_failure(self):
        if not hasattr(panel, 'write_run_state'):
            self.fail('Legacy main has no staged checkpoint cleanup')
        with patch.object(panel.os, 'replace', side_effect=OSError('original replace failure')):
            with patch.object(Path, 'unlink', side_effect=PermissionError('cleanup failure')):
                with self.assertRaisesRegex(OSError, 'original replace failure'):
                    write_state(self.state, [{'new': True}])
        self.assertEqual(self.state.read_bytes(), self.prior)
        self.assertEqual(len(list(self.out.glob('.run-state.json.*'))), 1)

    def test_real_child_hard_exit_during_write_preserves_prior(self):
        script = self.root / 'hard_exit.py'
        script.write_text('''import importlib.util, json, os, sys
from pathlib import Path
s=importlib.util.spec_from_file_location('target',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
p=Path(sys.argv[2]); data=[{'next':'x'*5000}]
if hasattr(m,'write_run_state'):
    original=m.tempfile.NamedTemporaryFile
    class KillWriter:
        def __init__(self,*a,**kw): self.f=original(*a,**kw); self.name=self.f.name
        def __enter__(self): return self
        def __exit__(self,*a): self.f.close()
        def write(self,b): self.f.write(b[:17]); self.f.flush(); os._exit(71)
    m.tempfile.NamedTemporaryFile=KillWriter
    m.write_run_state(p,data)
else:
    original=Path.write_text
    def partial(self,body,*a,**kw):
        with self.open('w') as f: f.write(body[:17]); f.flush(); os._exit(71)
    Path.write_text=partial
    p.write_text(json.dumps(data,indent=2)+'\\n')
''')
        proc = subprocess.run([sys.executable, str(script), str(SOURCE), str(self.state)], timeout=8,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 71, proc.stderr)
        self.assertEqual(self.state.read_bytes(), self.prior)

    def test_real_worker_process_error_does_not_lose_sibling(self):
        # A real process boundary below main, independent of TANDEM's report
        # identity/reuse logic. This replaces only run_job with a fixture worker.
        driver = self.root / 'process_driver.py'
        driver.write_text("""import importlib.util, json, os, subprocess, sys
from pathlib import Path
s=importlib.util.spec_from_file_location('target',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
fixture = "import os,sys,time; from pathlib import Path; bad=sys.argv[1]=='bad'; time.sleep(0 if bad else .10); os.write(1,bytes([255])) if bad else Path(sys.argv[2]).write_text('fixture returned')"
def run_job(job,evaluator,engine,opponents,out):
    result=out/(job['arm']+'.returned')
    subprocess.run([sys.executable,'-c',fixture,job['arm'],str(result)],
                   text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True)
    return {**job,'status':'complete','fixture_returned':result.read_text()}
m.run_job=run_job
sys.argv=[sys.argv[1]]+sys.argv[2:]
raise SystemExit(m.main())
""")
        cfg = self.root / 'real.json'
        cfg.write_text(json.dumps({'seeds': {'first': 12, 'last': 12, 'shard_size': 1},
                                   'arms': {'bad': 'bad', 'good': 'good'},
                                   'evaluator': 'fixture', 'engine': str(self.root),
                                   'opponents': ['fixture']}))
        proc = subprocess.run([sys.executable, str(driver), str(SOURCE), '--config', str(cfg),
                               '--output', str(self.out), '--jobs', '2'], capture_output=True,
                              text=True, timeout=8)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('UnicodeDecodeError', proc.stderr)
        self.assertTrue((self.out / 'good.returned').is_file())
        rows = {r.get('arm'): r for r in self.rows()}
        self.assertEqual(set(rows), {'bad', 'good'})
        self.assertEqual(rows['bad']['failure']['type'], 'UnicodeDecodeError')
        self.assertEqual(rows['good']['fixture_returned'], 'fixture returned')

    def test_all_returned_rows_survive_reordered_completions(self):
        lock = threading.Lock(); calls = []
        def worker(job, *args):
            time.sleep((4 - int(job['arm'])) * .01)
            with lock: calls.append(job['arm'])
            return {**job, 'status': 'complete', 'marker': job['arm']}
        self.assertEqual(self.invoke(['1', '2', '3', '4'], worker, jobs=4), 0)
        self.assertCountEqual(calls, ['1', '2', '3', '4'])
        self.assertEqual(len(self.rows()), 4)
        self.assertTrue(all(r['marker'] == r['arm'] for r in self.rows()))


if __name__ == '__main__':
    unittest.main()
