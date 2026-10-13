from __future__ import annotations

import datetime as dt
import unittest

from host.actions_queue_cancel import drain_stale_runs
from host.actions_queue_triage import GitHubError


REPO = "woahwhattheheck/commons"
SHA_A = "a" * 40
SHA_B = "b" * 40
NOW = dt.datetime(2026, 9, 13, 8, 0, tzinfo=dt.timezone.utc)


def queued_run(
    run_id: int,
    *,
    sha: str = SHA_A,
    branch: str = "old-branch",
    pr_number: int | None = 7,
    status: str = "queued",
    created_at: str = "2026-09-13T07:00:00Z",
):
    return {
        "id": run_id,
        "name": "tests",
        "event": "pull_request" if pr_number is not None else "push",
        "head_sha": sha,
        "head_branch": branch,
        "head_repository": {"full_name": REPO},
        "pull_requests": [] if pr_number is None else [{"number": pr_number}],
        "status": status,
        "created_at": created_at,
    }


def branch(name: str, sha: str):
    return {"name": name, "commit": {"sha": sha}}


def pull(number: int, sha: str, state: str = "open"):
    return {"number": number, "state": state, "head": {"sha": sha}}


class FakeGitHub:
    def __init__(
        self,
        runs,
        *,
        snapshots=None,
        live_sequences=None,
        cancel_status=202,
        cancel_error: Exception | None = None,
    ):
        self.runs = list(runs)
        self.snapshots = snapshots or [([], [])]
        self.snapshot_index = 0
        self.live_sequences = {
            key: list(value) for key, value in (live_sequences or {}).items()
        }
        self.get_counts: dict[int, int] = {}
        self.cancel_status = cancel_status
        self.cancel_error = cancel_error
        self.cancelled: list[int] = []

    def queued_runs(self, cap):
        return self.runs[:cap], len(self.runs)

    def paged(self, path, cap=None):
        index = min(self.snapshot_index, len(self.snapshots) - 1)
        branches, pulls = self.snapshots[index]
        if path.endswith("/branches"):
            return list(branches)
        if "/pulls?state=open" in path:
            self.snapshot_index += 1
            return list(pulls)
        raise AssertionError(path)

    def get(self, path, params=None):
        run_id = int(path.rsplit("/", 1)[-1])
        sequence = self.live_sequences.get(run_id)
        if not sequence:
            original = next(row for row in self.runs if row["id"] == run_id)
            return dict(original)
        count = self.get_counts.get(run_id, 0)
        self.get_counts[run_id] = count + 1
        return dict(sequence[min(count, len(sequence) - 1)])

    def cancel_run(self, run_id):
        if self.cancel_error is not None:
            raise self.cancel_error
        self.cancelled.append(run_id)
        return self.cancel_status


