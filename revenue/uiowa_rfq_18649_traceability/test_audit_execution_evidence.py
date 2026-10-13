"""Execution-evidence regressions for OP5-LANTERN's retained auditor.

ZZ-Astra Relay / GPT-6 Astra Pro. Local synthetic lanes only.
No API calls, shared worktree mutations, or third-party execution.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import audit_self_sealing as A

PASS = '''import unittest
class T(unittest.TestCase):
    def test_pass(self):
        self.assertTrue(True)
'''
SKIP = '''import unittest
@unittest.skip("synthetic missing prerequisite")
class T(unittest.TestCase):
    def test_skipped(self):
        self.fail("must not execute")
'''
FAIL = '''import unittest
class T(unittest.TestCase):
    def test_fail(self):
        self.assertEqual(1, 2)
'''


class ExecutionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='execution-evidence-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lane = self.root / 'uiowa_rfq_18649_execution'
        self.lane.mkdir()

    def write(self, body=PASS, path='test_case.py'):
        target = self.lane / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding='utf-8')
        return str(target)

    def run_child(self, body=PASS):
        return A.run_suite(str(self.lane), [self.write(body)], 5)

    def audit(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = A.main([str(self.root), '--format', 'json', *args])
        return code, json.loads(buf.getvalue())

    def test_zero_test_module_has_measured_zero_not_clean(self):
        result = self.run_child('# deliberately no TestCase\n')
        self.assertEqual(result['state'], 'NO_TESTS_EXECUTED')
        self.assertEqual(result['execution']['tests_run'], 0)
        self.assertEqual(result['execution']['selected'], 0)

    def test_all_skipped_is_not_clean(self):
        result = self.run_child(SKIP)
        self.assertEqual(result['state'], 'NO_TESTS_EXECUTED')
        self.assertEqual(result['execution']['tests_run'], 1)
        self.assertEqual(result['execution']['skipped'], 1)

    def test_class_setup_skip_is_not_clean(self):
        result = self.run_child('''import unittest
class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise unittest.SkipTest("synthetic missing prerequisite")
    def test_never_entered(self):
        self.fail("must not run")
''')
        self.assertEqual(result['state'], 'NO_TESTS_EXECUTED')
        self.assertEqual(result['execution']['selected'], 1)
        self.assertEqual(result['execution']['tests_run'], 0)
        self.assertEqual(result['execution']['skipped'], 1)

    def test_launch_failure_keeps_unknown_exit(self):
        self.write()
        with mock.patch.object(A.subprocess, 'run', side_effect=OSError('synthetic launch error')):
            code, results = self.audit('--require-clean')
        result = results[0]
        self.assertEqual(code, 2)
        self.assertEqual(result['verdict'], 'TEST_EXECUTION_UNKNOWN')
        self.assertIsNone(result['suite']['returncode'])
        self.assertFalse(result['suite']['runs'][0]['ran'])

    def test_timeout_is_unknown_and_preserves_timeout_detail(self):
        path = self.write()
        with mock.patch.object(A.subprocess, 'run', side_effect=subprocess.TimeoutExpired('python', 5)):
            result = A.run_suite(str(self.lane), [path], 5)
        self.assertEqual(result['state'], 'TEST_EXECUTION_UNKNOWN')
        self.assertTrue(result['timed_out'])
        self.assertIsNone(result['returncode'])

    def test_early_clean_process_exit_without_receipt_is_unknown(self):
        result = self.run_child('raise SystemExit(0)\n')
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(result['state'], 'TEST_EXECUTION_UNKNOWN')
        self.assertIsNone(result['execution'])

    def test_child_inherits_actual_optimization(self):
        result = self.run_child('''import sys, unittest
class T(unittest.TestCase):
    def test_mode(self):
        self.assertEqual(sys.flags.optimize, %d)
''' % sys.flags.optimize)
        self.assertEqual(result['state'], 'CLEAN')
        self.assertEqual(result['execution']['optimization'], sys.flags.optimize)

    def test_environment_cannot_silently_change_optimization(self):
        other = (sys.flags.optimize + 1) % 3
        with mock.patch.dict(os.environ, {'PYTHONOPTIMIZE': str(other)}):
            result = self.run_child()
        self.assertEqual(result['execution']['optimization'], sys.flags.optimize)
        self.assertEqual(result['state'], 'CLEAN')

    def test_failure_is_measured_not_an_execution_gap(self):
        result = self.run_child(FAIL)
        self.assertEqual(result['state'], 'TESTS_NOT_GREEN')
        self.assertEqual(result['execution']['failures'], 1)
        self.assertEqual(result['returncode'], 1)

    def test_import_failure_is_measured_as_error(self):
        result = self.run_child('import intentionally_missing_auditor_dependency_xyz\n')
        self.assertEqual(result['state'], 'TESTS_NOT_GREEN')
        self.assertGreater(result['execution']['errors'], 0)

    def test_pre_runner_import_crash_keeps_execution_unknown(self):
        result = self.run_child('raise RuntimeError("synthetic pre-runner crash")\n')
        self.assertEqual(result['state'], 'TEST_EXECUTION_UNKNOWN')
        self.assertNotEqual(result['returncode'], 0)
        self.assertIsNone(result['execution'])

    def test_ordinary_pass_has_actual_count(self):
        result = self.run_child()
        self.assertEqual(result['state'], 'CLEAN')
        self.assertEqual(result['execution']['tests_run'], 1)
        self.assertEqual(result['execution']['skipped'], 0)

    def test_console_text_does_not_replace_measured_counts(self):
        result = self.run_child('''import sys
sys.stderr.write("Ran 99999 tests in 0.1s\\nOK\\n")
''')
        self.assertEqual(result['state'], 'NO_TESTS_EXECUTED')
        self.assertEqual(result['execution']['tests_run'], 0)

    def test_partial_skip_is_reported_as_partial_coverage(self):
        result = self.run_child(PASS + '''
class Skipped(unittest.TestCase):
    @unittest.skip("synthetic missing prerequisite")
    def test_absent(self):
        pass
''')
        self.assertEqual(result['state'], 'PARTIAL_TEST_COVERAGE')
        self.assertEqual(result['execution']['tests_run'], 2)
        self.assertEqual(result['execution']['skipped'], 1)

    def test_expected_failure_does_not_claim_complete_clean_coverage(self):
        result = self.run_child('''import unittest
class T(unittest.TestCase):
    @unittest.expectedFailure
    def test_known_defect(self):
        self.assertEqual(1, 2)
''')
        self.assertEqual(result['state'], 'PARTIAL_TEST_COVERAGE')
        self.assertEqual(result['execution']['expected_failures'], 1)

    def test_unexpected_success_is_a_measured_failure(self):
        result = self.run_child('''import unittest
class T(unittest.TestCase):
    @unittest.expectedFailure
    def test_no_longer_fails(self):
        self.assertEqual(1, 1)
''')
        self.assertEqual(result['state'], 'TESTS_NOT_GREEN')
        self.assertEqual(result['execution']['unexpected_successes'], 1)

    def test_empty_group_does_not_hide_other_groups_execution(self):
        self.write('# no tests here\n')
        self.write(PASS, 'tests/test_actual.py')
        code, results = self.audit('--require-clean')
        result = results[0]
        self.assertEqual(code, 2)
        self.assertEqual(result['verdict'], 'PARTIAL_TEST_COVERAGE')
        states = {r['state'] for r in result['suite']['runs']}
        self.assertEqual(states, {'CLEAN', 'NO_TESTS_EXECUTED'})

    def test_later_success_cannot_erase_earlier_execution_unknown(self):
        self.write()
        self.write(PASS, 'tests/test_actual.py')
        original = A.run_suite
        def selective(workdir, tests, timeout):
            if Path(workdir).name == self.lane.name:
                with mock.patch.object(A.subprocess, 'run', side_effect=OSError('first group unavailable')):
                    return original(workdir, tests, timeout)
            return original(workdir, tests, timeout)
        with mock.patch.object(A, 'run_suite', side_effect=selective):
            code, results = self.audit('--require-clean')
        self.assertEqual(code, 2)
        self.assertEqual(results[0]['verdict'], 'TEST_EXECUTION_UNKNOWN')
        self.assertIsNone(results[0]['suite']['returncode'])

    def test_mutation_evidence_is_preserved_when_execution_is_incomplete(self):
        self.write('''from pathlib import Path
Path("fixture.txt").write_text("synthetic change", encoding="utf-8")
raise SystemExit(0)
''')
        code, results = self.audit('--require-clean')
        self.assertEqual(code, 1)
        self.assertEqual(results[0]['verdict'], 'NON_HERMETIC')
        self.assertEqual(results[0]['suite']['state'], 'TEST_EXECUTION_UNKNOWN')
        self.assertFalse((self.lane / 'fixture.txt').exists())

    def test_receipt_is_not_misreported_as_source_mutation(self):
        self.write()
        before = A.snapshot(str(self.root))
        code, results = self.audit('--require-clean')
        self.assertEqual(code, 0)
        self.assertEqual(results[0]['mutated'], [])
        self.assertEqual(A.snapshot(str(self.root)), before)

    def test_missing_only_target_is_error_not_no_tests(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            self.audit('--only', 'uiowa_rfq_18649_does_not_exist')
        self.assertEqual(caught.exception.code, 2)

    def test_cli_works_when_module_docstring_is_stripped(self):
        self.write()
        with mock.patch.object(A, '__doc__', None):
            code, results = self.audit('--require-clean')
        self.assertEqual(code, 0)
        self.assertEqual(results[0]['verdict'], 'CLEAN')

    def test_nonpositive_timeout_is_rejected(self):
        for value in ('0', '-1'):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                self.audit('--timeout', value)
            self.assertEqual(caught.exception.code, 2)

    def test_current_donor_no_tests_warning_is_preserved(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = A.main([str(self.root), '--require-clean'])
        self.assertEqual(code, 2)
        self.assertIn('That is a coverage gap, not a pass:', output.getvalue())
        self.assertIn(self.lane.name, output.getvalue())
        self.assertIn('NO_TESTS=1', output.getvalue())

    def test_require_clean_exit_codes_are_the_same_in_text_and_json(self):
        for source, wanted in ((PASS, 0), (FAIL, 1), (SKIP, 2)):
            self.write(source)
            for fmt in ('text', 'json'):
                with self.subTest(wanted=wanted, fmt=fmt), contextlib.redirect_stdout(io.StringIO()):
                    code = A.main([str(self.root), '--format', fmt, '--require-clean'])
                self.assertEqual(code, wanted)


class ExecutionReceiptValidationTests(unittest.TestCase):
    def receipt(self):
        return dict(selected=1, tests_run=1, skipped=0, failures=0, errors=0,
                    expected_failures=0, unexpected_successes=0, successful=True,
                    optimization=sys.flags.optimize, skipped_test_cases=0,
                    skipped_case_events=0, skipped_fixtures=0, skipped_subtests=0, passed_subtests=0)

    def read(self, receipt, code=0):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'receipt.json'
            path.write_text(json.dumps(receipt), encoding='utf-8')
            return A._read_execution_receipt(str(path), code)

    def test_count_fields_reject_bools_strings_missing_and_negative(self):
        for key in A._COUNT_FIELDS + ('optimization',):
            for bad in (True, False, '1', -1, None, 1.5):
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    receipt = self.receipt()
                    receipt[key] = bad
                    self.read(receipt)
            with self.subTest(key=key, bad='missing'), self.assertRaises(ValueError):
                receipt = self.receipt()
                del receipt[key]
                self.read(receipt)

    def test_success_is_strict_bool(self):
        for bad in (1, 0, 'true', None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                receipt = self.receipt()
                receipt['successful'] = bad
                self.read(receipt)

    def test_success_cannot_contradict_failures(self):
        for key in ('failures', 'errors', 'unexpected_successes'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                receipt = self.receipt()
                receipt[key] = 1
                self.read(receipt)

    def test_exit_cannot_contradict_success(self):
        with self.assertRaises(ValueError):
            self.read(self.receipt(), code=1)

    def test_optimization_mismatch_is_unknown_not_clean(self):
        receipt = self.receipt()
        receipt['optimization'] = (sys.flags.optimize + 1) % 3
        with self.assertRaises(ValueError):
            self.read(receipt)

    def test_non_object_and_missing_fields_are_rejected(self):
        for bad in ([], 1, None, {}, {'successful': True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.read(bad)

    def test_valid_receipt_is_retained_exactly(self):
        receipt = self.receipt()
        self.assertEqual(self.read(receipt), receipt)


class ExitPolicyTests(unittest.TestCase):
    def test_default_exit_policy_retains_backward_compatibility(self):
        for verdict in ('CLEAN', 'NO_TESTS', 'TESTS_NOT_GREEN', 'NON_HERMETIC',
                        'TEST_EXECUTION_UNKNOWN', 'NO_TESTS_EXECUTED',
                        'PARTIAL_TEST_COVERAGE'):
            with self.subTest(verdict=verdict):
                self.assertEqual(A.audit_exit_code([{'verdict': verdict}]), 0)
        self.assertEqual(A.audit_exit_code([{'verdict': 'SELF_SEALING'}]), 1)

    def test_require_clean_refuses_empty_or_unrecognized_coverage(self):
        self.assertEqual(A.audit_exit_code([], True), 2)
        self.assertEqual(A.audit_exit_code([{'verdict': 'FUTURE_UNKNOWN_STATE'}], True), 2)
        self.assertEqual(A.audit_exit_code([{'verdict': 'NO_TESTS'}], True), 2)

    def test_observed_defect_takes_precedence_without_erasing_rows(self):
        results = [{'verdict': 'TEST_EXECUTION_UNKNOWN'}, {'verdict': 'TESTS_NOT_GREEN'}]
        self.assertEqual(A.audit_exit_code(results, True), 1)
        self.assertEqual(len(results), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
