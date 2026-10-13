"""Process evidence at the existing benchmark boundary; no solver panel runs."""
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
TARGET = Path(os.environ.get('ROADEF_BENCHMARK_SOURCE', HERE / 'benchmark.py'))
spec = importlib.util.spec_from_file_location('benchmark_under_test', TARGET)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class BenchmarkProcessEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def command(self, code):
        return [sys.executable, '-I', '-S', '-u', '-c', code]

    def receipt(self, label, stdout, stderr, status, returncode):
        self.assertEqual((self.root / (label + '.stdout')).read_bytes(), stdout)
        self.assertEqual((self.root / (label + '.stderr')).read_bytes(), stderr)
        record = json.loads((self.root / (label + '.process.json')).read_text(encoding='utf-8'))
        self.assertEqual(record['schema'], 'roadef.benchmark.process.v1')
        self.assertEqual(record['label'], label)
        self.assertEqual(record['status'], status)
        self.assertEqual(record['returncode'], returncode)
        self.assertEqual(record['capture_complete'], status != 'timeout')
        self.assertGreaterEqual(record['wall_seconds'], 0)
        for name, data in [('stdout', stdout), ('stderr', stderr)]:
            self.assertEqual(record[name + '_bytes'], len(data))
            self.assertEqual(record[name + '_sha256'], hashlib.sha256(data).hexdigest())
        self.assertNotIn('score', record)
        self.assertNotIn('valid', record)
        return record

    def test_real_timeout_preserves_raw_partial_streams(self):
        code = "import os,time;os.write(1,b'checkpoint\\xff\\x00');os.write(2,b'diagnostic\\x80');time.sleep(10)"
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            benchmark.execute(self.command(code), self.root, 'solver', timeout=1)
        error = caught.exception
        self.assertEqual(error.stdout, b'checkpoint\xff\x00')
        self.assertEqual(error.stderr, b'diagnostic\x80')
        record = self.receipt('solver', error.stdout, error.stderr, 'timeout', None)
        self.assertEqual(record['timeout_seconds'], 1)
        self.assertGreaterEqual(record['wall_seconds'], 1)

    def test_real_silent_timeout_records_empty_capture_not_success(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            benchmark.execute(self.command('import time;time.sleep(10)'), self.root, 'checker-6', timeout=.5)
        self.receipt('checker-6', b'', b'', 'timeout', None)

    def test_real_timeout_preserves_existing_solution_and_does_not_retry(self):
        solution = self.root / 'solution.json'
        calls = self.root / 'calls'
        code = ("from pathlib import Path;import time;"
                f"p=Path({str(calls)!r});p.open('ab').write(b'x');"
                f"Path({str(solution)!r}).write_bytes(b'{{\"srpaths\":[]}}\\n');"
                "print('checkpoint',flush=True);time.sleep(10)")
        with self.assertRaises(subprocess.TimeoutExpired):
            benchmark.execute(self.command(code), self.root, 'solver', timeout=1)
        self.assertEqual(solution.read_bytes(), b'{"srpaths":[]}\n')
        self.assertEqual(calls.read_bytes(), b'x')
        self.receipt('solver', b'checkpoint\n', b'', 'timeout', None)
        self.assertFalse((self.root / 'result.json').exists())
        self.assertFalse((self.root / 'summary.json').exists())

    def test_success_retains_completed_process_and_environment(self):
        env = dict(os.environ, ROADEF_TEST_TEXT='native-success')
        command = self.command("import os;print(os.environ['ROADEF_TEST_TEXT'])")
        result, elapsed = benchmark.execute(command, self.root, 'solver', env, timeout=3)
        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.args, command)
        self.assertEqual(result.returncode, 0)
        self.assertGreater(elapsed, 0)
        self.assertEqual(result.stdout, b'native-success\n')
        self.receipt('solver', result.stdout, b'', 'completed', 0)

    def test_real_nonzero_exit_retains_original_error_and_logs(self):
        command = self.command("import os;os.write(1,b'partial');os.write(2,b'failed\\xff');raise SystemExit(7)")
        with self.assertRaisesRegex(RuntimeError, r"solver exited 7: b'failed\\xff'"):
            benchmark.execute(command, self.root, 'solver', timeout=3)
        self.receipt('solver', b'partial', b'failed\xff', 'nonzero_exit', 7)

    def test_new_completed_attempt_replaces_timeout_status(self):
        error = subprocess.TimeoutExpired(['old'], 1, output=b'old', stderr=b'old-error')
        with patch.object(benchmark.subprocess, 'run', side_effect=error):
            with self.assertRaises(subprocess.TimeoutExpired):
                benchmark.execute(['old'], self.root, 'checker-12', timeout=1)
        benchmark.execute(self.command("print('new')"), self.root, 'checker-12', timeout=3)
        self.receipt('checker-12', b'new\n', b'', 'completed', 0)

    def test_same_timeout_object_and_call_arguments_are_preserved(self):
        command = [Path('/local/fixture'), 6]
        env = {'LOCAL_TEST': 'preserved'}
        error = subprocess.TimeoutExpired(['/local/fixture', '6'], 7, output=b'a', stderr=None)
        with patch.object(benchmark.subprocess, 'run', side_effect=error) as run:
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                benchmark.execute(command, self.root, 'checker-6', env=env, timeout=7)
        self.assertIs(caught.exception, error)
        run.assert_called_once_with(['/local/fixture', '6'], capture_output=True, env=env, timeout=7)
        self.receipt('checker-6', b'a', b'', 'timeout', None)

    def test_write_failure_does_not_hide_original_timeout(self):
        error = subprocess.TimeoutExpired(['fixture'], 1, output=b'partial')
        with patch.object(benchmark.subprocess, 'run', side_effect=error), \
             patch.object(Path, 'write_bytes', side_effect=OSError('fixture storage unavailable')):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                benchmark.execute(['fixture'], self.root, 'solver', timeout=1)
        self.assertIs(caught.exception, error)
        self.assertIsInstance(error.__cause__, OSError)
        self.assertIn('Could not persist all timeout evidence: OSError', error.__notes__)

    def test_receipt_write_failure_does_not_hide_original_timeout(self):
        error = subprocess.TimeoutExpired(['fixture'], 1, output=b'partial', stderr=b'error')
        with patch.object(benchmark.subprocess, 'run', side_effect=error), \
             patch.object(Path, 'write_text', side_effect=OSError('fixture receipt unavailable')):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                benchmark.execute(['fixture'], self.root, 'solver', timeout=1)
        self.assertIs(caught.exception, error)
        self.assertEqual((self.root / 'solver.stdout').read_bytes(), b'partial')
        self.assertEqual((self.root / 'solver.stderr').read_bytes(), b'error')
        self.assertFalse((self.root / 'solver.process.json').exists())

    def test_process_receipt_excludes_command_and_environment(self):
        result = subprocess.CompletedProcess(['fixture', 'private-argument'], 0, b'', b'')
        with patch.object(benchmark.subprocess, 'run', return_value=result):
            benchmark.execute(['fixture', 'private-argument'], self.root, 'solver',
                              env={'LOCAL_TEST_VALUE': 'private-environment'})
        text = (self.root / 'solver.process.json').read_text()
        self.assertNotIn('private-argument', text)
        self.assertNotIn('private-environment', text)
        self.assertNotIn('LOCAL_TEST_VALUE', text)

    def test_cancellation_and_launch_errors_still_propagate_once(self):
        for error in (KeyboardInterrupt(), SystemExit(4), FileNotFoundError('fixture')):
            with self.subTest(error=type(error).__name__), \
                 patch.object(benchmark.subprocess, 'run', side_effect=error) as run:
                with self.assertRaises(type(error)) as caught:
                    benchmark.execute(['fixture'], self.root, 'solver')
                self.assertIs(caught.exception, error)
                run.assert_called_once()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_concurrent_process_outputs_stay_with_their_labels(self):
        labels = ('solver', 'checker-6', 'checker-12')
        def run(label):
            return benchmark.execute(self.command(f'print({label!r})'), self.root, label, timeout=3)
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(run, labels))
        for label, (result, elapsed) in zip(labels, results):
            self.assertEqual(result.returncode, 0)
            self.receipt(label, (label+'\n').encode(), b'', 'completed', 0)


if __name__ == '__main__':
    unittest.main()