class QueueCancellationFenceTests(unittest.TestCase):
    def test_dry_run_never_posts(self):
        run = queued_run(10)
        github = FakeGitHub([run], snapshots=[([], []), ([], [])])
        receipt = drain_stale_runs(
            github, REPO, execute=False, min_age_seconds=0, now=NOW
        )
        self.assertEqual(receipt["initial_cancel_candidates"], 1)
        self.assertEqual(receipt["cancel_posts_attempted"], 0)
        self.assertEqual(receipt["cancel_accepted"], 0)
        self.assertEqual(github.cancelled, [])
        self.assertEqual(receipt["results"][0]["outcome"], "WOULD_CANCEL")

    def test_execute_cancels_only_after_live_recheck(self):
        run = queued_run(11)
        github = FakeGitHub([run], snapshots=[([], []), ([], [])])
        receipt = drain_stale_runs(
            github, REPO, execute=True, min_age_seconds=0, now=NOW
        )
        self.assertEqual(github.cancelled, [11])
        self.assertEqual(receipt["cancel_posts_attempted"], 1)
        self.assertEqual(receipt["cancel_accepted"], 1)
        self.assertEqual(receipt["results"][0]["outcome"], "CANCEL_ACCEPTED")

    def test_new_live_pr_head_reclassifies_to_keep(self):
        run = queued_run(12)
        github = FakeGitHub(
            [run],
            snapshots=[([], []), ([], [pull(7, SHA_A)])],
        )
        receipt = drain_stale_runs(
            github, REPO, execute=True, min_age_seconds=0, now=NOW
        )
        self.assertEqual(github.cancelled, [])
        self.assertEqual(receipt["results"][0]["outcome"], "KEEP_RECLASSIFIED")
        self.assertEqual(
            receipt["results"][0]["live_classification"], "LIVE_PR_HEAD_KEEP"
        )

    def test_final_inventory_recheck_preserves_reopened_pr(self):
        run = queued_run(21)
        github = FakeGitHub(
            [run],
            snapshots=[([], []), ([], []), ([], [pull(7, SHA_A)])],
        )
        receipt = drain_stale_runs(
            github, REPO, execute=True, min_age_seconds=0, now=NOW
        )
        self.assertEqual(github.cancelled, [])
        self.assertEqual(
            receipt["results"][0]["outcome"], "KEEP_RECLASSIFIED_FINAL"
        )
        self.assertEqual(
            receipt["results"][0]["final_classification"], "LIVE_PR_HEAD_KEEP"
        )

    def test_run_that_started_during_recheck_is_preserved(self):
        run = queued_run(13)
        started = {**run, "status": "in_progress"}
        github = FakeGitHub(
            [run],
            snapshots=[([], []), ([], [])],
            live_sequences={13: [run, started]},
        )
        receipt = drain_stale_runs(
            github, REPO, execute=True, min_age_seconds=0, now=NOW
        )
        self.assertEqual(github.cancelled, [])
        self.assertEqual(
            receipt["results"][0]["outcome"], "KEEP_NOT_QUEUED_FINAL"
        )

    def test_head_movement_fails_closed(self):
        run = queued_run(14)
        moved = {**run, "head_sha": SHA_B}
        github = FakeGitHub(
            [run], snapshots=[([], [])], live_sequences={14: [moved]}
        )
        receipt = drain_stale_runs(
            github, REPO, execute=True, min_age_seconds=0, now=NOW
        )
        self.assertEqual(github.cancelled, [])
        self.assertEqual(receipt["holds"], 1)
        self.assertEqual(receipt["results"][0]["outcome"], "HOLD_HEAD_MOVED")

    def test_current_branch_tip_never_enters_candidate_set(self):
        run = queued_run(15, pr_number=None, branch="main")
        github = FakeGitHub([run], snapshots=[([branch("main", SHA_A)], [])])
        receipt = drain_stale_runs(
            github, REPO, execute=True, min_age_seconds=0, now=NOW
        )
        self.assertEqual(receipt["initial_cancel_candidates"], 0)
        self.assertEqual(github.cancelled, [])

    def test_minimum_age_preserves_fresh_stale_head(self):
        run = queued_run(16, created_at="2026-09-13T07:59:45Z")
        github = FakeGitHub([run], snapshots=[([], [])])
        receipt = drain_stale_runs(
            github, REPO, execute=True, min_age_seconds=60, now=NOW
        )
        self.assertEqual(github.cancelled, [])
        self.assertEqual(receipt["results"][0]["outcome"], "KEEP_TOO_NEW")

    def test_batch_limit_bounds_posts(self):
        first = queued_run(17, pr_number=17)
        second = queued_run(18, pr_number=18)
        github = FakeGitHub(
            [first, second], snapshots=[([], []), ([], []), ([], [])]
        )
        receipt = drain_stale_runs(
            github,
            REPO,
            execute=True,
            max_cancels=1,
            min_age_seconds=0,
            now=NOW,
        )
        self.assertEqual(github.cancelled, [17])
        self.assertEqual(receipt["cancel_posts_attempted"], 1)
        self.assertEqual(receipt["cancel_accepted"], 1)
        self.assertEqual(
            [row["outcome"] for row in receipt["results"]],
            ["CANCEL_ACCEPTED", "KEEP_BATCH_LIMIT"],
        )

    def test_cancel_transport_failure_is_recorded_and_held(self):
        run = queued_run(19)
        github = FakeGitHub(
            [run],
            snapshots=[([], []), ([], [])],
            cancel_error=GitHubError("synthetic cancel failure"),
        )
        receipt = drain_stale_runs(
            github, REPO, execute=True, min_age_seconds=0, now=NOW
        )
        self.assertEqual(github.cancelled, [])
        self.assertEqual(receipt["cancel_posts_attempted"], 1)
        self.assertEqual(receipt["cancel_accepted"], 0)
        self.assertEqual(receipt["holds"], 1)
        self.assertEqual(receipt["results"][0]["outcome"], "ERROR_HOLD")
        self.assertIn("synthetic cancel failure", receipt["results"][0]["error"])

    def test_unexpected_cancel_status_fails_closed(self):
        run = queued_run(20)
        github = FakeGitHub(
            [run], snapshots=[([], []), ([], [])], cancel_status=200
        )
        receipt = drain_stale_runs(
            github, REPO, execute=True, min_age_seconds=0, now=NOW
        )
        self.assertEqual(receipt["cancel_accepted"], 0)
        self.assertEqual(receipt["holds"], 1)
        self.assertEqual(receipt["results"][0]["outcome"], "ERROR_HOLD")


if __name__ == "__main__":
    unittest.main()
