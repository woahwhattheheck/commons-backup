#!/usr/bin/env python3
"""Real Git round trips for attached/detached backup HEAD identity."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from host import repo_backup


class RepoBackupHeadIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git(self.source, "init", "-b", "main")
        self.git(self.source, "config", "user.email", "backup-test@example.invalid")
        self.git(self.source, "config", "user.name", "backup-test")
        (self.source / "proof.txt").write_text("original\n", encoding="utf-8")
        self.git(self.source, "add", "proof.txt")
        self.git(self.source, "commit", "-m", "original")
        self.git(self.source, "tag", "proof-v1")
        self.output = self.root / "backup"

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def git(repo: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, text=True, capture_output=True
        ).stdout.strip()

    def head_text(self, repo: Path, bare: bool = False) -> str:
        return ((repo if bare else repo / ".git") / "HEAD").read_text(encoding="utf-8").strip()

    def assert_round_trip(self, manifest: Path, expected_head: str) -> None:
        source_refs = repo_backup._repo_heads(self.source)
        for bare in (False, True):
            with self.subTest(bare=bare):
                target = self.root / ("bare-restored" if bare else "work-restored")
                receipt = repo_backup.restore(manifest, target, bare=bare)
                self.assertEqual(receipt["state"], "RESTORED")
                self.assertEqual(self.head_text(target, bare), expected_head)
                self.assertEqual(repo_backup._repo_heads(target), source_refs)
                self.assertEqual(self.git(target, "rev-parse", "HEAD"), self.git(self.source, "rev-parse", "HEAD"))
                if not bare:
                    self.assertEqual((target / "proof.txt").read_bytes(), (self.source / "proof.txt").read_bytes())
                    self.assertEqual(self.git(target, "config", "remote.origin.fetch"), "+refs/heads/*:refs/remotes/origin/*")

    def test_attached_branch_with_shared_tip_is_preserved(self) -> None:
        self.git(self.source, "checkout", "-b", "feature")
        manifest = repo_backup.snapshot(self.source, self.output)
        self.assert_round_trip(manifest, "ref: refs/heads/feature")

    def test_detached_head_at_existing_branch_tip_stays_detached(self) -> None:
        self.git(self.source, "checkout", "--detach")
        expected = self.git(self.source, "rev-parse", "HEAD")
        manifest = repo_backup.snapshot(self.source, self.output)
        self.assert_round_trip(manifest, expected)

    def test_detached_head_with_unique_commit_stays_detached(self) -> None:
        self.git(self.source, "checkout", "--detach")
        (self.source / "proof.txt").write_text("detached\n", encoding="utf-8")
        self.git(self.source, "commit", "-am", "detached")
        manifest = repo_backup.snapshot(self.source, self.output)
        self.assert_round_trip(manifest, self.git(self.source, "rev-parse", "HEAD"))

    def test_new_manifest_records_attached_head_ref(self) -> None:
        self.git(self.source, "checkout", "-b", "feature/nested")
        manifest = repo_backup.snapshot(self.source, self.output)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "commons-open-repo-backup/v2")
        self.assertEqual(payload["head_ref"], "refs/heads/feature/nested")
        self.assertEqual(repo_backup.verify(manifest)["head_ref"], payload["head_ref"])

    def test_new_manifest_records_null_for_detached_head(self) -> None:
        self.git(self.source, "checkout", "--detach")
        manifest = repo_backup.snapshot(self.source, self.output)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertIn("head_ref", payload)
        self.assertIsNone(payload["head_ref"])
        self.assertIsNone(repo_backup.verify(manifest)["head_ref"])

    def test_v1_manifest_still_verifies_and_restores(self) -> None:
        manifest = repo_backup.snapshot(self.source, self.output)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["schema_version"] = "commons-open-repo-backup/v1"
        payload.pop("head_ref", None)
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        self.assertNotIn("head_ref", repo_backup.verify(manifest))
        self.assert_round_trip(manifest, "ref: refs/heads/main")

    def test_v2_manifest_requires_explicit_head_state(self) -> None:
        manifest = repo_backup.snapshot(self.source, self.output)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload.pop("head_ref", None)
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(repo_backup.BackupError):
            repo_backup.verify(manifest)

    def test_invalid_or_missing_symbolic_ref_is_reported_before_restore(self) -> None:
        manifest = repo_backup.snapshot(self.source, self.output)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        for value in (True, 42, [], "", "refs/heads/missing"):
            with self.subTest(head_ref=value):
                payload["head_ref"] = value
                manifest.write_text(json.dumps(payload), encoding="utf-8")
                target = self.root / "invalid-restore"
                with self.assertRaises(repo_backup.BackupError):
                    repo_backup.restore(manifest, target)
                self.assertFalse(target.exists())

    def test_head_ref_must_point_to_manifest_commit(self) -> None:
        self.git(self.source, "branch", "older")
        (self.source / "proof.txt").write_text("newer\n", encoding="utf-8")
        self.git(self.source, "commit", "-am", "newer")
        manifest = repo_backup.snapshot(self.source, self.output)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["head_ref"] = "refs/heads/older"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(repo_backup.BackupError):
            repo_backup.verify(manifest)

    def test_branch_change_during_snapshot_is_detected(self) -> None:
        self.git(self.source, "branch", "feature")
        original_run = repo_backup._run

        def switch_after_bundle(args: list[str], **kwargs):
            result = original_run(args, **kwargs)
            if args[:2] == ["bundle", "create"]:
                self.git(self.source, "checkout", "feature")
            return result

        with mock.patch.object(repo_backup, "_run", side_effect=switch_after_bundle):
            with self.assertRaises(repo_backup.BackupError):
                repo_backup.snapshot(self.source, self.output)
        self.assertEqual(list(self.output.glob("*.manifest.json")), [])

    def test_cli_round_trip_keeps_feature_branch(self) -> None:
        self.git(self.source, "checkout", "-b", "feature")
        tool = Path(repo_backup.__file__).resolve()
        snap = subprocess.run(
            [sys.executable, str(tool), "snapshot", "--source", str(self.source), "--output-dir", str(self.output)],
            check=True, text=True, capture_output=True,
        )
        manifest = json.loads(snap.stdout)["manifest"]
        target = self.root / "cli-restored"
        restored = subprocess.run(
            [sys.executable, str(tool), "restore", manifest, str(target)],
            check=True, text=True, capture_output=True,
        )
        self.assertEqual(json.loads(restored.stdout)["head_ref"], "refs/heads/feature")
        self.assertEqual(self.head_text(target), "ref: refs/heads/feature")

    def test_existing_target_remains_unchanged(self) -> None:
        manifest = repo_backup.snapshot(self.source, self.output)
        target = self.root / "existing"
        target.mkdir()
        sentinel = target / "keep.txt"
        sentinel.write_text("keep\n", encoding="utf-8")
        with self.assertRaises(repo_backup.BackupError):
            repo_backup.restore(manifest, target)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")


if __name__ == "__main__":
    unittest.main()
