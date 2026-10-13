"""Persistent lifecycle regressions for UIOWA-047 / OSPREY-86C1-CLEANUP-R2.

Every record is fictional. No network, real fixture execution, or institutional
findings. Latest-attempt evidence and completed lifecycle transitions differ.
"""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
from itertools import product
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('osprey047_cleanup_assessor', ROOT / 'assess.py')
assessor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(assessor)
CUTOFF = '2026-09-19T12:00:00Z'


def event(hour, outcome='succeeded', *, versioned=False, backed=True):
    result = {'at': f'2026-09-19T{hour:02d}:00:00Z', 'outcome': outcome,
              'evidence_ref': f'FICTIONAL-{hour}-{outcome}' if backed else None}
    if versioned:
        result.update(fixture_version='v1', contract_version='c1')
    return result


def catalog():
    return {'schema_version': 1, 'context': 'synthetic-demo',
        'contracts': [{'id': 'CONTRACT-FICTIONAL', 'group': 'ESS', 'version': 'c1',
                       'required_cases': ['CASE-ONE']}],
        'fixtures': [{'id': 'FIXTURE-FICTIONAL', 'contract_id': 'CONTRACT-FICTIONAL',
                      'contract_version': 'c1', 'fixture_version': 'v1', 'origin': 'synthetic',
                      'state': 'active', 'owner': 'Fictional fixture-maintenance role',
                      'maintenance_hours': 1, 'refresh_interval_days': 7, 'recipe_ref': 'FICTIONAL-RECIPE',
                      'created_at': '2026-09-19T07:00:00Z', 'cleanup_due_at': '2026-09-20T00:00:00Z',
                      'refreshes': [event(8, versioned=True)], 'cleanups': [event(10)],
                      'cases': [{'id': 'CASE-ONE', 'input_class': 'Fictional boundary',
                                 'expected_behavior': 'Fictional example expectation',
                                 'runs': [event(9, versioned=True)]}]}]}


