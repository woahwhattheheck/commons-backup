import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parent / 'verify_joint.py'


class TimeoutEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'fixture'
        self.root.mkdir()
        shutil.copyfile(SOURCE, self.root / 'verify_joint.py')
        for name, content in {
            'joint-net.json': '{}\n', 'joint-tm.json': '{}\n', 'joint-scenario.json': '{}\n',
            'joint-budget-tm.json': '{}\n', 'joint-budget-scenario.json': '{}\n',
            'joint-budget-incumbent.json': '{}\n', 'main.cpp': '// fixture\n',
            'solver': 'fixture\n', 'checker': 'fixture\n'}.items():
            (self.root / name).write_text(content)
        spec = importlib.util.spec_from_file_location('verify_joint_subject_' + self.tmp.name.replace('/', '_'), self.root/'verify_joint.py')
        self.subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.subject)
        self.out = Path(self.tmp.name) / 'out'
        self.out.mkdir()
        self.argv = ['verify_joint.py', '--solver', str(self.root/'solver'), '--checker', str(self.root/'checker'), '--output', str(self.out)]

    def call_main(self):
        with patch.object(sys, 'argv', self.argv):
            return self.subject.main()

    def test_solver_timeout_preserves_streams_and_receipt(self):
        error = subprocess.TimeoutExpired(['solver'], 60, output=b'solver-out\n', stderr=b'solver-err\n')
        with patch.object(self.subject.subprocess, 'run', side_effect=error), self.assertRaises(subprocess.TimeoutExpired) as caught:
            self.call_main()
        self.assertIs(caught.exception, error)
        self.assertEqual((self.out/'joint-disabled.log').read_bytes(), b'solver-out\nsolver-err\n')
        receipt = json.loads((self.out/'joint-disabled-timeout.json').read_text())
        self.assertEqual(receipt['status'], 'timeout')
        self.assertEqual(receipt['stage'], 'solver')
        self.assertEqual(receipt['timeout_seconds'], 60)
        self.assertEqual(receipt['stdout_sha256'], hashlib.sha256(b'solver-out\n').hexdigest())
        self.assertEqual(receipt['stderr_sha256'], hashlib.sha256(b'solver-err\n').hexdigest())
        self.assertEqual(receipt['stdout_bytes'], 11)
        self.assertEqual(receipt['stderr_bytes'], 11)
        self.assertFalse((self.out/'joint-disabled-checker.json').exists())

    def test_checker_timeout_preserves_both_streams_and_solver_log(self):
        calls = 0

        def runner(command, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                out = Path(command[-1])
                out.write_text('{"srpaths":[]}\n')
                Path(kwargs['env']['SEDGE_STATS']).write_text('{"accepted":0,"joint_accepted":0,"budget_used":[0,3],"resumed":false}\n')
                return subprocess.CompletedProcess(command, 0, stdout='solver-ok\n', stderr='solver-note\n')
            raise subprocess.TimeoutExpired(command, 30, output=b'{"valid":', stderr=b'checker-err\n')

        with patch.object(self.subject.subprocess, 'run', side_effect=runner), self.assertRaises(subprocess.TimeoutExpired):
            self.call_main()
        self.assertEqual((self.out/'joint-disabled.log').read_text(), 'solver-ok\nsolver-note\n')
        self.assertEqual((self.out/'joint-disabled-checker.json').read_bytes(), b'{"valid":')
        self.assertEqual((self.out/'joint-disabled-checker.log').read_bytes(), b'checker-err\n')
        receipt = json.loads((self.out/'joint-disabled-timeout.json').read_text())
        self.assertEqual(receipt['stage'], 'checker')
        self.assertEqual(receipt['timeout_seconds'], 30)

    def test_timeout_stream_normalization(self):
        self.assertEqual(self.subject.captured_text(None), '')
        self.assertEqual(self.subject.captured_text('abc'), 'abc')
        self.assertEqual(self.subject.captured_bytes(b'a\xffb'), b'a\xffb')
        self.assertEqual(self.subject.captured_text(b'a\xffb'), 'a\ufffdb')

    def test_timeout_receipt_replaces_stale_evidence(self):
        path = self.out/'x-timeout.json'
        path.write_text('{"stale":true}\n')
        self.subject.timeout_receipt(path, 'checker', 3.5, b'out', b'err')
        doc = json.loads(path.read_text())
        self.assertEqual(doc['stage'], 'checker')
        self.assertEqual(doc['timeout_seconds'], 3.5)
        self.assertNotIn('stale', doc)


if __name__ == '__main__':
    unittest.main()
