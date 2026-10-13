# SPDX-License-Identifier: Apache-2.0
"""Runner/queue-copy evidence contracts, never execution of archived tests."""
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
PROJECTION = ROOT + 'cloud-selected-projection/'
WORKFLOW = '.github/workflows/titan-selected-projection.yml'
RUNNER_REPORT = 'stress-runner-boundary.json'
QUEUE_REPORT = 'queue-copy-results.json'
SPECS = {
    'stress_runner_boundary': ('stress-runner-boundary-tests.log', RUNNER_REPORT, 20,
                               STRESS + 'test_runner_guard_join.py'),
    'stress_runner_existing': ('stress-runner-existing-tests.log', None, 2, STRESS + 'test_runner.py'),
    'stress_runner_reporter': ('stress-runner-reporter-tests.log', None, 13,
                               PROJECTION + 'test_stress_runner_report.py'),
    'queue_copy': ('queue-copy-tests.log', QUEUE_REPORT, 23, MARKET + 'test_queue_copy.py'),
    'queue_copy_reporter': ('queue-copy-reporter-tests.log', None, 14,
                            PROJECTION + 'test_queue_copy_report.py'),
}
BINDINGS = {'runner_sha256': STRESS + 'runner.py',
            'adapter_sha256': STRESS + 'deadline_adapter.py',
            'test_sha256': STRESS + 'test_runner_guard_join.py'}
COUNTS = ('queue_comparisons', 'replacement_comparisons',
          'complete_transform_comparisons', 'feasibility_comparisons')


def log(count, ending='OK'):
    return f'Ran {count} tests in 0.01s\n\n{ending}\n'.encode()


def fixture():
    paths = {v[3] for v in SPECS.values()} | set(BINDINGS.values())
    paths.update({LAB + p for p in ('selected_action_sell.py', 'selected_sell_core.py',
                                   'mechanics.py', 'reference/decision/decision.py')})
    paths.update((PROJECTION + 'build_combined_report.py', WORKFLOW))
    files = {path: {'sha256': hashlib.sha256(path.encode()).hexdigest()} for path in paths}
    members = {v[0]: log(v[2]) for v in SPECS.values()}
    # This source-backed subset requires method identity, not only a count.
    members['stress-runner-existing-tests.log'] = (
        b'test_known_order_cost_keeps_sequence (test_runner.RunnerTests.test_known_order_cost_keeps_sequence) ... ok\n'
        b'test_summary_counts_cash_and_timeouts (test_runner.RunnerTests.test_summary_counts_cash_and_timeouts) ... ok\n'
        + log(2))
    runner = dict(tests_run=20, failures=[], errors=[], skipped=[],
                  actual_source=False, full_games=0, new_game_seeds=[],
                  **{k: files[p]['sha256'] for k, p in BINDINGS.items()})
    queue = dict(schema='titan.queue-copy.final.v1', methods=23, failures=0, errors=0,
                 passed=True, counts={k: 1 for k in COUNTS}, log=log(23).decode(),
                 source_sha256=files[LAB + 'selected_action_sell.py']['sha256'],
                 new_games=0, engine_transitions=0)
    members[RUNNER_REPORT] = json.dumps(runner).encode()
    members[QUEUE_REPORT] = json.dumps(queue).encode()
    snapshot = {'files': files, 'checkout': 'a'*40, 'run_id': '123', 'attempt': '1',
                'source_context': {'event': 'pull_request', 'event_sha': 'a'*40,
                                   'pull_request_head': 'b'*40}}
    core = {'status': 'COMPLETE_PASS', 'reported_test_methods': 51, 'checkout': 'a'*40}
    return members, snapshot, core


