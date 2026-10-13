#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest

stub = types.ModuleType("coordination_state")
class _GitHub: pass
class _GitHubError(RuntimeError): pass
stub.GitHub = _GitHub
stub.GitHubError = _GitHubError
stub.discover_token = lambda: ""
sys.modules.setdefault("coordination_state", stub)

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("swarm_preclaim_fence", HERE / "swarm_preclaim_fence.py")
fence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fence)


def report(*, stable=None, exact=None, paths=None, comparisons=None, kind="pull",
           errors=None, census=None, stable_id="OP-1", candidate_paths=None,
           semantic_tokens=None, upstream_state="open"):
    return {
        "input": {
            "stable_id": stable_id,
            "candidate_paths": list(candidate_paths or []),
            "semantic_tokens": list(semantic_tokens or []),
        },
        "slack": {
            "stable_id_hits": stable or [],
            "exact_target_hits": exact or [],
            "path_semantic_hits": paths or [],
        },
        "owner": {
            "repo": "owner/repo", "default_branch": "main",
            "head_sha": "owner", "tree_sha": "tree",
        },
        "upstream": {
            "kind": kind, "repo": "upstream/repo", "number": 842,
            "state": upstream_state,
            "head_sha": "donor", "changed_files": [],
        },
        "owner_pr_census": census if census is not None else {
            "complete": True, "open_pr_count": 0, "hits": []
        },
        "blob_comparisons": comparisons or [],
        "errors": errors or [],
    }


class DecisionFixtures(unittest.TestCase):
    def test_red_a_exact_pr_hit_blocks_even_without_stable_id_hit(self):
        value = report(
            exact=[{"text": "TAKE SOURCE+MERGE · upstream/repo#842", "ts": "1"}],
            comparisons=[{"path": "x.py", "comparable": True, "match": False}],
        )
        out = fence.finalize(value)
        self.assertEqual(out["decision"], fence.OWNED)
        self.assertFalse(out["branch_write_allowed"])
        self.assertEqual(out["exit_code"], 20)

    def test_red_b_matching_owner_blob_is_already_absorbed(self):
        value = report(
            comparisons=[{
                "path": "x.py",
                "upstream_blob_oid": "abc",
                "owner_blob_oid": "abc",
                "upstream_status": "modified",
                "comparable": True,
                "match": True,
            }]
        )
        out = fence.finalize(value)
        self.assertEqual(out["decision"], fence.ALREADY_ABSORBED)
        self.assertFalse(out["branch_write_allowed"])
        self.assertEqual(out["exit_code"], 21)

    def test_red_c_different_owner_blob_needs_manual_diff(self):
        value = report(
            comparisons=[{
                "path": "x.py",
                "upstream_blob_oid": "abc",
                "owner_blob_oid": "def",
                "upstream_status": "modified",
                "comparable": True,
                "match": False,
            }]
        )
        out = fence.finalize(value)
        self.assertEqual(out["decision"], fence.NEEDS_MANUAL_DIFF)
        self.assertFalse(out["branch_write_allowed"])
        self.assertEqual(out["exit_code"], 22)

    def test_issue_without_custody_hit_is_safe_to_bind_after_complete_census(self):
        out = fence.finalize(report(kind="issue", stable_id="ISSUE-OP"))
        self.assertEqual(out["decision"], fence.SAFE_TO_BIND_BRANCH)
        self.assertTrue(out["branch_write_allowed"])
        self.assertEqual(out["exit_code"], 0)

    def test_closed_issue_never_becomes_safe_to_bind(self):
        out = fence.finalize(report(
            kind="issue", stable_id="ISSUE-OP", upstream_state="closed"
        ))
        self.assertEqual(out["decision"], fence.NEEDS_MANUAL_DIFF)
        self.assertFalse(out["branch_write_allowed"])
        self.assertEqual(out["exit_code"], 22)

    def test_issue_with_missing_canonical_state_fails_closed(self):
        out = fence.finalize(report(
            kind="issue", stable_id="ISSUE-OP", upstream_state=None
        ))
        self.assertEqual(out["decision"], fence.NEEDS_MANUAL_DIFF)
        self.assertFalse(out["branch_write_allowed"])

    def test_closed_pull_keeps_existing_donor_absorption_semantics(self):
        out = fence.finalize(report(
            kind="pull",
            upstream_state="closed",
            comparisons=[{
                "path": "x.py",
                "upstream_blob_oid": "abc",
                "owner_blob_oid": "abc",
                "upstream_status": "modified",
                "comparable": True,
                "match": True,
            }],
        ))
        self.assertEqual(out["decision"], fence.ALREADY_ABSORBED)
        self.assertFalse(out["branch_write_allowed"])

    def test_issue_without_any_identity_key_fails_closed(self):
        out = fence.finalize(report(
            kind="issue", stable_id=None, candidate_paths=[], semantic_tokens=[]
        ))
        self.assertEqual(out["decision"], fence.NEEDS_MANUAL_DIFF)

    def test_incomplete_owner_pr_census_fails_closed(self):
        out = fence.finalize(report(
            kind="issue",
            census={"complete": False, "open_pr_count": None, "hits": []},
        ))
        self.assertEqual(out["decision"], fence.NEEDS_MANUAL_DIFF)
        self.assertFalse(out["branch_write_allowed"])

    def test_owner_pr_exact_target_blocks_without_slack_hit(self):
        out = fence.finalize(report(
            kind="issue",
            census={
                "complete": True,
                "open_pr_count": 1,
                "hits": [{
                    "number": 77, "strength": "exact",
                    "reasons": ["exact_target"],
                }],
            },
        ))
        self.assertEqual(out["decision"], fence.OWNED)
        self.assertEqual(out["exit_code"], 20)

    def test_owner_pr_path_overlap_requires_manual_diff(self):
        out = fence.finalize(report(
            kind="issue",
            candidate_paths=["src/x.py"],
            census={
                "complete": True,
                "open_pr_count": 1,
                "hits": [{
                    "number": 77, "strength": "overlap",
                    "reasons": ["path_overlap"], "shared_paths": ["src/x.py"],
                }],
            },
        ))
        self.assertEqual(out["decision"], fence.NEEDS_MANUAL_DIFF)

    def test_mixed_take_release_text_fails_closed_as_owned(self):
        out = fence.finalize(report(
            kind="issue",
            exact=[{"text": "RELEASE old lane; TAKE SOURCE+MERGE upstream/repo#842"}],
        ))
        self.assertEqual(out["decision"], fence.OWNED)

    def test_evidence_reader_error_fails_closed(self):
        out = fence.finalize(report(kind="issue", errors=["slack: rate_limited"]))
        self.assertEqual(out["decision"], fence.NEEDS_MANUAL_DIFF)
        self.assertFalse(out["branch_write_allowed"])

    def test_release_hit_is_not_ownership(self):
        out = fence.finalize(report(
            kind="issue",
            exact=[{"text": "YIELD/RELEASE upstream/repo#842 to queue"}],
        ))
        self.assertEqual(out["decision"], fence.SAFE_TO_BIND_BRANCH)

    def test_candidate_path_missing_from_pr_fails_closed(self):
        out = fence.finalize(report(comparisons=[{
            "path": "expected.py",
            "upstream_status": "not_in_pr",
            "upstream_blob_oid": None,
            "owner_blob_oid": None,
            "comparable": False,
            "match": False,
        }]))
        self.assertEqual(out["decision"], fence.NEEDS_MANUAL_DIFF)

    def test_offline_report_exit_code_is_machine_gate(self):
        payload = report(comparisons=[{
            "path": "x.py", "comparable": True, "match": True,
            "upstream_blob_oid": "abc", "owner_blob_oid": "abc",
            "upstream_status": "modified",
        }])
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "report.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(
                fence.main(["--offline-report", str(path), "--json"]), 21
            )


