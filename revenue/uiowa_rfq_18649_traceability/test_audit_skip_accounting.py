"""R2 regressions: skip events and started test cases are different units.

ZZ-Astra Relay-R2 / GPT-6 Astra Pro. Temporary synthetic tests only.
"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import audit_self_sealing as A

PASS = '''import unittest
class Passing(unittest.TestCase):
    def test_pass(self): self.assertTrue(True)
'''
CLASS_SKIP = '''
class Absent(unittest.TestCase):
    @classmethod
    def setUpClass(cls): raise unittest.SkipTest("synthetic class prerequisite")
    def test_unentered(self): self.fail("must not run")
'''
SUBTESTS = '''import unittest
class T(unittest.TestCase):
    def test_mixed(self):
        with self.subTest(case="pass"): self.assertTrue(True)
        with self.subTest(case="skip"): self.skipTest("synthetic gap")
'''


class SkipAccountingTests(unittest.TestCase):
    def execute(self, source, extras=None):
        with tempfile.TemporaryDirectory(prefix='auditor-r2-skip-') as tmp:
            root = Path(tmp)
            files = {'test_case.py': source, **(extras or {})}
            paths = []
            for name, body in files.items():
                path = root / name
                path.write_text(body, encoding='utf-8')
                paths.append(str(path))
            result = A.run_suite(tmp, paths, 12)
        self.assertIsNotNone(result['execution'], result)
        self.assertEqual(result['execution']['optimization'], sys.flags.optimize)
        e = result['execution']
        self.assertEqual(e['skipped'], e['skipped_case_events'] +
                         e['skipped_fixtures'] + e['skipped_subtests'])
        return result

    def test_passing_method_plus_class_setup_skip_is_partial_in_both_orders(self):
        for name in ('AAbsent', 'ZAbsent'):
            with self.subTest(name=name):
                r = self.execute(PASS + CLASS_SKIP.replace('Absent', name))
                self.assertEqual(r['state'], 'PARTIAL_TEST_COVERAGE')
                self.assertEqual(r['execution']['tests_run'], 1)
                self.assertEqual(r['execution']['skipped_fixtures'], 1)
                self.assertEqual(r['execution']['skipped_test_cases'], 0)

    def test_only_class_fixture_skip_still_has_no_case_execution(self):
        r = self.execute('import unittest\n' + CLASS_SKIP)
        self.assertEqual(r['state'], 'NO_TESTS_EXECUTED')
        self.assertEqual(r['execution']['tests_run'], 0)
        self.assertEqual(r['execution']['skipped_fixtures'], 1)

    def test_passing_method_plus_module_setup_skip_is_partial(self):
        module = PASS + '\ndef setUpModule(): raise unittest.SkipTest("module absent")\n'
        r = self.execute(PASS, {'test_other.py': module})
        self.assertEqual(r['state'], 'PARTIAL_TEST_COVERAGE')
        self.assertEqual(r['execution']['tests_run'], 1)
        self.assertEqual(r['execution']['skipped_fixtures'], 1)

    def test_class_teardown_skip_does_not_erase_completed_case(self):
        source = PASS + '''    @classmethod
    def tearDownClass(cls): raise unittest.SkipTest("synthetic teardown gap")
'''
        r = self.execute(source)
        self.assertEqual(r['state'], 'PARTIAL_TEST_COVERAGE')
        self.assertEqual(r['execution']['skipped_fixtures'], 1)

    def test_module_teardown_skip_does_not_erase_completed_case(self):
        r = self.execute(PASS + '\ndef tearDownModule(): raise unittest.SkipTest("gap")\n')
        self.assertEqual(r['state'], 'PARTIAL_TEST_COVERAGE')
        self.assertEqual(r['execution']['skipped_fixtures'], 1)

    def test_passing_and_skipped_subtests_are_partial(self):
        r = self.execute(SUBTESTS)
        self.assertEqual(r['state'], 'PARTIAL_TEST_COVERAGE')
        self.assertEqual(r['execution']['passed_subtests'], 1)
        self.assertEqual(r['execution']['skipped_subtests'], 1)
        self.assertEqual(r['execution']['skipped_test_cases'], 0)

    def test_multiple_subtest_skips_do_not_subtract_multiple_parent_cases(self):
        source = '''import unittest
class T(unittest.TestCase):
    def test_subcases(self):
        for n in range(3):
            with self.subTest(n=n): self.skipTest("gap")
'''
        r = self.execute(source)
        self.assertEqual(r['state'], 'PARTIAL_TEST_COVERAGE')
        self.assertEqual(r['execution']['tests_run'], 1)
        self.assertEqual(r['execution']['skipped_subtests'], 3)

    def test_successful_subtest_survives_later_parent_skip(self):
        source = SUBTESTS + '        self.skipTest("whole remainder unavailable")\n'
        r = self.execute(source)
        self.assertEqual(r['state'], 'PARTIAL_TEST_COVERAGE')
        self.assertEqual(r['execution']['passed_subtests'], 1)
        self.assertEqual(r['execution']['skipped_test_cases'], 1)

    def test_passing_and_individually_skipped_cases_stay_partial(self):
        source = PASS + '''    @unittest.skip("gap")
    def test_skip(self): self.fail("must not run")
'''
        r = self.execute(source)
        self.assertEqual(r['state'], 'PARTIAL_TEST_COVERAGE')
        self.assertEqual(r['execution']['tests_run'], 2)
        self.assertEqual(r['execution']['skipped_test_cases'], 1)

    def test_all_individually_skipped_cases_stay_unexecuted(self):
        source = PASS.replace('class Passing', '@unittest.skip("gap")\nclass Passing')
        r = self.execute(source)
        self.assertEqual(r['state'], 'NO_TESTS_EXECUTED')
        self.assertEqual(r['execution']['skipped_test_cases'], 1)

    def test_failed_subtest_keeps_failure_precedence(self):
        r = self.execute(SUBTESTS.replace('self.assertTrue(True)', 'self.assertEqual(1, 2)'))
        self.assertEqual(r['state'], 'TESTS_NOT_GREEN')
        self.assertEqual(r['returncode'], 1)
        self.assertEqual(r['execution']['failures'], 1)
        self.assertEqual(r['execution']['skipped_subtests'], 1)

    def test_unexecuted_selected_case_is_partial_not_clean(self):
        source = PASS + '''
class PartialSuite(unittest.TestSuite):
    def run(self, result, debug=False):
        self._tests[0](result)
        return result
def load_tests(loader, tests, pattern):
    return PartialSuite([Passing("test_pass"), Passing("test_pass")])
'''
        r = self.execute(source)
        self.assertEqual(r['state'], 'PARTIAL_TEST_COVERAGE')
        self.assertEqual(r['execution']['selected'], 2)
        self.assertEqual(r['execution']['tests_run'], 1)
        self.assertEqual(r['execution']['skipped'], 0)

    def test_successful_subtests_without_gaps_remain_clean(self):
        r = self.execute(SUBTESTS.replace('self.skipTest("synthetic gap")', 'self.assertTrue(True)'))
        self.assertEqual(r['state'], 'CLEAN')
        self.assertEqual(r['execution']['passed_subtests'], 2)
        self.assertEqual(r['execution']['skipped'], 0)

    def test_receipt_rejects_mixed_units_and_impossible_subtests(self):
        receipt = self.execute(PASS)['execution']
        cases = [dict(skipped=1), dict(skipped_test_cases=2, skipped_case_events=2, skipped=2),
                 dict(skipped_test_cases=1), dict(skipped_case_events=1, skipped=1),
                 dict(tests_run=0, passed_subtests=1),
                 dict(tests_run=0, skipped_subtests=1, skipped=1)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'receipt.json'
            for fields in cases:
                with self.subTest(fields=fields), self.assertRaises(ValueError):
                    path.write_text(json.dumps({**receipt, **fields}), encoding='utf-8')
                    A._read_execution_receipt(str(path), 0)

    def test_repeated_setup_cleanup_skips_count_one_unexecuted_case(self):
        source = """import unittest
