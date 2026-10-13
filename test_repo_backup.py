#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import open_door_guard as guard
from host import repo_backup

ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "open-repo-backup.yml"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def show_ref_head(repo: Path) -> list[dict[str, str]]:
    rows = []
    for line in git(repo, "show-ref", "--head").splitlines():
        sha, separator, ref = line.partition(" ")
        if separator:
            rows.append({"ref": ref.strip(), "sha": sha})
    return sorted(rows, key=lambda row: row["ref"])


class RepoBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        git(self.source, "init", "-b", "main")
        git(self.source, "config", "user.email", "backup-test@example.invalid")
        git(self.source, "config", "user.name", "backup-test")
        (self.source / "proof.txt").write_text("open door\n", encoding="utf-8")
        git(self.source, "add", "proof.txt")
        git(self.source, "commit", "-m", "proof")
        git(self.source, "tag", "proof-v1")
        self.output = self.root / "backup"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_snapshot_verify_restore_round_trip(self) -> None:
        manifest_path = repo_backup.snapshot(self.source, self.output)
        verified = repo_backup.verify(manifest_path)
        self.assertEqual(verified["state"], "VERIFIED")
        self.assertGreaterEqual(verified["refs"], 3)

        target = self.root / "restored"
        restored = repo_backup.restore(manifest_path, target)
        self.assertEqual(restored["state"], "RESTORED")
        self.assertEqual(restored["restored_head_sha"], git(self.source, "rev-parse", "HEAD"))
        self.assertEqual(
            (target / "proof.txt").read_text(encoding="utf-8"),
            "open door\n",
        )

    def test_inventory_includes_head_and_matches_source_show_ref(self) -> None:
        manifest_path = repo_backup.snapshot(self.source, self.output)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = show_ref_head(self.source)
        self.assertEqual(manifest["refs"], expected)
        self.assertTrue(any(row["ref"] == "HEAD" for row in manifest["refs"]))
        self.assertEqual(manifest["head_sha"], git(self.source, "rev-parse", "HEAD"))

    def test_manifest_and_bundle_are_exact_and_tamper_evident(self) -> None:
        manifest_path = repo_backup.snapshot(self.source, self.output)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], repo_backup.SCHEMA_VERSION)
        bundle = manifest_path.parent / manifest["bundle"]
        with bundle.open("ab") as handle:
            handle.write(b"tamper")
        with self.assertRaises(repo_backup.BackupError):
            repo_backup.verify(manifest_path)

    def test_restore_refuses_existing_target(self) -> None:
        manifest_path = repo_backup.snapshot(self.source, self.output)
        target = self.root / "exists"
        target.mkdir()
        with self.assertRaises(repo_backup.BackupError):
            repo_backup.restore(manifest_path, target)

    def test_cli_snapshot_verify_restore(self) -> None:
        tool = ROOT / "host" / "repo_backup.py"
        snap = subprocess.run(
            [
                sys.executable,
                str(tool),
                "snapshot",
                "--source",
                str(self.source),
                "--output-dir",
                str(self.output),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        payload = json.loads(snap.stdout)
        self.assertEqual(payload["state"], "SNAPSHOT")
        manifest = Path(payload["manifest"])
        verify = subprocess.run(
            [sys.executable, str(tool), "verify", str(manifest)],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(json.loads(verify.stdout)["state"], "VERIFIED")
        target = self.root / "cli-restored"
        restore = subprocess.run(
            [sys.executable, str(tool), "restore", str(manifest), str(target)],
            check=True,
            text=True,
            capture_output=True,
        )
        restored = json.loads(restore.stdout)
        self.assertEqual(restored["state"], "RESTORED")
        self.assertEqual(restored["restored_head_sha"], git(self.source, "rev-parse", "HEAD"))

    def test_drill_round_trip_and_forced_receipt_flags(self) -> None:
        restore_dir = self.root / "drill-restored"
        env = {
            "run_id": "24862801",
            "run_attempt": "1",
            "repository": "woahwhattheheck/commons",
            "ref": "refs/heads/main",
            "sha": git(self.source, "rev-parse", "HEAD"),
        }
        result = repo_backup.drill(
            self.source,
            self.output,
            restore_dir,
            storage="github-actions-artifact",
            retention_days=90,
            artifact_name="commons-open-repo-backup",
            bare=True,
            run=env,
        )
        self.assertEqual(result["state"], "DRILLED")
        self.assertEqual(result["restored_head_sha"], git(self.source, "rev-parse", "HEAD"))
        self.assertTrue(result["bare"])
        receipt_path = Path(result["receipt"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(set(receipt), repo_backup.DRILL_FIELDS)
        self.assertEqual(receipt["schema_version"], repo_backup.DRILL_SCHEMA_VERSION)
        self.assertEqual(receipt["storage"], "github-actions-artifact")
        self.assertEqual(receipt["retention_days"], 90)
        self.assertEqual(receipt["artifact_name"], "commons-open-repo-backup")
        self.assertIs(receipt["github_outage_protection"], False)
        self.assertIs(receipt["same_repo_copy"], False)
        self.assertIs(receipt["owner_disk"], False)
        self.assertIs(receipt["secrets_present"], False)
        self.assertIs(receipt["independent_of_git_objects"], True)
        self.assertIs(receipt["independent_of_owner_disk"], True)
        self.assertIs(receipt["github_hosted"], True)
        self.assertEqual(receipt["run_id"], "24862801")
        self.assertEqual(receipt["sha"], env["sha"])
        with self.assertRaises(repo_backup.BackupError):
            repo_backup.drill(
                self.source,
                self.output,
                self.root / "drill-restored-2",
                storage="github-actions-artifact",
                retention_days=90,
                artifact_name="commons-open-repo-backup",
                bare=True,
                run=env,
            )

    def test_make_drill_receipt_rejects_unmeasured_storage_and_forces_false_flags(self) -> None:
        manifest_path = repo_backup.snapshot(self.source, self.output)
        restored = repo_backup.restore(manifest_path, self.root / "for-receipt", bare=True)
        restored["github_outage_protection"] = True
        restored["same_repo_copy"] = True
        restored["owner_disk"] = True
        restored["secrets_present"] = True
        with self.assertRaises(repo_backup.BackupError):
            repo_backup.make_drill_receipt(
                storage="s3",
                retention_days=90,
                artifact_name="commons-open-repo-backup",
                restore_receipt=restored,
            )
        with self.assertRaises(repo_backup.BackupError):
            repo_backup.make_drill_receipt(
                storage="google-drive",
                retention_days=90,
                artifact_name="commons-open-repo-backup",
                restore_receipt=restored,
            )
        with self.assertRaises(repo_backup.BackupError):
            repo_backup.make_drill_receipt(
                storage="github-actions-artifact",
                retention_days=30,
                artifact_name="commons-open-repo-backup",
                restore_receipt=restored,
            )
        receipt = repo_backup.make_drill_receipt(
            storage="github-actions-artifact",
            retention_days=90,
            artifact_name="commons-open-repo-backup",
            restore_receipt=restored,
            run={"run_id": "x", "run_attempt": "1", "repository": "woahwhattheheck/commons", "ref": "refs/heads/main", "sha": restored["head_sha"]},
        )
        self.assertIs(receipt["github_outage_protection"], False)
        self.assertIs(receipt["same_repo_copy"], False)
        self.assertIs(receipt["owner_disk"], False)
        self.assertIs(receipt["secrets_present"], False)
        self.assertEqual(receipt["storage"], "github-actions-artifact")
        self.assertEqual(receipt["retention_days"], 90)

    def test_cli_drill(self) -> None:
        tool = ROOT / "host" / "repo_backup.py"
        env = os.environ.copy()
        env["GITHUB_RUN_ID"] = "cli-run"
        env["GITHUB_RUN_ATTEMPT"] = "1"
        env["GITHUB_REPOSITORY"] = "woahwhattheheck/commons"
        env["GITHUB_REF"] = "refs/heads/main"
        env["GITHUB_SHA"] = git(self.source, "rev-parse", "HEAD")
        completed = subprocess.run(
            [
                sys.executable,
                str(tool),
                "drill",
                "--source",
                str(self.source),
                "--output-dir",
                str(self.output),
                "--restore-dir",
                str(self.root / "cli-drill"),
                "--bare",
                "--storage",
                "github-actions-artifact",
                "--retention-days",
                "90",
                "--artifact-name",
                "commons-open-repo-backup",
            ],
            check=True,
            text=True,
            capture_output=True,
            env=env,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["state"], "DRILLED")
        self.assertEqual(payload["run_id"], "cli-run")
        self.assertIs(payload["github_outage_protection"], False)

    def test_workflow_file_contract(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("schedule:", text)
        self.assertIn('cron: "17 5 * * *"', text)
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("contents: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("secrets.", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("host/repo_backup.py drill", text)
        self.assertIn("github-actions-artifact", text)
        self.assertIn("retention-days: 90", text)
        self.assertIn("upload-artifact", text)
        self.assertIn("commons-open-repo-backup", text)
        self.assertIn("if-no-files-found: error", text)
        self.assertIn("fetch-depth: 0", text)
        self.assertIn("timeout-minutes: 120", text)

    def test_law_names_90_day_artifact_and_not_github_outage_protection(self) -> None:
        law = (ROOT / "ground" / "BACKUP_OPEN_REPO.md").read_text(encoding="utf-8")
        readme = (ROOT / "backups" / "README.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for text in (law, readme, agents):
            self.assertIn("90-day", text)
            self.assertIn("not GitHub-outage protection", text)
            self.assertIn("Do not add GitHub auth", text)

    def test_backup_law_is_prohibition_not_a_lock(self) -> None:
        paths = (
            ROOT / "AGENTS.md",
            ROOT / "ground" / "BACKUP_OPEN_REPO.md",
            ROOT / "backups" / "README.md",
            ROOT / "host" / "repo_backup.py",
            ROOT / "test_repo_backup.py",
            WORKFLOW,
        )
        lines = [
            guard.AddedLine(path.as_posix(), line_number, text)
            for path in paths
            for line_number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        ]
        self.assertEqual(guard.scan_added(lines), [])


if __name__ == "__main__":
    unittest.main()
