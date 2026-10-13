"""Exercise benchmark retention with actual children and temporary file faults."""
from __future__ import annotations
import ast
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import benchmark_stream as benchmark
from test_stream_observations import fixture

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get('T07_COK_SOURCE', HERE/'sources/cok-v10/main.py'))
PACK = Path(os.environ.get('T07_PACK', HERE.parent/'cloud-pack'))


class BenchmarkCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.input = self.root/'input.jsonl'
        self.output = self.root/'measurement'
        self.input.write_text(json.dumps({'observation': fixture()})+'\n', encoding='utf-8')
        self.args = ['--source',str(SOURCE), '--pack',str(PACK), '--input',str(self.input),
                     '--output-dir',str(self.output)]
        self.real_run = subprocess.run

    def invoke(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return benchmark.main(self.args)

    def report(self):
        path = self.output/'benchmark.json'
        self.assertTrue(path.exists(), 'The returned measurement needs a durable report')
        return json.loads(path.read_text(encoding='utf-8'))

    def test_success_keeps_exact_worker_outputs_and_comparison(self):
        before = self.input.read_bytes()
        self.assertEqual(self.invoke(), 0)
        result = self.report()
        self.assertIs(result.get('complete'), True)
        self.assertIsNone(result['failure'])
        self.assertIsNone(result['active_worker'])
        self.assertEqual([r['status'] for r in result['attempts']], ['completed','completed'])
        self.assertTrue(result['input_unchanged'])
        for kind in ('telemetry','summary'):
            self.assertTrue(result[kind+'_bytes_equal'])
        self.assertEqual(self.input.read_bytes(), before)
        self.assertEqual((self.output/'baseline.jsonl').read_bytes(), (self.output/'stream.jsonl').read_bytes())
        self.assertEqual((self.output/'baseline-summary.json').read_bytes(), (self.output/'stream-summary.json').read_bytes())
        for item in result['results']:
            self.assertEqual(item['calls'], 1)
            self.assertEqual(item['telemetry_errors'], 0)
            self.assertGreater(item['python_peak_bytes'], 0)
        expected = 1-result['results'][1]['python_peak_bytes']/result['results'][0]['python_peak_bytes']
        self.assertEqual(result['peak_python_memory_reduction_fraction'], expected)

    def test_second_real_worker_failure_keeps_first_exact_result(self):
        measurements, errors, modes = [], [], []
        def dispatch(command, **kwargs):
            modes.append(command[-1])
            if command[-1] == 'stream': self.input.write_text('{invalid\n',encoding='utf-8')
            try:
                completed = self.real_run(command, **kwargs)
            except subprocess.CalledProcessError as exc:
                errors.append(exc)
                raise
            measurements.append(json.loads(completed.stdout))
            return completed
        with patch.object(benchmark.subprocess,'run',side_effect=dispatch):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                self.invoke()
        self.assertIs(raised.exception, errors[0])
        result = self.report()
        self.assertEqual(result['results'], measurements)
        self.assertEqual(modes, ['baseline','stream'])
        self.assertFalse(result['complete'])
        self.assertFalse(result['input_unchanged'])
        self.assertIsNone(result['telemetry_bytes_equal'])
        self.assertEqual(result['attempts'][1]['status'],'failed')
        self.assertEqual(result['attempts'][1]['returncode'],errors[0].returncode)
        self.assertEqual(result['attempts'][1]['stderr'],errors[0].stderr)
        self.assertEqual(result['failure']['stage'],'worker')

    def test_first_real_worker_failure_does_not_start_second(self):
        self.input.write_text('{invalid\n',encoding='utf-8')
        modes=[]
        def dispatch(command, **kwargs):
            modes.append(command[-1]); return self.real_run(command,**kwargs)
        with patch.object(benchmark.subprocess,'run',side_effect=dispatch):
            with self.assertRaises(subprocess.CalledProcessError): self.invoke()
        result=self.report()
        self.assertEqual(modes,['baseline'])
        self.assertEqual(result['results'],[])
        self.assertEqual(result['attempts'][0]['status'],'failed')
        self.assertFalse(result['complete'])

    def parent_exit(self, mode):
        script=self.root/'exit_parent.py'
        script.write_text('import os,sys,subprocess\nfrom unittest.mock import patch\n'
            +f'sys.path.insert(0,{str(HERE)!r})\nimport benchmark_stream as b\n'
            +'real=subprocess.run\n'
            +'def run(command,**kwargs):\n'
            +f' if command[-1]=={mode!r}: os._exit(73)\n'
            +' return real(command,**kwargs)\n'
            +'with patch.object(b.subprocess,"run",side_effect=run):\n'
            +f' b.main({self.args!r})\n',encoding='utf-8')
        process=self.real_run([sys.executable,'-B',str(script)],capture_output=True,text=True,timeout=20)
        self.assertEqual(process.returncode,73,process.stderr)
        return self.report()

    def test_real_parent_exit_before_second_worker_keeps_baseline(self):
        result=self.parent_exit('stream')
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['results']),1)
        self.assertEqual(result['results'][0]['runner'],'baseline')
        self.assertEqual([r['status'] for r in result['attempts']],['completed','running'])
        self.assertEqual(result['active_worker'],'stream')
        self.assertFalse((self.output/'stream.jsonl').exists())

    def test_real_parent_exit_before_first_worker_is_explicitly_incomplete(self):
        result=self.parent_exit('baseline')
        self.assertFalse(result['complete'])
        self.assertEqual(result['results'],[])
        self.assertEqual(result['active_worker'],'baseline')
        self.assertEqual(result['attempts'][0]['status'],'running')

    def test_bad_json_from_exited_worker_keeps_previous_result(self):
        original=[]
        def dispatch(command,**kwargs):
            process=self.real_run(command,**kwargs)
            if command[-1]=='stream': process.stdout='not json\n'
            else: original.append(json.loads(process.stdout))
            return process
        with patch.object(benchmark.subprocess,'run',side_effect=dispatch):
            with self.assertRaises(json.JSONDecodeError): self.invoke()
        result=self.report()
        self.assertEqual(result['results'],original)
        self.assertFalse(result['complete'])
        self.assertEqual(result['failure']['stage'],'measurement')
        self.assertEqual(result['attempts'][1]['returncode'],0)
        self.assertEqual(result['attempts'][1]['stdout'],'not json\n')

    def test_measurement_shape_retains_complete_result_without_coercion(self):
        self.assertTrue(hasattr(benchmark,'_measurement'))
        original={'runner':'baseline','calls':1,'actors':1,'telemetry_errors':0,
                  'python_peak_bytes':100,'instrumented_seconds':0.5,
                  'telemetry_sha256':'a'*64,'summary_sha256':'b'*64,'future_field':{'kept':True}}
        self.assertEqual(benchmark._measurement(json.dumps(original),'baseline'),original)
        for change in ({'runner':'stream'}, {'calls':True}, {'actors':-1}, {'telemetry_errors':None},
                       {'python_peak_bytes':0}, {'instrumented_seconds':float('inf')},
                       {'instrumented_seconds':False}, {'telemetry_sha256':'not a digest'},
                       {'summary_sha256':'g'*64}):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    benchmark._measurement(json.dumps(original | change),'baseline')
        for value in (None,[],42,{}, {'runner':'baseline'}):
            with self.assertRaises(ValueError): benchmark._measurement(json.dumps(value),'baseline')

    def check_atomic(self, fault):
        self.assertTrue(hasattr(benchmark,'_write_checkpoint'))
        destination=self.root/'checkpoint.json'; destination.write_bytes(b'previous exact bytes\n')
        with fault:
            with self.assertRaises((OSError,TypeError)):
                benchmark._write_checkpoint(destination,{'value':3})
        self.assertEqual(destination.read_bytes(),b'previous exact bytes\n')
        self.assertFalse(list(self.root.glob('.checkpoint.json.*')))

    def test_serialization_error_retains_previous_checkpoint(self):
        self.check_atomic(patch.object(benchmark.json,'dump',side_effect=TypeError('injected serialization')))

    def test_fsync_error_retains_previous_checkpoint(self):
        self.assertTrue(hasattr(benchmark,'_write_checkpoint'))
        self.check_atomic(patch.object(benchmark.os,'fsync',side_effect=OSError('injected sync')))

    def test_replace_error_retains_previous_checkpoint(self):
        self.assertTrue(hasattr(benchmark,'_write_checkpoint'))
        self.check_atomic(patch.object(benchmark.os,'replace',side_effect=OSError('injected replacement')))

    def test_failure_checkpoint_error_does_not_mask_original_exception(self):
        self.assertTrue(hasattr(benchmark,'_write_checkpoint'))
        write=benchmark._write_checkpoint; errors=[]
        def persist(path,result):
            if result['failure'] is not None: raise OSError('checkpoint unavailable')
            return write(path,result)
        def dispatch(command,**kwargs):
            if command[-1]=='stream': self.input.write_text('{invalid\n')
            try: return self.real_run(command,**kwargs)
            except subprocess.CalledProcessError as exc: errors.append(exc); raise
        with patch.object(benchmark,'_write_checkpoint',side_effect=persist), \
                patch.object(benchmark.subprocess,'run',side_effect=dispatch):
            with self.assertRaises(subprocess.CalledProcessError) as raised: self.invoke()
        self.assertIs(raised.exception,errors[0])
        self.assertIn('not saved',raised.exception.__notes__[0])
        result=self.report()
        self.assertFalse(result['complete']); self.assertEqual(len(result['results']),1)
        self.assertEqual(result['attempts'][1]['status'],'running')

    def test_final_write_failure_retains_two_completed_measurements(self):
        self.assertTrue(hasattr(benchmark,'_write_checkpoint'))
        actual=benchmark._write_checkpoint
        def persist(path,result):
            if result['complete']: raise OSError('final checkpoint unavailable')
            return actual(path,result)
        with patch.object(benchmark,'_write_checkpoint',side_effect=persist):
            with self.assertRaisesRegex(OSError,'final checkpoint'): self.invoke()
        result=self.report()
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['results']),2)
        self.assertEqual([r['status'] for r in result['attempts']],['completed','completed'])

    def test_final_input_read_error_retains_results_and_exception(self):
        actual=benchmark.file_hash; calls=0; error=OSError('final input unavailable')
        def hashed(path):
            nonlocal calls
            calls+=1
            if calls==2: raise error
            return actual(path)
        with patch.object(benchmark,'file_hash',side_effect=hashed):
            with self.assertRaises(OSError) as raised: self.invoke()
        self.assertIs(raised.exception,error)
        result=self.report()
        self.assertFalse(result['complete']); self.assertEqual(len(result['results']),2)
        self.assertEqual(result['failure']['stage'],'comparison')

    def test_existing_output_directory_remains_untouched(self):
        self.output.mkdir(); sentinel=self.output/'kept.bin'; sentinel.write_bytes(b'unchanged')
        with patch.object(benchmark.subprocess,'run',side_effect=AssertionError('unexpected child')):
            with self.assertRaises(FileExistsError): self.invoke()
        self.assertEqual(sentinel.read_bytes(),b'unchanged')
        self.assertEqual(list(self.output.iterdir()),[sentinel])


if __name__=='__main__': unittest.main()
