# SPDX-License-Identifier: Apache-2.0
"""Three added receipt contracts; all generated fixtures are synthetic."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest

from supplemental_receipt import (ADAPTIVE, LAB, WORKFLOW, SUPPLEMENTS,
                                  inspect_supplemental)
from test_supplemental_receipt import fixture, log

ADDED = ('capture_binding', 'score_schedule', 'workflow_bindings')


def expanded_fixture():
    members, snapshot, core = fixture()
    for label in ADDED:
        filename, _, count, paths = SUPPLEMENTS[label]
        members[filename] = log(count)
        for path in paths:
            snapshot['files'][path] = {'sha256': hashlib.sha256(path.encode()).hexdigest()}
    members['capture-binding-results.json'] = json.dumps({
        'tests': {'run': 22, 'failures': 0, 'errors': 0, 'success': True},
        'runtime_sha256': snapshot['files'][ADAPTIVE + 'runtime.py']['sha256'],
        'optimizer_sha256': snapshot['files'][LAB + 'selected_sell_core.py']['sha256'],
        'games': 0,
        'scope': 'synthetic parser fixture; not executed agent evidence',
    }).encode()
    return members, snapshot, core


class CoverSupplementTests(unittest.TestCase):
    def setUp(self):
        self.members, self.snapshot, self.core = expanded_fixture()

    def read(self, **kwargs):
        return inspect_supplemental(self.members, self.snapshot, self.core, **kwargs)

    def change_report(self, **changes):
        report = json.loads(self.members['capture-binding-results.json'])
        report.update(changes)
        self.members['capture-binding-results.json'] = json.dumps(report).encode()

    def change_tests(self, **changes):
        report = json.loads(self.members['capture-binding-results.json'])
        report['tests'].update(changes)
        self.members['capture-binding-results.json'] = json.dumps(report).encode()

    def test_adds_exactly_forty_methods_without_counting_foreign_suites(self):
        self.members['funded-join-tests.log'] = log(16)
        self.members['reporter-tests.log'] = log(24)
        self.members['deadline-cancellation-tests.log'] = log(18)
        result = self.read()
        self.assertEqual(result['status'], 'COMPLETE_PASS')
        self.assertEqual(result['reported_test_methods'], 68)
        self.assertEqual(result['core_plus_supplemental_methods'], 119)
        self.assertEqual(result['represented_suite_count'], 6)
        self.assertEqual({k: result['suites'][k]['test_methods'] for k in ADDED},
                         {'capture_binding': 22, 'score_schedule': 10, 'workflow_bindings': 8})

    def test_shared_runtime_dependencies_do_not_invent_historical_execution(self):
        members, snapshot, core = fixture()
        for label in ADDED:
            for path in SUPPLEMENTS[label][3][1:]:
                snapshot['files'][path] = {'sha256': 'a' * 64}
        result = inspect_supplemental(members, snapshot, core)
        self.assertEqual(result['status'], 'COMPLETE_PASS')
        self.assertEqual(result['reported_test_methods'], 28)
        self.assertEqual(result['represented_suite_count'], 3)

    def test_test_source_anchor_makes_missing_log_explicit(self):
        for label in ADDED:
            with self.subTest(label=label):
                self.members, self.snapshot, self.core = expanded_fixture()
                del self.members[SUPPLEMENTS[label][0]]
                self.assertEqual(self.read()['status'], 'INCOMPLETE')

    def test_log_requires_test_source_and_runtime_closure(self):
        for label in ADDED:
            for path in SUPPLEMENTS[label][3]:
                with self.subTest(path=path):
                    self.members, self.snapshot, self.core = expanded_fixture()
                    del self.snapshot['files'][path]
                    self.assertEqual(self.read()['status'], 'INCOMPLETE')

    def test_actual_capture_shape_needs_no_loader_schema(self):
        result = self.read()
        self.assertEqual(result['status'], 'COMPLETE_PASS')
        self.assertEqual(result['suites']['capture_binding']['test_methods'], 22)

    def test_flattened_loader_shape_is_not_a_capture_report(self):
        self.change_report(tests=None, test_methods=22, failures=0, errors=0, successful=True)
        self.assertEqual(self.read()['status'], 'FAIL')

    def test_capture_count_must_match_its_log(self):
        self.change_tests(run=23)
        self.assertEqual(self.read()['status'], 'FAIL')
        self.members['capture-binding-tests.log'] = log(23)
        self.assertEqual(self.read()['status'], 'COMPLETE_PASS')

    def test_capture_rejects_booleans_strings_floats_and_negative_counts(self):
        for key in ('run', 'failures', 'errors'):
            for value in (False, True, '0', 0.0, -1):
                with self.subTest(key=key, value=value):
                    self.members, self.snapshot, self.core = expanded_fixture()
                    self.change_tests(**{key: value})
                    self.assertEqual(self.read()['status'], 'FAIL')

    def test_capture_success_must_be_true(self):
        for value in (False, None, 'true', 1):
            with self.subTest(value=value):
                self.change_tests(success=value)
                self.assertEqual(self.read()['status'], 'FAIL')

    def test_capture_failure_and_error_reports_are_not_hidden_by_ok_log(self):
        for key in ('failures', 'errors'):
            with self.subTest(key=key):
                self.members, self.snapshot, self.core = expanded_fixture()
                self.change_tests(**{key: 1})
                self.assertEqual(self.read()['status'], 'FAIL')

    def test_capture_runtime_and_optimizer_must_match_snapshot(self):
        for key in ('runtime_sha256', 'optimizer_sha256'):
            with self.subTest(key=key):
                self.members, self.snapshot, self.core = expanded_fixture()
                self.change_report(**{key: 'f' * 64})
                self.assertEqual(self.read()['status'], 'FAIL')

    def test_capture_missing_hash_remains_incomplete(self):
        for key in ('runtime_sha256', 'optimizer_sha256'):
            with self.subTest(key=key):
                self.members, self.snapshot, self.core = expanded_fixture()
                report = json.loads(self.members['capture-binding-results.json'])
                del report[key]
                self.members['capture-binding-results.json'] = json.dumps(report).encode()
                self.assertEqual(self.read()['status'], 'INCOMPLETE')

    def test_capture_report_absence_is_not_satisfied_by_log(self):
        del self.members['capture-binding-results.json']
        self.assertEqual(self.read()['status'], 'INCOMPLETE')

    def test_added_suite_logs_retain_failed_qualified_and_partial_status(self):
        for label in ADDED:
            name, _, count, _ = SUPPLEMENTS[label]
            for content, expected in ((log(count, 'FAILED (errors=1)'), 'FAIL'),
                                      (log(count, 'OK (skipped=1)'), 'INCOMPLETE'),
                                      (b'test starts\n', 'INCOMPLETE')):
                with self.subTest(label=label, content=content):
                    self.members, self.snapshot, self.core = expanded_fixture()
                    self.members[name] = content
                    self.assertEqual(self.read()['status'], expected)

    def test_minimum_methods_apply_to_each_added_log(self):
        for label in ADDED:
            with self.subTest(label=label):
                self.members, self.snapshot, self.core = expanded_fixture()
                name, _, count, _ = SUPPLEMENTS[label]
                self.members[name] = log(count - 1)
                self.assertEqual(self.read()['status'], 'FAIL')

    def test_workflow_source_identity_is_present_and_valid(self):
        result = self.read()
        self.assertEqual(result['sources'][WORKFLOW], self.snapshot['files'][WORKFLOW]['sha256'])
        self.snapshot['files'][WORKFLOW] = {'sha256': 'invalid'}
        self.assertEqual(self.read()['status'], 'FAIL')

    def test_capture_games_and_seed_scope_stay_zero(self):
        for value in (None, False, True, 1, '0', 0.0):
            with self.subTest(value=value):
                self.members, self.snapshot, self.core = expanded_fixture()
                self.change_report(games=value)
                self.assertEqual(self.read()['status'], 'FAIL')
        self.members, self.snapshot, self.core = expanded_fixture()
        self.change_report(seeds_consumed=[1])
        self.assertEqual(self.read()['status'], 'FAIL')

    def test_capture_json_duplicate_keys_nonfinite_and_nonobject(self):
        for raw in (b'{"tests":{},"tests":{}}', b'{"tests":NaN}', b'[]', b'\xff'):
            with self.subTest(raw=raw):
                self.members['capture-binding-results.json'] = raw
                self.assertEqual(self.read()['status'], 'FAIL')

    def test_new_results_leave_original_objects_unchanged(self):
        before = copy.deepcopy((self.members, self.snapshot, self.core))
        self.read()
        self.assertEqual((self.members, self.snapshot, self.core), before)

    def test_individual_supplement_remains_usable_without_other_suites(self):
        members, snapshot, core = expanded_fixture()
        paths = SUPPLEMENTS['capture_binding'][3]
        sub = {name: value for name, value in members.items() if name.startswith('capture-')}
        result = inspect_supplemental(sub, {'files': {p: snapshot['files'][p] for p in paths}}, core)
        self.assertEqual(result['status'], 'COMPLETE_PASS')
        self.assertEqual(result['reported_test_methods'], 22)
        self.assertEqual(set(result['suites']), {'capture_binding'})

    def test_changed_source_cannot_be_fixed_by_other_suite_hash(self):
        self.snapshot['files'][ADAPTIVE + 'runtime.py']['sha256'] = 'e' * 64
        result = self.read()
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(any(p['detail'].startswith('capture_binding runtime:')
                            for p in result['problems']))

    def test_core_failure_is_carried_not_overridden(self):
        self.core['status'] = 'FAIL'
        result = self.read()
        self.assertEqual(result['status'], 'COMPLETE_PASS')
        self.assertEqual(result['core_status'], 'FAIL')
        self.assertEqual(result['tests_rerun'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
