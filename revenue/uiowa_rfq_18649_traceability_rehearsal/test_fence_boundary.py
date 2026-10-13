"""Retained QUARTZ-M7R4 fenced-example regressions; synthetic inputs only."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("_uiowa093_fence_copperr61", HERE / "validate_trace.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class FenceBoundaryTests(unittest.TestCase):
    """Independent QUARTZ-M7R4 fixture; no edited University/native source data."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.statement = "**S-001.** Synthetic statement. [F:F-001] [E:E-001]\n"
        files = {
            "evidence.csv": "evidence_id,locator\nE-001,synthetic.txt:L1\n",
            "findings.csv": "finding_id,evidence_ids\nF-001,E-001\n",
            "recommendations.csv": "recommendation_id,linked_findings\n",
            "trace-map.csv": "statement_id,report_location,finding_ids,recommendation_ids,evidence_ids\nS-001,executive-summary.md#findings,F-001,,E-001\n",
            "final-report.md": "# Other report\n",
        }
        for name, text in files.items():
            (self.root / name).write_text(text, encoding="utf-8")

    def check_report(self, body, expected):
        (self.root / "executive-summary.md").write_text("# Findings\n\n" + body, encoding="utf-8")
        result = checker.validate(self.root)
        self.assertEqual(result["status"], expected, result)
        if expected == "PASS":
            self.assertEqual(result["issues"], [])
        else:
            self.assertIn("MISSING_STATEMENT", {i["code"] for i in result["issues"]})
        return result

    def test_real_statement_is_accepted(self):
        self.check_report(self.statement, "PASS")

    def test_example_statement_is_not_evidence(self):
        self.check_report("```text\n" + self.statement + "```\n", "INCOMPLETE")

    def test_zero_to_three_space_closers_are_valid(self):
        for fence in ("```", "~~~"):
            for spaces in range(4):
                with self.subTest(fence=fence, spaces=spaces):
                    self.check_report(fence + "text\n" + " " * spaces + fence + "\n" + self.statement, "PASS")

    def test_four_space_false_closer_keeps_statement_in_example(self):
        self.check_report("```text\n    ```\n" + self.statement + "```\n", "INCOMPLETE")

    def test_tab_false_closer_keeps_statement_in_example(self):
        self.check_report("```text\n\t```\n" + self.statement + "```\n", "INCOMPLETE")

    def test_mixed_indentation_false_closer_keeps_statement_in_example(self):
        for indent in (" \t", "  \t", "   \t", "\t "):
            with self.subTest(indent=indent):
                self.check_report("~~~text\n" + indent + "~~~\n" + self.statement + "~~~\n", "INCOMPLETE")

    def test_wrong_delimiter_does_not_close(self):
        for opening, closing in (("```", "~~~"), ("~~~", "```")):
            with self.subTest(opening=opening):
                self.check_report(opening + "text\n" + closing + "\n" + self.statement + opening + "\n", "INCOMPLETE")

    def test_shorter_closer_does_not_close(self):
        for fence in ("````", "~~~~~"):
            with self.subTest(fence=fence):
                self.check_report(fence + "text\n" + fence[:-1] + "\n" + self.statement + fence + "\n", "INCOMPLETE")

    def test_longer_closer_is_valid(self):
        for fence in ("```", "~~~"):
            with self.subTest(fence=fence):
                self.check_report(fence + "text\n  " + fence * 2 + "\n" + self.statement, "PASS")

    def test_closer_may_end_in_spaces_and_tabs(self):
        self.check_report("```text\n   ``` \t \n" + self.statement, "PASS")

    def test_trailing_text_is_not_a_closer(self):
        for suffix in ("text", " x", "<!-- not a closer -->", "\u00a0"):
            with self.subTest(suffix=suffix):
                self.check_report("```text\n```" + suffix + "\n" + self.statement + "```\n", "INCOMPLETE")

    def test_unclosed_fence_does_not_declare_statement(self):
        self.check_report("```text\n" + self.statement, "INCOMPLETE")

    def test_non_ascii_leading_whitespace_is_not_closer_indentation(self):
        self.check_report("```text\n\u00a0```\n" + self.statement + "```\n", "INCOMPLETE")

    def test_review_counterexamples_match_under_optimized_python(self):
        for indent in ("    ", "\t"):
            with self.subTest(indent=indent):
                result = self.check_report("```text\n" + indent + "```\n" + self.statement + "```\n", "INCOMPLETE")
                done = subprocess.run([sys.executable, "-O", str(HERE / "validate_trace.py"), str(self.root), "--json"],
                                      capture_output=True, text=True, timeout=10)
                self.assertEqual(done.returncode, 1, done.stderr)
                self.assertEqual(json.loads(done.stdout), result)


if __name__ == "__main__":
    unittest.main()
