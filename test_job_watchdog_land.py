#!/usr/bin/env python3
"""Regression for job-watchdog land losing a moving-main push race.

Run 33186268839 on SHA 7bd5c37b8a8ec096c154903cbb1af17bce5090f1 rebased,
then `git push origin HEAD:main` was rejected (`fetch first`) because
another land hit main in the gap. Cite:
woahwhattheheck/commons:job-watchdog:7bd5c37b8a8ec096c154903cbb1af17bce5090f1:land job state on main only

Run 33204247596 on SHA 9fc85d4c58e895fba469d029aea2a7698492cae4 then
hit REBASE_CONFLICT: add/add on three grkrev wake_jobs rows plus a content
split on grok-community-evidence-portable-20260828.json. Cite:
woahwhattheheck/commons:job-watchdog:9fc85d4c58e895fba469d029aea2a7698492cae4:land job state on main only

Sibling run 33204368748 on SHA e9c3e87a70bfe135747ee5b41d647b5ad1e72551
failed the same land step with the same four wake_jobs paths after a
two-hour queue on a stale checkout. Compose landed in #5124. Unique
leftover: refresh onto current main before the tick so queued runs do
not replay hours-old job files. Cite:
woahwhattheheck/commons:job-watchdog:e9c3e87a70bfe135747ee5b41d647b5ad1e72551:land job state on main only

Run 33206968416 on SHA a231d7ec6711b5ae5a40efed06847fdf6d245cda then
failed the same land step after the same two-hour queue, with the same
four paths plus content on grok-slack-e2e-proof-20260828-05.json.
Refresh and compose were already on main; GitHub still executed the
pre-repair workflow YAML bound to the triggering SHA. Unique leftover:
cancel redundant main ticks so those snapshots never land. Cite:
woahwhattheheck/commons:job-watchdog:a231d7ec6711b5ae5a40efed06847fdf6d245cda:land job state on main only

Run 33211112146 on SHA 57d934d10fcfe7b63df057b5af4098df6c1f8ed0 then
failed the same land step after an ~80-minute queue. Exact stderr is
eight CONFLICT (content) wake_jobs paths, attempts=1. Concurrency
cancel-in-progress (#5157) cannot rewrite pre-concurrency YAML.
Unique leftover: current-main ticks explicitly cancel those siblings.
Cite:
woahwhattheheck/commons:job-watchdog:57d934d10fcfe7b63df057b5af4098df6c1f8ed0:land job state on main only
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness_wake.land import (
    COMMIT_MESSAGE,
    compose_wake_json,
    is_push_race,
    land,
)
from harness_wake.cancel_stale import (
    cancel_stale,
    select_stale_runs,
)


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github/workflows/job-watchdog.yml"

# Exact stderr from https://github.com/woahwhattheheck/commons/actions/runs/33186268839
RUN_33186268839_STDERR = """\
To https://github.com/woahwhattheheck/commons
 ! [rejected]            HEAD -> main (fetch first)
error: failed to push some refs to 'https://github.com/woahwhattheheck/commons'
hint: Updates were rejected because the remote contains work that you do not
hint: have locally. This is usually caused by another repository pushing to
hint: the same ref. If you want to integrate the remote changes, use
hint: 'git pull' before pushing again.
hint: See the 'Note about fast-forwards' in 'git push --help' for details.
"""

# Exact rebase stderr from https://github.com/woahwhattheheck/commons/actions/runs/33204247596
RUN_33204247596_REBASE = """\
Auto-merging wake_jobs/grkrev-0d3057ebbe56903f6c3076b9.json
CONFLICT (add/add): Merge conflict in wake_jobs/grkrev-0d3057ebbe56903f6c3076b9.json
Auto-merging wake_jobs/grkrev-6d23f7078fd691bad2a983f8.json
CONFLICT (add/add): Merge conflict in wake_jobs/grkrev-6d23f7078fd691bad2a983f8.json
Auto-merging wake_jobs/grkrev-ced8dfd809c45f0ef23f9606.json
CONFLICT (add/add): Merge conflict in wake_jobs/grkrev-ced8dfd809c45f0ef23f9606.json
Auto-merging wake_jobs/grok-community-evidence-portable-20260828.json
CONFLICT (content): Merge conflict in wake_jobs/grok-community-evidence-portable-20260828.json

