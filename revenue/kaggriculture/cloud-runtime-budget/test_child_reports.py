# SPDX-License-Identifier: Apache-2.0
"""Exercise malformed child-output recovery with real subprocesses, not games."""
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
import base64,sys
if sys.argv[2] != "missing":
    Path(sys.argv[1]).write_bytes(base64.b64decode(sys.argv[2]))
print("child stdout retained")
print("child stderr retained", file=sys.stderr)
raise SystemExit(int(sys.argv[3]))
'''


class ChildReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.counter = 0

    def tearDown(self):
        self.tmp.cleanup()

    def run_case(self, raw, exit_code=7):
        self.counter += 1
        output = self.root / ('case%d.json' % self.counter)
        args = SimpleNamespace(entrypoint=self.root/'unused.py', factory='make_agent', method='act',
            timing_source=self.root/'timing.py', replay=self.root/'work.json', seat=0,
            max_decisions=3, classification='constructed-child-output', process_timeout=10, output=output)
        real_run = subprocess.run
        calls = []
        def child(command, **kwargs):
            child_output = command[command.index('--output')+1]
            calls.append(command)
            mode = command[command.index('--worker-mode')+1]
            data = raw(mode) if callable(raw) else raw
            payload = 'missing' if data is None else base64.b64encode(data).decode('ascii')
            return real_run([sys.executable, '-c', CHILD, child_output, payload, str(exit_code)], **kwargs)
        with patch.object(p.subprocess, 'run', child):
            code = p.supervise(args)
        self.assertEqual(len(calls), 2, 'one process per mode, no failure retries')
        result = json.loads(output.read_text())
        for mode in ('ordinary', 'profile'):
            log = output.with_name(output.stem+'.'+mode+'.log').read_text()
            self.assertIn('child stdout retained', log)
            self.assertIn('child stderr retained', log)
        for mode in ('ordinary', 'instrumented'):
            self.assertEqual(result[mode]['process_exit_code'], exit_code)
        return code, result, output

    def assert_invalid(self, raw):
        code, result, output = self.run_case(raw)
        self.assertEqual(code, 2)
        self.assertFalse(result['instrumentation_action_parity'])
        for mode in ('ordinary', 'instrumented'):
            report = result[mode]
            self.assertEqual(report['status'], 'process_error')
            self.assertEqual(report['error']['type'], 'InvalidChildReport')
            retained = report['invalid_report']
            self.assertEqual(retained['bytes'], len(raw))
            self.assertEqual(retained['sha256'], p.digest(raw))
            self.assertEqual(Path(retained['path']).read_bytes(), raw)
        self.assertEqual(output.with_name(output.stem+'.ordinary.invalid.bin').read_bytes(), raw)
        self.assertEqual(output.with_name(output.stem+'.profile.invalid.bin').read_bytes(), raw)

    def test_truncated_json_preserves_bytes_logs_exit_and_final_result(self):
        self.assert_invalid(b'{"status":')

    def test_non_utf8_child_output_preserved_exactly(self):
        self.assert_invalid(b'{"status":"\xff"}')

    def test_non_object_and_missing_status_are_classified(self):
        for value in (None, [], 'report', 7, {}, {'status': False}, {'status': ''}):
            with self.subTest(value=value):
                self.assert_invalid(json.dumps(value).encode())

    def test_invalid_calls_do_not_abort_next_mode(self):
        for calls in (None, {}, [], [None], [{}], [{'step': True, 'wall_s': .1}],
                      [{'step': 0}], [{'step': 0, 'wall_s': 'slow'}],
                      [{'step': 0, 'wall_s': False}], [{'step': 0, 'wall_s': -1}],
                      [{'step': 0, 'wall_s': float('nan')}], [{'step': 0, 'wall_s': float('inf')}]):
            with self.subTest(calls=calls):
                self.assert_invalid(json.dumps({'status':'complete','calls':calls}).encode())

    def test_nonfinite_metadata_and_deep_json_preserve_raw_bytes(self):
        for raw in (b'{"status":"error","calls":[],"extra":NaN}',
                    b'{"status":"error","calls":[],"extra":1e9999}',
                    b'['*2000 + b'0' + b']'*2000):
            with self.subTest(prefix=raw[:60]):
                self.assert_invalid(raw)

    def test_missing_child_report_keeps_log_and_summary(self):
        code, result, output = self.run_case(None)
        self.assertEqual(code, 2)
        for mode in ('ordinary', 'instrumented'):
            self.assertEqual(result[mode]['error']['type'], 'MissingChildReport')
        self.assertFalse(list(self.root.glob('*.invalid.bin')))

    def test_valid_original_failure_is_not_relabelled(self):
        original = {'status':'error', 'calls':[], 'error':{'type':'TypeError','message':'original actor body'}}
        code, result, output = self.run_case(json.dumps(original).encode())
        self.assertEqual(code, 2)
        for mode in ('ordinary', 'instrumented'):
            self.assertEqual(result[mode]['status'], 'error')
            self.assertEqual(result[mode]['error'], original['error'])
            self.assertEqual(result[mode]['calls'], [])
        self.assertFalse(list(self.root.glob('*.invalid.bin')))

    def test_structured_complete_child_report_remains_accepted(self):
        # This is a transport-only fixture, not evidence of actor/game execution.
        digest = 'a' * 64
        report = {'schema':'titan.saved-runtime-pass.v1', 'status':'complete',
            'calls':[{'step':0,'wall_s':.01,'action_sha256':digest}],
            'action_sequence_sha256':digest,'profiler_sha256':digest,
            'timing_source_sha256':digest,'runtime_sources':{'main.py':digest},
            'input':{'records':1,'transport_sha256':digest,'decoded_sha256':digest},
            'loaded_sources':{
                'finch_existing_timing':{'path':'/fixture/timing.py','sha256':digest},
                'finch_profile_target':{'path':'/fixture/main.py','sha256':digest}},
            'loaded_sources_unchanged':True,'sources_unchanged':True}
        code, result, output = self.run_case(
            lambda mode: json.dumps(dict(report, mode=mode)).encode(), 0)
        self.assertEqual(code, 0)
        self.assertTrue(result['instrumentation_action_parity'])
        self.assertEqual(result['ordinary']['calls'], report['calls'])
        self.assertFalse(list(self.root.glob('*.invalid.bin')))

    def test_existing_invalid_output_is_not_overwritten(self):
        output = self.root/'fresh.json'
        retained = self.root/'fresh.ordinary.invalid.bin'
        retained.write_bytes(b'previous bytes')
        args = SimpleNamespace(output=output)
        with patch.object(p.subprocess, 'run', side_effect=AssertionError('must not start')):
            with self.assertRaises(FileExistsError):
                p.supervise(args)
        self.assertEqual(retained.read_bytes(), b'previous bytes')
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
