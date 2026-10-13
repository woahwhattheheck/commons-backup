# SPDX-License-Identifier: Apache-2.0
"""Bind queue-copy JSON reports to the producer's persisted console summary."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest

from supplemental_receipt import inspect_supplemental

ROOT = 'revenue/kaggriculture/'
LAB = ROOT + 'cloud-execution-lab/'
MARKET = ROOT + 'cloud-selected-market-checks/'
REPORT = 'queue-copy-results.json'
LOG = 'queue-copy-tests.log'
PATHS = (
    MARKET + 'test_queue_copy.py',
    LAB + 'selected_action_sell.py',
    LAB + 'selected_sell_core.py',
    LAB + 'mechanics.py',
    LAB + 'reference/decision/decision.py',
)
COUNTS = ('queue_comparisons', 'replacement_comparisons',
          'complete_transform_comparisons', 'feasibility_comparisons')


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def inner_log():
    return (
        'test_copy (test_queue_copy.CopyCases.test_copy) ... ok\n'
        '\n----------------------------------------------------------------------\n'
        'Ran 23 tests in 0.010s\n\nOK\n'
    )


def fixture(*, producer=True):
    hashes = {path: hashlib.sha256(path.encode()).hexdigest() for path in PATHS}
    report = {
        'schema': 'titan.queue-copy.final.v1',
        'methods': 23,
        'failures': 0,
        'errors': 0,
        'passed': True,
        'counts': {name: index + 1 for index, name in enumerate(COUNTS)},
        'log': inner_log(),
        'source_sha256': hashes[LAB + 'selected_action_sell.py'],
        'new_games': 0,
        'engine_transitions': 0,
    }
    if producer:
        report['python'] = '3.12.test'
    summary = {key: value for key, value in report.items()
               if key not in ('log', 'benchmark')}
    outer = report['log']
    if producer:
        outer += json.dumps(summary, sort_keys=True) + '\n'
    members = {LOG: outer.encode(), REPORT: json.dumps(report).encode()}
    snapshot = {'files': {path: {'sha256': digest} for path, digest in hashes.items()},
                'checkout': 'a' * 40}
    core = {'status': 'COMPLETE_PASS', 'reported_test_methods': 51,
            'checkout': 'a' * 40}
    return members, snapshot, core


class QueueTeeConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.members, self.snapshot, self.core = fixture()

    def read(self):
        return inspect_supplemental(self.members, self.snapshot, self.core)

    def report(self):
        return json.loads(self.members[REPORT])

    def put_report(self, report):
        self.members[REPORT] = json.dumps(report).encode()

    def summary(self):
        return json.loads(self.members[LOG].decode().rstrip().splitlines()[-1])

    def put_summary(self, summary, *, prefix=None, suffix='\n'):
        if prefix is None:
            prefix = self.report()['log']
        self.members[LOG] = (prefix + json.dumps(summary) + suffix).encode()

    def assert_failure(self, fragment):
        result = self.read()
        self.assertEqual(result['status'], 'FAIL', result)
        self.assertIn(fragment, json.dumps(result['problems']))

    def test_matching_producer_outputs_pass_and_are_marked_bound(self):
        result = self.read()
        self.assertEqual(result['status'], 'COMPLETE_PASS', result)
        self.assertTrue(result['suites']['queue_copy']['emitted_summary_bound'])

    def test_report_change_cannot_hide_behind_stale_summary(self):
        report = self.report(); report['counts']['queue_comparisons'] += 1
        self.put_report(report)
        self.assert_failure('emitted summary differs from report')

    def test_summary_change_cannot_hide_behind_valid_report(self):
        summary = self.summary(); summary['source_sha256'] = '0' * 64
        self.put_summary(summary)
        self.assert_failure('emitted summary differs from report')

    def test_outer_and_embedded_unittest_text_must_match(self):
        self.put_summary(self.summary(), prefix=self.report()['log'].replace('test_copy', 'test_other'))
        self.assert_failure('emitted unittest text differs from report')

    def test_malformed_duplicate_and_nonfinite_summaries_fail(self):
        for tail, fragment in (
            ('{', 'invalid emitted summary'),
            ('{"methods":23,"methods":24}', 'duplicate JSON key'),
            ('{"methods":NaN}', 'non-finite JSON'),
            ('[]', 'emitted summary is not an object'),
        ):
            with self.subTest(tail=tail):
                self.setUp()
                self.members[LOG] = (self.report()['log'] + tail + '\n').encode()
                self.assert_failure(fragment)

    def test_console_fields_are_type_sensitive(self):
        summary = self.summary(); summary['methods'] = 23.0
        self.put_summary(summary)
        self.assert_failure('emitted summary differs from report')

    def test_missing_or_repeated_summary_is_not_complete_emission(self):
        for outer, fragment in (
            (self.report()['log'], 'invalid emitted summary'),
            (self.members[LOG].decode() + json.dumps(self.summary()) + '\n',
             'emitted unittest text differs from report'),
        ):
            with self.subTest(fragment=fragment):
                self.setUp(); self.members[LOG] = outer.encode()
                self.assert_failure(fragment)

    def test_crlf_output_is_equivalent(self):
        self.members[LOG] = self.members[LOG].replace(b'\n', b'\r\n')
        report = self.report(); report['log'] = report['log'].replace('\n', '\r\n')
        summary = {key: value for key, value in report.items()
                   if key not in ('log', 'benchmark')}
        self.put_report(report)
        self.members[LOG] = (report['log'] + json.dumps(summary) + '\r\n').encode()
        self.assertEqual(self.read()['status'], 'COMPLETE_PASS')

    def test_matching_future_metadata_and_benchmark_are_preserved(self):
        report = self.report(); report['future_field'] = {'value': 1}; report['benchmark'] = {'x': 2}
        self.put_report(report)
        summary = {key: value for key, value in report.items()
                   if key not in ('log', 'benchmark')}
        self.put_summary(summary)
        self.assertEqual(self.read()['status'], 'COMPLETE_PASS')

    def test_invalid_present_python_identity_fails(self):
        report = self.report(); report['python'] = ['not', 'text']
        self.put_report(report)
        self.assert_failure('invalid producer Python identity')

    def test_legacy_report_without_python_or_summary_stays_compatible(self):
        members, snapshot, core = fixture(producer=False)
        result = inspect_supplemental(members, snapshot, core)
        self.assertEqual(result['status'], 'COMPLETE_PASS', result)
        self.assertNotIn('emitted_summary_bound', result['suites']['queue_copy'])

    def test_legacy_unstructured_trailing_json_stays_compatible(self):
        members, snapshot, core = fixture(producer=False)
        members[LOG] += b'{"methods":23,"passed":true}\n'
        result = inspect_supplemental(members, snapshot, core)
        self.assertEqual(result['status'], 'COMPLETE_PASS', result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
