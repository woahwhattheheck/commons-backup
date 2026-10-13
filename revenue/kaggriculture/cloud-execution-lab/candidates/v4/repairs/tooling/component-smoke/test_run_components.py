# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import run_components as runner

GOOD = "import unittest\nclass Test(unittest.TestCase):\n    def test_ok(self): self.assertEqual(2 + 2, 4)\n"


class ComponentRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def put(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path

    def run_all(self, **kwargs):
        return runner.run(self.root, ["**/test_*.py"], timeout=10, **kwargs)

    def test_hyphenated_nonpackage_is_discovered_and_executed(self):
        self.put("repairs/gameplay/fert-sweep/test_example.py", GOOD)
        ordinary = unittest.TestLoader().discover(str(self.root)).countTestCases()
        self.assertEqual(ordinary, 0)
        result = self.run_all()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["selected_files"], 1)
        self.assertEqual([row["optimized"] for row in result["runs"]], [0, 1])
        self.assertEqual([row["tests"] for row in result["runs"]], [1, 1])

    def test_missing_selector_cannot_hide_behind_passing_suite(self):
        self.put("test_present.py", GOOD)
        result = runner.run(self.root, ["test_present.py", "missing/test_*.py"], timeout=10)
        self.assertEqual([row["status"] for row in result["runs"]], ["passed", "passed"])
        self.assertEqual(result["unmatched_selectors"], ["missing/test_*.py"])
        self.assertEqual(result["status"], "failed")

    def test_source_change_between_modes_is_not_green(self):
        path = self.put("test_present.py", GOOD)
        original = runner.run_file
        def mutate_after_normal(test, **kwargs):
            result = original(test, **kwargs)
            if not kwargs["optimized"]:
                path.write_text(GOOD + "# next revision\n")
            return result
        with mock.patch.object(runner, "run_file", side_effect=mutate_after_normal):
            result = self.run_all()
        self.assertEqual([row["status"] for row in result["runs"]], ["passed", "passed"])
        self.assertFalse(result["test_inputs_unchanged"])
        self.assertEqual(result["status"], "failed")

    def test_empty_selection_is_not_green(self):
        self.assertEqual(self.run_all()["status"], "failed")

    def test_module_without_unittest_is_not_green(self):
        self.put("test_zero.py", "def test_pytest_only():\n    pass\n")
        self.assertTrue(all(row["status"] != "passed" for row in self.run_all()["runs"]))

    def test_failed_assertion_stays_red_under_optimization(self):
        self.put("test_bad.py", GOOD.replace("2 + 2, 4", "2 + 2, 5"))
        rows = self.run_all()["runs"]
        self.assertEqual([row["failures"] for row in rows], [1, 1])
        self.assertTrue(all(row["status"] == "failed" for row in rows))

    def test_import_error_and_import_system_exit_are_not_green(self):
        for source in ("import deliberately_missing_titan_dependency\n", "raise SystemExit(0)\n"):
            self.put("test_import.py", source)
            self.assertTrue(all(row["status"] != "passed" for row in self.run_all()["runs"]))

    def test_skip_and_expected_failure_are_incomplete(self):
        for decorator, body in (("@unittest.skip('missing engine')", "self.assertTrue(True)"),
                                ("@unittest.expectedFailure", "self.assertTrue(False)")):
            self.put("test_incomplete.py", f"import unittest\nclass Test(unittest.TestCase):\n    {decorator}\n    def test_one(self): {body}\n")
            self.assertTrue(all(row["status"] == "failed" for row in self.run_all()["runs"]))

    def test_unexpected_success_is_not_green(self):
        self.put("test_xpass.py", "import unittest\nclass Test(unittest.TestCase):\n    @unittest.expectedFailure\n    def test_one(self): self.assertTrue(True)\n")
        self.assertTrue(all(row["unexpected_successes"] == 1 for row in self.run_all()["runs"]))

    def test_duplicate_helper_names_are_isolated_between_files(self):
        for label, number in (("a-lane", 1), ("b-lane", 2)):
            self.put(f"{label}/helper.py", f"VALUE = {number}\n")
            self.put(f"{label}/test_helper.py", "import unittest, helper\nclass Test(unittest.TestCase):\n    def test_value(self): self.assertEqual(helper.VALUE, " + str(number) + ")\n")
        result = self.run_all()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(len(result["runs"]), 4)

    def test_zero_exit_without_receipt_is_not_green(self):
        self.put("test_exit.py", "import os\nos._exit(0)\n")
        self.assertTrue(all(row["reason"] == "child produced no receipt" for row in self.run_all()["runs"]))

    def test_timeout_is_not_green(self):
        self.put("test_slow.py", "import time\ntime.sleep(5)\n")
        result = runner.run(self.root, ["test_slow.py"], timeout=0.1)
        self.assertTrue(all(row["status"] == "timeout" for row in result["runs"]))

    def test_donor_historical_and_legacy_are_not_selected(self):
        for directory in ("donor", "historical", "original", "raw", "fixtures", "legacy", "legacy-refile"):
            self.put(f"repairs/{directory}/test_ignored.py", GOOD)
        self.put("repairs/live/test_kept.py", GOOD)
        selected = runner.select_tests(self.root, ["**/test_*.py", "**/test_*.py"])
        self.assertEqual([path.name for path in selected], ["test_kept.py"])

    def test_selector_escape_is_rejected(self):
        for selector in ("../test_*.py", "/tmp/test_*.py"):
            with self.assertRaises(ValueError):
                runner.select_tests(self.root, [selector])

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external) / "test_external.py"
            outside.write_text(GOOD)
            (self.root / "test_link.py").symlink_to(outside)
            with self.assertRaises(ValueError):
                runner.select_tests(self.root, ["test_*.py"])

    def test_bind_mutation_fails_whole_run(self):
        bound = self.put("bound.txt", "original")
        self.put("test_mutation.py", GOOD + "\nfrom pathlib import Path\nPath(" + repr(str(bound)) + ").write_text('changed')\n")
        result = self.run_all(binds=[bound])
        self.assertFalse(result["bound_inputs_unchanged"])
        self.assertEqual(result["status"], "failed")

    def test_nonfinite_or_nonpositive_timeouts_rejected(self):
        for timeout in (float("nan"), float("inf"), -1, 0):
            with self.assertRaises(ValueError):
                runner.run(self.root, [], timeout=timeout)

    def test_cli_emits_result_and_exit_code(self):
        self.put("test_good.py", GOOD)
        output = self.root / "report.json"
        command = [sys.executable] + (["-S"] if sys.flags.no_site else []) + [str(Path(runner.__file__).resolve()), "--root", str(self.root),
                   "--include", "test_*.py", "--output", str(output)]
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(output.read_text())["status"], "passed")
        self.put("test_bad.py", "pass\n")
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(json.loads(output.read_text())["status"], "failed")


if __name__ == "__main__":
    unittest.main()