class RunnerQueueReceiptTests(unittest.TestCase):
    def setUp(self):
        self.members, self.snapshot, self.core = fixture()

    def read(self, **kwargs):
        return inspect_supplemental(self.members, self.snapshot, self.core, **kwargs)

    def edit(self, name, change):
        report = json.loads(self.members[name])
        change(report)
        self.members[name] = json.dumps(report).encode()

    def assert_issue(self, detail, status='FAIL'):
        result = self.read()
        self.assertEqual(result['status'], status, result)
        self.assertIn(detail, json.dumps(result['problems']))

    def test_five_suites_add_exactly_72_without_recounting_core(self):
        r = self.read()
        self.assertEqual(r['status'], 'COMPLETE_PASS', r)
        self.assertEqual(set(r['suites']), set(SPECS))
        self.assertEqual(r['reported_test_methods'], 72)
        self.assertEqual(r['core_plus_supplemental_methods'], 123)
        self.assertFalse(r['suites']['stress_runner_boundary']['actual_source'])
        self.assertEqual(r['suites']['stress_runner_existing']['retained_runner_methods'], 2)

    def test_inputs_and_core_failure_remain_unchanged(self):
        self.core['status'] = 'FAIL'
        before = copy.deepcopy((self.members, self.snapshot, self.core))
        r = self.read()
        self.assertEqual((self.members, self.snapshot, self.core), before)
        self.assertEqual(r['core_status'], 'FAIL')
        self.assertEqual((r['tests_rerun'], r['game_panels'], r['seeds_consumed']), (0, 0, []))

    def test_runtime_and_shared_runner_test_do_not_declare_execution(self):
        for label, spec in SPECS.items():
            if label != 'stress_runner_existing':
                self.snapshot['files'].pop(spec[3])
        r = inspect_supplemental({}, self.snapshot, self.core)
        self.assertEqual(r['status'], 'COMPLETE_PASS', r)
        self.assertEqual(r['reported_test_methods'], 0)
        self.assertEqual(r['suites'], {})

    def test_unique_test_source_without_its_log_is_incomplete(self):
        for label, spec in SPECS.items():
            with self.subTest(label=label):
                self.setUp(); self.members.pop(spec[0])
                if spec[1]: self.members.pop(spec[1])
                r = self.read()
                if label == 'stress_runner_existing':
                    self.assertNotIn(label, r['suites'])
                else:
                    self.assertEqual(r['status'], 'INCOMPLETE', r)
                    self.assertIn(spec[0], str(r['problems']))

    def test_missing_report_keeps_log_coverage_incomplete(self):
        for name in (RUNNER_REPORT, QUEUE_REPORT):
            with self.subTest(name=name):
                self.setUp(); self.members.pop(name)
                self.assert_issue(name, 'INCOMPLETE')

    def test_missing_log_keeps_report_coverage_incomplete(self):
        for label in ('stress_runner_boundary', 'queue_copy'):
            with self.subTest(label=label):
                self.setUp(); self.members.pop(SPECS[label][0])
                self.assert_issue(SPECS[label][0], 'INCOMPLETE')

    def test_failed_logs_are_not_hidden_by_reports(self):
        for label, spec in SPECS.items():
            with self.subTest(label=label):
                self.setUp(); self.members[spec[0]] = log(spec[2], 'FAILED (errors=1)')
                self.assert_issue(label)

    def test_truncated_reversed_duplicate_qualified_logs(self):
        for label, spec in SPECS.items():
            for text in (b'test started', b'OK\n'+log(spec[2]).split(b'\n\n')[0]+b'\n',
                         log(spec[2])*2, log(spec[2], 'OK (skipped=1)')):
                with self.subTest(label=label, text=text):
                    self.setUp(); self.members[spec[0]] = text
                    self.assert_issue(label, 'INCOMPLETE')

    def test_crlf_completions_and_embedded_log(self):
        for spec in SPECS.values():
            self.members[spec[0]] = self.members[spec[0]].replace(b'\n', b'\r\n')
        self.edit(QUEUE_REPORT, lambda d: d.update(log=d['log'].replace('\n', '\r\n')))
        self.assertEqual(self.read()['status'], 'COMPLETE_PASS')

    def test_missing_and_malformed_test_source(self):
        for spec in SPECS.values():
            for value in (None, {'sha256': 'not-a-hash'}):
                with self.subTest(path=spec[3], value=value):
                    self.setUp()
                    if value is None: self.snapshot['files'].pop(spec[3])
                    else: self.snapshot['files'][spec[3]] = value
                    self.assert_issue(spec[3], 'INCOMPLETE' if value is None else 'FAIL')

    def test_stress_count_must_match_log_and_not_be_boolean(self):
        for value in (True, 0, 19, 21, '20'):
            with self.subTest(value=value):
                self.setUp(); self.edit(RUNNER_REPORT, lambda d: d.update(tests_run=value))
                self.assert_issue('stress_runner_boundary')

    def test_stress_failures_errors_are_empty_arrays(self):
        for key in ('failures', 'errors'):
            for value in (0, False, None, {}, ['traceback']):
                with self.subTest(key=key, value=value):
                    self.setUp(); self.edit(RUNNER_REPORT, lambda d: d.update({key: value}))
                    self.assert_issue('stress_runner_boundary')

    def test_stress_skip_is_incomplete_not_passing_coverage(self):
        self.edit(RUNNER_REPORT, lambda d: d.update(skipped=['unsupported']))
        self.assert_issue('stress_runner_boundary', 'INCOMPLETE')
        self.edit(RUNNER_REPORT, lambda d: d.update(skipped=0))
        self.assert_issue('stress_runner_boundary')

    def test_stress_actual_source_cannot_relabel_local_methods(self):
        for value in (True, 0, 'false', None):
            with self.subTest(value=value):
                self.setUp(); self.edit(RUNNER_REPORT, lambda d: d.update(actual_source=value))
                self.assert_issue('actual_source')

    def test_stress_runner_adapter_and_test_hashes_bound(self):
        for key in BINDINGS:
            with self.subTest(key=key):
                self.setUp(); self.edit(RUNNER_REPORT, lambda d: d.update({key: '0'*64}))
                self.assert_issue(key)

    def test_stress_missing_hash_cannot_be_inferred(self):
        for key in BINDINGS:
            with self.subTest(key=key):
                self.setUp(); self.edit(RUNNER_REPORT, lambda d: d.pop(key))
                self.assert_issue(key, 'INCOMPLETE')

    def test_stress_scope_requires_zero_games_and_no_seeds(self):
        for changes in ({'full_games': False}, {'full_games': 1}, {'new_game_seeds': [1]}):
            with self.subTest(changes=changes):
                self.setUp(); self.edit(RUNNER_REPORT, lambda d: d.update(changes))
                self.assert_issue('stress_runner_boundary')

    def test_retained_runner_subset_does_not_recount_three_guard_tests(self):
        for count in (1, 3, 5):
            with self.subTest(count=count):
                self.setUp(); self.members['stress-runner-existing-tests.log'] = log(count)
                self.assert_issue('stress_runner_existing')

    def test_queue_schema_count_and_boolean_success(self):
        for changes in ({'schema': 'other'}, {'methods': True}, {'methods': 22}, {'methods': 24},
                        {'passed': False}, {'passed': 1}, {'passed': 'true'}):
            with self.subTest(changes=changes):
                self.setUp(); self.edit(QUEUE_REPORT, lambda d: d.update(changes))
                self.assert_issue('queue_copy')

    def test_queue_failures_errors_are_integer_zero(self):
        for key in ('failures', 'errors'):
            for value in (False, [], 1, '0', None):
                with self.subTest(key=key, value=value):
                    self.setUp(); self.edit(QUEUE_REPORT, lambda d: d.update({key: value}))
                    self.assert_issue('queue_copy')

    def test_queue_seller_hash_bound(self):
        self.edit(QUEUE_REPORT, lambda d: d.update(source_sha256='0'*64))
        self.assert_issue('queue_copy seller')
        self.edit(QUEUE_REPORT, lambda d: d.pop('source_sha256'))
        self.assert_issue('queue_copy seller', 'INCOMPLETE')

    def test_queue_no_games_or_engine_transitions(self):
        for key in ('new_games', 'engine_transitions'):
            for value in (True, False, 1, None):
                with self.subTest(key=key, value=value):
                    self.setUp(); self.edit(QUEUE_REPORT, lambda d: d.update({key: value}))
                    self.assert_issue('queue_copy')

    def test_queue_comparison_counts_are_not_test_counts(self):
        self.edit(QUEUE_REPORT, lambda d: d.update(counts={k: 500000 for k in COUNTS}))
        r = self.read(); self.assertEqual(r['status'], 'COMPLETE_PASS')
        self.assertEqual(r['reported_test_methods'], 72)
        self.assertEqual(r['suites']['queue_copy']['test_methods'], 23)

    def test_queue_counts_match_producer_nonnegative_contract(self):
        self.edit(QUEUE_REPORT, lambda d: d.update(counts={k: 0 for k in COUNTS}))
        self.assertEqual(self.read()['status'], 'COMPLETE_PASS')
        for key in COUNTS:
            for value in (False, -1, '1', None):
                with self.subTest(key=key, value=value):
                    self.setUp(); self.edit(QUEUE_REPORT, lambda d: d['counts'].update({key: value}))
                    self.assert_issue(key)

    def test_queue_counts_require_mapping(self):
        self.edit(QUEUE_REPORT, lambda d: d.update(counts=[]))
        self.assert_issue('counts is not an object')

    def test_queue_missing_embedded_log_is_incomplete(self):
        for value in (None, [], 1):
            with self.subTest(value=value):
                self.setUp(); self.edit(QUEUE_REPORT, lambda d: d.update(log=value))
                self.assert_issue('embedded', 'INCOMPLETE')

    def test_queue_embedded_completion_must_be_unambiguous(self):
        for value in ('', 'OK\nRan 23 tests in 0.1s\n', log(23).decode()*2,
                      log(23, 'OK (skipped=1)').decode()):
            with self.subTest(value=value):
                self.setUp(); self.edit(QUEUE_REPORT, lambda d: d.update(log=value))
                self.assert_issue('embedded', 'INCOMPLETE')

    def test_queue_embedded_failure_is_not_hidden_by_outer_pass(self):
        self.edit(QUEUE_REPORT, lambda d: d.update(log=log(23, 'FAILED (errors=1)').decode()))
        self.assert_issue('embedded')

    def test_queue_embedded_count_must_match_outer(self):
        self.edit(QUEUE_REPORT, lambda d: d.update(log=log(24).decode()))
        self.assert_issue('embedded count')

    def test_actual_tee_trailing_json_does_not_add_a_completion(self):
        self.members['queue-copy-tests.log'] += json.dumps({'methods': 23, 'passed': True}).encode()+b'\n'
        r = self.read(); self.assertEqual(r['status'], 'COMPLETE_PASS', r)
        self.assertEqual(r['reported_test_methods'], 72)

    def test_bad_json_duplicate_nonfinite_and_nonbytes(self):
        for name in (RUNNER_REPORT, QUEUE_REPORT):
            for value in (b'[]', b'{', b'{"failures":[],"failures":[]}', b'{"v":NaN}', b'\xff', 'text'):
                with self.subTest(name=name, value=value):
                    self.setUp(); self.members[name] = value
                    self.assert_issue(name)

    def test_reporter_workflow_and_builder_sources_are_bound(self):
        for path in (WORKFLOW, PROJECTION+'build_combined_report.py'):
            with self.subTest(path=path):
                self.setUp(); self.snapshot['files'].pop(path)
                self.assert_issue(path, 'INCOMPLETE')


if __name__ == '__main__':
    unittest.main(verbosity=2)
