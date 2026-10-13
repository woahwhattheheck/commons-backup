import json
from pathlib import Path
import tempfile
import unittest

import actions_queue_triage as q


A = "a" * 40
B = "b" * 40
C = "c" * 40
D = "d" * 40


def branch(name, sha):
    return {"name": name, "commit": {"sha": sha}}


def pr(number, sha):
    return {"number": number, "head": {"sha": sha}}


def run(run_id, sha=A, branch_name="topic", event="push", prs=(), repo="woahwhattheheck/commons"):
    return {
        "id": run_id,
        "name": "ci",
        "event": event,
        "head_sha": sha,
        "head_branch": branch_name,
        "head_repository": {"full_name": repo},
        "pull_requests": [{"number": n} for n in prs],
        "html_url": f"https://example.invalid/runs/{run_id}",
    }


class QueueClassification(unittest.TestCase):
    def snapshot(self, branches=(), prs=(), **kw):
        return q.make_snapshot(branches, prs, **kw)

    def test_exact_open_pr_head_is_keep_even_when_branch_inventory_moved(self):
        snap = self.snapshot([branch("topic", B)], [pr(7, A)])
        got = q.classify_run(run(1, prs=(7,)), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "LIVE_PR_HEAD_KEEP")
        self.assertFalse(got["cancel_candidate"])

    def test_exact_branch_tip_is_keep(self):
        snap = self.snapshot([branch("topic", A)], [])
        got = q.classify_run(run(2), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "LIVE_BRANCH_HEAD_KEEP")

    def test_open_pr_head_moved_is_candidate(self):
        snap = self.snapshot([], [pr(7, B)])
        got = q.classify_run(run(3, prs=(7,), event="pull_request"), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "SUPERSEDED_PR_HEAD_CANDIDATE")
        self.assertTrue(got["cancel_candidate"])
        self.assertIn(B, got["reason"])

    def test_incomplete_open_pr_inventory_blocks_partial_moved_pr_proof(self):
        snap = self.snapshot([], [pr(7, B)], complete_open_prs=False)
        got = q.classify_run(run(31, prs=(7, 8), event="pull_request"), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "UNKNOWN_KEEP")
        self.assertFalse(got["cancel_candidate"])
        self.assertIn("open-PR inventory incomplete", got["reason"])

    def test_incomplete_open_pr_inventory_blocks_branch_candidate(self):
        snap = self.snapshot([branch("topic", B)], [], complete_open_prs=False)
        got = q.classify_run(run(32), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "UNKNOWN_KEEP")
        self.assertFalse(got["cancel_candidate"])

    def test_incomplete_branch_inventory_blocks_pr_candidate_for_same_repo(self):
        snap = self.snapshot([], [pr(7, B)], complete_branches=False)
        got = q.classify_run(run(33, prs=(7,), event="pull_request"), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "UNKNOWN_KEEP")
        self.assertFalse(got["cancel_candidate"])
        self.assertIn("branch inventory incomplete", got["reason"])

    def test_positive_live_proofs_survive_incomplete_other_inventory(self):
        pr_snap = self.snapshot([], [pr(7, A)], complete_branches=False, complete_open_prs=False)
        self.assertEqual(
            q.classify_run(run(34, prs=(7,)), pr_snap, q.DEFAULT_REPO)["classification"],
            "LIVE_PR_HEAD_KEEP",
        )
        branch_snap = self.snapshot([branch("topic", A)], [], complete_branches=False,
                                    complete_open_prs=False)
        self.assertEqual(
            q.classify_run(run(35), branch_snap, q.DEFAULT_REPO)["classification"],
            "LIVE_BRANCH_HEAD_KEEP",
        )

    def test_closed_pr_reference_is_candidate_only_with_complete_open_pr_inventory(self):
        complete = self.snapshot([], [])
        got = q.classify_run(run(4, prs=(7,), event="pull_request"), complete, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "CLOSED_PR_HEAD_CANDIDATE")
        incomplete = self.snapshot([], [], complete_open_prs=False)
        got = q.classify_run(run(5, prs=(7,), event="pull_request"), incomplete, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "UNKNOWN_KEEP")
        self.assertFalse(got["cancel_candidate"])

    def test_live_branch_tip_beats_historical_closed_pr_reference(self):
        snap = self.snapshot([branch("topic", A)], [])
        got = q.classify_run(run(6, prs=(7,)), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "LIVE_BRANCH_HEAD_KEEP")

    def test_same_repo_moved_branch_is_candidate(self):
        snap = self.snapshot([branch("topic", B)], [])
        got = q.classify_run(run(7), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "SUPERSEDED_BRANCH_HEAD_CANDIDATE")
        self.assertTrue(got["cancel_candidate"])

    def test_deleted_push_branch_is_candidate(self):
        snap = self.snapshot([], [])
        got = q.classify_run(run(8), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "ORPHANED_PUSH_HEAD_CANDIDATE")

    def test_deleted_dispatch_branch_is_unknown_keep(self):
        snap = self.snapshot([], [])
        got = q.classify_run(run(9, event="workflow_dispatch"), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "UNKNOWN_KEEP")

    def test_foreign_repo_branch_absence_is_not_a_base_repo_stale_proof(self):
        snap = self.snapshot([], [])
        got = q.classify_run(run(10, repo="someone/fork"), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "UNKNOWN_KEEP")

    def test_null_repo_provenance_cannot_claim_live_base_branch(self):
        snap = self.snapshot([branch("topic", A)], [])
        row = run(13)
        row["head_repository"] = None
        got = q.classify_run(row, snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "UNKNOWN_KEEP")
        self.assertFalse(got["cancel_candidate"])

    def test_missing_repo_provenance_cannot_claim_moved_base_branch(self):
        snap = self.snapshot([branch("topic", B)], [])
        row = run(14)
        del row["head_repository"]
        got = q.classify_run(row, snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "UNKNOWN_KEEP")
        self.assertFalse(got["cancel_candidate"])

    def test_null_repo_provenance_cannot_claim_orphaned_base_push(self):
        snap = self.snapshot([], [])
        row = run(15)
        row["head_repository"] = None
        got = q.classify_run(row, snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "UNKNOWN_KEEP")
        self.assertFalse(got["cancel_candidate"])

    def test_missing_repo_provenance_does_not_block_pr_head_evidence(self):
        snap = self.snapshot([], [pr(7, B)])
        row = run(16, prs=(7,), event="pull_request")
        del row["head_repository"]
        got = q.classify_run(row, snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "SUPERSEDED_PR_HEAD_CANDIDATE")
        self.assertTrue(got["cancel_candidate"])

    def test_incomplete_branch_inventory_fails_closed(self):
        snap = self.snapshot([branch("other", B)], [], complete_branches=False)
        got = q.classify_run(run(11), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "UNKNOWN_KEEP")

    def test_invalid_sha_fails_closed(self):
        snap = self.snapshot([], [])
        got = q.classify_run(run(12, sha="nope"), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "UNKNOWN_KEEP")

    def test_report_is_deterministic_except_timestamp_and_exposes_safety_contract(self):
        snap = self.snapshot([branch("topic", B), branch("live", C)], [pr(4, D)])
        rows = [run(30, sha=A), run(20, sha=C, branch_name="live")]
        report = q.build_report(q.DEFAULT_REPO, rows, 2, snap, cap=1000)
        self.assertTrue(report["queued_inventory_complete"])
        self.assertEqual(report["cancel_candidates"], 1)
        self.assertFalse(report["safety"]["mutates_github"])
        self.assertFalse(report["safety"]["cancels_runs"])
        self.assertEqual(
            [row["run_id"] for row in report["runs"]],
            [20, 30],
        )


