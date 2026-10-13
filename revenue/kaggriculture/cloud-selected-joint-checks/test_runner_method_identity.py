# SPDX-License-Identifier: Apache-2.0
"""Check the two-method runner subset using an existing validation artifact.

Only the receipt reader executes. Mutations are separate temporary test ZIPs;
original provider bytes, runtime tests, engines and game results are untouched.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import zipfile

ARCHIVE = None
READER = None
EXPECTED = 'fe33a36cebf521ee4188609fc68a1739c68bbbb26e99f9ef87e3b7abbe91000b'
LOG = 'stress-runner-existing-tests.log'
CASES = []


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(path):
    raw = Path(path).read_bytes()
    return {'sha256': sha256(raw),
            'git_blob': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}


class RunnerMethodIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sha256(ARCHIVE.read_bytes()) != EXPECTED:
            raise ValueError('This discriminator requires the unchanged HAZEL artifact10039313918')
        cls.members = READER.read_members(ARCHIVE)
        cls.original_log = cls.members[LOG].decode('utf-8')
        cls.method_lines = cls.original_log.splitlines(keepends=True)[:2]
        cls.footer = ''.join(cls.original_log.splitlines(keepends=True)[2:])
        cls.original = READER.inspect_archive(ARCHIVE, expected_sha256=EXPECTED)
        if cls.original['status'] != 'COMPLETE_PASS' or cls.original['reported_test_methods'] != 282:
            raise ValueError('The healthy source composition must first recognize all 282 methods')
        CASES.append({'case': 'original_provider_archive', 'mutated': False,
                      'result': cls.original})

    def inspect_log(self, case, text):
        members = dict(self.members)
        members[LOG] = text.encode()
        combined = json.loads(members['COMBINED-RESULTS.json'])
        combined['input_sha256'][LOG] = sha256(members[LOG])
        members['COMBINED-RESULTS.json'] = json.dumps(combined, indent=2).encode()
        # Updating the derived test digest prevents a checksum failure from
        # masquerading as method-identity validation. It is not a provider claim.
        with tempfile.TemporaryDirectory(prefix='titan-method-identity-') as temporary:
            path = Path(temporary) / 'fixture.zip'
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, raw in members.items():
                    archive.writestr(name, raw)
            digest = sha256(path.read_bytes())
            result = READER.inspect_archive(path, expected_sha256=digest)
        CASES.append({'case': case, 'mutated': True, 'mutation': 'runner log and its aggregate input digest only',
                      'test_log': text, 'test_archive_sha256': digest, 'result': result})
        return result

    def assert_identity_rejected(self, result):
        new = [p for p in result['problems'] if p not in self.original['problems']]
        self.assertNotEqual(result['status'], 'COMPLETE_PASS', result)
        self.assertTrue(any('stress_runner_existing' in p['detail'] for p in new), new)
        self.assertFalse(any('input digest differs' in p['detail'] for p in new), new)

    def test_original_18_suites_remain_complete(self):
        self.assertEqual(self.original['reported_test_methods'], 282)
        self.assertEqual(len(self.original['suites']), 18)
        self.assertEqual(self.original['problems'], [])
        self.assertEqual(self.original['tests_rerun'], 0)

    def test_already_counted_guards_cannot_replace_runner_methods(self):
        guards = [line for line in self.members['deadline-cancellation-tests.log'].decode().splitlines()
                  if '(unchanged_upstream_guard_tests.RunnerTests.' in line]
        self.assertEqual(len(guards), 3)
        text = '\n'.join((guards[0], guards[2])) + '\n' + self.footer
        result = self.inspect_log('two_previously_counted_guards', text)
        self.assert_identity_rejected(result)

    def test_one_runner_method_cannot_be_counted_twice(self):
        text = self.method_lines[0] * 2 + self.footer
        self.assert_identity_rejected(self.inspect_log('duplicate_runner_method', text))

    def test_count_only_footer_does_not_identify_subset(self):
        self.assert_identity_rejected(self.inspect_log('missing_method_identities', self.footer))

    def test_original_methods_may_run_in_reverse_order(self):
        text = ''.join(reversed(self.method_lines)) + self.footer
        result = self.inspect_log('reordered_original_methods', text)
        self.assertEqual(result['status'], 'COMPLETE_PASS', result)
        self.assertEqual(result['reported_test_methods'], 282)

    def test_crlf_method_log_remains_supported(self):
        result = self.inspect_log('crlf_original_methods', self.original_log.replace('\n', '\r\n'))
        self.assertEqual(result['status'], 'COMPLETE_PASS', result)
        self.assertEqual(result['reported_test_methods'], 282)


def main():
    global ARCHIVE, READER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--reader', type=Path, default=Path(__file__).with_name('check_joint_receipt.py'))
    parser.add_argument('--expected-helper-blob')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    ARCHIVE = args.archive.resolve()
    source = args.reader.resolve()
    sys.path.insert(0, str(source.parent))
    spec = importlib.util.spec_from_file_location('runner_identity_receipt_reader', source)
    READER = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(READER)
    helper = Path(sys.modules['supplemental_receipt'].__file__)
    helper_identity = identity(helper)
    if args.expected_helper_blob and helper_identity['git_blob'] != args.expected_helper_blob:
        raise ValueError('Loaded helper differs from the supplied source pin')
    before = sha256(ARCHIVE.read_bytes())
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RunnerMethodIdentityTests))
    text = output.getvalue()
    print(text, end='')
    report = {
        'schema': 'titan.runner-method-identity-tests.v1', 'python': sys.version.split()[0],
        'methods': result.testsRun, 'successful': result.wasSuccessful(),
        'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
        'sources': {'reader': identity(source), 'helper': helper_identity, 'test': identity(__file__)},
        'input': {'artifact_id': 10039313918, 'provider_sha256': EXPECTED, 'actual_sha256': before,
                  'original_unchanged': before == sha256(ARCHIVE.read_bytes())},
        'cases': deepcopy(CASES), 'log': text,
        'failure_details': [(str(test), detail) for test, detail in result.failures + result.errors],
        'archived_tests_rerun': 0, 'engine_transitions': 0, 'games': 0,
        'scope': 'Original saved artifact plus method-identity mutation controls; not hosted execution attestation',
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
