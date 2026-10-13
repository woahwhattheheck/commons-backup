"""Independent reducer tests: a distinct run never disappears behind green.

The predecessor classifier is mocked at its documented output boundary. These
are aggregation tests, not substitutes for test_train's real-classifier cases.
"""
from __future__ import annotations

import copy
import itertools
import unittest
from unittest.mock import patch

from ci.actions_merge_train import workflow

REPOSITORY = "example/synthetic"
HEAD = "a" * 40
KINDS = (
    "SOURCE_EXECUTED_GREEN", "SOURCE_EXECUTED_RED", "PROVIDER_QUEUED",
    "PROVIDER_NO_RUN", "PROVIDER_CANCELLED_BEFORE_EXECUTION", "HOLD_AMBIGUOUS",
)


def classified(kind: str, run_id: int, attempt: int = 1) -> dict:
    state, status, conclusion, executed = {
        "SOURCE_EXECUTED_GREEN": ("EXECUTED_GREEN", "completed", "success", 1),
        "SOURCE_EXECUTED_RED": ("EXECUTED_NON_GREEN", "completed", "failure", 1),
        "PROVIDER_QUEUED": ("PENDING_EXECUTION", "queued", None, 0),
        "PROVIDER_NO_RUN": ("NOT_EXECUTED_RUNNER_UNASSIGNED", "completed", "failure", 0),
        "PROVIDER_CANCELLED_BEFORE_EXECUTION": (
            "NOT_EXECUTED_RUNNER_UNASSIGNED", "completed", "cancelled", 0
        ),
        "HOLD_AMBIGUOUS": ("INCONCLUSIVE_TERMINAL", "completed", "failure", 0),
    }[kind]
    return {
        "repository": REPOSITORY, "head_sha": HEAD,
        "run_id": run_id, "run_attempt": attempt, "classification": state,
        "run_status": status, "run_conclusion": conclusion,
        "executed_step_count": executed, "capture_projection_sha256": "c" * 64,
    }


def reduce_rows(rows: list[dict], *, complete: bool = True) -> dict:
    group = {
        "name": "synthetic-workflow",
        "observation": {"pagination_exhausted": complete},
        "cases": [{"run": row, "jobs": {}} for row in rows],
    }
    with patch.object(workflow, "classify_case", side_effect=lambda run, jobs: copy.deepcopy(run)):
        return workflow.workflow_result(group, REPOSITORY, HEAD)


class LatestAttemptCompositionTests(unittest.TestCase):
    def test_all_36_distinct_run_pairs_only_all_green_are_green(self):
        for left, right in itertools.product(KINDS, repeat=2):
            with self.subTest(left=left, right=right):
                result = reduce_rows([classified(left, 1), classified(right, 2)])
                self.assertEqual(
                    result["disposition"] == "SOURCE_EXECUTED_GREEN",
                    left == right == "SOURCE_EXECUTED_GREEN",
                )
                self.assertEqual(len(result["latest_attempts"]), 2)
                self.assertEqual(result["replaced_attempts"], [])
                self.assertFalse(result["merge_authorized"])

    def test_green_does_not_erase_each_provider_hold_in_either_input_order(self):
        for pending in KINDS[2:5]:
            rows = [classified("SOURCE_EXECUTED_GREEN", 100), classified(pending, 1)]
            for ordered in (rows, rows[::-1]):
                with self.subTest(pending=pending, order=[r["run_id"] for r in ordered]):
                    result = reduce_rows(ordered)
                    self.assertEqual(result["disposition"], pending)
                    self.assertEqual(result["provider_hold_attempt_count"], 1)
                    self.assertNotEqual(result["rerun_advice"], "NO_PROVIDER_RERUN_ADVICE_SOURCE_EXECUTED")

    def test_newer_green_supersedes_only_older_attempt_of_same_run(self):
        for old in KINDS:
            with self.subTest(old=old):
                result = reduce_rows([classified("SOURCE_EXECUTED_GREEN", 7, 2), classified(old, 7, 1)])
                self.assertEqual(result["disposition"], "SOURCE_EXECUTED_GREEN")
                self.assertEqual([r["run_attempt"] for r in result["latest_attempts"]], [2])
                self.assertEqual([r["run_attempt"] for r in result["replaced_attempts"]], [1])

    def test_newer_pending_supersedes_older_green_of_same_run(self):
        for latest in KINDS[1:]:
            with self.subTest(latest=latest):
                result = reduce_rows([classified("SOURCE_EXECUTED_GREEN", 7, 1), classified(latest, 7, 2)])
                self.assertEqual(result["disposition"], latest)

    def test_input_permutation_preserves_complete_output(self):
        rows = [classified("SOURCE_EXECUTED_GREEN", 12, 1),
                classified("PROVIDER_QUEUED", 12, 2),
                classified("SOURCE_EXECUTED_GREEN", 3, 1)]
        expected = reduce_rows(rows)
        for permutation in itertools.permutations(rows):
            self.assertEqual(reduce_rows(list(permutation)), expected)

    def test_incomplete_enumeration_and_empty_evidence_still_hold(self):
        self.assertEqual(reduce_rows([classified("SOURCE_EXECUTED_GREEN", 1)], complete=False)["disposition"],
                         "EVIDENCE_INCOMPLETE")
        self.assertEqual(reduce_rows([])["disposition"], "EVIDENCE_ABSENT")

    def test_duplicate_run_attempt_is_not_a_second_observation(self):
        row = classified("SOURCE_EXECUTED_GREEN", 1)
        with self.assertRaises(workflow.EvidenceError):
            reduce_rows([row, copy.deepcopy(row)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