class ClientAndPublication(unittest.TestCase):
    def test_queued_runs_honors_cap_and_total(self):
        calls = []
        def transport(path):
            calls.append(path)
            self.assertIn("status=queued", path)
            return {"total_count": 140, "workflow_runs": [{"id": i} for i in range(100)]}
        gh = q.GitHub(q.DEFAULT_REPO, transport=transport)
        rows, total = gh.queued_runs(cap=60)
        self.assertEqual(len(rows), 60)
        self.assertEqual(total, 140)
        self.assertEqual(len(calls), 1)

    def test_existing_query_uses_ampersand_for_pagination(self):
        calls = []
        def transport(path):
            calls.append(path)
            return []
        gh = q.GitHub(q.DEFAULT_REPO, transport=transport)
        self.assertEqual(gh.paged(f"/repos/{q.DEFAULT_REPO}/pulls?state=open"), [])
        self.assertEqual(
            calls,
            [f"/repos/{q.DEFAULT_REPO}/pulls?state=open&per_page=100&page=1"],
        )

    def test_unknown_queued_total_is_not_claimed_complete(self):
        snap = q.make_snapshot([], [])
        report = q.build_report(q.DEFAULT_REPO, [], None, snap, cap=1000)
        self.assertFalse(report["queued_inventory_complete"])

    def test_uppercase_sha_matches_lowercase_live_inventory(self):
        snap = q.make_snapshot([branch("topic", A)], [])
        got = q.classify_run(run(99, sha=A.upper()), snap, q.DEFAULT_REPO)
        self.assertEqual(got["classification"], "LIVE_BRANCH_HEAD_KEEP")

    def test_output_is_create_exclusive(self):
        report = {"schema": q.SCHEMA, "runs": []}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "triage.json"
            q._write_report(report, path)
            self.assertEqual(json.loads(path.read_text())["schema"], q.SCHEMA)
            with self.assertRaises(FileExistsError):
                q._write_report(report, path)


if __name__ == "__main__":
    unittest.main()
