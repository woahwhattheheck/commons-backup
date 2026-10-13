import copy
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci.actions_merge_train import core

SHA = "a" * 40
BASE = "b" * 40


def run_capture(run_id=1, *, attempt=1, status="completed", conclusion="success", head=SHA, repo="acme/widgets"):
    return {
        "schema": "github-actions-workflow-run-capture/v1",
        "run": {
            "id": run_id,
            "run_attempt": attempt,
            "repository": repo,
            "head_sha": head,
            "status": status,
            "conclusion": conclusion,
        },
    }


def step(number=1, *, status="completed", conclusion="success", name="test"):
    return {"number": number, "name": name, "status": status, "conclusion": conclusion}


def job(job_id=11, *, status="completed", conclusion="success", runner_id=55, steps=None, name="test"):
    return {
        "id": job_id,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "runner_id": runner_id,
        "steps": list(steps or []),
    }


def jobs_capture(jobs, *, run_id=1, attempt=1, head=SHA, repo="acme/widgets"):
    return {
        "schema": "github-actions-jobs-capture/v1",
        "run_id": run_id,
        "run_attempt": attempt,
        "repository": repo,
        "head_sha": head,
        "jobs": list(jobs),
    }


def case(run_id=1, *, attempt=1, status="completed", conclusion="success", runner_id=55, steps=None):
    if steps is None:
        steps = [step()] if conclusion == "success" else [step(conclusion="failure")]
    return {
        "run": run_capture(run_id, attempt=attempt, status=status, conclusion=conclusion),
        "jobs": jobs_capture(
            [
                job(
                    status=status if status != "completed" else "completed",
                    conclusion=conclusion if status == "completed" else None,
                    runner_id=runner_id,
                    steps=steps,
                )
            ],
            run_id=run_id,
            attempt=attempt,
        ),
    }


def workflow(name, cases, *, complete=True, observed_count=None, pages=1, next_cursor=None):
    if observed_count is None:
        observed_count = len(cases)
    if complete:
        next_cursor = None
    elif next_cursor is None:
        next_cursor = "cursor-2"
    return {
        "name": name,
        "cases": cases,
        "observation": {
            "schema": core.WORKFLOW_OBSERVATION_SCHEMA,
            "repository": "acme/widgets",
            "head_sha": SHA,
            "workflow": name,
            "observed_case_count": observed_count,
            "pages_fetched": pages,
            "pagination_exhausted": complete,
            "next_cursor": next_cursor,
        },
    }


def capture(workflows=None, *, review="GREEN", topology="CURRENT", review_id=7, behind=0):
    workflows = workflows if workflows is not None else [workflow("source-parses", [case()])]
    return {
        "schema": core.CAPTURE_SCHEMA,
        "repository": "acme/widgets",
        "pr_number": 42,
        "head_sha": SHA,
        "workflows": workflows,
        "source_review": {
            "schema": core.REVIEW_SCHEMA,
            "repository": "acme/widgets",
            "pr_number": 42,
            "head_sha": SHA,
            "state": review,
            "review_id": review_id if review in {"GREEN", "RED"} else None,
        },
        "topology": {
            "schema": core.TOPOLOGY_SCHEMA,
            "repository": "acme/widgets",
            "pr_number": 42,
            "head_sha": SHA,
            "base_sha": BASE if topology != "ABSENT" else None,
            "behind_by": behind if topology != "ABSENT" else None,
            "state": topology,
            "required_workflows": sorted(w["name"] for w in workflows),
        },
    }


