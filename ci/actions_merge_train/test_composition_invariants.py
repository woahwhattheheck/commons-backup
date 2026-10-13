"""Independent end-to-end composition invariants; all captures are synthetic.

Authored by ZZ-FARADAY-Q6M4. These tests use the real strict capture contract and
retained execution classifier, not mocked rows or a second scoring engine.
"""
from __future__ import annotations

import copy
import itertools
import unittest

from ci.actions_merge_train import core

REPOSITORY = "acme/widgets"
HEAD = "a" * 40
BASE = "b" * 40
READY = "READY_FOR_GUARDED_REVIEW"
STATES = (
    "green", "red", "queued", "no_run", "cancelled",
    "assigned_zero_step", "interrupted", "inconclusive",
)


def execution(kind, run_id=1, attempt=1):
    """Construct valid capture shapes with independently selected step evidence."""
    status, conclusion, runner = "completed", "success", 17
    steps = [{"number": 1, "name": "synthetic test", "status": "completed", "conclusion": "success"}]
    if kind == "red":
        conclusion = "failure"
        steps[0]["conclusion"] = "failure"
    elif kind == "queued":
        status, conclusion, runner, steps = "queued", None, 0, []
    elif kind == "no_run":
        conclusion, runner, steps = "failure", 0, []
    elif kind == "cancelled":
        conclusion, runner, steps = "cancelled", 0, []
    elif kind == "assigned_zero_step":
        conclusion, steps = "failure", []
    elif kind == "interrupted":
        conclusion = "cancelled"
    elif kind == "inconclusive":
        steps = []
    elif kind != "green":
        raise ValueError(f"unknown fixture kind: {kind}")
    return {
        "run": {
            "schema": "github-actions-workflow-run-capture/v1",
            "run": {"id": run_id, "run_attempt": attempt, "repository": REPOSITORY,
                    "head_sha": HEAD, "status": status, "conclusion": conclusion},
        },
        "jobs": {
            "schema": "github-actions-jobs-capture/v1", "run_id": run_id,
            "run_attempt": attempt, "repository": REPOSITORY, "head_sha": HEAD,
            "jobs": [{"id": run_id * 100 + attempt, "name": "synthetic job", "status": status,
                      "conclusion": conclusion, "runner_id": runner, "steps": steps}],
        },
    }


def group(name, cases, complete=True):
    return {
        "name": name, "cases": cases,
        "observation": {
            "schema": core.WORKFLOW_OBSERVATION_SCHEMA,
            "repository": REPOSITORY, "head_sha": HEAD, "workflow": name,
            "observed_case_count": len(cases), "pages_fetched": 1,
            "pagination_exhausted": complete,
            "next_cursor": None if complete else "synthetic-next-page",
        },
    }


def capture(groups, review="GREEN", topology="CURRENT"):
    return {
        "schema": core.CAPTURE_SCHEMA, "repository": REPOSITORY,
        "pr_number": 42, "head_sha": HEAD, "workflows": groups,
        "source_review": {
            "schema": core.REVIEW_SCHEMA, "repository": REPOSITORY,
            "pr_number": 42, "head_sha": HEAD, "state": review,
            "review_id": 7 if review in {"GREEN", "RED"} else None,
        },
        "topology": {
            "schema": core.TOPOLOGY_SCHEMA, "repository": REPOSITORY,
            "pr_number": 42, "head_sha": HEAD, "state": topology,
            "base_sha": None if topology == "ABSENT" else BASE,
            "behind_by": None if topology == "ABSENT" else (0 if topology == "CURRENT" else 1),
            "required_workflows": [item["name"] for item in groups],
        },
    }


class CompositionInvariantTests(unittest.TestCase):
    def test_all_584_distinct_run_state_vectors_require_every_latest_run_green(self):
        count = 0
        for length in range(1, 4):
            for kinds in itertools.product(STATES, repeat=length):
                cases = [execution(kind, idx + 1) for idx, kind in enumerate(kinds)]
                packet = capture([group("source-parses", cases)])
                with self.subTest(kinds=kinds):
                    row = core.compile_capture(packet)
                    self.assertEqual(row["overall_disposition"] == READY, set(kinds) == {"green"})
                    self.assertIs(row["merge_authorized"], False)
                    self.assertIs(row["workflow_mutation_authorized"], False)
                    reverse = copy.deepcopy(packet)
                    reverse["workflows"][0]["cases"].reverse()
                    self.assertEqual(core.compile_train([packet]), core.compile_train([reverse]))
                count += 1
        self.assertEqual(count, 584)

    def test_each_trust_root_remains_independent_of_executed_green(self):
        for complete, review, topology in itertools.product(
            (False, True), ("GREEN", "RED", "ABSENT", "AMBIGUOUS"),
            ("CURRENT", "STALE", "ABSENT", "AMBIGUOUS"),
        ):
            with self.subTest(complete=complete, review=review, topology=topology):
                row = core.compile_capture(capture(
                    [group("source-parses", [execution("green")], complete)], review, topology
                ))
                self.assertEqual(row["overall_disposition"] == READY,
                                 complete and review == "GREEN" and topology == "CURRENT")

    def test_same_run_latest_attempt_supersedes_only_its_own_history(self):
        for older, latest in itertools.product(STATES, repeat=2):
            with self.subTest(older=older, latest=latest):
                cases = [execution(older, 9, 1), execution(latest, 9, 2)]
                row = core.compile_capture(capture([group("source-parses", cases)]))
                self.assertEqual(row["overall_disposition"] == READY, latest == "green")
                result = row["workflows"][0]
                self.assertEqual([item["run_attempt"] for item in result["latest_attempts"]], [2])
                self.assertEqual([item["run_attempt"] for item in result["replaced_attempts"]], [1])

    def test_reusing_one_run_across_workflow_names_is_rejected_even_across_attempts(self):
        for attempts in ((1, 2), (2, 1), (1, 1)):
            groups = [group("source-parses", [execution("green", 9, attempts[0])]),
                      group("path-manifest", [execution("green", 9, attempts[1])])]
            for ordered in (groups, list(reversed(groups))):
                with self.subTest(attempts=attempts, reverse=ordered is not groups):
                    with self.assertRaises(core.EvidenceError):
                        core.compile_capture(capture(ordered))

    def test_replaced_attempt_cannot_be_relabelled_as_another_required_workflow(self):
        groups = [group("source-parses", [execution("green", 9, 1), execution("green", 9, 3)]),
                  group("path-manifest", [execution("green", 9, 2)])]
        with self.assertRaises(core.EvidenceError):
            core.compile_capture(capture(groups))

    def test_legitimate_distinct_runs_and_within_workflow_attempt_history_still_work(self):
        groups = [group("source-parses", [execution("red", 9, 1), execution("green", 9, 2)]),
                  group("path-manifest", [execution("green", 10)])]
        receipt = core.compile_train([capture(groups)])
        self.assertEqual(receipt["prs"][0]["overall_disposition"], READY)
        self.assertTrue(core.verify_receipt(receipt, [capture(groups)])["valid"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