Rebasing (1/1)
error: could not apply 30ae5bc52... jobs: watchdog tick (no model)
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply 30ae5bc52... # jobs: watchdog tick (no model)
"""

# Exact rebase stderr from https://github.com/woahwhattheheck/commons/actions/runs/33206968416
RUN_33206968416_REBASE = """\
Auto-merging wake_jobs/grkrev-0d3057ebbe56903f6c3076b9.json
CONFLICT (add/add): Merge conflict in wake_jobs/grkrev-0d3057ebbe56903f6c3076b9.json
Auto-merging wake_jobs/grkrev-6d23f7078fd691bad2a983f8.json
CONFLICT (add/add): Merge conflict in wake_jobs/grkrev-6d23f7078fd691bad2a983f8.json
Auto-merging wake_jobs/grkrev-ced8dfd809c45f0ef23f9606.json
CONFLICT (add/add): Merge conflict in wake_jobs/grkrev-ced8dfd809c45f0ef23f9606.json
Auto-merging wake_jobs/grok-community-evidence-portable-20260828.json
CONFLICT (content): Merge conflict in wake_jobs/grok-community-evidence-portable-20260828.json
Auto-merging wake_jobs/grok-slack-e2e-proof-20260828-05.json
CONFLICT (content): Merge conflict in wake_jobs/grok-slack-e2e-proof-20260828-05.json

Rebasing (1/1)
error: could not apply e122fc235... jobs: watchdog tick (no model)
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply e122fc235... # jobs: watchdog tick (no model)
"""

# Exact rebase stderr from https://github.com/woahwhattheheck/commons/actions/runs/33211112146
RUN_33211112146_REBASE = """\
Auto-merging wake_jobs/grkrev-0d3057ebbe56903f6c3076b9.json
CONFLICT (content): Merge conflict in wake_jobs/grkrev-0d3057ebbe56903f6c3076b9.json
Auto-merging wake_jobs/grkrev-6d23f7078fd691bad2a983f8.json
CONFLICT (content): Merge conflict in wake_jobs/grkrev-6d23f7078fd691bad2a983f8.json
Auto-merging wake_jobs/grkrev-ced8dfd809c45f0ef23f9606.json
CONFLICT (content): Merge conflict in wake_jobs/grkrev-ced8dfd809c45f0ef23f9606.json
Auto-merging wake_jobs/grok-community-evidence-portable-20260828.json
CONFLICT (content): Merge conflict in wake_jobs/grok-community-evidence-portable-20260828.json
Auto-merging wake_jobs/grok-fa-wake-reconcile-20260828-02.json
CONFLICT (content): Merge conflict in wake_jobs/grok-fa-wake-reconcile-20260828-02.json
Auto-merging wake_jobs/grok-slack-e2e-proof-20260828-05.json
CONFLICT (content): Merge conflict in wake_jobs/grok-slack-e2e-proof-20260828-05.json
Auto-merging wake_jobs/grok-slack-immediate-ingress-repair-20260828-01.json
CONFLICT (content): Merge conflict in wake_jobs/grok-slack-immediate-ingress-repair-20260828-01.json
Auto-merging wake_jobs/probe-env-tiny01.json
CONFLICT (content): Merge conflict in wake_jobs/probe-env-tiny01.json

