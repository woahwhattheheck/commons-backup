# SPDX-License-Identifier: Apache-2.0
"""Synthetic parser regressions, not hosted-suite or game executions."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest

from supplemental_receipt import inspect_supplemental, SUPPLEMENTS, LOADER_SOURCES

# Retain the original three-suite fixture as a historical compatibility case.
LEGACY_SUPPLEMENTS = {name: SUPPLEMENTS[name]
                      for name in ('loader', 'empty_lot', 'joined_wrapper')}


def log(count: int, ending: str = 'OK') -> bytes:
    return f'\nRan {count} tests in 0.013s\n\n{ending}\n'.encode()


def fixture():
    files = {name: {'sha256': hashlib.sha256(name.encode()).hexdigest()}
             for _, _, _, paths in LEGACY_SUPPLEMENTS.values() for name in paths}
    files.update({name: {'sha256': hashlib.sha256(name.encode()).hexdigest()}
                  for name in LOADER_SOURCES.values()})
    snapshot = {'files': files}
    members = {name: log(count) for name, _, count, _ in LEGACY_SUPPLEMENTS.values()}
    report = {'schema': 'titan.selected-market-loader-tests.v1', 'test_methods': 7,
              'failures': 0, 'errors': 0, 'successful': True, 'game_panels': 0,
              'seeds_consumed': [], 'source_sha256': {
                  key: files[name]['sha256'] for key, name in LOADER_SOURCES.items()}}
    members['loader-results.json'] = json.dumps(report).encode()
    core = {'status': 'COMPLETE_PASS', 'reported_test_methods': 51, 'checkout': 'a' * 40}
    return members, snapshot, core


class SupplementalTests(unittest.TestCase):
    def setUp(self):
        self.members, self.snapshot, self.core = fixture()

    def read(self, **kwargs):
        return inspect_supplemental(self.members, self.snapshot, self.core, **kwargs)

    def change_report(self, **changes):
        report = json.loads(self.members['loader-results.json'])
        report.update(changes)
        self.members['loader-results.json'] = json.dumps(report).encode()

    def test_three_suites_add_28_to_existing_51(self):
        result = self.read()
        self.assertEqual(result['status'], 'COMPLETE_PASS')
        self.assertEqual(result['reported_test_methods'], 28)
        self.assertEqual(result['core_plus_supplemental_methods'], 79)
        self.assertEqual(result['represented_suite_count'], 3)
        self.assertEqual(result['tests_rerun'], 0)

    def test_caller_inputs_are_unchanged(self):
        before = copy.deepcopy((self.members, self.snapshot, self.core))
        self.read()
        self.assertEqual((self.members, self.snapshot, self.core), before)

    def test_historical_core_status_remains_separate(self):
        result = inspect_supplemental({}, {'files': {}}, {'status': 'INCOMPLETE', 'reported_test_methods': 37})
        self.assertEqual(result['core_status'], 'INCOMPLETE')
        self.assertEqual(result['reported_test_methods'], 0)
        self.assertEqual(result['core_plus_supplemental_methods'], 37)
        self.assertEqual(result['represented_suite_count'], 0)

    def test_require_all_reports_missing_suites_on_old_artifact(self):
        result = inspect_supplemental({}, {'files': {}}, self.core, require_all=True)
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['represented_suite_count'], len(SUPPLEMENTS))

    def test_known_source_without_log_is_incomplete(self):
        del self.members['empty-lot-tests.log']
        self.assertEqual(self.read()['status'], 'INCOMPLETE')

    def test_failed_supplement_does_not_replace_core_result(self):
        self.members['empty-lot-tests.log'] = log(15, 'FAILED (failures=1)')
        result = self.read()
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['core_status'], 'COMPLETE_PASS')
        self.assertFalse(result['suites']['empty_lot']['reported_pass'])

    def test_below_coverage_counts_fail(self):
        self.members['joined-wrapper-tests.log'] = log(5)
        self.assertEqual(self.read()['status'], 'FAIL')

    def test_truncated_duplicate_and_reversed_summaries(self):
        for text in (b'test ok\n', log(6) + log(6), b'OK\nRan 6 tests in 0.01s\n'):
            with self.subTest(text=text):
                self.members['joined-wrapper-tests.log'] = text
                self.assertEqual(self.read()['status'], 'INCOMPLETE')

    def test_qualified_completion_is_not_all_passed(self):
        self.members['empty-lot-tests.log'] = log(15, 'OK (skipped=1)')
        self.assertEqual(self.read()['status'], 'INCOMPLETE')

    def test_crlf_supplemental_logs(self):
        for name, value in list(self.members.items()):
            if name.endswith('.log'):
                self.members[name] = value.replace(b'\n', b'\r\n')
        self.assertEqual(self.read()['status'], 'COMPLETE_PASS')

    def test_loader_report_and_log_counts_must_agree(self):
        self.change_report(test_methods=8)
        self.assertEqual(self.read()['status'], 'FAIL')

    def test_loader_source_mismatch_is_not_accepted(self):
        self.change_report(source_sha256={key: 'f' * 64 for key in LOADER_SOURCES})
        self.assertEqual(self.read()['status'], 'FAIL')

    def test_missing_source_and_malformed_source_differ(self):
        name = LOADER_SOURCES['loader']
        del self.snapshot['files'][name]
        self.assertEqual(self.read()['status'], 'INCOMPLETE')
        self.snapshot['files'][name] = {'sha256': 'bad'}
        self.assertEqual(self.read()['status'], 'FAIL')

    def test_boolean_counts_are_not_integers(self):
        for key in ('test_methods', 'errors', 'failures', 'game_panels'):
            with self.subTest(key=key):
                self.members, self.snapshot, self.core = fixture()
                self.change_report(**{key: False})
                self.assertEqual(self.read()['status'], 'FAIL')

    def test_invalid_json_duplicate_nonfinite_and_nonobject(self):
        for value in (b'{', b'{"successful":true,"successful":false}', b'{"x":NaN}', b'[]'):
            with self.subTest(value=value):
                self.members['loader-results.json'] = value
                self.assertEqual(self.read()['status'], 'FAIL')

    def test_invalid_utf8_and_nonbytes_members(self):
        for name in ('loader-results.json', 'empty-lot-tests.log'):
            for value in (b'\xff', 'not bytes'):
                with self.subTest(name=name, value=value):
                    self.members, self.snapshot, self.core = fixture()
                    self.members[name] = value
                    self.assertEqual(self.read()['status'], 'FAIL')

    def test_failed_loader_or_nonzero_errors_remain_failed(self):
        for changes in ({'successful': False}, {'errors': 1}, {'successful': 'true'}, {'schema': 'unknown'}):
            with self.subTest(changes=changes):
                self.members, self.snapshot, self.core = fixture()
                self.change_report(**changes)
                self.assertEqual(self.read()['status'], 'FAIL')

    def test_unexpected_game_scope_is_not_relabelled(self):
        self.change_report(game_panels=1, seeds_consumed=[123])
        self.assertEqual(self.read()['status'], 'FAIL')

    def test_missing_loader_report_stays_explicit(self):
        del self.members['loader-results.json']
        self.assertEqual(self.read()['status'], 'INCOMPLETE')

    def test_invalid_source_mapping_stays_explicit(self):
        self.change_report(source_sha256=[])
        self.assertEqual(self.read()['status'], 'FAIL')
        self.snapshot['files'] = []
        self.assertEqual(self.read()['status'], 'FAIL')

    def test_missing_core_count_is_not_invented(self):
        del self.core['reported_test_methods']
        self.assertIsNone(self.read()['core_plus_supplemental_methods'])

    def test_unknown_suites_are_not_claimed_as_covered(self):
        self.members['funded-join-tests.log'] = log(16)
        result = self.read()
        self.assertEqual(set(result['suites']), set(LEGACY_SUPPLEMENTS))
        self.assertEqual(result['core_plus_supplemental_methods'], 79)


if __name__ == '__main__':
    unittest.main(verbosity=2)
