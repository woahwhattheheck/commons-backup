# SPDX-License-Identifier: Apache-2.0
"""Retain actual child report bytes after process timeouts, without game calls."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import profile_saved as p

CHILD = '''from pathlib import Path
import base64,sys,time
if sys.argv[2] != "missing":
    Path(sys.argv[1]).write_bytes(base64.b64decode(sys.argv[2]))
print("stdout before exit or timeout", flush=True)
print("stderr before exit or timeout", file=sys.stderr, flush=True)
if sys.argv[3] == "timeout":
    time.sleep(30)
raise SystemExit(0)
'''


def complete_report():
    # Transport-only fixture; the real profiler test below executes an actor.
    return {'status': 'complete', 'calls': [{'step': 0, 'wall_s': .01}],
            'action_sequence_sha256': 'fixture', 'runtime_sources': {'main.py': 'fixture'},
            'input': {'fixture': True}, 'loaded_sources': {'target': 'fixture'},
            'loaded_sources_unchanged': True, 'sources_unchanged': True}


class TimeoutReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.counter = 0

    def tearDown(self):
        self.tmp.cleanup()

    def run_case(self, raw, outcomes=('timeout', 'timeout')):
        self.counter += 1
        output = self.root / ('case%d.json' % self.counter)
        args = SimpleNamespace(entrypoint=self.root/'unused.py', factory='make_agent', method='act',
            timing_source=self.root/'timing.py', replay=self.root/'work.json', seat=0,
            max_decisions=3, classification='constructed-timeout-transport',
            process_timeout=1.0, output=output)
        real_run = subprocess.run
        calls = []
        payload = 'missing' if raw is None else base64.b64encode(raw).decode('ascii')

        def child(command, **kwargs):
            index = len(calls)
            calls.append(command)
            child_output = command[command.index('--output') + 1]
            return real_run([sys.executable, '-c', CHILD, child_output, payload, outcomes[index]], **kwargs)

        with patch.object(p.subprocess, 'run', child):
            code = p.supervise(args)
        self.assertEqual(len(calls), 2, 'exactly one child per mode, no timeout retries')
        result = json.loads(output.read_text())
        self.assertEqual(code, 2)
        self.assertFalse(result['instrumentation_action_parity'])
        for mode in ('ordinary', 'profile'):
            log = output.with_name(output.stem + '.' + mode + '.log').read_text()
            self.assertIn('stdout before exit or timeout', log)
            self.assertIn('stderr before exit or timeout', log)
        return result, output

    def assert_retained(self, result, output, raw, modes=('ordinary', 'instrumented')):
        for mode in modes:
            report = result[mode]
            self.assertEqual(report['status'], 'process_timeout')
            self.assertIsNone(report['process_exit_code'])
            self.assertEqual(report['error']['type'], 'ProcessTimeout')
            self.assertIn('timed_out_child_report', report)
            retained = report['timed_out_child_report']
            suffix = 'profile' if mode == 'instrumented' else mode
            expected_path = output.with_name(output.stem + '.' + suffix + '.timeout.bin')
            self.assertEqual(Path(retained['path']), expected_path)
            self.assertEqual(retained['bytes'], len(raw))
            self.assertEqual(retained['sha256'], p.digest(raw))
            self.assertEqual(expected_path.read_bytes(), raw)
            self.assertEqual(json.loads(expected_path.with_name(expected_path.name.replace('.timeout.bin', '.json')).read_text()), report)

    def test_original_actor_failure_survives_timeout(self):
        raw = b'{"status":"error","calls":[],"error":{"type":"TypeError","message":"original body"}}\n'
        result, output = self.run_case(raw)
        self.assert_retained(result, output, raw)

    def test_complete_claim_never_overrides_process_timeout(self):
        raw = json.dumps(complete_report(), indent=2).encode()
        result, output = self.run_case(raw)
        self.assert_retained(result, output, raw)

    def test_truncated_report_is_preserved_without_attempting_json_recovery(self):
        raw = b'{"status":"complete","calls":['
        result, output = self.run_case(raw)
        self.assert_retained(result, output, raw)
        self.assertFalse(list(self.root.glob('*.invalid.bin')))

    def test_non_utf8_report_is_preserved_exactly(self):
        raw = b'\xff\x00\xfe\r\n'
        result, output = self.run_case(raw)
        self.assert_retained(result, output, raw)

    def test_empty_child_report_is_distinct_from_missing(self):
        result, output = self.run_case(b'')
        self.assert_retained(result, output, b'')

    def test_missing_report_retains_timeout_without_fabricated_evidence(self):
        result, output = self.run_case(None)
        for mode in ('ordinary', 'instrumented'):
            self.assertEqual(result[mode]['status'], 'process_timeout')
            self.assertNotIn('timed_out_child_report', result[mode])
        self.assertFalse(list(self.root.glob('*.timeout.bin')))

    def test_only_second_child_times_out(self):
        raw = json.dumps(complete_report()).encode()
        result, output = self.run_case(raw, ('complete', 'timeout'))
        self.assertEqual(result['ordinary']['status'], 'complete')
        self.assertEqual(result['ordinary']['process_exit_code'], 0)
        self.assert_retained(result, output, raw, ('instrumented',))
        self.assertFalse(output.with_name(output.stem + '.ordinary.timeout.bin').exists())

    def test_first_timeout_is_not_cleared_by_second_completion(self):
        raw = json.dumps(complete_report()).encode()
        result, output = self.run_case(raw, ('timeout', 'complete'))
        self.assert_retained(result, output, raw, ('ordinary',))
        self.assertEqual(result['instrumented']['status'], 'complete')
        self.assertEqual(result['instrumented']['process_exit_code'], 0)
        self.assertFalse(output.with_name(output.stem + '.profile.timeout.bin').exists())

    def test_existing_timeout_evidence_prevents_overwrite_before_process_start(self):
        for mode in ('ordinary', 'profile'):
            with self.subTest(mode=mode):
                output = self.root / (mode + '.json')
                retained = output.with_name(output.stem + '.' + mode + '.timeout.bin')
                retained.write_bytes(b'previous diagnostic')
                with patch.object(p.subprocess, 'run', side_effect=AssertionError('must not start')):
                    with self.assertRaises(FileExistsError):
                        p.supervise(SimpleNamespace(output=output, entrypoint=self.root/'unused.py',
                            factory='make_agent', method='act', timing_source=self.root/'timing.py',
                            replay=self.root/'work.json', seat=0, max_decisions=1,
                            classification='existing-evidence', process_timeout=1.0))
                self.assertEqual(retained.read_bytes(), b'previous diagnostic')
                self.assertFalse(output.exists())

    def test_actual_profiler_preserves_complete_report_when_shutdown_hangs(self):
        actor = self.root/'actor.py'
        actor.write_text('import atexit,time\natexit.register(time.sleep,30)\n'
                         'class Agent:\n    def act(self,obs,cfg):\n        return {"market":[],"hand":[]}\n'
                         'def make_agent():\n    return Agent()\n')
        workload = self.root/'workload.json'
        workload.write_text(json.dumps({'schema': 'titan.profile.observations.v1', 'records': [
            {'observation': {'farms': [], 'private': {}, 'market': {}, 'step': 0, 'player': 0},
             'expected_action': {'market': [], 'hand': []}}]}))
        timing = Path(__file__).resolve().parent.parent/'cloud-combination-analysis/execution_timing.py'
        output = self.root/'actual.json'
        completed = subprocess.run([sys.executable, '-B', str(Path(p.__file__).resolve()),
            '--entrypoint', str(actor), '--timing-source', str(timing), '--replay', str(workload),
            '--max-decisions', '1', '--process-timeout', '.7', '--output', str(output)],
            capture_output=True, text=True, timeout=8)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        result = json.loads(output.read_text())
        self.assertFalse(result['instrumentation_action_parity'])
        for mode in ('ordinary', 'instrumented'):
            report = result[mode]
            self.assertEqual(report['status'], 'process_timeout')
            self.assertIn('timed_out_child_report', report)
            retained = report['timed_out_child_report']
            raw = Path(retained['path']).read_bytes()
            self.assertEqual(len(raw), retained['bytes'])
            self.assertEqual(p.digest(raw), retained['sha256'])
            original = json.loads(raw)
            self.assertEqual(original['status'], 'complete')
            self.assertEqual(len(original['calls']), 1)
            self.assertEqual(original['expected_actions']['mismatches'], 0)
            self.assertTrue(original['loaded_sources_unchanged'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