Rebasing (1/1)
error: could not apply f26875b86... jobs: watchdog tick (no model)
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply f26875b86... # jobs: watchdog tick (no model)
"""

GRKREV_PATHS = (
    "wake_jobs/grkrev-0d3057ebbe56903f6c3076b9.json",
    "wake_jobs/grkrev-6d23f7078fd691bad2a983f8.json",
    "wake_jobs/grkrev-ced8dfd809c45f0ef23f9606.json",
)
EVIDENCE_PATH = "wake_jobs/grok-community-evidence-portable-20260828.json"
SLACK_E2E_PATH = "wake_jobs/grok-slack-e2e-proof-20260828-05.json"
RUN_33211112146_CONTENT_PATHS = (
    "wake_jobs/grkrev-0d3057ebbe56903f6c3076b9.json",
    "wake_jobs/grkrev-6d23f7078fd691bad2a983f8.json",
    "wake_jobs/grkrev-ced8dfd809c45f0ef23f9606.json",
    "wake_jobs/grok-community-evidence-portable-20260828.json",
    "wake_jobs/grok-fa-wake-reconcile-20260828-02.json",
    "wake_jobs/grok-slack-e2e-proof-20260828-05.json",
    "wake_jobs/grok-slack-immediate-ingress-repair-20260828-01.json",
    "wake_jobs/probe-env-tiny01.json",
)


def _job(*, job_id: str, updated_at: str, receipts: list, attempt_count: int = 0, status: str = "OPEN") -> dict:
    return {
        "attempt_count": attempt_count,
        "event_receipts": receipts,
        "job_id": job_id,
        "status": status,
        "updated_at": updated_at,
        "created_at": "2026-08-28T10:46:59Z",
    }


def _dump(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


class FakeGit:
    def __init__(
        self,
        *,
        cached_dirty: bool = True,
        push_results: list[tuple[int, str]] | None = None,
        rebase_code: int = 0,
        continue_code: int = 0,
        unmerged: list[str] | None = None,
        stages: dict[str, tuple[str, str]] | None = None,
        rebase_stderr: str = "",
    ):
        self.calls: list[list[str]] = []
        self.cached_dirty = cached_dirty
        self.push_results = list(push_results or [(0, "")])
        self.rebase_code = rebase_code
        self.continue_code = continue_code
        self.unmerged = list(unmerged or [])
        self.stages = dict(stages or {})
        self.rebase_stderr = rebase_stderr
        self.slept: list[float] = []
        self.added_paths: list[str] = []

    def __call__(self, args, **kwargs):
        cmd = list(args)
        self.calls.append(cmd)
        git_op = cmd[1] if len(cmd) > 1 else ""
        stdout, stderr, code = "", "", 0
        if git_op == "diff":
            if "--diff-filter=U" in cmd:
                stdout = "\n".join(self.unmerged) + ("\n" if self.unmerged else "")
                code = 0
            else:
                code = 1 if self.cached_dirty else 0
        elif git_op == "commit":
            stdout = "[main deadbeef] %s" % COMMIT_MESSAGE
        elif git_op == "push":
            code, stderr = self.push_results.pop(0)
        elif git_op == "show":
            spec = cmd[-1]
            if spec.startswith(":") and spec.count(":") >= 2:
                stage, path = spec[1:].split(":", 1)
                pair = self.stages.get(path)
                if pair is None:
                    code = 1
                else:
                    stdout = pair[0] if stage == "2" else pair[1]
            else:
                code = 1
        elif git_op == "add":
            if len(cmd) >= 4 and cmd[2] == "--":
                self.added_paths.append(cmd[3])
        elif git_op == "rebase":
            if "--abort" in cmd:
                code = 0
            elif "--continue" in cmd or "--skip" in cmd:
                code = self.continue_code
            else:
                code = self.rebase_code
                if code:
                    stderr = self.rebase_stderr or (
                        "CONFLICT (content): merge conflict in wake_jobs/x.json"
                    )
        return subprocess.CompletedProcess(cmd, code, stdout, stderr)

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    def verbs(self) -> list[str]:
        return [cmd[1] for cmd in self.calls if len(cmd) > 1]


class JobWatchdogLandTests(unittest.TestCase):
    def test_workflow_lands_through_retrying_helper(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python3 -m harness_wake.land", text)
        self.assertIn("name: refresh onto current main", text)
        self.assertIn("git fetch origin main", text)
        self.assertIn("git reset --hard origin/main", text)
        self.assertIn("concurrency:", text)
        conc = text.split("concurrency:", 1)[1].split("jobs:", 1)[0]
        self.assertIn("cancel-in-progress:", conc)
        self.assertIn("github.ref", conc)
        self.assertIn("pull_request", conc)
        self.assertNotIn("--force", text)
        self.assertIn("actions: write", text)
        self.assertIn("name: cancel stale sibling ticks", text)
        self.assertIn("python3 -m harness_wake.cancel_stale", text)
        cancel_step = text.split("name: cancel stale sibling ticks", 1)[1]
        self.assertIn("github.ref == 'refs/heads/main'", cancel_step.split("run:", 1)[0])
        self.assertIn("GH_TOKEN", cancel_step.split("name:", 1)[0])
        refresh_at = text.find("name: refresh onto current main")
        cancel_at = text.find("name: cancel stale sibling ticks")
        tick_at = text.find("name: cheap tick, never a model")
        self.assertTrue(refresh_at < cancel_at < tick_at)
        land_step = text.split("name: land job state on main only", 1)[1]
        self.assertNotIn("git pull --rebase origin main", land_step)
        self.assertNotIn("git push origin HEAD:main", land_step)
        self.assertNotIn("--force", land_step)
        self.assertIn("github.ref == 'refs/heads/main'", land_step.split("run:", 1)[0])

    def test_quiet_tree_does_not_push(self):
        git = FakeGit(cached_dirty=False)
        result = land(run=git, sleep=git.sleep)
        self.assertEqual(result["state"], "QUIET")
        self.assertTrue(result["ok"])
        self.assertEqual(git.verbs(), ["add", "diff"])

    def test_first_push_success_lands_once(self):
        git = FakeGit(push_results=[(0, "")])
        result = land(run=git, sleep=git.sleep)
        self.assertEqual(result, {"ok": True, "state": "LANDED", "attempts": 1})
        self.assertEqual(git.verbs(), ["add", "diff", "commit", "push"])
        self.assertEqual(git.slept, [])

    def test_run_33186268839_race_retries_and_lands(self):
        git = FakeGit(push_results=[(1, RUN_33186268839_STDERR), (0, "")])
        result = land(run=git, sleep=git.sleep)
        self.assertTrue(is_push_race(subprocess.CompletedProcess(
            ["git", "push"], 1, "", RUN_33186268839_STDERR
        )))
        self.assertEqual(result, {"ok": True, "state": "LANDED", "attempts": 2})
        self.assertEqual(
            git.verbs(),
            ["add", "diff", "commit", "push", "fetch", "rebase", "push"],
        )
        self.assertEqual(git.slept, [3])
        joined = " ".join(" ".join(cmd) for cmd in git.calls)
        self.assertNotIn("--force", joined)

    def test_non_race_push_failure_does_not_retry(self):
        git = FakeGit(push_results=[(1, "error: remote unpack failed")])
        result = land(run=git, sleep=git.sleep)
        self.assertEqual(result["state"], "PUSH_FAILED")
        self.assertFalse(result["ok"])
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(git.verbs(), ["add", "diff", "commit", "push"])
        self.assertEqual(git.slept, [])

    def test_rebase_conflict_aborts_without_force(self):
        git = FakeGit(
            push_results=[(1, RUN_33186268839_STDERR)],
            rebase_code=1,
        )
        result = land(run=git, sleep=git.sleep)
        self.assertEqual(result["state"], "REBASE_CONFLICT")
        self.assertFalse(result["ok"])
        self.assertEqual(result["resolve"]["reason"], "NO_UNMERGED")
        self.assertEqual(
            git.verbs(),
            ["add", "diff", "commit", "push", "fetch", "rebase", "diff", "rebase"],
        )
        self.assertEqual(git.calls[-1], ["git", "rebase", "--abort"])
        joined = " ".join(" ".join(cmd) for cmd in git.calls)
        self.assertNotIn("--force", joined)

    def test_exhausted_race_reports_push_race(self):
        git = FakeGit(push_results=[
            (1, RUN_33186268839_STDERR),
            (1, RUN_33186268839_STDERR),
        ])
        result = land(attempts=2, run=git, sleep=git.sleep)
        self.assertEqual(result["state"], "PUSH_RACE")
        self.assertFalse(result["ok"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(git.slept, [3])
        self.assertEqual(git.verbs().count("push"), 2)
        self.assertEqual(git.verbs().count("rebase"), 2)

    def test_helper_main_prints_json_receipt(self):
        from harness_wake import land as land_mod

        git = FakeGit(cached_dirty=False)
        original = land_mod.land
        try:
            land_mod.land = lambda **_kwargs: land(run=git, sleep=git.sleep)
            code = land_mod.main([])
        finally:
            land_mod.land = original
        self.assertEqual(code, 0)

    def test_add_add_identical_grkrev_composes(self):
        body = _dump(_job(
            job_id="grkrev-0d3057ebbe56903f6c3076b9",
            updated_at="2026-08-28T20:40:47Z",
            receipts=[],
        ))
        composed = compose_wake_json(body, body)
        self.assertEqual(composed, body)

    def test_content_split_unions_event_receipts(self):
        ours = _job(
            job_id="grok-community-evidence-portable-20260828",
            updated_at="2026-08-28T16:51:35Z",
            attempt_count=4,
            receipts=[{"attempt_id": "a04", "event": "wake", "ts": "2026-08-28T16:51:35Z"}],
        )
        theirs = _job(
            job_id="grok-community-evidence-portable-20260828",
            updated_at="2026-08-28T21:22:29Z",
            attempt_count=5,
            receipts=[
                {"attempt_id": "a04", "event": "wake", "ts": "2026-08-28T16:51:35Z"},
                {"attempt_id": "a05", "event": "wake", "ts": "2026-08-28T21:22:29Z"},
            ],
        )
        composed = json.loads(compose_wake_json(_dump(ours), _dump(theirs)))
        self.assertEqual(composed["attempt_count"], 5)
        self.assertEqual(composed["updated_at"], "2026-08-28T21:22:29Z")
        self.assertEqual(len(composed["event_receipts"]), 2)
        ids = {row["attempt_id"] for row in composed["event_receipts"]}
        self.assertEqual(ids, {"a04", "a05"})

    def test_terminal_status_is_kept(self):
        open_row = _job(
            job_id="specter-watchdog-head-proof-20260825-01",
            updated_at="2026-08-28T21:22:29Z",
            attempt_count=1,
            receipts=[{"event": "wake", "ts": "2026-08-28T21:22:29Z"}],
            status="OPEN",
        )
        done_row = _job(
            job_id="specter-watchdog-head-proof-20260825-01",
            updated_at="2026-08-25T07:38:33Z",
            attempt_count=0,
            receipts=[{"event": "auto_complete", "ts": "2026-08-25T07:38:33Z"}],
            status="DONE",
        )
        composed = json.loads(compose_wake_json(_dump(open_row), _dump(done_row)))
        self.assertEqual(composed["status"], "DONE")
        events = {row["event"] for row in composed["event_receipts"]}
        self.assertEqual(events, {"wake", "auto_complete"})

    def test_split_job_ids_are_not_composed(self):
        left = _dump(_job(job_id="alpha", updated_at="2026-08-28T20:00:00Z", receipts=[]))
        right = _dump(_job(job_id="beta", updated_at="2026-08-28T21:00:00Z", receipts=[]))
        self.assertIsNone(compose_wake_json(left, right))

    def test_run_33204247596_add_add_compose_lands(self):
        tmp = tempfile.mkdtemp()
        stages = {}
        unmerged = list(GRKREV_PATHS) + [EVIDENCE_PATH]
        for path in GRKREV_PATHS:
            ident = Path(path).stem
            body = _dump(_job(job_id=ident, updated_at="2026-08-28T20:40:47Z", receipts=[]))
            stages[path] = (body, body)
        ours = _dump(_job(
            job_id="grok-community-evidence-portable-20260828",
            updated_at="2026-08-28T16:51:35Z",
            attempt_count=4,
            receipts=[{"attempt_id": "a04", "event": "wake", "ts": "2026-08-28T16:51:35Z"}],
        ))
        theirs = _dump(_job(
            job_id="grok-community-evidence-portable-20260828",
            updated_at="2026-08-28T21:22:29Z",
            attempt_count=5,
            receipts=[
                {"attempt_id": "a04", "event": "wake", "ts": "2026-08-28T16:51:35Z"},
                {"attempt_id": "a05", "event": "wake", "ts": "2026-08-28T21:22:29Z"},
            ],
        ))
        stages[EVIDENCE_PATH] = (ours, theirs)
        git = FakeGit(
            push_results=[(1, RUN_33186268839_STDERR), (0, "")],
            rebase_code=1,
            continue_code=0,
            unmerged=unmerged,
            stages=stages,
            rebase_stderr=RUN_33204247596_REBASE,
        )
        result = land(cwd=tmp, run=git, sleep=git.sleep)
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "LANDED")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["resolve"]["state"], "COMPOSED")
        self.assertEqual(git.added_paths, unmerged)
        self.assertIn(["git", "rebase", "--continue"], git.calls)
        self.assertNotIn(["git", "rebase", "--abort"], git.calls)
        joined = " ".join(" ".join(cmd) for cmd in git.calls)
        self.assertNotIn("--force", joined)
        evidence = json.loads((Path(tmp) / EVIDENCE_PATH).read_text(encoding="utf-8"))
        self.assertEqual(evidence["attempt_count"], 5)
        self.assertEqual(len(evidence["event_receipts"]), 2)

    def test_run_33206968416_five_file_compose_lands(self):
        tmp = tempfile.mkdtemp()
        stages = {}
        unmerged = list(GRKREV_PATHS) + [EVIDENCE_PATH, SLACK_E2E_PATH]
        for path in GRKREV_PATHS:
            ident = Path(path).stem
            body = _dump(_job(job_id=ident, updated_at="2026-08-28T20:40:47Z", receipts=[]))
            stages[path] = (body, body)
        ours = _dump(_job(
            job_id="grok-community-evidence-portable-20260828",
            updated_at="2026-08-28T16:51:35Z",
            attempt_count=4,
            receipts=[{"attempt_id": "a04", "event": "wake", "ts": "2026-08-28T16:51:35Z"}],
        ))
        theirs = _dump(_job(
            job_id="grok-community-evidence-portable-20260828",
            updated_at="2026-08-28T21:22:29Z",
            attempt_count=5,
            receipts=[
                {"attempt_id": "a04", "event": "wake", "ts": "2026-08-28T16:51:35Z"},
                {"attempt_id": "a05", "event": "wake", "ts": "2026-08-28T21:22:29Z"},
            ],
        ))
        stages[EVIDENCE_PATH] = (ours, theirs)
        slack_ours = _dump(_job(
            job_id="grok-slack-e2e-proof-20260828-05",
            updated_at="2026-08-28T19:25:34Z",
            attempt_count=0,
            receipts=[],
        ))
        slack_theirs = _dump(_job(
            job_id="grok-slack-e2e-proof-20260828-05",
            updated_at="2026-08-28T22:22:22Z",
            attempt_count=1,
            receipts=[{"attempt_id": "grok-slack-e2e-proof-20260828-05-a01", "event": "wake", "ts": "2026-08-28T22:22:22Z"}],
        ))
        stages[SLACK_E2E_PATH] = (slack_ours, slack_theirs)
        git = FakeGit(
            push_results=[(1, RUN_33186268839_STDERR), (0, "")],
            rebase_code=1,
            continue_code=0,
            unmerged=unmerged,
            stages=stages,
            rebase_stderr=RUN_33206968416_REBASE,
        )
        result = land(cwd=tmp, run=git, sleep=git.sleep)
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "LANDED")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["resolve"]["state"], "COMPOSED")
        self.assertEqual(git.added_paths, unmerged)
        self.assertIn(["git", "rebase", "--continue"], git.calls)
        self.assertNotIn(["git", "rebase", "--abort"], git.calls)
        joined = " ".join(" ".join(cmd) for cmd in git.calls)
        self.assertNotIn("--force", joined)
        slack = json.loads((Path(tmp) / SLACK_E2E_PATH).read_text(encoding="utf-8"))
        self.assertEqual(slack["attempt_count"], 1)
        self.assertEqual(len(slack["event_receipts"]), 1)
        self.assertIn("CONFLICT (content): Merge conflict in " + SLACK_E2E_PATH, RUN_33206968416_REBASE)

    def test_run_33211112146_eight_file_content_compose_lands(self):
        tmp = tempfile.mkdtemp()
        stages = {}
        unmerged = list(RUN_33211112146_CONTENT_PATHS)
        for path in unmerged:
            ident = Path(path).stem
            ours = _dump(_job(
                job_id=ident,
                updated_at="2026-08-28T21:03:45Z",
                attempt_count=0,
                receipts=[],
            ))
            theirs = _dump(_job(
                job_id=ident,
                updated_at="2026-08-28T22:28:44Z",
                attempt_count=1,
                receipts=[{
                    "attempt_id": ident + "-a01",
                    "event": "wake",
                    "ts": "2026-08-28T22:28:44Z",
                }],
            ))
            stages[path] = (ours, theirs)
        git = FakeGit(
            push_results=[(1, RUN_33186268839_STDERR), (0, "")],
            rebase_code=1,
            continue_code=0,
            unmerged=unmerged,
            stages=stages,
            rebase_stderr=RUN_33211112146_REBASE,
        )
        result = land(cwd=tmp, run=git, sleep=git.sleep)
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "LANDED")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["resolve"]["state"], "COMPOSED")
        self.assertEqual(git.added_paths, unmerged)
        self.assertIn(["git", "rebase", "--continue"], git.calls)
        self.assertNotIn(["git", "rebase", "--abort"], git.calls)
        joined = " ".join(" ".join(cmd) for cmd in git.calls)
        self.assertNotIn("--force", joined)
        for path in unmerged:
            self.assertIn("CONFLICT (content): Merge conflict in " + path, RUN_33211112146_REBASE)
            body = json.loads((Path(tmp) / path).read_text(encoding="utf-8"))
            self.assertEqual(body["attempt_count"], 1)
            self.assertEqual(len(body["event_receipts"]), 1)
        self.assertNotIn("CONFLICT (add/add)", RUN_33211112146_REBASE)

    def test_stale_preconcurrency_push_is_selected(self):
        self_id = "33220000000"
        stale = {
            "databaseId": 33211112146,
            "event": "push",
            "status": "in_progress",
            "headSha": "57d934d10fcfe7b63df057b5af4098df6c1f8ed0",
        }
        selected = select_stale_runs(
            [
                stale,
                {"databaseId": int(self_id), "event": "push", "status": "in_progress"},
                {"databaseId": 1, "event": "pull_request", "status": "queued"},
                {"databaseId": 2, "event": "push", "status": "completed"},
            ],
            self_id=self_id,
        )
        self.assertEqual([row["databaseId"] for row in selected], [33211112146])

    def test_cancel_stale_cancels_sibling_and_keeps_self(self):
        calls: list[list[str]] = []

        def fake_gh(args, **_kwargs):
            cmd = list(args)
            calls.append(cmd)
            if len(cmd) > 2 and cmd[2] == "list":
                payload = [
                    {
                        "databaseId": 33211112146,
                        "event": "push",
                        "status": "in_progress",
                        "headSha": "57d934d10fcfe7b63df057b5af4098df6c1f8ed0",
                    },
                    {
                        "databaseId": 33220000000,
                        "event": "push",
                        "status": "in_progress",
                        "headSha": "deadbeef",
                    },
                ]
                return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        result = cancel_stale(
            self_id="33220000000",
            run=fake_gh,
            env={"GH_TOKEN": "test-token", "GITHUB_RUN_ID": "33220000000"},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "CANCELLED")
        self.assertEqual(result["cancelled"], ["33211112146"])
        self.assertEqual(result["self_id"], "33220000000")
        self.assertEqual(calls[-1], ["gh", "run", "cancel", "33211112146"])
        joined = " ".join(" ".join(cmd) for cmd in calls)
        self.assertNotIn("--force", joined)

    def test_cancel_stale_fail_open_without_token(self):
        result = cancel_stale(self_id="1", run=lambda *_a, **_k: None, env={})
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "NO_TOKEN")
        self.assertEqual(result["cancelled"], [])

    def test_semantic_split_still_aborts(self):
        tmp = tempfile.mkdtemp()
        path = "wake_jobs/clash.json"
        git = FakeGit(
            push_results=[(1, RUN_33186268839_STDERR)],
            rebase_code=1,
            unmerged=[path],
            stages={
                path: (
                    _dump(_job(job_id="alpha", updated_at="2026-08-28T20:00:00Z", receipts=[])),
                    _dump(_job(job_id="beta", updated_at="2026-08-28T21:00:00Z", receipts=[])),
                )
            },
            rebase_stderr="CONFLICT (content): Merge conflict in wake_jobs/clash.json",
        )
        result = land(cwd=tmp, run=git, sleep=git.sleep)
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "REBASE_CONFLICT")
        self.assertEqual(result["resolve"]["reason"], "SEMANTIC_DISAGREE")
        self.assertEqual(git.calls[-1], ["git", "rebase", "--abort"])

    def test_this_module_does_not_trip_open_door_guard(self):
        import open_door_guard

        hits = []
        for i, line in enumerate(Path(__file__).read_text(encoding="utf-8").splitlines(), 1):
            if open_door_guard._negative_assertion(line):
                continue
            if open_door_guard._directive_or_prohibition(line):
                continue
            for rule in open_door_guard.LINE_RULES:
                if rule.pattern.search(line):
                    hits.append("%s:%s:%s" % (i, rule.name, line.strip()))
        self.assertEqual(hits, [])


def _git(cwd: str | Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GIT_AUTHOR_NAME": "watchdog-test", "GIT_AUTHOR_EMAIL": "w@t",
             "GIT_COMMITTER_NAME": "watchdog-test", "GIT_COMMITTER_EMAIL": "w@t"},
    )
    if check and result.returncode != 0:
        raise AssertionError("%s\n%s\n%s" % (args, result.stdout, result.stderr))
    return result


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "watchdog-test")
    _git(path, "config", "user.email", "w@t")
    _git(path, "config", "commit.gpgsign", "false")
    _git(path, "config", "advice.mergeConflict", "false")


class LiveWakeJobsComposeTests(unittest.TestCase):
    def test_two_clone_add_add_and_content_land(self):
        tmp = Path(tempfile.mkdtemp())
        origin = tmp / "origin.git"
        racer = tmp / "racer"
        stale = tmp / "stale"
        _git(tmp, "init", "--bare", "--initial-branch=main", str(origin))
        _init_repo(racer)
        _git(racer, "remote", "add", "origin", str(origin))
        (racer / "wake_jobs").mkdir()
        seed = _job(
            job_id="grok-community-evidence-portable-20260828",
            updated_at="2026-08-28T11:18:04Z",
            attempt_count=3,
            receipts=[{"attempt_id": "a03", "event": "wake", "ts": "2026-08-28T11:18:04Z"}],
        )
        (racer / EVIDENCE_PATH).write_text(_dump(seed), encoding="utf-8")
        (racer / "wake_jobs" / "peer.json").write_text(
            _dump(_job(job_id="peer", updated_at="2026-08-28T10:00:00Z", receipts=[])),
            encoding="utf-8",
        )
        _git(racer, "add", "wake_jobs")
        _git(racer, "commit", "-m", "seed")
        _git(racer, "push", "-u", "origin", "main")
        _git(tmp, "clone", "-b", "main", str(origin), str(stale))
        _git(stale, "config", "user.name", "watchdog-test")
        _git(stale, "config", "user.email", "w@t")
        _git(stale, "config", "commit.gpgsign", "false")

        racer_evidence = _job(
            job_id="grok-community-evidence-portable-20260828",
            updated_at="2026-08-28T21:22:29Z",
            attempt_count=5,
            receipts=[
                {"attempt_id": "a03", "event": "wake", "ts": "2026-08-28T11:18:04Z"},
                {"attempt_id": "a05", "event": "wake", "ts": "2026-08-28T21:22:29Z"},
            ],
        )
        (racer / EVIDENCE_PATH).write_text(_dump(racer_evidence), encoding="utf-8")
        for path in GRKREV_PATHS:
            ident = Path(path).stem
            (racer / path).write_text(
                _dump(_job(job_id=ident, updated_at="2026-08-28T20:40:47Z", receipts=[])),
                encoding="utf-8",
            )
        _git(racer, "add", "wake_jobs")
        _git(racer, "commit", "-m", "racer tick")
        _git(racer, "push", "origin", "main")

        stale_evidence = _job(
            job_id="grok-community-evidence-portable-20260828",
            updated_at="2026-08-28T16:51:35Z",
            attempt_count=4,
            receipts=[
                {"attempt_id": "a03", "event": "wake", "ts": "2026-08-28T11:18:04Z"},
                {"attempt_id": "a04", "event": "wake", "ts": "2026-08-28T16:51:35Z"},
            ],
        )
        (stale / EVIDENCE_PATH).write_text(_dump(stale_evidence), encoding="utf-8")
        for path in GRKREV_PATHS:
            ident = Path(path).stem
            (stale / path).write_text(
                _dump(_job(job_id=ident, updated_at="2026-08-28T20:41:00Z", receipts=[])),
                encoding="utf-8",
            )
        result = land(cwd=str(stale), attempts=5)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["state"], "LANDED")
        self.assertGreaterEqual(result["attempts"], 2)

        verify = tmp / "verify"
        _git(tmp, "clone", str(origin), str(verify))
        landed = json.loads((verify / EVIDENCE_PATH).read_text(encoding="utf-8"))
        ids = {row["attempt_id"] for row in landed["event_receipts"]}
        self.assertEqual(ids, {"a03", "a04", "a05"})
        self.assertEqual(landed["attempt_count"], 5)
        self.assertTrue((verify / "wake_jobs" / "peer.json").is_file())
        for path in GRKREV_PATHS:
            self.assertTrue((verify / path).is_file())
        log = _git(verify, "log", "--oneline")
        self.assertNotIn("force", log.stdout.lower())


if __name__ == "__main__":
    raise SystemExit(unittest.main())
