"""Synthetic regression tests; no network, runner, or University data required."""
import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('uiowa_test_reliability', HERE / 'analyze.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def row(attempt=1, outcome='fail', **changes):
    clock_attempt = attempt if isinstance(attempt, int) and 1 <= attempt < 10 else 1
    values = dict.fromkeys(a.FIELDS, '')
    values.update(run_id='synthetic-run', group='ESS', service='fictional-registration',
                  test_id='synthetic-check', revision='example-revision-a', environment='fixture-env-1',
                  data_version='fixture-data-1', attempt=str(attempt), outcome=outcome,
                  failure_kind='test' if outcome == 'fail' else '',
                  failure_signature='assertion-example' if outcome == 'fail' else '',
                  queued_at=f'2026-01-01T00:0{clock_attempt-1}:00Z',
                  started_at=f'2026-01-01T00:0{clock_attempt-1}:10Z',
                  finished_at=f'2026-01-01T00:0{clock_attempt-1}:30Z',
                  triage='unreviewed', source_ref=f'synthetic:run/attempt/{attempt}')
    values.update(changes)
    return values


def csv_text(rows, fields=a.FIELDS):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def report(*rows, **options):
    return a.analyze(a.parse_csv(csv_text(rows)), synthetic=True, **options)


class ReliabilityTests(unittest.TestCase):
    def test_recovery_is_candidate_not_confirmed_flakiness(self):
        r = report(row(), row(2, 'pass'))
        c = r['cohorts'][0]
        self.assertEqual(c['observed_pattern'], 'retry_recovered_unconfirmed')
        self.assertEqual(c['reported_triage'], 'unreviewed')
        self.assertEqual(r['summary']['observed_test_retry_recovery_rate'], a.rate(1, 1))
        self.assertEqual(c['logical_feedback_seconds'], 90)
        self.assertEqual(c['retry_execution']['total_observed_seconds'], 20)
        self.assertEqual(c['failure_signatures'], ['assertion-example'])

    def test_repeated_failure_does_not_prove_product_defect(self):
        r = report(row(), row(2))
        self.assertEqual(r['cohorts'][0]['observed_pattern'], 'repeated_test_failure_unconfirmed')
        self.assertEqual(r['cohorts'][0]['reported_triage'], 'unreviewed')
        self.assertEqual(r['summary']['observed_test_retry_recovery_rate'], a.rate(0, 1))

    def test_different_failure_signatures_remain_unresolved(self):
        r = report(row(), row(2, failure_signature='another-failure'))
        self.assertEqual(r['cohorts'][0]['observed_pattern'], 'unresolved_failure')

    def test_changed_context_never_counts_as_retry_recovery(self):
        for field in ('revision', 'environment', 'data_version'):
            with self.subTest(field=field):
                r = report(row(), row(2, 'pass', **{field: 'changed'}))
                self.assertEqual(r['cohorts'][0]['observed_pattern'], 'unresolved_failure')
                self.assertIn('comparison_context_changed', r['cohorts'][0]['data_issues'])
                self.assertIsNone(r['summary']['observed_test_retry_recovery_rate']['fraction'])

    def test_missing_context_never_proves_recovery(self):
        for field in ('revision', 'environment', 'data_version'):
            with self.subTest(field=field):
                r = report(row(**{field: ''}), row(2, 'pass', **{field: ''}))
                self.assertFalse(r['cohorts'][0]['comparison_context_stable'])
                self.assertEqual(r['cohorts'][0]['observed_pattern'], 'unresolved_failure')

    def test_infrastructure_recovery_not_a_flaky_test(self):
        for first in (row(failure_kind='infrastructure'), row(outcome='error')):
            with self.subTest(first=first['outcome']):
                r = report(first, row(2, 'pass'))
                self.assertEqual(r['cohorts'][0]['observed_pattern'], 'infrastructure_or_execution_error')
                self.assertIsNone(r['summary']['observed_test_retry_recovery_rate']['fraction'])

    def test_unknown_failure_kind_not_a_test_recovery(self):
        for kind in ('', 'unknown'):
            with self.subTest(kind=kind):
                r = report(row(failure_kind=kind), row(2, 'pass'))
                self.assertEqual(r['cohorts'][0]['observed_pattern'], 'unresolved_failure')

    def test_confirmed_triage_requires_reference(self):
        for triage in ('confirmed_flaky', 'confirmed_defect', 'confirmed_infrastructure'):
            with self.subTest(triage=triage):
                with self.assertRaises(a.InputError):
                    report(row(triage=triage))
                r = report(row(triage=triage, triage_ref='synthetic:triage/decision'))
                self.assertEqual(r['cohorts'][0]['reported_triage'], triage)
                self.assertIn('synthetic:triage/decision', r['cohorts'][0]['triage_refs'])

    def test_conflicting_triage_is_preserved(self):
        r = report(row(triage='confirmed_defect', triage_ref='synthetic:triage/a'),
                   row(2, triage='confirmed_flaky', triage_ref='synthetic:triage/b'))
        self.assertEqual(r['cohorts'][0]['reported_triage'], 'conflicting')
        self.assertEqual(r['investigations'][0]['kind'], 'conflicting_triage')
        self.assertEqual(len(r['cohorts'][0]['triage_refs']), 2)

    def test_missing_time_is_not_zero(self):
        r = report(row(outcome='pass', queued_at=''))
        s = r['summary']
        self.assertEqual(s['queue']['observed_count'], 0)
        self.assertEqual(s['queue']['unavailable_count'], 1)
        self.assertIsNone(s['queue']['p50_seconds'])
        self.assertEqual(s['execution']['p50_seconds'], 20)
        self.assertIsNone(s['logical_feedback']['p50_seconds'])

    def test_invalid_or_naive_time_excluded_without_losing_outcome(self):
        for stamp in ('not-a-time', '2026-01-01T00:00:00', '2026-13-99T00:00:00Z'):
            with self.subTest(stamp=stamp):
                r = report(row(outcome='pass', queued_at=stamp))
                self.assertIsNone(r['summary']['queue']['p50_seconds'])
                self.assertEqual(r['summary']['observed_final_pass_rate'], a.rate(1, 1))
                self.assertIn('invalid:queued_at', r['row_issues'][0]['issues'])

    def test_timezone_offsets_normalized(self):
        r = report(row(outcome='pass', queued_at='2025-12-31T19:00:00-05:00'))
        self.assertEqual(r['summary']['queue']['p50_seconds'], 10)

    def test_reversed_clock_invalidates_all_row_durations(self):
        r = report(row(queued_at='2026-01-01T00:01:00Z'))
        for key in ('queue', 'execution', 'logical_feedback'):
            self.assertIsNone(r['summary'][key]['p50_seconds'])

    def test_attempt_overlap_invalidates_recovery_and_feedback(self):
        r = report(row(), row(2, 'pass', started_at='2026-01-01T00:00:20Z'))
        c = r['cohorts'][0]
        self.assertEqual(c['observed_pattern'], 'unresolved_failure')
        self.assertIn('attempt_chronology_conflict', c['data_issues'])
        self.assertIsNone(c['logical_feedback_seconds'])

    def test_missing_attempt_one_is_not_first_pass(self):
        r = report(row(2, 'pass'))
        self.assertEqual(r['cohorts'][0]['observed_pattern'], 'incomplete_execution')
        self.assertIsNone(r['summary']['first_attempt_failure_rate']['fraction'])
        self.assertIsNone(r['summary']['logical_feedback']['p50_seconds'])

    def test_gap_in_attempt_history_not_recovered(self):
        r = report(row(), row(3, 'pass'))
        self.assertEqual(r['cohorts'][0]['observed_pattern'], 'unresolved_failure')
        self.assertIn('attempt_history_incomplete', r['cohorts'][0]['data_issues'])

    def test_cancelled_and_skipped_are_not_passing_or_zero_runtime(self):
        for outcome in ('cancelled', 'skipped'):
            with self.subTest(outcome=outcome):
                r = report(row(outcome=outcome))
                self.assertEqual(r['summary']['execution']['eligible_count'], 0)
                self.assertIsNone(r['summary']['observed_final_pass_rate']['fraction'])
                self.assertIsNone(r['cohorts'][0]['logical_feedback_seconds'])

    def test_cancelled_last_attempt_censors_feedback(self):
        r = report(row(), row(2, 'cancelled'))
        self.assertIsNone(r['cohorts'][0]['logical_feedback_seconds'])
        self.assertEqual(r['summary']['first_attempt_failure_rate'], a.rate(1, 1))

    def test_pass_then_fail_not_recovery(self):
        r = report(row(outcome='pass'), row(2))
        self.assertEqual(r['cohorts'][0]['observed_pattern'], 'unresolved_failure')
        self.assertIsNone(r['summary']['observed_test_retry_recovery_rate']['fraction'])

    def test_passing_reruns_get_investigation(self):
        r = report(row(outcome='pass'), row(2, 'pass'))
        self.assertEqual(r['cohorts'][0]['observed_pattern'], 'passes_with_extra_attempts')
        self.assertEqual(r['investigations'][0]['priority'], 3)

    def test_shared_run_id_does_not_collapse_services_groups_or_tests(self):
        r = report(row(outcome='pass'), row(outcome='pass', service='other'),
                   row(outcome='pass', group='IAM'), row(outcome='pass', test_id='other'))
        self.assertEqual(r['summary']['logical_test_count'], 4)
        self.assertEqual(len(r['by_service']), 3)

    def test_duplicate_attempt_is_rejected_not_counted_twice(self):
        with self.assertRaises(a.InputError):
            report(row(), row())
        with self.assertRaises(a.InputError):
            report(row(attempt='01'), row())

    def test_required_identity_and_source(self):
        for field in ('run_id', 'group', 'service', 'test_id', 'source_ref'):
            with self.subTest(field=field), self.assertRaises(a.InputError):
                report(row(**{field: ''}))

    def test_bad_attempt_values(self):
        for attempt in ('0', '-1', '1.5', '2e1', '1_000', '１', ''):
            with self.subTest(attempt=attempt), self.assertRaises(a.InputError):
                report(row(attempt=attempt))

    def test_bad_enum_and_inconsistent_failure_fields(self):
        for changes in ({'outcome': 'success'}, {'triage': 'yes'}, {'failure_kind': 'bug'},
                        {'outcome': 'pass', 'failure_kind': 'test'}):
            with self.subTest(changes=changes), self.assertRaises(a.InputError):
                report(row(**changes))

    def test_header_errors(self):
        for text in ('', 'wrong\n', ','.join(a.FIELDS + ('run_id',)) + '\n'):
            with self.subTest(text=text), self.assertRaises(a.InputError):
                a.parse_csv(text)

    def test_wrong_number_of_fields(self):
        for values in ('a,b\n', ','.join(['x'] * (len(a.FIELDS) + 1)) + '\n'):
            with self.subTest(values=values), self.assertRaises(a.InputError):
                a.parse_csv(','.join(a.FIELDS) + '\n' + values)

    def test_empty_export_unknown_denominators(self):
        r = report()
        self.assertEqual(r['summary']['logical_test_count'], 0)
        self.assertIsNone(r['summary']['first_attempt_failure_rate']['fraction'])
        self.assertEqual(r['investigations'], [])

    def test_distribution_zero_and_nearest_rank(self):
        d = a.distribution([0, 100, None])
        self.assertEqual((d['p50_seconds'], d['p95_seconds']), (50, 100))
        self.assertEqual((d['observed_count'], d['eligible_count']), (2, 3))
        self.assertEqual(d['total_observed_seconds'], 100)

    def test_thresholds_are_finite_nonnegative(self):
        for value in (-1, math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(a.InputError):
                report(row(), queue_threshold=value)
        report(row(), queue_threshold=0, feedback_threshold=0)

    def test_trigger_thresholds_are_explicit(self):
        r = report(row(outcome='pass'), queue_threshold=5, feedback_threshold=25)
        kinds = {x['kind'] for x in r['investigations']}
        self.assertEqual(kinds, {'queue_delay', 'feedback_delay'})
        self.assertEqual(r['thresholds_seconds']['queue'], 5)

    def test_input_order_does_not_change_analysis(self):
        records = [row(), row(2, 'pass'), row(outcome='pass', run_id='another-run')]
        self.assertEqual(report(*records), report(*reversed(records)))

    def test_markdown_escapes_markup_and_pipe_in_evidence(self):
        r = report(row(source_ref='<script>alert(1)</script>|evil\nline'))
        text = a.markdown(r)
        self.assertNotIn('<script>', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertIn('\\|evil line', text)

    def test_bom_and_quoted_commas_supported(self):
        rows = a.parse_csv('\ufeff' + csv_text([row(source_ref='synthetic:one,two')]))
        self.assertEqual(rows[0]['source_ref'], 'synthetic:one,two')

    def test_cli_hash_json_markdown_and_input_immutability(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fixture.csv'
            payload = csv_text([row(), row(2, 'pass')]).encode()
            path.write_bytes(payload)
            for fmt in ('json', 'markdown'):
                p = subprocess.run([sys.executable, str(HERE / 'analyze.py'), str(path),
                                    '--synthetic', '--format', fmt], capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(path.read_bytes(), payload)
                if fmt == 'json':
                    r = json.loads(p.stdout)
                    self.assertEqual(r['input_sha256'], hashlib.sha256(payload).hexdigest())
                    self.assertTrue(r['synthetic'])
                else:
                    self.assertIn('SYNTHETIC EXERCISE', p.stdout)

    def test_worked_fixture_matches_explicit_denominators(self):
        r = a.analyze(a.parse_csv((HERE / 'synthetic_runs.csv').read_text()), synthetic=True)
        s = r['summary']
        self.assertEqual((s['attempt_count'], s['logical_test_count']), (18, 12))
        for name, expected in (('first_attempt_failure_rate', (6, 10)),
                               ('observed_final_pass_rate', (9, 11)),
                               ('observed_test_retry_recovery_rate', (2, 4))):
            self.assertEqual(s[name], a.rate(*expected))
        for name, expected in (('queue', (15, 17)), ('execution', (16, 17)),
                               ('logical_feedback', (8, 12)), ('retry_execution', (7, 7))):
            self.assertEqual((s[name]['observed_count'], s[name]['eligible_count']), expected)
        self.assertEqual(s['retry_execution']['total_observed_seconds'], 140)
        self.assertEqual(s['queue']['p95_seconds'], 1200)
        self.assertEqual(s['logical_feedback']['p95_seconds'], 2700)
        self.assertEqual(s['triage_counts']['confirmed_defect'], 1)
        self.assertEqual(s['pattern_counts']['retry_recovered_unconfirmed'], 2)

    def test_committed_example_is_reproducible(self):
        payload = (HERE / 'synthetic_runs.csv').read_bytes()
        r = a.analyze(a.parse_csv(payload.decode()), synthetic=True)
        r['input_sha256'] = hashlib.sha256(payload).hexdigest()
        self.assertEqual(a.markdown(r), (HERE / 'SYNTHETIC_REPORT.md').read_text())

    def test_cli_error_no_partial_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.csv'
            path.write_text('wrong\n')
            p = subprocess.run([sys.executable, str(HERE / 'analyze.py'), str(path)],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
            self.assertEqual(p.stdout, '')
            self.assertIn('Input error', p.stderr)


if __name__ == '__main__':
    unittest.main()
