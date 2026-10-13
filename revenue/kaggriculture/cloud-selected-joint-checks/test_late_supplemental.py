# SPDX-License-Identifier: Apache-2.0
"""Cancellation/ledger evidence-reader contracts; no archived code is executed."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest

from supplemental_receipt import inspect_supplemental

ROOT = 'revenue/kaggriculture/'
LAB = ROOT + 'cloud-execution-lab/'
MARKET = ROOT + 'cloud-selected-market-checks/'
STRESS = ROOT + 'cloud-economic-stress/'
CANCEL = 'deadline-cancellation.json'
LEDGER = 'ledger-schedule-results.json'
SPECS = {
    'deadline_cancellation': ('deadline-cancellation-tests.log', CANCEL, 18,
                              STRESS + 'cancellation/test_deadline_cancellation.py'),
    'ledger_schedule': ('ledger-schedule-tests.log', LEDGER, 20,
                        MARKET + 'test_ledger_schedule.py'),
}
CLOSURE = (STRESS + 'test_runner.py', STRESS + 'cancellation/measure_cancellation.py',
           STRESS + 'cancellation/source/plan_overlay_commit_excerpt.py')
RUNTIME = ('selected_action_sell.py', 'selected_sell_core.py', 'mechanics.py',
           'reference/decision/decision.py')
ENGINE = ('kaggriculture.py', 'kaggriculture.json', 'utils.py')
REFERENCE = MARKET + 'fixtures/ledger_feasible_0364fa0a.py'
COUNTS = ('feasibility_comparisons', 'transform_comparisons',
          'ordered_capacity_comparisons', 'official_market_calls')


def log(n: int, ending: str = 'OK') -> bytes:
    return f'Ran {n} tests in 0.01s\n\n{ending}\n'.encode()


def fixture():
    paths = [v[3] for v in SPECS.values()] + list(CLOSURE)
    paths += [STRESS + 'deadline_adapter.py', REFERENCE]
    paths += [LAB + p for p in RUNTIME] + [LAB + 'reference/engine/' + p for p in ENGINE]
    files = {p: {'sha256': hashlib.sha256(p.encode()).hexdigest()} for p in paths}
    snapshot = {'files': files, 'checkout': 'a'*40, 'run_id': '11', 'attempt': '1',
                'source_context': {'event': 'pull_request', 'event_sha': 'a'*40,
                                   'pull_request_head': 'b'*40,
                                   'checkout_semantics': 'pull_request_merge'}}
    members = {v[0]: log(v[2]) for v in SPECS.values()}
    members[CANCEL] = json.dumps({
        'tests_run': 18, 'failures': [], 'errors': [], 'skipped': [],
        'new_regression_methods': 15, 'unchanged_upstream_guard_methods': 3,
        'adapter': '/unused/absolute/path/deadline_adapter.py',
        'adapter_sha256': files[STRESS + 'deadline_adapter.py']['sha256'],
    }).encode()
    members[LEDGER] = json.dumps({
        'test_methods': 20, 'failures': 0, 'errors': 0, 'skipped': 0,
        'successful': True, 'full_games': 0, 'game_seeds': [],
        'sources_sha256': {p: files[LAB+p]['sha256'] for p in RUNTIME},
        'engine_sha256': {p: files[LAB+'reference/engine/'+p]['sha256'] for p in ENGINE},
        'reference_method_sha256': files[REFERENCE]['sha256'],
        'counts': {key: 1 for key in COUNTS},
    }).encode()
    return members, snapshot, {'status': 'COMPLETE_PASS', 'reported_test_methods': 51,
                               'checkout': snapshot['checkout']}


class LateSupplementalTests(unittest.TestCase):
    def setUp(self):
        self.members, self.snapshot, self.core = fixture()

    def read(self):
        return inspect_supplemental(self.members, self.snapshot, self.core)

    def revise(self, name, change):
        d = json.loads(self.members[name]); change(d)
        self.members[name] = json.dumps(d).encode()

    def bad(self, label, status='FAIL'):
        out = self.read()
        self.assertEqual(out['status'], status, out)
        self.assertIn(label, json.dumps(out['problems']), out)

    def test_two_suites_add_38_not_a_full_reader_total(self):
        r = self.read()
        self.assertEqual(r['status'], 'COMPLETE_PASS', r)
        self.assertEqual(r['reported_test_methods'], 38)
        self.assertEqual(set(r['suites']), set(SPECS))
        self.assertEqual(r['core_plus_supplemental_methods'], 89)
        self.assertEqual(r['suites']['deadline_cancellation']['test_methods'], 18)

    def test_inputs_and_core_verdict_preserved(self):
        self.core['status'] = 'FAIL'
        before = copy.deepcopy((self.members, self.snapshot, self.core))
        r = self.read()
        self.assertEqual((self.members, self.snapshot, self.core), before)
        self.assertEqual(r['core_status'], 'FAIL')
        self.assertEqual(r['tests_rerun'], 0)
        self.assertEqual(r['game_panels'], 0)
        self.assertEqual(r['seeds_consumed'], [])

    def test_source_only_runtime_does_not_declare_late_tests(self):
        for spec in SPECS.values():
            self.snapshot['files'].pop(spec[3])
        r = inspect_supplemental({}, self.snapshot, self.core)
        self.assertEqual(r['status'], 'COMPLETE_PASS', r)
        self.assertEqual(r['reported_test_methods'], 0)
        self.assertEqual(r['represented_suite_count'], 0)

    def test_missing_late_log_or_report_remains_incomplete(self):
        for label, (log_name, report_name, _, _) in SPECS.items():
            for name in (log_name, report_name):
                with self.subTest(name=name):
                    self.setUp(); self.members.pop(name)
                    self.bad(name, 'INCOMPLETE')

    def test_failed_late_logs_are_not_pass(self):
        for label, (name, _, count, _) in SPECS.items():
            with self.subTest(label=label):
                self.setUp(); self.members[name] = log(count, 'FAILED (failures=1)')
                self.bad(label)

    def test_late_log_completion_order_and_skips(self):
        for label, (name, _, count, _) in SPECS.items():
            for data in (b'test started', log(count)*2,
                         f'OK\nRan {count} tests in 0.1s\n'.encode(),
                         log(count, 'OK (skipped=1)')):
                with self.subTest(label=label, data=data):
                    self.setUp(); self.members[name] = data
                    self.bad(label, 'INCOMPLETE')

    def test_late_log_report_counts_agree(self):
        for name, key, value in ((CANCEL, 'tests_run', 19), (LEDGER, 'test_methods', 21)):
            with self.subTest(name=name):
                self.setUp(); self.revise(name, lambda d: d.update({key: value}))
                self.assertEqual(self.read()['status'], 'FAIL')

    def test_cancellation_failures_errors_are_lists_and_empty(self):
        for field in ('failures', 'errors'):
            for value in (0, False, None, {}, ['traceback']):
                with self.subTest(field=field, value=value):
                    self.setUp(); self.revise(CANCEL, lambda d: d.update({field: value}))
                    self.bad('deadline_cancellation')

    def test_cancellation_skipped_has_distinct_incomplete_status(self):
        self.revise(CANCEL, lambda d: d.update(skipped=['unavailable signal']))
        self.bad('deadline_cancellation', 'INCOMPLETE')
        self.revise(CANCEL, lambda d: d.update(skipped=0))
        self.bad('deadline_cancellation')

    def test_cancellation_partition_integer_and_count_contract(self):
        for changes in ({'new_regression_methods': True}, {'unchanged_upstream_guard_methods': False},
                        {'new_regression_methods': 14}, {'new_regression_methods': 16},
                        {'unchanged_upstream_guard_methods': 4}, {'tests_run': True}):
            with self.subTest(changes=changes):
                self.setUp(); self.revise(CANCEL, lambda d: d.update(changes))
                self.bad('deadline_cancellation')

    def test_cancellation_future_additive_methods_keep_inherited_three(self):
        self.revise(CANCEL, lambda d: d.update(tests_run=19, new_regression_methods=16))
        self.members['deadline-cancellation-tests.log'] = log(19)
        r = self.read(); self.assertEqual(r['status'], 'COMPLETE_PASS', r)
        self.assertEqual(r['reported_test_methods'], 39)

    def test_cancellation_adapter_hash_mismatch(self):
        self.revise(CANCEL, lambda d: d.update(adapter_sha256='0'*64))
        self.bad('deadline_cancellation adapter')

    def test_cancellation_adapter_missing_identity(self):
        self.revise(CANCEL, lambda d: d.pop('adapter_sha256'))
        self.bad('deadline_cancellation adapter', 'INCOMPLETE')

    def test_cancellation_source_closure_missing(self):
        for path in CLOSURE:
            with self.subTest(path=path):
                self.setUp(); del self.snapshot['files'][path]
                self.bad(path, 'INCOMPLETE')

    def test_ledger_status_counts_reject_boolean_or_nonzero(self):
        for key in ('failures', 'errors'):
            for value in (True, False, -1, '0', [], 1):
                with self.subTest(key=key, value=value):
                    self.setUp(); self.revise(LEDGER, lambda d: d.update({key: value}))
                    self.bad('ledger_schedule')

    def test_ledger_skips_are_not_full_coverage(self):
        self.revise(LEDGER, lambda d: d.update(skipped=1))
        self.bad('ledger_schedule', 'INCOMPLETE')
        self.revise(LEDGER, lambda d: d.update(skipped=False))
        self.bad('ledger_schedule')

    def test_ledger_success_requires_true_boolean(self):
        for value in (False, 1, 'true', None):
            with self.subTest(value=value):
                self.setUp(); self.revise(LEDGER, lambda d: d.update(successful=value))
                self.bad('ledger_schedule')

    def test_ledger_runtime_hashes_match_snapshot(self):
        for key in RUNTIME:
            with self.subTest(key=key):
                self.setUp(); self.revise(LEDGER, lambda d: d['sources_sha256'].update({key: '0'*64}))
                self.bad(key)

    def test_ledger_engine_hashes_match_snapshot(self):
        for key in ENGINE:
            with self.subTest(key=key):
                self.setUp(); self.revise(LEDGER, lambda d: d['engine_sha256'].update({key: '0'*64}))
                self.bad(key)

    def test_ledger_reference_hash_is_bound(self):
        self.revise(LEDGER, lambda d: d.update(reference_method_sha256='0'*64))
        self.bad('reference method')

    def test_ledger_missing_engine_reference_is_incomplete(self):
        for path in (REFERENCE, LAB+'reference/engine/kaggriculture.py'):
            with self.subTest(path=path):
                self.setUp(); del self.snapshot['files'][path]
                self.bad(path, 'INCOMPLETE')

    def test_ledger_source_hash_mappings_require_objects(self):
        for key in ('sources_sha256', 'engine_sha256'):
            with self.subTest(key=key):
                self.setUp(); self.revise(LEDGER, lambda d: d.update({key: []}))
                self.bad(key)

    def test_ledger_counts_require_positive_integers(self):
        for key in COUNTS:
            for value in (False, 0, -1, '1'):
                with self.subTest(key=key, value=value):
                    self.setUp(); self.revise(LEDGER, lambda d: d['counts'].update({key: value}))
                    self.bad(key)

    def test_ledger_game_scope_is_not_forgiven(self):
        for changes in ({'full_games': 1}, {'full_games': False}, {'game_seeds': [123]}):
            with self.subTest(changes=changes):
                self.setUp(); self.revise(LEDGER, lambda d: d.update(changes))
                self.bad('ledger_schedule')

    def test_late_json_duplicate_keys_nonfinite_and_nonobject_rejected(self):
        for name in (CANCEL, LEDGER):
            for data in (b'[]', b'{', b'{"tests_run":18,"tests_run":19}', b'{"v":NaN}'):
                with self.subTest(name=name, data=data):
                    self.setUp(); self.members[name] = data
                    self.bad(name)

    def test_source_presence_cannot_replace_missing_test_source(self):
        for spec in SPECS.values():
            with self.subTest(path=spec[3]):
                self.setUp(); del self.snapshot['files'][spec[3]]
                self.bad(spec[3], 'INCOMPLETE')

    def test_reported_absolute_adapter_path_is_never_opened(self):
        self.revise(CANCEL, lambda d: d.update(adapter='/not/a/real/source'))
        self.assertEqual(self.read()['status'], 'COMPLETE_PASS')

    def test_crlf_late_logs(self):
        for spec in SPECS.values():
            self.members[spec[0]] = self.members[spec[0]].replace(b'\n', b'\r\n')
        self.assertEqual(self.read()['status'], 'COMPLETE_PASS')


if __name__ == '__main__':
    unittest.main(verbosity=2)