class T(unittest.TestCase):
    def setUp(self):
        self.addCleanup(self.skipTest, "cleanup gap")
        self.skipTest("setup gap")
    def test_never(self): self.fail("must not run")
"""
        r = self.execute(source)
        self.assertEqual(r['state'], 'NO_TESTS_EXECUTED')
        self.assertEqual(r['execution']['tests_run'], 1)
        self.assertEqual(r['execution']['skipped_case_events'], 2)
        self.assertEqual(r['execution']['skipped_test_cases'], 1)

    def test_repeated_case_skips_do_not_erase_a_different_passing_case(self):
        source = PASS + """
class Absent(unittest.TestCase):
    def setUp(self):
        self.addCleanup(self.skipTest, "cleanup gap")
        self.skipTest("setup gap")
    def test_never(self): self.fail("must not run")
"""
        r = self.execute(source)
        self.assertEqual(r['state'], 'PARTIAL_TEST_COVERAGE')
        self.assertEqual(r['execution']['tests_run'], 2)
        self.assertEqual(r['execution']['skipped_case_events'], 2)
        self.assertEqual(r['execution']['skipped_test_cases'], 1)

    def test_strict_cli_retains_partial_state_in_both_formats_and_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane = root / 'uiowa_rfq_18649_skip_example'
            lane.mkdir()
            source = lane / 'test_case.py'
            source.write_text(PASS + CLASS_SKIP, encoding='utf-8')
            before = A.snapshot(tmp)
            for fmt in ('text', 'json'):
                with self.subTest(format=fmt), contextlib.redirect_stdout(io.StringIO()) as out:
                    code = A.main([tmp, '--format', fmt, '--require-clean'])
                self.assertEqual(code, 2)
                self.assertIn('PARTIAL_TEST_COVERAGE', out.getvalue())
                self.assertEqual(A.snapshot(tmp), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
