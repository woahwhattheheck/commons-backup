# SPDX-License-Identifier: Apache-2.0
"""Check the existing receipt reader on saved ZIPs and detached newline fixtures.

Nothing in an evidence ZIP is executed. Changed fixture digests are local identities,
not provider attestations. This file adds no alternate receipt parser or CLI.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ARTIFACTS = {
    'legacy': ('af9b3fc1de67eaed39c842b6c71d8fcd84e4ae8c0bd31465cb89ed73252cae29', 95),
    'v2': ('ddacdc557419258c072e1c2ef62ebe4d101a5f3b79e6967a153a650268a6d42d', 159),
}
OPTIONS = None
READS = []
BASE_LOGS = {'original-seller-tests.log': 16, 'projection-tests.log': 21,
             'market-tests.log': 14, 'funded-join-tests.log': 16}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def load_reader(path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('newline_reader_under_test', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Cannot import supplied local reader')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def crlf(data):
    return data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')


class LineEndingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if OPTIONS is None:
            raise unittest.SkipTest('Run explicitly with --archive and --v2-archive')
        cls.reader = load_reader(OPTIONS.reader)
        cls.members = {}
        for label, path in [('legacy', OPTIONS.archive), ('v2', OPTIONS.v2_archive)]:
            data = path.read_bytes()
            if sha(data) != ARTIFACTS[label][0]:
                raise ValueError('Expected unchanged ' + label + ' provider ZIP')
            with zipfile.ZipFile(path) as z:
                cls.members[label] = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def inspect(self, change=None, *, label='legacy', refresh_v2=False, **kwargs):
        members = copy.deepcopy(self.members[label])
        original = copy.deepcopy(members)
        if change:
            change(members)
        if refresh_v2:
            report = json.loads(members['COMBINED-RESULTS.json'])
            self.assertEqual(report['schema'], 'titan.selected-projection.combined.v2')
            # Update only digests of existing declared inputs in a detached fixture.
            for name in report['input_sha256']:
                if name in members and members[name] != original[name]:
                    report['input_sha256'][name] = sha(members[name])
            members['COMBINED-RESULTS.json'] = json.dumps(report, sort_keys=True).encode()
        if change is None:
            path = OPTIONS.archive if label == 'legacy' else OPTIONS.v2_archive
        else:
            path = Path(self.tmp.name) / 'detached-evidence.zip'
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                for name, body in members.items():
                    z.writestr(name, body)
        digest = sha(path.read_bytes())
        snapshot = json.loads(members['SOURCE-SNAPSHOT.json'])
        out = self.reader.inspect_archive(path, expected_sha256=digest,
            expected_checkout=snapshot['checkout'], expected_run_id=snapshot['run_id'],
            expected_attempt=snapshot['attempt'], **kwargs)
        self.assertTrue(out['provider_digest_matched'])
        self.assertEqual(out['tests_rerun'], 0)
        self.assertEqual(out['game_panels'], 0)
        self.assertEqual(out['seeds_consumed'], [])
        self.assertEqual(sha(path.read_bytes()), digest, 'Reader must not rewrite its input')
        READS.append({'test': self.id().rsplit('.', 1)[-1], 'label': label,
                      'detached_fixture': change is not None, 'zip_sha256': digest,
                      'status': out['status'], 'methods': out['reported_test_methods'],
                      'problems': out['problems']})
        return out

    def test_unchanged_archives_remain_complete(self):
        for label, (_, count) in ARTIFACTS.items():
            with self.subTest(label=label):
                out = self.inspect(label=label)
                self.assertEqual((out['status'], out['reported_test_methods']), ('COMPLETE_PASS', count))

    def test_each_core_and_funded_crlf_log_retains_all_95(self):
        for log in BASE_LOGS:
            with self.subTest(log=log):
                out = self.inspect(lambda m: m.__setitem__(log, crlf(m[log])))
                self.assertEqual((out['status'], out['reported_test_methods']), ('COMPLETE_PASS', 95))
                self.assertEqual(out['problems'], [])

    def test_all_seven_crlf_logs_retains_95(self):
        def change(m):
            for name in list(m):
                if name.endswith('-tests.log'):
                    m[name] = crlf(m[name])
        out = self.inspect(change)
        self.assertEqual((out['status'], out['reported_test_methods']), ('COMPLETE_PASS', 95))

    def test_mixed_lf_and_crlf_log_remains_complete(self):
        def change(m):
            m['funded-join-tests.log'] = b'test_example ... ok\r\nRan 16 tests in 0.1s\n\r\nOK\r\n'
        out = self.inspect(change)
        self.assertEqual((out['status'], out['reported_test_methods']), ('COMPLETE_PASS', 95))

    def test_supplemental_crlf_compatibility_unchanged(self):
        out = self.inspect(lambda m: m.__setitem__('loader-tests.log', crlf(m['loader-tests.log'])))
        self.assertEqual((out['status'], out['reported_test_methods']), ('COMPLETE_PASS', 95))
        self.assertEqual(out['supplemental_receipt']['reported_test_methods'], 28)

    def test_reporter_crlf_with_bound_v2_remains_complete(self):
        out = self.inspect(lambda m: m.__setitem__('reporter-tests.log', crlf(m['reporter-tests.log'])),
                           label='v2', refresh_v2=True)
        self.assertEqual((out['status'], out['reported_test_methods']), ('COMPLETE_PASS', 159))
        self.assertTrue(out['aggregate_summary']['declarations_checked'])

    def test_all_v2_crlf_inputs_use_raw_byte_digests(self):
        def change(m):
            for name in list(m):
                if name.endswith('-tests.log'):
                    m[name] = crlf(m[name])
        out = self.inspect(change, label='v2', refresh_v2=True)
        self.assertEqual((out['status'], out['reported_test_methods']), ('COMPLETE_PASS', 159))
        self.assertEqual(out['problems'], [])

    def test_line_normalization_does_not_mask_stale_v2_digest(self):
        out = self.inspect(lambda m: m.__setitem__('funded-join-tests.log', crlf(m['funded-join-tests.log'])),
                           label='v2')
        self.assertEqual(out['status'], 'FAIL')
        self.assertTrue(any('input digest differs: funded-join-tests.log' in p['detail']
                            for p in out['problems']))

    def test_failed_crlf_footer_is_failure(self):
        out = self.inspect(lambda m: m.__setitem__('funded-join-tests.log',
                            b'Ran 16 tests in 0.1s\r\n\r\nFAILED (errors=1)\r\n'))
        self.assertEqual(out['status'], 'FAIL')
        self.assertTrue(any('failure footer' in p['detail'] for p in out['problems']))

    def test_skipped_crlf_footer_is_not_full_coverage(self):
        out = self.inspect(lambda m: m.__setitem__('funded-join-tests.log',
                            b'Ran 16 tests in 0.1s\r\n\r\nOK (skipped=1)\r\n'))
        self.assertEqual(out['status'], 'INCOMPLETE')
        self.assertTrue(any('qualified completion' in p['detail'] for p in out['problems']))

    def test_reversed_crlf_footer_is_still_incomplete(self):
        out = self.inspect(lambda m: m.__setitem__('funded-join-tests.log',
                            b'OK\r\n\r\nRan 16 tests in 0.1s\r\n'))
        self.assertEqual(out['status'], 'INCOMPLETE')
        self.assertFalse(out['suites']['funded_join']['reported_pass'])

    def test_duplicate_crlf_completion_is_still_incomplete(self):
        out = self.inspect(lambda m: m.__setitem__('funded-join-tests.log',
                            2 * b'Ran 16 tests in 0.1s\r\n\r\nOK\r\n'))
        self.assertEqual(out['status'], 'INCOMPLETE')
        self.assertFalse(out['suites']['funded_join']['reported_pass'])

    def test_crlf_count_conflict_cannot_be_ignored(self):
        out = self.inspect(lambda m: m.__setitem__('funded-join-tests.log',
                            b'Ran 17 tests in 0.1s\r\n\r\nOK\r\n'))
        self.assertEqual(out['status'], 'FAIL')
        self.assertTrue(any('report and log method counts differ' in p['detail'] for p in out['problems']))

    def test_crlf_invalid_utf8_remains_failure(self):
        out = self.inspect(lambda m: m.__setitem__('funded-join-tests.log',
                            b'\xff\r\nRan 16 tests in 0.1s\r\n\r\nOK\r\n'))
        self.assertEqual(out['status'], 'FAIL')
        self.assertTrue(any('invalid UTF-8' in p['detail'] for p in out['problems']))

    def test_bare_carriage_return_is_not_newline(self):
        out = self.inspect(lambda m: m.__setitem__('funded-join-tests.log',
                            b'Ran 16 tests in 0.1s\r\rOK\r'))
        self.assertEqual(out['status'], 'INCOMPLETE')

    def test_unknown_crlf_failed_footer_remains_failure(self):
        # NEWLINE-RESUME's retained discriminator, using this suite's saved95 fixture.
        out = self.inspect(lambda m: m.__setitem__(
            'new-tests.log', b'Ran 1 test in 0.01s\r\n\r\nFAILED\r\n'))
        self.assertEqual(out['status'], 'FAIL')
        self.assertIn('new-tests.log: unittest failure footer is present',
                      [p['detail'] for p in out['problems']])

    def test_real_cli_crlf_and_byte_preservation(self):
        members = copy.deepcopy(self.members['legacy'])
        members['funded-join-tests.log'] = crlf(members['funded-join-tests.log'])
        path, output = Path(self.tmp.name) / 'crlf.zip', Path(self.tmp.name) / 'receipt.json'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for name, body in members.items():
                z.writestr(name, body)
        digest = sha(path.read_bytes())
        proc = subprocess.run([sys.executable, '-B', str(OPTIONS.reader), str(path),
                               '--expected-sha256', digest, '--require-suite', 'funded_join',
                               '--json-output', str(output)], capture_output=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode(errors='replace'))
        self.assertEqual(proc.stdout, output.read_bytes())
        self.assertEqual(json.loads(proc.stdout)['reported_test_methods'], 95)
        self.assertEqual(sha(path.read_bytes()), digest)


def main():
    global OPTIONS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', type=Path, default=Path(__file__).with_name('check_joint_receipt.py'))
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--v2-archive', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    OPTIONS = parser.parse_args()
    OPTIONS.reader = OPTIONS.reader.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LineEndingTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if OPTIONS.report:
        report = {'schema': 'titan.receipt.crlf-validation.v1', 'methods': result.testsRun,
                  'failure_assertions_or_subtests': len(result.failures), 'errors': len(result.errors),
                  'skipped': len(result.skipped), 'successful': result.wasSuccessful(),
                  'reader_git_blob': git_blob(OPTIONS.reader.read_bytes()),
                  'reader_sha256': sha(OPTIONS.reader.read_bytes()),
                  'helper_git_blob': git_blob(OPTIONS.reader.with_name('supplemental_receipt.py').read_bytes()),
                  'test_sha256': sha(Path(__file__).read_bytes()),
                  'cases': READS, 'failures': [{'test': str(t), 'traceback': tb}
                                              for t, tb in result.failures + result.errors],
                  'archived_suites_rerun': 0, 'game_panels': 0, 'seeds_consumed': []}
        OPTIONS.report.parent.mkdir(parents=True, exist_ok=True)
        OPTIONS.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