class CollectorTests(unittest.TestCase):
    def test_parse_target_accepts_urls_and_shorthand(self):
        self.assertEqual(
            fence.parse_target("https://github.com/up/repo/pull/842"),
            {"repo": "up/repo", "number": 842, "kind": "pull"},
        )
        self.assertEqual(
            fence.parse_target("up/repo#842"),
            {"repo": "up/repo", "number": 842, "kind": None},
        )

    def test_collect_github_compares_owner_tree_to_pr_blob_oids(self):
        class FakeGitHub:
            def rest(self, path, params=None):
                if path == "/repos/owner/repo":
                    return {"default_branch": "main"}
                if path == "/repos/owner/repo/branches/main":
                    return {
                        "commit": {
                            "sha": "owner-head",
                            "commit": {"tree": {"sha": "owner-tree"}},
                        }
                    }
                if path == "/repos/owner/repo/git/trees/owner-tree":
                    return {
                        "truncated": False,
                        "tree": [
                            {"path": "same.py", "type": "blob", "sha": "abc"},
                            {"path": "different.py", "type": "blob", "sha": "owner-def"},
                        ],
                    }
                if path == "/repos/up/repo/pulls/842":
                    return {
                        "state": "open", "title": "x", "html_url": "u",
                        "head": {"sha": "donor-head"}, "base": {"sha": "base"},
                    }
                if path == "/repos/up/repo/pulls/842/files":
                    return [
                        {"filename": "same.py", "status": "modified", "sha": "abc"},
                        {"filename": "different.py", "status": "modified", "sha": "donor-def"},
                    ]
                raise AssertionError((path, params))

        owner, upstream, comparisons = fence.collect_github(
            FakeGitHub(),
            "owner/repo",
            {"repo": "up/repo", "number": 842, "kind": "pull"},
            [],
        )
        self.assertEqual(owner["head_sha"], "owner-head")
        self.assertEqual(upstream["head_sha"], "donor-head")
        self.assertEqual([c["match"] for c in comparisons], [True, False])
        self.assertEqual(
            fence.finalize(report(comparisons=comparisons))["decision"],
            fence.NEEDS_MANUAL_DIFF,
        )

    def test_owner_pr_census_finds_exact_target_and_path_overlap(self):
        class FakeGitHub:
            def rest(self, path, params=None):
                if path == "/repos/owner/repo/pulls":
                    return [{
                        "number": 9,
                        "title": "carrier",
                        "body": "Implements upstream/repo#842",
                        "html_url": "https://github.com/owner/repo/pull/9",
                        "head": {"sha": "head9"},
                    }]
                if path == "/repos/owner/repo/pulls/9/files":
                    return [{"filename": "src/x.py", "status": "added", "sha": "abc"}]
                raise AssertionError((path, params))

        census = fence.collect_owner_pr_census(
            FakeGitHub(),
            "owner/repo",
            {"repo": "upstream/repo", "number": 842, "kind": "issue"},
            "OP-842",
            ["src/x.py"],
            [],
            {"cross_referenced_prs": []},
        )
        self.assertTrue(census["complete"])
        self.assertEqual(census["open_pr_count"], 1)
        self.assertEqual(census["hits"][0]["strength"], "exact")
        self.assertIn("exact_target", census["hits"][0]["reasons"])
        self.assertIn("path_overlap", census["hits"][0]["reasons"])

    def test_issue_timeline_cross_reference_marks_owner_pr_exact(self):
        class FakeGitHub:
            def rest(self, path, params=None):
                if path == "/repos/owner/repo/pulls":
                    return [{
                        "number": 44, "title": "carrier", "body": "",
                        "html_url": "https://github.com/owner/repo/pull/44",
                        "head": {"sha": "head44"},
                    }]
                raise AssertionError((path, params))

        census = fence.collect_owner_pr_census(
            FakeGitHub(),
            "owner/repo",
            {"repo": "up/repo", "number": 12, "kind": "issue"},
            "OP-12",
            [],
            [],
            {
                "cross_referenced_prs": [{
                    "repo": "owner/repo", "number": 44, "state": "open"
                }]
            },
        )
        self.assertEqual(census["hits"][0]["strength"], "exact")
        self.assertIn("exact_target", census["hits"][0]["reasons"])

    def test_rename_half_absorbed_is_not_already_absorbed(self):
        class FakeGitHub:
            def rest(self, path, params=None):
                if path == "/repos/owner/repo":
                    return {"default_branch": "main"}
                if path == "/repos/owner/repo/branches/main":
                    return {
                        "commit": {
                            "sha": "owner-head",
                            "commit": {"tree": {"sha": "owner-tree"}},
                        }
                    }
                if path == "/repos/owner/repo/git/trees/owner-tree":
                    return {
                        "truncated": False,
                        "tree": [
                            {"path": "old.py", "type": "blob", "sha": "old-blob"},
                            {"path": "new.py", "type": "blob", "sha": "donor-blob"},
                        ],
                    }
                if path == "/repos/up/repo/pulls/842":
                    return {
                        "state": "open", "title": "rename", "html_url": "u",
                        "head": {"sha": "donor-head"}, "base": {"sha": "base"},
                    }
                if path == "/repos/up/repo/pulls/842/files":
                    return [{
                        "filename": "new.py", "previous_filename": "old.py",
                        "status": "renamed", "sha": "donor-blob",
                    }]
                raise AssertionError((path, params))

        _, _, comparisons = fence.collect_github(
            FakeGitHub(),
            "owner/repo",
            {"repo": "up/repo", "number": 842, "kind": "pull"},
            [],
        )
        self.assertEqual(comparisons[0]["previous_owner_blob_oid"], "old-blob")
        self.assertFalse(comparisons[0]["match"])
        self.assertEqual(
            fence.finalize(report(comparisons=comparisons))["decision"],
            fence.NEEDS_MANUAL_DIFF,
        )

    def test_rename_fully_absorbed_requires_old_path_absent(self):
        class FakeGitHub:
            def rest(self, path, params=None):
                if path == "/repos/owner/repo":
                    return {"default_branch": "main"}
                if path == "/repos/owner/repo/branches/main":
                    return {
                        "commit": {
                            "sha": "owner-head",
                            "commit": {"tree": {"sha": "owner-tree"}},
                        }
                    }
                if path == "/repos/owner/repo/git/trees/owner-tree":
                    return {
                        "truncated": False,
                        "tree": [
                            {"path": "new.py", "type": "blob", "sha": "donor-blob"},
                        ],
                    }
                if path == "/repos/up/repo/pulls/842":
                    return {
                        "state": "open", "title": "rename", "html_url": "u",
                        "head": {"sha": "donor-head"}, "base": {"sha": "base"},
                    }
                if path == "/repos/up/repo/pulls/842/files":
                    return [{
                        "filename": "new.py", "previous_filename": "old.py",
                        "status": "renamed", "sha": "donor-blob",
                    }]
                raise AssertionError((path, params))

        _, _, comparisons = fence.collect_github(
            FakeGitHub(),
            "owner/repo",
            {"repo": "up/repo", "number": 842, "kind": "pull"},
            [],
        )
        self.assertIsNone(comparisons[0]["previous_owner_blob_oid"])
        self.assertTrue(comparisons[0]["match"])
        self.assertEqual(
            fence.finalize(report(comparisons=comparisons))["decision"],
            fence.ALREADY_ABSORBED,
        )


if __name__ == "__main__":
    unittest.main()
