# SPDX-License-Identifier: Apache-2.0
"""Real CLI input-custody regressions for the existing fast-clone verifier.

Only the fixture-free graph mode is executed. The default and historical
modes are checked at invalid-input boundaries, not claimed as corpus runs.
Set TITAN_CLONE_RUNNER_UNDER_TEST to a saved predecessor for comparison.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
RUNNER = 'verify_fast_clone.py'
HELPER = 'r04_fast_tape_clone.py'
GRAPH = 'test_fast_clone_graph_contract.py'
FIXTURE_PINS = {
    HELPER: 'b7c1fd2f7f786c5dc5f8a3b9a7116815ea40607a',
    GRAPH: 'da78c6664ff9b0537a910cf4672355fcaafb0a9e',
}


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


class VerifierInputContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = {name: (HERE / name).read_bytes() for name in FIXTURE_PINS}
        for name, expected in FIXTURE_PINS.items():
            actual = git_blob(cls.inputs[name])
            if actual != expected:
                raise RuntimeError(f'wrong real fixture {name}: {actual} != {expected}')
        runner_path = Path(os.environ.get('TITAN_CLONE_RUNNER_UNDER_TEST', HERE / RUNNER))
        cls.inputs[RUNNER] = runner_path.read_bytes()

    def invoke(self, arguments, replacements=None, removed=()):
        payloads = dict(self.inputs)
        payloads.update(replacements or {})
        for name in removed:
            payloads.pop(name, None)
        with tempfile.TemporaryDirectory(prefix='titan-clone-input-test-') as directory:
            stage = Path(directory) / 'repo' / 'candidates' / 'v4' / 'repairs' / 'performance' / 'fast-tape-clone'
            stage.mkdir(parents=True)
            for name, data in payloads.items():
                (stage / name).write_bytes(data)
            command = [sys.executable, '-I']
            if sys.flags.optimize:
                command.append('-O')
            command += [str(stage / RUNNER), *arguments]
            done = subprocess.run(command, cwd=stage, capture_output=True,
                                  text=True, timeout=30, check=False)
            after = {path.name: path.read_bytes() for path in stage.iterdir() if path.is_file()}
            self.assertEqual(after, payloads, 'verifier modified its input directory')
            return done

    def rejected(self, done, error_fragment):
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertEqual(done.stdout, '', 'invalid inputs emitted a result/PASS payload')
        self.assertIn(error_fragment, done.stderr)
        self.assertNotIn('Traceback', done.stderr)
        self.assertNotIn('Ran 8 tests', done.stderr, 'drift reached the test interpreter')

    def test_exact_graph_suite_normal_and_optimized(self):
        done = self.invoke(['--generated-only'])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        report = json.loads(done.stdout)
        self.assertEqual(report, {
            'status': 'PASS', 'scope': 'historical-clone-source-only',
            'generated_only': True, 'legacy_port': False,
            'input_blobs': FIXTURE_PINS,
            'runs': [
                {'optimized': False, 'tests': 8, 'skipped': 0, 'ok': True},
                {'optimized': True, 'tests': 8, 'skipped': 0, 'ok': True},
            ],
            'production_changed': False,
        })

    def test_graph_comment_drift_rejected_before_execution(self):
        done = self.invoke(['--generated-only'], {GRAPH: self.inputs[GRAPH] + b'# drift\n'})
        self.rejected(done, GRAPH + ': expected ' + FIXTURE_PINS[GRAPH])

    def test_graph_coverage_reduction_with_same_test_count_is_rejected(self):
        old = b'        self.assertEqual(graph(actual)[:2], graph(expected)[:2])\n'
        self.assertEqual(self.inputs[GRAPH].count(old), 1)
        changed = self.inputs[GRAPH].replace(old, b'        # Accidentally removed graph-equality assertion.\n')
        done = self.invoke(['--generated-only'], {GRAPH: changed})
        self.rejected(done, GRAPH + ': expected ' + FIXTURE_PINS[GRAPH])

    def test_empty_and_invalid_utf8_graph_are_rejected_before_import(self):
        for replacement in (b'', b'\xff\xfe\x00'):
            with self.subTest(payload=replacement):
                self.rejected(self.invoke(['--generated-only'], {GRAPH: replacement}),
                              GRAPH + ': expected ' + FIXTURE_PINS[GRAPH])

    def test_graph_pin_applies_before_default_or_legacy_fixture_reads(self):
        choices = (
            [],
            ['--legacy-port', '--parent-apply', 'absent-parent.py',
             '--archived-router', 'absent-router.py'],
            ['--slack-package', 'absent-package.tar.gz'],
            ['--slack-package', 'absent-package.tar.gz', '--legacy-port',
             '--parent-apply', 'absent-parent.py', '--archived-router', 'absent-router.py'],
        )
        for arguments in choices:
            with self.subTest(arguments=arguments):
                self.rejected(self.invoke(arguments, {GRAPH: self.inputs[GRAPH] + b'\n'}),
                              GRAPH + ': expected ' + FIXTURE_PINS[GRAPH])

    def test_missing_graph_fails_without_pass(self):
        self.rejected(self.invoke(['--generated-only'], removed=(GRAPH,)), GRAPH)

    def test_helper_drift_remains_rejected(self):
        self.rejected(self.invoke(['--generated-only'], {HELPER: self.inputs[HELPER] + b'\n'}),
                      HELPER + ': expected ' + FIXTURE_PINS[HELPER])

    def test_missing_helper_fails_without_pass(self):
        self.rejected(self.invoke(['--generated-only'], removed=(HELPER,)), HELPER)

    def test_incompatible_mode_flags_remain_rejected(self):
        cases = (
            (['--generated-only', '--legacy-port'], '--generated-only cannot include --legacy-port'),
            (['--legacy-port'], '--legacy-port requires'),
            (['--parent-apply', 'absent.py'], 'historical inputs require'),
            (['--archived-router', 'absent.py'], 'historical inputs require'),
            (['--generated-only', '--tapes', 'absent.py'], '--generated-only does not consume --tapes'),
            (['--generated-only', '--slack-package', 'absent.tar.gz'],
             '--generated-only does not consume --tapes or --slack-package'),
            (['--tapes', 'absent.py', '--slack-package', 'absent.tar.gz'],
             'not allowed with argument'),
        )
        for arguments, error in cases:
            with self.subTest(arguments=arguments):
                self.rejected(self.invoke(arguments), error)

    def test_missing_default_fixtures_do_not_fall_back_to_graph_only(self):
        self.rejected(self.invoke([]), 'test_r04_fast_tape_clone.py')


if __name__ == '__main__':
    unittest.main(verbosity=2)
