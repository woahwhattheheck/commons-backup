from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from .authority import classify
from .cli import main
from .common import EvidenceError, parse_json_bytes

HEAD = "a" * 40
BASE = "b" * 40
REPO = "acme/widget"
NOW = datetime(2026, 9, 13, 8, 30, tzinfo=timezone.utc)
_DEFAULT = object()


def workflow(workflow_id: int = 101, path: str = ".github/workflows/ci.yml", name: str = "CI") -> dict:
    return {"workflow_id": workflow_id, "workflow_path": path, "workflow_name": name}


def policy(*required: dict) -> dict:
    return {
        "schema_version": "commons-actions-policy/v1",
        "source": {
            "kind": "repository_manifest",
            "locator": f"{BASE}:.github/actions-authority-policy.json",
            "source_sha256": "sha256:" + "c" * 64,
        },
        "base_ref": "refs/heads/main",
        "base_sha": BASE,
        "captured_at": "2026-09-13T08:24:00Z",
        "required_workflows": list(required) or [workflow()],
    }


def inventory(total_count: int) -> dict:
    return {
        "source": "github-actions-runs",
        "locator": f"github-actions:runs:{REPO}:{HEAD}",
        "repository": REPO,
        "head_sha": HEAD,
        "complete": True,
        "total_count": total_count,
        "pages": 1,
        "next_url": None,
    }


def job_inventory(run_id: int, run_attempt: int, total_count: int) -> dict:
    return {
        "source": "github-actions-attempt-jobs",
        "locator": f"github-actions:attempt-jobs:{REPO}:{run_id}:{run_attempt}",
        "repository": REPO,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "complete": True,
        "total_count": total_count,
        "pages": 1,
        "next_url": None,
    }


def job(
    *,
    run_id: int = 1,
    run_attempt: int = 1,
    status: str = "completed",
    conclusion: str | None = "success",
    runner: str | None = "GitHub Actions 1",
    runner_id: int | None = 701,
    started: str | None = "2026-09-13T08:20:02Z",
    completed: str | None | object = _DEFAULT,
    steps: list | None | object = _DEFAULT,
    job_id: int = 11,
) -> dict:
    if completed is _DEFAULT:
        completed = "2026-09-13T08:21:00Z" if status == "completed" else None
    if steps is _DEFAULT:
        if status == "completed" and conclusion == "success":
            steps = [{"name": "test", "status": "completed", "conclusion": "success"}]
        else:
            steps = []
    return {
        "job_id": job_id,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "name": "test",
        "status": status,
        "conclusion": conclusion,
        "runner_id": runner_id,
        "runner_name": runner,
        "started_at": started,
        "completed_at": completed,
        "steps": steps,
    }


def run(
    *,
    workflow_id: int = 101,
    workflow_path: str = ".github/workflows/ci.yml",
    workflow_name: str = "CI",
    run_id: int = 1,
    run_number: int = 1,
    run_attempt: int = 1,
    status: str = "completed",
    conclusion: str | None = "success",
    jobs: list | None = None,
    started: str | None | object = _DEFAULT,
    completed: str | None | object = _DEFAULT,
) -> dict:
    if jobs is None:
        jobs = [job(run_id=run_id, run_attempt=run_attempt)]
    if started is _DEFAULT:
        started = "2026-09-13T08:20:01Z" if status in {"in_progress", "completed"} else None
    if completed is _DEFAULT:
        completed = "2026-09-13T08:21:01Z" if status == "completed" else None
    return {
        "run_id": run_id,
        "run_number": run_number,
        "run_attempt": run_attempt,
        "workflow_id": workflow_id,
        "workflow_path": workflow_path,
        "workflow_name": workflow_name,
        "head_sha": HEAD,
        "status": status,
        "conclusion": conclusion,
        "created_at": "2026-09-13T08:20:00Z",
        "started_at": started,
        "completed_at": completed,
        "jobs_inventory": job_inventory(run_id, run_attempt, len(jobs)),
        "jobs": jobs,
    }


def payload(*runs: dict, required: list[dict] | None = None) -> dict:
    rows = list(runs)
    return {
        "schema_version": "commons-actions-evidence/v3",
        "repository": REPO,
        "head_sha": HEAD,
        "captured_at": "2026-09-13T08:25:00Z",
        "policy": policy(*(required or [workflow()])),
        "inventory": inventory(len(rows)),
        "runs": rows,
    }


