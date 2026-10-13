"""Real-classifier terminal consistency regressions; all evidence is synthetic."""
from __future__ import annotations

import copy
import itertools
import unittest

from ci.actions_merge_train import core
from ci.actions_merge_train.test_composition_invariants import capture, execution, group

UNFINISHED = ("queued", "in_progress", "pending")
TERMINAL_CONCLUSIONS = (
    "success", "failure", "cancelled", "timed_out", "action_required",
    "neutral", "skipped", "stale", "startup_failure",
)


def unfinished_case(status="queued", conclusion="success", *, run_status="completed"):
    case = execution("green")
    case["run"]["run"].update(
        status=run_status, conclusion=conclusion if run_status == "completed" else None
    )
    job = case["jobs"]["jobs"][0]
    job["conclusion"] = conclusion
    job["steps"].append({
        "number": 2, "name": "synthetic unfinished step", "status": status, "conclusion": None,
    })
    return case


class TerminalConsistencyTests(unittest.TestCase):
    def test_all_terminal_conclusions_with_unfinished_steps_remain_inconclusive(self):
        for conclusion, status in itertools.product(TERMINAL_CONCLUSIONS, UNFINISHED):
            case = unfinished_case(status, conclusion)
            with self.subTest(conclusion=conclusion, status=status):
                result = core.classify_case(case["run"], case["jobs"])
                self.assertEqual(result["classification"], "INCONCLUSIVE_TERMINAL")
                self.assertIn("TERMINAL_JOB_HAS_NONTERMINAL_STEP:101:2", result["reasons"])
                self.assertIs(result["github_actions_green"], False)
                self.assertIs(result["source_regression_proven"], False)
                # The contradiction must not erase the step we did observe.
                self.assertEqual(result["executed_step_count"], 1)

    def test_unfinished_step_cannot_satisfy_guarded_review_readiness(self):
        for status in UNFINISHED:
            packet = capture([group("source-parses", [unfinished_case(status)])])
            with self.subTest(status=status):
                row = core.compile_capture(packet)
                self.assertEqual(row["overall_disposition"], "HOLD_AMBIGUOUS")
                self.assertIn("EXECUTION_AMBIGUOUS", row["hold_reasons"])
                self.assertEqual(row["workflows"][0]["disposition"], "HOLD_AMBIGUOUS")
                self.assertIs(row["merge_authorized"], False)
                self.assertIs(row["workflow_mutation_authorized"], False)

    def test_pending_runs_remain_pending_despite_contradictory_completed_job(self):
        for run_status, step_status in itertools.product(
            ("queued", "in_progress", "waiting", "requested", "pending"), UNFINISHED
        ):
            case = unfinished_case(step_status, run_status=run_status)
            with self.subTest(run_status=run_status, step_status=step_status):
                result = core.classify_case(case["run"], case["jobs"])
                self.assertEqual(result["classification"], "PENDING_EXECUTION")
                self.assertIn("TERMINAL_JOB_HAS_NONTERMINAL_STEP:101:2", result["reasons"])
                self.assertIs(result["github_actions_green"], False)

    def test_terminal_skipped_steps_are_not_unfinished_steps(self):
        case = execution("green")
        case["jobs"]["jobs"][0]["steps"].append({
            "number": 2, "name": "synthetic skipped step", "status": "completed", "conclusion": "skipped",
        })
        result = core.classify_case(case["run"], case["jobs"])
        self.assertEqual(result["classification"], "EXECUTED_GREEN")
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["executed_step_count"], 1)

    def test_ordinary_failure_interruption_and_no_run_controls_are_unchanged(self):
        expected = {
            "green": "EXECUTED_GREEN", "red": "EXECUTED_NON_GREEN",
            "queued": "PENDING_EXECUTION", "no_run": "NOT_EXECUTED_RUNNER_UNASSIGNED",
            "cancelled": "NOT_EXECUTED_RUNNER_UNASSIGNED",
            "assigned_zero_step": "NOT_EXECUTED_AFTER_ASSIGNMENT",
            "interrupted": "EXECUTION_INTERRUPTED", "inconclusive": "INCONCLUSIVE_TERMINAL",
        }
        for kind, classification in expected.items():
            with self.subTest(kind=kind):
                case = execution(kind)
                result = core.classify_case(case["run"], case["jobs"])
                self.assertEqual(result["classification"], classification)

    def test_multiple_unfinished_steps_are_named_and_order_independent(self):
        case = unfinished_case()
        case["jobs"]["jobs"][0]["steps"].append({
            "number": 3, "name": "synthetic second unfinished step", "status": "in_progress", "conclusion": None,
        })
        packet = capture([group("source-parses", [case])])
        reverse = copy.deepcopy(packet)
        reverse["workflows"][0]["cases"][0]["jobs"]["jobs"][0]["steps"].reverse()
        first = core.compile_train([packet])
        self.assertEqual(first, core.compile_train([reverse]))
        row = core.classify_case(case["run"], case["jobs"])
        self.assertEqual(row["reasons"], [
            "TERMINAL_JOB_HAS_NONTERMINAL_STEP:101:2",
            "TERMINAL_JOB_HAS_NONTERMINAL_STEP:101:3",
        ])
        self.assertTrue(core.verify_receipt(first, [packet])["valid"])

    def test_rehashed_false_green_receipt_fails_recomputation(self):
        packet = capture([group("source-parses", [unfinished_case()])])
        receipt = core.compile_train([packet])
        self.assertNotEqual(receipt["prs"][0]["overall_disposition"], "READY_FOR_GUARDED_REVIEW")
        tampered = copy.deepcopy(receipt)
        tampered["prs"][0]["overall_disposition"] = "READY_FOR_GUARDED_REVIEW"
        projection = dict(tampered)
        projection.pop("receipt_sha256")
        tampered["receipt_sha256"] = core.digest(projection)
        verification = core.verify_receipt(tampered, [packet])
        self.assertFalse(verification["valid"])
        self.assertIn("RECEIPT_RECOMPUTE_MISMATCH", verification["reason_codes"])
        self.assertNotIn("SUPPLIED_RECEIPT_DIGEST_MISMATCH", verification["reason_codes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
