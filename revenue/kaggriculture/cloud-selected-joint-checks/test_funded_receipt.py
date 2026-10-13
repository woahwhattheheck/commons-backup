# SPDX-License-Identifier: Apache-2.0
"""Funded-suite consumer contracts; synthetic evidence only, never engine games."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import check_joint_receipt as reader
from test_joint_receipt import synthetic_members


def funded_members():
    members = synthetic_members()
    snapshot = members['SOURCE-SNAPSHOT.json']
    for name in reader.FUNDED_SOURCES:
        snapshot['files'].setdefault(reader.ROOT + name, {
            'sha256': hashlib.sha256(name.encode()).hexdigest()})
    path = reader.LAB + 'test_ordered_selected_sell.py'
    snapshot['files'][path] = {'sha256': hashlib.sha256(path.encode()).hexdigest()}
    members['joined-wrapper-tests.log'] = 'Ran 6 tests in 0.1s\n\nOK\n'
    members['funded-join-tests.log'] = 'Ran 16 tests in 0.1s\n\nOK\n'
    members['funded-join-results.json'] = dict(
        test_methods=16, failures=0, errors=0, successful=True,
        full_games=0, new_game_seeds=0, official_transitions=14,
        workflow_run='123', workflow_attempt='1',
        sources={name: dict(snapshot['files'][reader.ROOT + name])
                 for name in reader.FUNDED_SOURCES})
    return members


class FundedReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'receipt.zip'
        self.members = funded_members()

    def write(self):
        with zipfile.ZipFile(self.path, 'w') as archive:
            for name, value in self.members.items():
                archive.writestr(name, json.dumps(value) if isinstance(value, dict) else value)
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def inspect(self, **kwargs):
        return reader.inspect_archive(self.path, expected_sha256=self.write(), **kwargs)

    def test_funded_discovery_and_scope(self):
        out = self.inspect()
        self.assertEqual((out['status'], out['reported_test_methods']), ('COMPLETE_PASS', 73))
        self.assertEqual(out['suites']['funded_join']['official_transitions'], 14)
        self.assertEqual(out['tests_rerun'], 0)
        self.assertEqual(out['game_panels'], 0)
        self.assertEqual(out['seeds_consumed'], [])

    def test_require_absent_funded_suite(self):
        self.members = synthetic_members()
        out = self.inspect(required_suites=('funded_join',))
        self.assertEqual(out['status'], 'INCOMPLETE')
        self.assertIn('funded_join', out['suite_coverage']['required_suites'])

    def test_aggregate_declares_missing_funded_suite(self):
        self.members = synthetic_members()
        self.members['COMBINED-RESULTS.json'] = dict(total_tests=67, funded_join_tests=16)
        self.assertEqual(self.inspect()['status'], 'INCOMPLETE')

    def test_noninteger_or_insufficient_counts(self):
        for value in (True, 0, 15, 16.0, '16', None):
            with self.subTest(value=value):
                self.members = funded_members()
                self.members['funded-join-results.json']['test_methods'] = value
                self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_no_game_scope_is_typed(self):
        for field in ('full_games', 'new_game_seeds'):
            for value in (True, False, 1, 0.0, None):
                with self.subTest(field=field, value=value):
                    self.members = funded_members()
                    self.members['funded-join-results.json'][field] = value
                    self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_positive_transition_count_is_required(self):
        for value in (True, 0, -1, None):
            with self.subTest(value=value):
                self.members = funded_members()
                self.members['funded-join-results.json']['official_transitions'] = value
                self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_report_sources_shape_and_hash_validation(self):
        for value in ([], None, {'cloud-integration-differentials/funded_main.py': 'wrong'}):
            with self.subTest(value=value):
                self.members = funded_members()
                self.members['funded-join-results.json']['sources'] = value
                self.assertIn(self.inspect()['status'], ('FAIL', 'INCOMPLETE'))
        self.members = funded_members()
        self.members['funded-join-results.json']['sources'][reader.FUNDED_SOURCES[-1]]['sha256'] = 'not-a-hash'
        self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_additional_reported_sources_are_checked(self):
        key = 'cloud-composition-cases/cypress/extra.py'
        digest = hashlib.sha256(key.encode()).hexdigest()
        self.members['SOURCE-SNAPSHOT.json']['files'][reader.ROOT + key] = {'sha256': digest}
        self.members['funded-join-results.json']['sources'][key] = {'sha256': digest}
        self.assertEqual(self.inspect()['status'], 'COMPLETE_PASS')
        self.members['funded-join-results.json']['sources'][key]['sha256'] = '0' * 64
        self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_larger_matching_suite_not_hardcoded_to_16(self):
        self.members['funded-join-tests.log'] = 'Ran 17 tests in 0.2s\n\nOK\n'
        self.members['funded-join-results.json']['test_methods'] = 17
        out = self.inspect()
        self.assertEqual((out['status'], out['reported_test_methods']), ('COMPLETE_PASS', 74))

    def test_qualified_success_is_incomplete(self):
        self.members['funded-join-tests.log'] = 'Ran 16 tests in 0.1s\n\nOK (skipped=1)\n'
        self.assertEqual(self.inspect()['status'], 'INCOMPLETE')

    def test_unrecognized_test_log_cannot_imply_full_coverage(self):
        self.members['new-check-tests.log'] = 'Ran 9 tests in 0.1s\n\nOK\n'
        out = self.inspect()
        self.assertEqual(out['status'], 'INCOMPLETE')
        self.assertEqual(out['suite_coverage']['unrecognized_test_logs'], ['new-check-tests.log'])
        self.members['new-check-tests.log'] = 'Ran 9 tests in 0.1s\n\nFAILED (errors=1)\n'
        self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_legacy_aggregate_is_advisory_not_test_result(self):
        self.members['COMBINED-RESULTS.json'] = dict(checkout='a'*40, total_tests=51)
        out = self.inspect()
        self.assertEqual(out['status'], 'COMPLETE_PASS')
        self.assertFalse(out['aggregate_summary']['total_matches_recognized'])
        self.assertFalse(out['aggregate_summary']['authoritative_for_suite_verdicts'])

    def test_cli_require_funded_and_unknown_suite(self):
        digest = self.write()
        output = Path(self.tmp.name) / 'out' / 'receipt.json'
        command = [sys.executable, str(Path(reader.__file__)), str(self.path),
                   '--expected-sha256', digest, '--require-suite', 'funded_join',
                   '--json-output', str(output)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(output.read_text())['reported_test_methods'], 73)
        command[6] = 'unknown_suite'
        run = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 3, run.stderr)


if __name__ == '__main__':
    unittest.main()
