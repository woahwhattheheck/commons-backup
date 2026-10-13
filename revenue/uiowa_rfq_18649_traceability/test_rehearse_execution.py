"""Finite operator-rehearsal tests; no additional auditor implementation."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import rehearse_execution as R


class RehearsalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = R.run_rehearsal()

    def test_actual_ten_lane_rehearsal_reports_all_expected_states(self):
        self.assertTrue(self.report['rehearsal_passed'], self.report['mismatches'])
        self.assertEqual(len(self.report['rows']), 10)
        self.assertEqual({r['lane']: r['observed'] for r in self.report['rows']}, R.EXPECTED)
        self.assertFalse(self.report['auditor_all_clean'])
        self.assertEqual(self.report['audit_exit_code'], 1)
        self.assertTrue(self.report['source_and_input_unchanged'])

    def test_real_child_receipts_inherit_optimization(self):
        receipts = [e for r in self.report['rows'] for e in r['execution'] if e]
        self.assertGreater(len(receipts), 0)
        self.assertTrue(all(e['optimization'] == sys.flags.optimize for e in receipts))
        self.assertEqual(self.report['optimization'], sys.flags.optimize)

    def test_expected_mixed_counts_are_not_flattened(self):
        rows = {r['lane']: r for r in self.report['rows']}
        self.assertEqual(rows['empty']['execution'][0]['tests_run'], 0)
        self.assertEqual(rows['skipped']['execution'][0]['skipped'], 1)
        self.assertEqual(rows['partial']['execution'][0]['tests_run'], 2)
        self.assertEqual(rows['partial']['execution'][0]['skipped'], 1)
        self.assertEqual(rows['unknown']['execution'], [None])
        self.assertGreater(rows['foreign']['mutated_files'], 0)

    def test_auditor_source_identity_is_reported(self):
        self.assertTrue(Path(R.__file__).with_name('audit_self_sealing.py').is_file())
        self.assertEqual(len(self.report['auditor_sha256']), 64)

    def test_missing_duplicate_and_unknown_rows_fail_rehearsal(self):
        correct = [{'lane': R.PREFIX + name, 'verdict': verdict}
                   for name, verdict in R.EXPECTED.items()]
        for rows in (correct[:-1], correct + correct[:1],
                     correct + [{'lane': 'unexpected', 'verdict': 'CLEAN'}]):
            child = subprocess.CompletedProcess([], 1, json.dumps(rows), '')
            with mock.patch.object(R.subprocess, 'run', return_value=child):
                report = R.run_rehearsal()
            self.assertFalse(report['rehearsal_passed'])
            self.assertTrue(report['mismatches'])

    def test_incorrect_all_clean_output_is_reported_not_hidden(self):
        rows = [{'lane': R.PREFIX + name, 'verdict': 'CLEAN'} for name in R.EXPECTED]
        child = subprocess.CompletedProcess([], 0, json.dumps(rows), '')
        with mock.patch.object(R.subprocess, 'run', return_value=child):
            report = R.run_rehearsal()
        self.assertFalse(report['rehearsal_passed'])
        self.assertTrue(report['auditor_all_clean'])
        self.assertEqual(report['audit_exit_code'], 0)

    def test_cli_error_is_not_rehearsal_success(self):
        for error in (OSError('synthetic launch failure'),
                      subprocess.TimeoutExpired('synthetic', 30),
                      ValueError('synthetic malformed JSON')):
            output = io.StringIO()
            with mock.patch.object(R, 'run_rehearsal', side_effect=error), contextlib.redirect_stdout(output):
                code = R.main(['--format', 'json'])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output.getvalue())['rehearsal_passed'])

    def test_cli_success_means_rehearsal_not_clean_audit(self):
        for fmt in ('text', 'json'):
            output = io.StringIO()
            with mock.patch.object(R, 'run_rehearsal', return_value=self.report), contextlib.redirect_stdout(output):
                self.assertEqual(R.main(['--format', fmt]), 0)
            self.assertIn('auditor_all_clean', output.getvalue())


if __name__ == '__main__':
    unittest.main()