class TrainTests(unittest.TestCase):
    def test_green_is_guarded_review_not_merge_authority(self):
        row = core.compile_capture(capture())
        self.assertEqual(row["overall_disposition"], "READY_FOR_GUARDED_REVIEW")
        self.assertFalse(row["merge_authorized"])
        self.assertEqual(row["workflows"][0]["disposition"], "SOURCE_EXECUTED_GREEN")
        self.assertTrue(row["workflows"][0]["observation"]["pagination_exhausted"])

    def test_incomplete_pagination_holds_even_when_seen_case_is_green(self):
        row = core.compile_capture(capture([workflow("source-parses", [case()], complete=False)]))
        self.assertEqual(row["workflows"][0]["disposition"], "EVIDENCE_INCOMPLETE")
        self.assertEqual(row["overall_disposition"], "HOLD_EVIDENCE_INCOMPLETE")
        self.assertIn("EXECUTION_EVIDENCE_INCOMPLETE", row["hold_reasons"])

    def test_omitted_case_cannot_mint_ready_when_observed_count_is_retained(self):
        group = workflow("source-parses", [case(1), case(2)])
        group["cases"].pop()
        with self.assertRaises(core.EvidenceError):
            core.compile_capture(capture([group]))

    def test_observation_binding_is_exact(self):
        for field, value in (
            ("repository", "other/repo"),
            ("head_sha", "c" * 40),
            ("workflow", "other"),
        ):
            group = workflow("source-parses", [case()])
            group["observation"][field] = value
            with self.subTest(field=field), self.assertRaises(core.EvidenceError):
                core.compile_capture(capture([group]))

    def test_provider_no_run_cancelled_and_queue_are_distinct(self):
        no = case(conclusion="failure", runner_id=0, steps=[])
        cancel = case(2, conclusion="cancelled", runner_id=0, steps=[])
        queued = case(3, status="queued", conclusion=None, runner_id=0, steps=[])
        rows = core.compile_capture(
            capture(
                [
                    workflow("a", [no]),
                    workflow("b", [cancel]),
                    workflow("c", [queued]),
                ]
            )
        )["workflows"]
        self.assertEqual(
            [row["disposition"] for row in rows],
            ["PROVIDER_NO_RUN", "PROVIDER_CANCELLED_BEFORE_EXECUTION", "PROVIDER_QUEUED"],
        )

    def test_assigned_zero_step_and_partial_matrix_fail_ambiguous(self):
        assigned = case(conclusion="failure", runner_id=9, steps=[])
        partial = {
            "run": run_capture(conclusion="failure"),
            "jobs": jobs_capture(
                [
                    job(11, conclusion="failure", runner_id=9, steps=[step()]),
                    job(12, status="queued", conclusion=None, runner_id=0, steps=[]),
                ]
            ),
        }
        a = core.compile_capture(capture([workflow("a", [assigned])]))
        b = core.compile_capture(capture([workflow("b", [partial])]))
        self.assertEqual(a["workflows"][0]["disposition"], "HOLD_AMBIGUOUS")
        self.assertEqual(b["workflows"][0]["disposition"], "HOLD_AMBIGUOUS")

    def test_latest_attempt_replaces_older_same_run(self):
        older = case(9, attempt=1, conclusion="failure", runner_id=0, steps=[])
        newer = case(9, attempt=2)
        row = core.compile_capture(capture([workflow("source-parses", [older, newer])]))["workflows"][0]
        self.assertEqual(row["disposition"], "SOURCE_EXECUTED_GREEN")
        self.assertEqual(row["latest_attempts"][0]["run_attempt"], 2)
        self.assertEqual(row["replaced_attempts"][0]["run_attempt"], 1)

    def test_conflicting_distinct_executions_hold(self):
        green = case(1)
        red = case(2, conclusion="failure")
        row = core.compile_capture(capture([workflow("source-parses", [green, red])]))["workflows"][0]
        self.assertEqual(row["disposition"], "HOLD_AMBIGUOUS")

    def test_distinct_green_plus_provider_hold_never_mints_ready(self):
        providers = (
            (
                case(2, status="queued", conclusion=None, runner_id=0, steps=[]),
                "PROVIDER_QUEUED",
                "HOLD_PROVIDER_QUEUED",
            ),
            (
                case(2, conclusion="failure", runner_id=0, steps=[]),
                "PROVIDER_NO_RUN",
                "HOLD_PROVIDER_STARVATION",
            ),
            (
                case(2, conclusion="cancelled", runner_id=0, steps=[]),
                "PROVIDER_CANCELLED_BEFORE_EXECUTION",
                "HOLD_PROVIDER_STARVATION",
            ),
        )
        for provider, workflow_disposition, overall in providers:
            for cases in ([case(1), provider], [provider, case(1)]):
                with self.subTest(
                    workflow_disposition=workflow_disposition,
                    first_run_id=cases[0]["run"]["run"]["id"],
                ):
                    compiled = core.compile_capture(capture([workflow("source-parses", cases)]))
                    self.assertEqual(compiled["workflows"][0]["disposition"], workflow_disposition)
                    self.assertEqual(compiled["overall_disposition"], overall)
                    self.assertTrue(compiled["work_feed_projection"]["provider_hold"])
                    self.assertNotEqual(compiled["overall_disposition"], "READY_FOR_GUARDED_REVIEW")

    def test_green_plus_multiple_provider_states_prefers_queued_hold(self):
        compiled = core.compile_capture(
            capture(
                [
                    workflow(
                        "source-parses",
                        [
                            case(1),
                            case(2, conclusion="failure", runner_id=0, steps=[]),
                            case(3, conclusion="cancelled", runner_id=0, steps=[]),
                            case(4, status="queued", conclusion=None, runner_id=0, steps=[]),
                        ],
                    )
                ]
            )
        )
        self.assertEqual(compiled["workflows"][0]["disposition"], "PROVIDER_QUEUED")
        self.assertEqual(compiled["overall_disposition"], "HOLD_PROVIDER_QUEUED")
        self.assertTrue(compiled["work_feed_projection"]["provider_hold"])

    def test_review_and_topology_are_independent_holds(self):
        self.assertEqual(core.compile_capture(capture(review="RED"))["overall_disposition"], "HOLD_SOURCE_REVIEW_RED")
        self.assertEqual(
            core.compile_capture(capture(topology="STALE", behind=2))["overall_disposition"],
            "HOLD_TOPOLOGY",
        )

    def test_missing_required_workflow_evidence_holds(self):
        row = core.compile_capture(capture([workflow("source-parses", [])]))
        self.assertEqual(row["workflows"][0]["disposition"], "EVIDENCE_ABSENT")
        self.assertEqual(row["overall_disposition"], "HOLD_EVIDENCE_ABSENT")

    def test_provider_storm_advice(self):
        one = case(8, attempt=1, conclusion="failure", runner_id=0, steps=[])
        two = case(8, attempt=2, conclusion="failure", runner_id=0, steps=[])
        row = core.compile_capture(capture([workflow("source-parses", [one, two])]))["workflows"][0]
        self.assertEqual(row["rerun_advice"], "BACKOFF_PROVIDER_STORM")

    def test_wrong_head_duplicate_cross_workflow_bool_and_topology_contract_rejected(self):
        wrong = case()
        wrong["run"]["run"]["head_sha"] = "c" * 40
        wrong["jobs"]["head_sha"] = "c" * 40
        with self.assertRaises(core.EvidenceError):
            core.compile_capture(capture([workflow("a", [wrong])]))

        same = case(5)
        with self.assertRaises(core.EvidenceError):
            core.compile_capture(
                capture(
                    [
                        workflow("a", [same]),
                        workflow("b", [copy.deepcopy(same)]),
                    ]
                )
            )

        bad = capture()
        bad["pr_number"] = True
        with self.assertRaises(core.EvidenceError):
            core.compile_capture(bad)

        bad2 = capture()
        bad2["topology"]["required_workflows"] = ["other"]
        with self.assertRaises(core.EvidenceError):
            core.compile_capture(bad2)

    def test_train_order_receipt_verify_and_tamper(self):
        a = capture()
        b = capture()
        b["pr_number"] = 41
        b["source_review"]["pr_number"] = 41
        b["topology"]["pr_number"] = 41
        first = core.compile_train([a, b])
        second = core.compile_train([b, a])
        self.assertEqual(first, second)
        self.assertTrue(core.verify_receipt(first, [a, b])["valid"])

        tampered = copy.deepcopy(first)
        tampered["prs"][0]["overall_disposition"] = "HOLD_AMBIGUOUS"
        self.assertIn(
            "SUPPLIED_RECEIPT_DIGEST_MISMATCH",
            core.verify_receipt(tampered, [a, b])["reason_codes"],
        )
        projection = dict(tampered)
        projection.pop("receipt_sha256", None)
        tampered["receipt_sha256"] = core.digest(projection)
        self.assertIn(
            "RECEIPT_RECOMPUTE_MISMATCH",
            core.verify_receipt(tampered, [a, b])["reason_codes"],
        )

    def test_markdown_deterministic_advisory_and_completeness_visible(self):
        receipt = core.compile_train([capture()])
        first = core.render_markdown(receipt)
        second = core.render_markdown(receipt)
        self.assertEqual(first, second)
        self.assertIn("not merge authorization", first)
        self.assertIn("READY_FOR_GUARDED_REVIEW", first)
        self.assertIn("enumeration complete", first)

    def test_strict_json_rejects_duplicate_keys(self):
        with self.assertRaises(core.EvidenceError):
            core.loads_strict(b'{"a":1,"a":2}', label="x")


if __name__ == "__main__":
    unittest.main(verbosity=2)
