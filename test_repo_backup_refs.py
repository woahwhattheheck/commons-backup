#!/usr/bin/env python3
"""Real-Git regressions for exact bundle ref restoration, not just HEAD."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from host import repo_backup

ROOT = Path(__file__).resolve().parent


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True,
    ).stdout.strip()


def refs(repo: Path) -> list[dict[str, str]]:
    return sorted(
        ({"ref": ref, "sha": sha} for sha, ref in
         (line.split(" ", 1) for line in git(repo, "show-ref", "--head").splitlines())),
        key=lambda row: row["ref"],
    )


class RepoBackupRefTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patch = mock.patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        })
        patch.start()
        self.addCleanup(patch.stop)
        self.source = self.make_source("source with spaces")

    def make_source(self, name: str, object_format: str = "sha1") -> Path:
        source = self.root / name
        source.mkdir()
        git(source, "init", "-b", "main", f"--object-format={object_format}")
        git(source, "config", "user.name", "backup-ref-test")
        git(source, "config", "user.email", "backup-ref-test@example.invalid")
        (source / "proof.txt").write_text("main\n", encoding="utf-8")
        git(source, "add", "proof.txt")
        git(source, "commit", "-m", "main commit")
        git(source, "tag", "lightweight")
        git(source, "tag", "-a", "annotated", "-m", "annotated tag")
        git(source, "checkout", "-b", "feature")
        (source / "proof.txt").write_text("feature\n", encoding="utf-8")
        git(source, "commit", "-am", "feature commit")
        feature = git(source, "rev-parse", "HEAD")
        git(source, "checkout", "main")
        git(source, "notes", "add", "-m", "retained note")
        git(source, "update-ref", "refs/commons/checkpoint", feature)
        git(source, "update-ref", "refs/remotes/origin/feature", feature)
        git(source, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/feature")
        git(source, "update-ref", "refs/archive/tree", git(source, "rev-parse", "HEAD^{tree}"))
        git(source, "update-ref", "refs/archive/blob", git(source, "rev-parse", "HEAD:proof.txt"))
        (source / "proof.txt").write_text("stashed work\n", encoding="utf-8")
        git(source, "stash", "push", "-m", "retained stash")
        return source

    def snapshot(self, source: Path | None = None) -> Path:
        return repo_backup.snapshot(source or self.source, self.root / "bundle output")

    def assert_round_trip(self, source: Path, *, name: str = "restored") -> None:
        manifest_path = self.snapshot(source)
        expected = refs(source)
        content = (source / "proof.txt").read_bytes()
        source_status = git(source, "status", "--porcelain")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["refs"], expected)
        for bare in (False, True):
            with self.subTest(bare=bare):
                target = self.root / f"{name} {bare}"
                receipt = repo_backup.restore(manifest_path, target, bare=bare)
                self.assertEqual(receipt["state"], "RESTORED")
                self.assertEqual(receipt["refs"], len(expected))
                self.assertEqual(refs(target), expected)
                self.assertEqual(receipt["restored_head_sha"], manifest["head_sha"])
                self.assertEqual(git(target, "rev-parse", "--is-bare-repository"), str(bare).lower())
                git(target, "fsck", "--full")
                if not bare:
                    self.assertEqual((target / "proof.txt").read_bytes(), content)
                    self.assertEqual(git(target, "status", "--porcelain"), "")
        self.assertEqual(refs(source), expected)
        self.assertEqual(git(source, "status", "--porcelain"), source_status)

    def test_all_namespaces_and_distinct_objects_round_trip(self) -> None:
        self.assert_round_trip(self.source)

    def test_non_default_branch_round_trip(self) -> None:
        git(self.source, "checkout", "feature")
        self.assert_round_trip(self.source)

    def test_detached_commit_round_trip(self) -> None:
        git(self.source, "checkout", "--detach")
        (self.source / "proof.txt").write_text("detached\n", encoding="utf-8")
        git(self.source, "commit", "-am", "detached commit")
        self.assert_round_trip(self.source)

    def test_head_only_bundle_round_trip(self) -> None:
        git(self.source, "checkout", "--detach")
        for row in refs(self.source):
            if row["ref"] != "HEAD":
                git(self.source, "update-ref", "--no-deref", "-d", row["ref"])
        self.assertEqual(len(refs(self.source)), 1)
        self.assert_round_trip(self.source)

    def test_packed_refs_round_trip(self) -> None:
        git(self.source, "pack-refs", "--all")
        self.assert_round_trip(self.source)

    def test_sha256_objects_round_trip(self) -> None:
        source = self.make_source("sha256 source", "sha256")
        self.assertEqual(len(git(source, "rev-parse", "HEAD")), 64)
        self.assert_round_trip(source)

    def test_unicode_branch_and_destination_round_trip(self) -> None:
        git(self.source, "branch", "topic/café")
        self.assert_round_trip(self.source, name="restore café")

    def test_repeat_snapshot_keeps_same_ref_inventory(self) -> None:
        manifest = self.snapshot()
        target = self.root / "first restore"
        repo_backup.restore(manifest, target)
        second = repo_backup.snapshot(target, self.root / "second bundle")
        before = json.loads(manifest.read_text(encoding="utf-8"))
        after = json.loads(second.read_text(encoding="utf-8"))
        self.assertEqual(after["refs"], before["refs"])
        repo_backup.restore(second, self.root / "second restore", bare=True)
        self.assertEqual(refs(self.root / "second restore"), before["refs"])

    def test_restore_does_not_need_original_repository(self) -> None:
        manifest = self.snapshot()
        expected = refs(self.source)
        self.source.rename(self.root / "moved source")
        for bare in (False, True):
            with self.subTest(bare=bare):
                target = self.root / f"source-independent-{bare}"
                repo_backup.restore(manifest, target, bare=bare)
                self.assertEqual(refs(target), expected)

    def test_work_tree_has_no_mirror_push_setting(self) -> None:
        manifest = self.snapshot()
        target = self.root / "work tree"
        repo_backup.restore(manifest, target)
        setting = subprocess.run(
            ["git", "config", "--get", "remote.origin.mirror"], cwd=target,
            text=True, capture_output=True,
        )
        self.assertEqual(setting.returncode, 1)
        self.assertEqual(git(target, "config", "--get-all", "remote.origin.fetch"),
                         "+refs/heads/*:refs/remotes/origin/*")
        self.assertEqual(git(target, "remote"), "origin")

    def test_existing_targets_remain_unchanged(self) -> None:
        manifest = self.snapshot()
        for bare in (False, True):
            for is_dir in (False, True):
                with self.subTest(bare=bare, is_dir=is_dir):
                    target = self.root / f"exists-{bare}-{is_dir}"
                    if is_dir:
                        target.mkdir()
                        marker = target / "keep.txt"
                    else:
                        marker = target
                    marker.write_text("untouched", encoding="utf-8")
                    with self.assertRaises(repo_backup.BackupError):
                        repo_backup.restore(manifest, target, bare=bare)
                    self.assertEqual(marker.read_text(encoding="utf-8"), "untouched")

    def test_target_created_during_restore_is_not_overwritten(self) -> None:
        manifest = self.snapshot()
        original_exists = Path.exists
        for bare in (False, True):
            with self.subTest(bare=bare):
                # Match restore() after Windows expands any short temp-path aliases.
                target = (self.root / f"concurrent-target-{bare}").resolve()
                raced = False

                def exists_with_concurrent_creator(path):
                    nonlocal raced
                    existed = original_exists(path)
                    if path == target and not existed and not raced:
                        raced = True
                        target.mkdir()
                        (target / "proof.txt").write_text("other work", encoding="utf-8")
                    return existed

                error = None
                with mock.patch.object(Path, "exists", exists_with_concurrent_creator):
                    try:
                        repo_backup.restore(manifest, target, bare=bare)
                    except repo_backup.BackupError as caught:
                        error = caught
                self.assertTrue(raced, "fixture did not intercept the target existence check")
                self.assertIsInstance(error, repo_backup.BackupError)
                self.assertEqual((target / "proof.txt").read_text(encoding="utf-8"), "other work")
                self.assertFalse((target / ".git").exists())

    def test_bad_bundle_is_rejected_before_creating_target(self) -> None:
        manifest = self.snapshot()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        with (manifest.parent / payload["bundle"]).open("ab") as handle:
            handle.write(b"changed")
        target = self.root / "not created"
        with self.assertRaisesRegex(repo_backup.BackupError, "sha256 mismatch"):
            repo_backup.restore(manifest, target)
        self.assertFalse(target.exists())

    def test_mismatched_ref_readback_never_reports_restored(self) -> None:
        manifest = self.snapshot()
        original_run = repo_backup._run
        for bare in (False, True):
            for fault in ("missing", "extra", "changed"):
                with self.subTest(bare=bare, fault=fault):
                    def run_with_ref_fault(args, cwd=None, check=True):
                        result = original_run(args, cwd=cwd, check=check)
                        if args[0] == "clone":
                            cloned = Path(args[-1])
                            if fault == "missing":
                                git(cloned, "update-ref", "-d", "refs/notes/commits")
                            elif fault == "extra":
                                git(cloned, "update-ref", "refs/extra/test", "HEAD")
                            else:
                                git(cloned, "update-ref", "refs/commons/checkpoint", "HEAD")
                        return result
                    with mock.patch.object(repo_backup, "_run", side_effect=run_with_ref_fault):
                        with self.assertRaisesRegex(repo_backup.BackupError, "ref inventory"):
                            repo_backup.restore(manifest, self.root / f"fault-{bare}-{fault}", bare=bare)

    def test_cli_preserves_all_refs(self) -> None:
        manifest = self.snapshot()
        expected = refs(self.source)
        for bare in (False, True):
            with self.subTest(bare=bare):
                target = self.root / f"cli-{bare}"
                args = [sys.executable, str(ROOT / "host" / "repo_backup.py"),
                        "restore", str(manifest), str(target)]
                if bare:
                    args.append("--bare")
                completed = subprocess.run(args, check=True, text=True, capture_output=True)
                receipt = json.loads(completed.stdout)
                self.assertEqual(receipt["state"], "RESTORED")
                self.assertEqual(receipt["refs"], len(expected))
                self.assertEqual(refs(target), expected)

    def test_drill_ref_count_matches_actual_restored_inventory(self) -> None:
        expected = refs(self.source)
        for bare in (False, True):
            with self.subTest(bare=bare):
                target = self.root / f"drill-{bare}"
                receipt = repo_backup.drill(
                    self.source, self.root / f"drill-output-{bare}", target,
                    storage="github-actions-artifact", retention_days=90, bare=bare,
                )
                self.assertEqual(receipt["state"], "DRILLED")
                self.assertEqual(receipt["ref_count"], len(refs(target)))
                self.assertEqual(refs(target), expected)
                for flag in ("github_outage_protection", "same_repo_copy", "owner_disk", "secrets_present"):
                    self.assertIs(receipt[flag], False)


if __name__ == "__main__":
    unittest.main()
