"""Executable regression coverage for the verifier itself; all lanes are fictional."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import verify_lanes as verifier


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def case(self, body="self.assertEqual(1 + 1, 2)", extra="", guard=False):
        return ("import unittest\n" + extra + "\nclass Checks(unittest.TestCase):\n"
                + "    def test_observed(self):\n        " + body.replace("\n", "\n        ") + "\n"
                + ("if __name__ == '__main__': unittest.main()\n" if guard else ""))

    def run_lane(self, timeout=5, runner="auto"):
        return verifier.run_tests(self.root, timeout, runner)

    def test_pass_without_main_guard_is_actually_discovered(self):
        self.write("test_actual.py", self.case())
        result = self.run_lane()
        self.assertEqual((result["status"], result["tests_executed"]), ("PASS", 1))
        self.assertEqual(result["files"][0]["runner"], "unittest")

    def test_failing_case_without_main_guard_is_not_pass_zero(self):
        self.write("test_actual.py", self.case('self.fail("intentional fixture")'))
        result = self.run_lane()
        self.assertEqual((result["status"], result["tests"]), ("FAIL", 1))
        self.assertEqual(result["files"][0]["failures"], 1)

    def test_existing_main_guard_remains_compatible(self):
        self.write("test_actual.py", self.case(guard=True))
        self.assertEqual(self.run_lane()["tests_executed"], 1)

    def test_whole_case_skip_is_not_executed_or_pass(self):
        self.write("test_actual.py", self.case().replace("class Checks", '@unittest.skip("fixture")\nclass Checks'))
        result = self.run_lane()
        self.assertEqual((result["status"], result["tests"], result["tests_executed"], result["tests_skipped"]),
                         ("SKIPPED", 1, 0, 1))

    def test_class_setup_skip_is_recorded_without_inventing_started_cases(self):
        self.write("test_actual.py", self.case().replace("    def test_observed",
                   '    @classmethod\n    def setUpClass(cls): raise unittest.SkipTest("fixture")\n    def test_observed'))
        result = self.run_lane()
        self.assertEqual((result["status"], result["tests"], result["tests_executed"], result["skip_events"]),
                         ("SKIPPED", 0, 0, 1))

    def test_subtest_skips_do_not_subtract_whole_cases(self):
        body = 'for i in range(2):\n    with self.subTest(i=i): self.skipTest("fixture")\nself.assertTrue(True)'
        self.write("test_actual.py", self.case(body))
        result = self.run_lane()
        self.assertEqual((result["status"], result["tests_executed"], result["tests_skipped"], result["skip_events"]),
                         ("PASS", 1, 0, 2))

    def test_mixed_real_case_and_case_skip_preserves_both_counts(self):
        source = self.case().replace('    def test_observed',
                 '    @unittest.skip("fixture")\n    def test_skipped(self): pass\n    def test_observed')
        self.write("test_actual.py", source)
        result = self.run_lane()
        self.assertEqual((result["status"], result["tests"], result["tests_executed"], result["tests_skipped"]),
                         ("PASS", 2, 1, 1))

    def test_expected_failure_remains_explicit_in_file_record(self):
        source = self.case('self.fail("expected fixture")').replace('    def test_observed',
                 '    @unittest.expectedFailure\n    def test_observed')
        self.write("test_actual.py", source)
        result = self.run_lane()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["files"][0]["expected_failures"], 1)

    def test_unexpected_success_remains_failure(self):
        source = self.case().replace('    def test_observed',
                 '    @unittest.expectedFailure\n    def test_observed')
        self.write("test_actual.py", source)
        self.assertEqual(self.run_lane()["status"], "FAIL")

    def test_silent_success_is_unverified_not_pass(self):
        self.write("test_empty.py", 'print("loaded, no test runner")\n')
        result = self.run_lane()
        self.assertEqual((result["status"], result["tests_executed"]), ("UNVERIFIED", 0))

    def test_plain_test_functions_are_not_claimed_executed(self):
        self.write("test_external_framework.py", 'def test_not_called():\n    raise AssertionError("fixture")\n')
        self.assertEqual(self.run_lane()["status"], "UNVERIFIED")

    def test_main_guard_syntax_error_is_failure(self):
        self.write("test_invalid.py", 'if this is not valid python\n')
        self.assertEqual(self.run_lane()["status"], "FAIL")

    def test_missing_import_is_failure_not_no_tests(self):
        self.write("test_actual.py", self.case(extra="import fictional_missing_lantern83_dependency"))
        result = self.run_lane()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["files"][0]["errors"], 1)

    def test_usage_text_inside_real_test_error_does_not_hide_failure(self):
        self.write("test_actual.py", self.case('print("usage: fixture")\nraise SystemExit(2)'))
        self.assertEqual(self.run_lane()["status"], "FAIL")

    def test_argument_cli_is_unverified_not_test_failure_or_pass(self):
        self.write("test_data_assessor.py", 'import argparse\np = argparse.ArgumentParser()\np.add_argument("input")\np.parse_args()\n')
        result = self.run_lane()
        self.assertEqual((result["status"], result["tests_executed"]), ("UNVERIFIED", 0))
        self.assertIn("arguments", result["files"][0]["detail"])

    def test_timeout_is_failure(self):
        self.write("test_slow.py", "import time\ntime.sleep(30)\n")
        result = self.run_lane(timeout=0.05)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("TIMEOUT", result["files"][0]["tail"])

    def test_nested_suite_can_import_lane_module_and_read_lane_fixture(self):
        self.write("lane_helper.py", "VALUE = 42\n")
        self.write("fixture.txt", "fictional")
        self.write("tests/test_nested.py", self.case('self.assertEqual(VALUE, 42)\nself.assertEqual(Path("fixture.txt").read_text(), "fictional")',
                   extra="from lane_helper import VALUE\nfrom pathlib import Path"))
        result = self.run_lane()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["files"][0]["file"], "tests/test_nested.py")

    def test_package_relative_imports_are_preserved(self):
        self.write("tests/__init__.py", "")
        self.write("tests/helper.py", "VALUE = 17\n")
        self.write("tests/test_nested.py", self.case("self.assertEqual(VALUE, 17)", extra="from .helper import VALUE"))
        self.assertEqual(self.run_lane()["status"], "PASS")

    def test_import_alias_and_local_subclass_are_recognized(self):
        self.write("test_alias.py", 'from unittest import TestCase as Case\nclass Base(Case): pass\nclass Child(Base):\n    def test_it(self): self.assertTrue(True)\n')
        result = self.run_lane()
        self.assertEqual((result["status"], result["tests_executed"]), ("PASS", 1))

    def test_module_alias_is_recognized(self):
        self.write("test_alias.py", self.case().replace("import unittest", "import unittest as u").replace("unittest.TestCase", "u.TestCase"))
        self.assertEqual(self.run_lane()["status"], "PASS")

    def test_load_tests_empty_suite_is_no_tests(self):
        self.write("test_hook.py", 'import unittest\ndef load_tests(loader, standard_tests, pattern):\n    return unittest.TestSuite()\n')
        self.assertEqual(self.run_lane()["status"], "NO-TESTS")

    def test_explicit_unittest_runner_supports_imported_base(self):
        self.write("custom_base.py", "from unittest import TestCase as CustomCase\n")
        self.write("test_custom.py", 'from custom_base import CustomCase\nclass Actual(CustomCase):\n    def test_it(self): self.assertTrue(True)\n')
        self.assertEqual(self.run_lane(runner="unittest")["status"], "PASS")

    def test_explicit_script_runner_preserves_existing_summary(self):
        self.write("test_actual.py", self.case(guard=True))
        result = self.run_lane(runner="script")
        self.assertEqual((result["status"], result["tests_executed"]), ("PASS", 1))
        self.assertEqual(result["files"][0]["runner"], "script")

    def test_optimization_setting_reaches_child(self):
        self.write("test_actual.py", self.case(f"self.assertEqual(sys.flags.optimize, {sys.flags.optimize})", extra="import sys"))
        self.assertEqual(self.run_lane()["status"], "PASS")

    def test_mixed_executed_and_unknown_does_not_promote_unknown(self):
        self.write("test_actual.py", self.case())
        self.write("test_silent.py", "pass\n")
        result = self.run_lane()
        self.assertEqual((result["status"], result["tests_executed"]), ("UNVERIFIED", 1))

    def test_failure_has_precedence_over_unverified(self):
        self.write("test_actual.py", self.case("self.fail()"))
        self.write("test_silent.py", "pass\n")
        self.assertEqual(self.run_lane()["status"], "FAIL")

    def test_no_suite_is_not_a_failure_or_pass(self):
        self.assertEqual(self.run_lane()["status"], "NO-TESTS")

    def test_glob_duplicates_and_matching_directories_are_excluded(self):
        self.write("test_double_test.py", "pass\n")
        self.write("tests/nested_test.py", "pass\n")
        (self.root / "test_directory.py").mkdir()
        self.assertEqual(len(verifier.find_tests(str(self.root))), 2)

    def test_timeout_and_runner_validation(self):
        for timeout in (0, -1, float("inf"), float("nan")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                verifier.run_tests(self.root, timeout)
        with self.assertRaises(ValueError):
            self.run_lane(runner="unknown")

    def test_invalid_observation_is_rejected(self):
        receipt = self.write("receipt.json", '{"schema":"commons-unittest-observation/v1"}')
        with self.assertRaises(ValueError):
            verifier._observation(receipt)

    def test_script_summary_requires_count_and_clean_ok(self):
        for text in ("", "Ran 2 tests in 1s\n", "OK\n", "Ran 0 tests in 1s\nOK\n", "Ran 1 test in 1s\nOK (skipped=1)\n"):
            with self.subTest(text=text):
                self.assertEqual(verifier._script_observation(text, 0)["status"], "UNVERIFIED")

    def test_cli_json_counts_skips_separately_and_unknown_exit_is_two(self):
        self.write("lanes/pass/test_one.py", self.case())
        self.write("lanes/skip/test_one.py", self.case().replace("class Checks", '@unittest.skip("fixture")\nclass Checks'))
        self.write("lanes/unknown/test_one.py", "pass\n")
        receipt = self.root / "observed.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = verifier.main([str(self.root), "--glob", "lanes/*", "--json", str(receipt)])
        value = json.loads(receipt.read_text())
        self.assertEqual((code, value["lanes"], value["pass"], value["skipped"], value["unverified"]), (2, 3, 1, 1, 1))
        self.assertEqual((value["tests"], value["tests_executed"], value["tests_skipped"]), (2, 1, 1))

    def test_cli_empty_selection_is_not_success(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verifier.main([str(self.root)]), 2)

    def test_child_start_error_does_not_abort_remaining_suite(self):
        self.write("test_actual.py", self.case())
        with patch.object(verifier.subprocess, "run", side_effect=OSError("fictional process error")):
            result = self.run_lane()
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("OSError", result["files"][0]["tail"])


if __name__ == "__main__":
    unittest.main()
