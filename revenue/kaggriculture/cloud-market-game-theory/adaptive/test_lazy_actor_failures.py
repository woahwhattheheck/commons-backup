# SPDX-License-Identifier: Apache-2.0
"""Failure retention at the existing coordinator's actual subprocess boundary.

Child programs are explicit coordinator fixtures, not policies or engine games.
No timing experiment, network, source export, or provider execution is started.
"""
import argparse
from contextlib import redirect_stdout
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCHMARK = Path(__file__).with_name('bench_lazy_actor.py')
B = None
REAL_RUN = subprocess.run


def load_benchmark():
    spec = importlib.util.spec_from_file_location('cove_failure_subject', BENCHMARK)
    module = importlib.util.module_from_spec(spec)
    exec(compile(BENCHMARK.read_bytes(), str(BENCHMARK), 'exec'), module.__dict__)
    return module


class FailureRetentionTests(unittest.TestCase):
    def setUp(self):
        self.b = load_benchmark()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        runtime = self.source / self.b.RUNTIME
        runtime.parent.mkdir(parents=True)
        runtime.write_text('offers = (self._offers(cfg, base) if ready else ())\n')
        self.profiler = self.root / 'profiler.py'
        self.profiler.write_text('def load_execution_receipt(path):\n return {"candidate_pythonhashseed": 7}, None\n')
        for name in ('timing.py', 'input.json', 'receipt.json'):
            (self.root / name).write_text('{}')
        self.output = self.root / 'output'
        self.command_calls = []
        self.fixture_timeout = None

    def invoke(self, launch):
        argv = ['bench', '--profiler', str(self.profiler), '--source-root', str(self.source),
                '--timing-source', str(self.root/'timing.py'), '--input', str(self.root/'input.json'),
                '--receipt', str(self.root/'receipt.json'), '--output', str(self.output), '--rounds', '1']
        def call(command, **kwargs):
            self.command_calls.append((command, kwargs))
            return launch(command, **kwargs)
        with patch.object(sys, 'argv', argv), patch.object(self.b.subprocess, 'run', side_effect=call), redirect_stdout(io.StringIO()):
            return self.b.main()

    def receipt(self):
        path = self.output/'FAILURE.json'
        self.assertTrue(path.is_file(), 'failed child lacks FAILURE.json')
        return json.loads(path.read_text())

    def real_timeout(self, command, **kwargs):
        code = 'import os,time;os.write(1,b"out\\xff\\n");os.write(2,b"err\\x00\\n");time.sleep(10)'
        try:
            return REAL_RUN([sys.executable, '-S', '-c', code], capture_output=True, timeout=1.0)
        except subprocess.TimeoutExpired as error:
            self.fixture_timeout = error
            raise

    def successful_child(self, command, **kwargs):
        output = Path(command[command.index('--output')+1])
        if '--trace-worker' in command:
            value = {'status':'complete', 'sources_unchanged':True, 'input':{'id':'fixture'},
                'records':[{'step':1, 'action':{'market':[]}, 'state':{'selected':'same'},
                 'inputs_unchanged':True, 'work':{'captured_windows':1, 'inspected_windows':1, 'compiled_windows':1}}]}
            output.write_bytes(gzip.compress(self.b.canonical(value)))
        else:
            value = {'status':'complete', 'sources_unchanged':True, 'calls':[{'wall_s':1.0}],
                 'action_sequence_sha256':'fixture-action', 'p99_call_s':1.0,
                 'target_load_through_first_attempt_wall_s':0.1,
                 'expected_actions':{'mismatches':0}, 'environment':{'fixture':True}}
            output.write_text(json.dumps(value))
        return subprocess.CompletedProcess(command, 0, b'fixture-out\n', b'fixture-err\n')

    def test_ordinary_timeout_saves_exact_binary_streams(self):
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            self.invoke(self.real_timeout)
        self.assertIs(caught.exception, self.fixture_timeout)
        expected = b'out\xff\nerr\x00\n'
        self.assertEqual(self.fixture_timeout.stdout+self.fixture_timeout.stderr, expected)
        log = self.output/'0-lazy.log'
        self.assertTrue(log.is_file(), 'timeout discarded captured output')
        self.assertEqual(log.read_bytes(), expected)
        r = self.receipt()
        self.assertEqual((r['kind'],r['phase'],r['timeout_seconds']),('timeout','lazy pass',1.0))
        self.assertFalse(r['complete']); self.assertFalse(r['child_output_validated'])
        self.assertEqual(r['captured_log_sha256'],hashlib.sha256(expected).hexdigest())
        self.assertFalse((self.output/'RESULTS.json').exists())

    def test_trace_timeout_retains_earlier_measurements(self):
        saved = {}
        def launch(command, **kw):
            if '--trace-worker' in command:
                return self.real_timeout(command, **kw)
            result = self.successful_child(command, **kw)
            p = Path(command[command.index('--output')+1]); saved[p.name]=p.read_bytes()
            return result
        with self.assertRaises(subprocess.TimeoutExpired): self.invoke(launch)
        self.assertEqual(len(saved),2)
        for name, data in saved.items(): self.assertEqual((self.output/name).read_bytes(),data)
        log=self.output/'lazy-trace.log'
        self.assertTrue(log.is_file(), 'trace timeout discarded captured output')
        self.assertEqual(log.read_bytes(), b'out\xff\nerr\x00\n')
        self.assertEqual(self.receipt()['phase'],'lazy trace')
        self.assertFalse((self.output/'RESULTS.json').exists())

    def test_nonzero_real_child_preserves_partial_output_without_validating_it(self):
        def launch(command, **kw):
            output=command[command.index('--output')+1]
            code='import os,sys;open(sys.argv[1],"wb").write(b"partial");os.write(1,b"failed-out");os.write(2,b"failed-err");sys.exit(17)'
            return REAL_RUN([sys.executable,'-S','-c',code,output],capture_output=True,timeout=5)
        with self.assertRaisesRegex(RuntimeError,'lazy pass failed; retained'): self.invoke(launch)
        self.assertEqual((self.output/'0-lazy.json').read_bytes(),b'partial')
        self.assertEqual((self.output/'0-lazy.log').read_bytes(),b'failed-outfailed-err')
        r=self.receipt(); self.assertEqual((r['kind'],r['returncode']),('exit',17))
        self.assertTrue(r['child_output_present']); self.assertFalse(r['child_output_validated'])

    def test_launch_error_keeps_identity_and_disposition(self):
        error=FileNotFoundError('fixture missing program')
        def launch(*a,**k): raise error
        with self.assertRaises(FileNotFoundError) as caught: self.invoke(launch)
        self.assertIs(caught.exception,error)
        r=self.receipt(); self.assertEqual((r['kind'],r['error_type']),('launch','FileNotFoundError'))
        self.assertIsNone(r['returncode']); self.assertEqual((self.output/'0-lazy.log').read_bytes(),b'')

    def test_missing_timeout_streams_create_empty_log(self):
        error=subprocess.TimeoutExpired(['fixture'],180)
        def launch(*a,**k): raise error
        with self.assertRaises(subprocess.TimeoutExpired) as caught: self.invoke(launch)
        self.assertIs(caught.exception,error)
        path=self.output/'0-lazy.log';self.assertTrue(path.is_file())
        self.assertEqual(path.read_bytes(),b'');self.assertEqual(self.receipt()['captured_log_bytes'],0)

    def test_failed_atomic_receipt_write_keeps_original_exception_and_prior_receipt(self):
        error=subprocess.TimeoutExpired(['fixture'],180,output=b'captured')
        def launch(*a,**k):
            (self.output/'FAILURE.json').write_bytes(b'previous-whole-receipt')
            raise error
        with patch.object(self.b.os,'replace',side_effect=OSError('fixture disk error')):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:self.invoke(launch)
        self.assertIs(caught.exception,error)
        self.assertEqual((self.output/'FAILURE.json').read_bytes(),b'previous-whole-receipt')
        self.assertFalse(list(self.output.glob('.child-failure-*.tmp')))
        self.assertIn('record:OSError',' '.join(getattr(error,'__notes__',[])))
        self.assertEqual((self.output/'0-lazy.log').read_bytes(),b'captured')

    def test_log_write_failure_still_retains_failure_record(self):
        error=subprocess.TimeoutExpired(['fixture'],180,output=b'captured')
        original=Path.write_bytes
        def write(path,data):
            if path.suffix=='.log':raise OSError('fixture log write failure')
            return original(path,data)
        def launch(*a,**k):raise error
        with patch.object(Path,'write_bytes',write):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:self.invoke(launch)
        self.assertIs(caught.exception,error)
        self.assertEqual(self.receipt()['retention_errors'],['log:OSError'])
        self.assertIn('log:OSError',' '.join(getattr(error,'__notes__',[])))

    def test_successful_pipeline_keeps_deadline_results_and_logs(self):
        self.assertEqual(self.invoke(self.successful_child),0)
        self.assertEqual(len(self.command_calls),4)
        for _,kw in self.command_calls:
            self.assertEqual(kw['timeout'],180);self.assertTrue(kw['capture_output'])
            self.assertEqual(kw['env']['PYTHONHASHSEED'],'7')
        r=json.loads((self.output/'RESULTS.json').read_text())
        self.assertTrue(r['comparison']['complete_correspondence'])
        self.assertEqual(r['timing']['median_action_time_reduction_pct'],0)
        self.assertEqual(len(list(self.output.glob('*.log'))),4)
        self.assertFalse((self.output/'FAILURE.json').exists())

    def test_nonzero_trace_disposition_retains_completed_pass_files(self):
        def launch(command,**kw):
            if '--trace-worker' not in command:return self.successful_child(command,**kw)
            return subprocess.CompletedProcess(command,2,b'trace-partial',b'trace-error')
        with self.assertRaisesRegex(RuntimeError,'lazy trace failed; retained'):self.invoke(launch)
        self.assertTrue((self.output/'0-lazy.json').is_file())
        self.assertTrue((self.output/'0-eager.json').is_file())
        self.assertEqual((self.output/'lazy-trace.log').read_bytes(),b'trace-partialtrace-error')
        r=self.receipt();self.assertEqual((r['phase'],r['returncode']),('lazy trace',2))
        self.assertFalse(r['child_output_present']);self.assertFalse(r['complete'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark',type=Path,default=BENCHMARK)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();BENCHMARK=args.benchmark.resolve()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FailureRetentionTests))
    if args.report:
        source=BENCHMARK.read_bytes()
        record={'benchmark_sha256':hashlib.sha256(source).hexdigest(),
                'tests':result.testsRun,'failures':[str(t) for t,_ in result.failures],
                'errors':[str(t) for t,_ in result.errors],'skipped':result.skipped,
                'successful':result.wasSuccessful(),'policy_calls':0,'engine_calls':0,
                'scope':'coordinator fixtures; two real timeout children and one nonzero-exit child'}
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(record,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