class CleanupHistoryTests(unittest.TestCase):
    def setUp(self):
        self.data = catalog()
        self.f = self.data['fixtures'][0]

    def report(self, cutoff=CUTOFF):
        return assessor.assess(self.data, cutoff)

    @staticmethod
    def codes(report):
        return {row['code'] for row in report['limitations']}

    def assert_cleaned(self):
        report = self.report()
        self.assertFalse(report['fixtures'][0]['current_evidence_eligible'])
        self.assertEqual(report['summary']['cases_with_supported_evidence'], 0)
        self.assertEqual(report['fixtures'][0]['cases'][0]['status'], 'unknown')
        self.assertIn('ACTIVE_AFTER_CLEANUP', self.codes(report))
        note = next(n for n in report['limitations'] if n['code'] == 'ACTIVE_AFTER_CLEANUP')
        self.assertEqual(note['evidence_refs'], ['FICTIONAL-10-succeeded'])
        return report

    def test_failed_retry_cannot_resurrect_cleaned_fixture(self):
        self.f['cleanups'].append(event(11, 'failed'))
        self.assert_cleaned()

    def test_unbacked_success_cannot_erase_completed_cleanup(self):
        self.f['cleanups'].append(event(11, backed=False))
        self.assert_cleaned()

    def test_unbacked_failure_cannot_erase_completed_cleanup(self):
        self.f['cleanups'].append(event(11, 'failed', backed=False))
        self.assert_cleaned()

    def test_failed_recreation_does_not_undo_cleanup(self):
        self.f['refreshes'].append(event(11, 'failed', versioned=True))
        report = self.assert_cleaned()
        self.assertIn('REFRESH_NOT_DEMONSTRATED', self.codes(report))

    def test_unbacked_recreation_does_not_undo_cleanup(self):
        self.f['refreshes'].append(event(11, versioned=True, backed=False))
        self.assert_cleaned()

    def test_completed_recreation_requires_a_new_case_run(self):
        self.f['refreshes'].append(event(11, versioned=True))
        report = self.report()
        self.assertNotIn('ACTIVE_AFTER_CLEANUP', self.codes(report))
        self.assertTrue(report['fixtures'][0]['current_evidence_eligible'])
        self.assertEqual(report['summary']['cases_with_supported_evidence'], 0)

    def test_completed_recreation_and_new_case_run_restore_support(self):
        self.f['refreshes'].append(event(11, versioned=True))
        self.f['cases'][0]['runs'].append(event(12, versioned=True))
        report = self.report()
        self.assertNotIn('ACTIVE_AFTER_CLEANUP', self.codes(report))
        self.assertEqual(report['summary']['cases_with_supported_evidence'], 1)

    def test_failed_refresh_after_completed_recreation_is_not_old_cleanup(self):
        self.f['refreshes'] += [event(11, versioned=True), event(12, 'failed', versioned=True)]
        report = self.report()
        self.assertNotIn('ACTIVE_AFTER_CLEANUP', self.codes(report))
        self.assertIn('REFRESH_NOT_DEMONSTRATED', self.codes(report))
        self.assertFalse(report['fixtures'][0]['current_evidence_eligible'])

    def test_retired_cleaned_fixture_does_not_regain_due_obligation_from_retry(self):
        self.f.update(state='retired', cleanup_due_at='2026-09-19T09:30:00Z')
        self.f['cleanups'].append(event(11, 'failed'))
        report = self.report()
        self.assertIn('RETIRED_FIXTURE', self.codes(report))
        self.assertNotIn('CLEANUP_NOT_DEMONSTRATED', self.codes(report))

    def test_old_cleanup_does_not_clear_a_recreated_generation(self):
        self.f['refreshes'].append(event(11, versioned=True))
        self.f.update(cleanup_due_at='2026-09-19T11:30:00Z')
        self.assertIn('CLEANUP_NOT_DEMONSTRATED', self.codes(self.report()))

    def test_failed_cleanup_after_recreation_does_not_revive_old_cleanup(self):
        self.f['refreshes'].append(event(11, versioned=True))
        self.f['cleanups'].append(event(12, 'failed'))
        self.f.update(cleanup_due_at='2026-09-19T11:30:00Z')
        report = self.report()
        self.assertNotIn('ACTIVE_AFTER_CLEANUP', self.codes(report))
        self.assertIn('CLEANUP_NOT_DEMONSTRATED', self.codes(report))

    def test_failure_alone_does_not_establish_completed_cleanup(self):
        self.f['cleanups'] = [event(10, 'failed')]
        report = self.report()
        self.assertNotIn('ACTIVE_AFTER_CLEANUP', self.codes(report))
        self.assertEqual(report['summary']['cases_with_supported_evidence'], 1)

    def test_unbacked_cleanup_alone_does_not_establish_completion(self):
        self.f['cleanups'] = [event(10, backed=False)]
        report = self.report()
        self.assertNotIn('ACTIVE_AFTER_CLEANUP', self.codes(report))
        self.assertEqual(report['summary']['cases_with_supported_evidence'], 1)

    def test_future_cleanup_is_not_used_before_cutoff(self):
        self.f['cleanups'] = [event(13)]
        report = self.report()
        self.assertEqual(report['summary']['cases_with_supported_evidence'], 1)
        self.assertEqual(report['fixtures'][0]['excluded_future_events'], 1)

    def test_cutoff_cleanup_is_included(self):
        self.f['cleanups'] = [event(12)]
        self.assertIn('ACTIVE_AFTER_CLEANUP', self.codes(self.report()))

    def test_timezone_equivalent_cutoff_is_identical(self):
        self.f['cleanups'].append(event(11, 'failed'))
        self.assertEqual(self.report(), self.report('2026-09-19T08:00:00-04:00'))

    def test_cleanup_and_refresh_at_same_instant_do_not_prove_recreation(self):
        self.f['refreshes'].append(event(10, versioned=True))
        self.assert_cleaned()

    def test_new_case_run_without_recreation_cannot_restore_support(self):
        self.f['cleanups'].append(event(11, 'failed'))
        self.f['cases'][0]['runs'].append(event(12, versioned=True))
        self.assert_cleaned()

    def test_cleanup_attempt_reporting_is_preserved(self):
        self.f['cleanups'].append(event(11, 'failed'))
        report = self.assert_cleaned()
        self.assertEqual(report['fixtures'][0]['latest_cleanup_at'], '2026-09-19T11:00:00Z')

    def test_unrelated_fixture_keeps_its_supported_evidence(self):
        other = deepcopy(self.f)
        other.update(id='FIXTURE-UNAFFECTED', cleanups=[])
        self.data['fixtures'].append(other)
        self.f['cleanups'].append(event(11, 'failed'))
        report = self.report()
        self.assertEqual(report['coverage'][0]['supported_by'], ['FIXTURE-UNAFFECTED'])
        self.assertEqual(report['coverage'][0]['unknown_by'], ['FIXTURE-FICTIONAL'])

    def test_input_catalog_is_not_modified(self):
        self.f['cleanups'].append(event(11, 'failed'))
        before = deepcopy(self.data)
        self.assert_cleaned()
        self.assertEqual(self.data, before)

    def test_cli_preserves_input_and_reports_completed_cleanup_reference(self):
        self.f['cleanups'].append(event(11, 'failed'))
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/'catalog.json', Path(directory)/'report.md'
            source.write_text(json.dumps(self.data), encoding='utf-8')
            before = source.read_bytes()
            self.assertEqual(assessor.main([str(source), '--as-of', CUTOFF, '--format', 'markdown', '--output', str(output)]), 0)
            self.assertEqual(source.read_bytes(), before)
            self.assertIn('FICTIONAL-10-succeeded', output.read_text())
            self.assertIn('ACTIVE_AFTER_CLEANUP', output.read_text())

    def test_enumerated_histories_match_independent_completion_state_machine(self):
        # 7 possibilities in three slots = 343 histories, at 3 cutoffs.
        # This oracle folds chronological state transitions; production takes maxima.
        choices = [None, ('cleanups', 'succeeded', True), ('cleanups', 'failed', True),
                   ('cleanups', 'succeeded', False), ('refreshes', 'succeeded', True),
                   ('refreshes', 'failed', True), ('refreshes', 'succeeded', False)]
        checked = 0
        for history in product(choices, repeat=3):
            data = catalog()
            fixture = data['fixtures'][0]
            fixture['cleanups'] = []
            for hour, choice in zip((9, 10, 11), history):
                if choice:
                    stream, outcome, backed = choice
                    fixture[stream].append(event(hour, outcome, versioned=stream=='refreshes', backed=backed))
            for cutoff_hour in (9, 10, 12):
                cleaned = False
                for hour, choice in zip((9, 10, 11), history):
                    if hour <= cutoff_hour and choice:
                        stream, outcome, backed = choice
                        if outcome == 'succeeded' and backed:
                            cleaned = stream == 'cleanups'
                report = assessor.assess(data, f'2026-09-19T{cutoff_hour:02d}:00:00Z')
                with self.subTest(history=history, cutoff=cutoff_hour):
                    self.assertEqual('ACTIVE_AFTER_CLEANUP' in self.codes(report), cleaned)
                checked += 1
        self.assertEqual(checked, 1029)

    def test_completion_state_is_independent_of_event_input_order(self):
        self.f['refreshes'] += [event(11, versioned=True), event(12, 'failed', versioned=True)]
        self.f['cleanups'] += [event(9), event(11, 'failed')]
        first = self.report()
        self.f['refreshes'].reverse()
        self.f['cleanups'].reverse()
        second = self.report()
        for key in ('summary', 'coverage', 'fixtures', 'limitations'):
            self.assertEqual(first[key], second[key])


if __name__ == '__main__':
    unittest.main()