class AuthorityTests(unittest.TestCase):
    def test_terminal_green_is_classification_only(self) -> None:
        receipt = classify(payload(run()), now=NOW)
        self.assertEqual(receipt["decision"], "TERMINAL_GREEN")
        self.assertTrue(receipt["declared_policy_green"])
        self.assertFalse(receipt["merge_authorized"])
        self.assertFalse(receipt["side_effects_authorized"])
        self.assertEqual(receipt["authorization_scope"], "CLASSIFICATION_ONLY")

    def test_v1_v2_are_rejected(self) -> None:
        for schema in ("commons-actions-evidence/v1", "commons-actions-evidence/v2"):
            evidence = payload(run())
            evidence["schema_version"] = schema
            with self.subTest(schema=schema), self.assertRaisesRegex(EvidenceError, "v1/v2"):
                classify(evidence, now=NOW)

    def test_latest_run_number_wins_and_attempt_is_reported(self) -> None:
        old = run(run_id=10, run_number=40)
        failed_job = job(run_id=11, run_attempt=2, conclusion="failure", steps=[{"name": "test", "status": "completed", "conclusion": "failure"}])
        new = run(run_id=11, run_number=41, run_attempt=2, conclusion="failure", jobs=[failed_job])
        receipt = classify(payload(old, new), now=NOW)
        self.assertEqual(receipt["decision"], "TERMINAL_RED")
        selected = receipt["required_workflows"][0]
        self.assertEqual((selected["selected_run_id"], selected["selected_run_attempt"]), (11, 2))
        self.assertEqual(selected["older_exact_head_run_ids"], [10])

    def test_duplicate_run_number_is_rejected(self) -> None:
        with self.assertRaisesRegex(EvidenceError, "duplicate run_number"):
            classify(payload(run(run_id=1, run_number=7), run(run_id=2, run_number=7)), now=NOW)

    def test_workflow_identity_aliases_are_rejected(self) -> None:
        cases = [
            payload(run(run_id=1), run(run_id=2, run_number=2, workflow_path=".github/workflows/other.yml")),
            payload(run(run_id=1), run(run_id=2, run_number=2, workflow_id=202)),
            payload(run(run_id=1), run(run_id=2, run_number=2, workflow_id=202, workflow_path=".github/workflows/other.yml", workflow_name="CI")),
        ]
        for evidence in cases:
            with self.subTest(row=evidence["runs"][1]), self.assertRaisesRegex(EvidenceError, "maps to multiple"):
                classify(evidence, now=NOW)

    def test_missing_required_workflow_is_wait_missing(self) -> None:
        delivery = workflow(202, ".github/workflows/delivery.yml", "Delivery")
        receipt = classify(payload(run(), required=[workflow(), delivery]), now=NOW)
        self.assertEqual(receipt["decision"], "WAIT_MISSING")
        self.assertIsNone(receipt["required_workflows"][1]["selected_run_id"])

    def test_complete_run_inventory_is_bound_to_repo_and_head(self) -> None:
        mutations = [
            ("complete", False),
            ("total_count", 2),
            ("next_url", "https://api.github.com/next"),
            ("repository", "other/repo"),
            ("head_sha", "d" * 40),
            ("locator", "github-actions:runs:other/repo:" + HEAD),
        ]
        for key, value in mutations:
            evidence = payload(run())
            evidence["inventory"][key] = value
            with self.subTest(key=key), self.assertRaises(EvidenceError):
                classify(evidence, now=NOW)

    def test_jobs_inventory_is_attempt_specific(self) -> None:
        evidence = payload(run(run_attempt=2, jobs=[job(run_attempt=2)]))
        self.assertEqual(classify(evidence, now=NOW)["decision"], "TERMINAL_GREEN")
        for key, value in (
            ("source", "github-actions-jobs"),
            ("run_id", 99),
            ("run_attempt", 1),
            ("locator", f"github-actions:attempt-jobs:{REPO}:1:1"),
            ("complete", False),
            ("total_count", 2),
        ):
            hostile = payload(run(run_attempt=2, jobs=[job(run_attempt=2)]))
            hostile["runs"][0]["jobs_inventory"][key] = value
            with self.subTest(key=key), self.assertRaises(EvidenceError):
                classify(hostile, now=NOW)

    def test_job_rows_bind_run_and_attempt(self) -> None:
        for key, value in (("run_id", 9), ("run_attempt", 2)):
            hostile = payload(run())
            hostile["runs"][0]["jobs"][0][key] = value
            with self.subTest(key=key), self.assertRaises(EvidenceError):
                classify(hostile, now=NOW)

    def test_cross_attempt_backlog_splice_is_rejected(self) -> None:
        zero_from_attempt_1 = job(
            run_attempt=1,
            status="completed",
            conclusion="cancelled",
            runner="",
            runner_id=0,
            started="2026-09-13T08:20:00Z",
            steps=[],
        )
        hostile = payload(run(run_attempt=2, conclusion="cancelled", jobs=[zero_from_attempt_1]))
        hostile["runs"][0]["jobs_inventory"] = job_inventory(1, 1, 1)
        with self.assertRaisesRegex(EvidenceError, "run_attempt"):
            classify(hostile, now=NOW)

    def test_provider_native_zero_step_shapes_are_backlog(self) -> None:
        for status, conclusion in (("queued", None), ("completed", "cancelled")):
            zero = job(
                status=status,
                conclusion=conclusion,
                runner="",
                runner_id=0,
                started="2026-09-13T08:20:00Z",
                completed="2026-09-13T08:21:00Z" if status == "completed" else None,
                steps=[],
            )
            evidence = payload(run(status=status, conclusion=conclusion, jobs=[zero]))
            receipt = classify(evidence, now=NOW)
            self.assertEqual(receipt["decision"], "WAIT_RUNNER_BACKLOG")
            self.assertTrue(receipt["runner_exception_candidate"])

    def test_assigned_cancelled_job_is_hold(self) -> None:
        assigned = job(status="completed", conclusion="cancelled", runner="runner-1", runner_id=42, steps=[])
        receipt = classify(payload(run(conclusion="cancelled", jobs=[assigned])), now=NOW)
        self.assertEqual(receipt["decision"], "HOLD")

    def test_queued_run_cannot_reuse_completed_cancelled_job_shape(self) -> None:
        completed_cancelled = job(
            status="completed",
            conclusion="cancelled",
            runner="",
            runner_id=0,
            steps=[],
        )
        receipt = classify(
            payload(run(status="queued", conclusion=None, jobs=[completed_cancelled])),
            now=NOW,
        )
        self.assertEqual(receipt["decision"], "WAIT_EXECUTION")
        self.assertFalse(receipt["runner_exception_candidate"])

    def test_runnerless_success_is_hold(self) -> None:
        fake = job(runner="", runner_id=0)
        receipt = classify(payload(run(jobs=[fake])), now=NOW)
        self.assertEqual(receipt["decision"], "HOLD")
        self.assertFalse(receipt["declared_policy_green"])

    def test_timestampless_success_is_hold(self) -> None:
        fake = job(started=None, completed=None)
        self.assertEqual(classify(payload(run(jobs=[fake])), now=NOW)["decision"], "HOLD")
        self.assertEqual(classify(payload(run(started=None, completed=None)), now=NOW)["decision"], "HOLD")

    def test_stepless_success_is_hold(self) -> None:
        for steps in (None, []):
            fake = job(steps=steps)
            with self.subTest(steps=steps):
                self.assertEqual(classify(payload(run(jobs=[fake])), now=NOW)["decision"], "HOLD")

    def test_incomplete_success_step_evidence_is_hold(self) -> None:
        pending_step = job(steps=[{"name": "test", "status": "in_progress", "conclusion": None}])
        self.assertEqual(classify(payload(run(jobs=[pending_step])), now=NOW)["decision"], "HOLD")
        failed_step = job(steps=[{"name": "test", "status": "completed", "conclusion": "failure"}])
        self.assertEqual(classify(payload(run(jobs=[failed_step])), now=NOW)["decision"], "HOLD")

    def test_hold_dominates_red(self) -> None:
        delivery = workflow(202, ".github/workflows/delivery.yml", "Delivery")
        red_job = job(run_id=2, job_id=22, conclusion="failure", steps=[{"name": "test", "status": "completed", "conclusion": "failure"}])
        red = run(workflow_id=202, workflow_path=delivery["workflow_path"], workflow_name=delivery["workflow_name"], run_id=2, conclusion="failure", jobs=[red_job])
        contradictory = run(jobs=[job(runner="", runner_id=0)])
        receipt = classify(payload(contradictory, red, required=[workflow(), delivery]), now=NOW)
        self.assertEqual(receipt["decision"], "HOLD")

    def test_wait_execution_and_optional_workflow(self) -> None:
        active = job(status="in_progress", conclusion=None, runner="runner-1", runner_id=42, completed=None, steps=[])
        waiting = classify(payload(run(status="in_progress", conclusion=None, jobs=[active])), now=NOW)
        self.assertEqual(waiting["decision"], "WAIT_EXECUTION")
        optional = run(workflow_id=303, workflow_path=".github/workflows/optional.yml", workflow_name="Optional", run_id=3)
        receipt = classify(payload(run(), optional), now=NOW)
        self.assertEqual(receipt["decision"], "TERMINAL_GREEN")
        self.assertEqual(receipt["ignored_extra_workflows"][0]["workflow_id"], 303)

    def test_wrong_head_stale_and_future_evidence_fail(self) -> None:
        cases = []
        wrong = payload(run())
        wrong["runs"][0]["head_sha"] = "b" * 40
        cases.append(wrong)
        stale = payload(run())
        stale["captured_at"] = "2026-09-13T07:00:00Z"
        cases.append(stale)
        stale_policy = payload(run())
        stale_policy["policy"]["captured_at"] = "2026-09-13T07:00:00Z"
        cases.append(stale_policy)
        postdated_policy = payload(run())
        postdated_policy["policy"]["captured_at"] = "2026-09-13T08:25:01Z"
        cases.append(postdated_policy)
        future = payload(run())
        future["captured_at"] = "2026-09-13T09:00:00Z"
        cases.append(future)
        for evidence in cases:
            with self.subTest(captured=evidence["captured_at"]), self.assertRaises(EvidenceError):
                classify(evidence, now=NOW)

    def test_timestamps_after_capture_fail(self) -> None:
        late = payload(run())
        late["runs"][0]["jobs"][0]["completed_at"] = "2026-09-13T08:31:00Z"
        late["runs"][0]["completed_at"] = "2026-09-13T08:31:01Z"
        with self.assertRaisesRegex(EvidenceError, "after the evidence capture"):
            classify(late, now=NOW)

    def test_duplicate_jobs_and_runner_identity_mismatch_fail(self) -> None:
        duplicate = payload(run(jobs=[job(job_id=11), job(job_id=11)]))
        with self.assertRaisesRegex(EvidenceError, "duplicate job ids"):
            classify(duplicate, now=NOW)
        mismatch = payload(run(jobs=[job(runner=None, runner_id=42)]))
        with self.assertRaisesRegex(EvidenceError, "assignment evidence disagree"):
            classify(mismatch, now=NOW)

    def test_strict_json_exact_fields_and_types(self) -> None:
        with self.assertRaises(EvidenceError):
            parse_json_bytes(b'{"schema_version":"x","schema_version":"y"}')
        evidence = payload(run())
        evidence["trust_me"] = True
        with self.assertRaises(EvidenceError):
            classify(evidence, now=NOW)
        evidence = payload(run())
        evidence["runs"][0]["jobs"][0]["run_attempt"] = True
        with self.assertRaises(EvidenceError):
            classify(evidence, now=NOW)

    def test_policy_and_receipt_digests_are_bound_and_deterministic(self) -> None:
        first = classify(payload(run()), now=NOW)
        later = classify(payload(run()), now=datetime(2026, 9, 13, 8, 31, tzinfo=timezone.utc))
        self.assertNotEqual(first["evaluated_at"], later["evaluated_at"])
        self.assertEqual(first["receipt_digest"], later["receipt_digest"])
        changed = payload(run())
        changed["policy"]["source"]["source_sha256"] = "sha256:" + "d" * 64
        second = classify(changed, now=NOW)
        self.assertNotEqual(first["policy_digest"], second["policy_digest"])
        self.assertNotEqual(first["receipt_digest"], second["receipt_digest"])

    def test_cli_create_exclusive_and_symlink_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "evidence.json"
            out = root / "receipt.json"
            src.write_text(json.dumps(payload(run())), encoding="utf-8")
            self.assertEqual(main([str(src), "--out", str(out), "--now", "2026-09-13T08:30:00Z"]), 3)
            receipt = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(receipt["merge_authorized"])
            self.assertEqual(main([str(src), "--out", str(out), "--now", "2026-09-13T08:30:00Z"]), 2)
            if hasattr(os, "symlink"):
                link = root / "link.json"
                try:
                    link.symlink_to(src.name)
                except (OSError, NotImplementedError):
                    return
                self.assertEqual(main([str(link), "--out", str(root / "other.json"), "--now", "2026-09-13T08:30:00Z"]), 2)


if __name__ == "__main__":
    unittest.main()
