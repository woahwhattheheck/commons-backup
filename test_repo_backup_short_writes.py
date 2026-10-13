#!/usr/bin/env python3
"""Exercise backup JSON writes with real short writes and offline Git bundles."""
from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from host import repo_backup


class BackupJSONWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_exact_serialization(self) -> None:
        for index, payload in enumerate(({}, {"z": [1, False, None], "a": "caf\u00e9"})):
            with self.subTest(payload=payload):
                path = self.root / f"manifest-{index}.json"
                repo_backup._write_exclusive_json(path, payload)
                # Preserve the existing native text-mode newlines from os.open.
                expected = (json.dumps(payload, indent=2, sort_keys=True) + "\n").replace("\n", os.linesep).encode("utf-8")
                self.assertEqual(path.read_bytes(), expected)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)

    def test_short_writes_complete_before_fsync(self) -> None:
        real_write, real_fsync = os.write, os.fsync
        payload = {"refs": [{"ref": "refs/heads/main", "sha": "a" * 40}], "note": "caf\u00e9"}
        expected = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        for chunk in (1, 7, 64):
            with self.subTest(chunk=chunk):
                path = self.root / f"short-{chunk}.json"
                written = bytearray()

                def short_write(fd: int, data: bytes) -> int:
                    count = real_write(fd, data[:chunk])
                    written.extend(data[:count])
                    return count

                def sync_complete_file(fd: int) -> None:
                    self.assertEqual(bytes(written), expected)
                    real_fsync(fd)

                with mock.patch.object(repo_backup.os, "write", side_effect=short_write) as write:
                    with mock.patch.object(repo_backup.os, "fsync", side_effect=sync_complete_file) as sync:
                        repo_backup._write_exclusive_json(path, payload)
                self.assertGreater(write.call_count, 1)
                sync.assert_called_once()
                self.assertEqual(path.read_bytes(), expected.replace(b"\n", os.linesep.encode("ascii")))

    def test_no_progress_raises_and_closes_without_fsync(self) -> None:
        path = self.root / "no-progress.json"
        descriptors = []

        def no_progress(fd: int, data: bytes) -> int:
            descriptors.append(fd)
            return 0

        with mock.patch.object(repo_backup.os, "write", side_effect=no_progress):
            with mock.patch.object(repo_backup.os, "fsync") as sync:
                with self.assertRaises(repo_backup.BackupError):
                    repo_backup._write_exclusive_json(path, {"state": "SNAPSHOT"})
        sync.assert_not_called()
        self.assertEqual(len(descriptors), 1)
        with self.assertRaises(OSError) as caught:
            os.fstat(descriptors[0])
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_write_error_is_backup_error_and_closes_descriptor(self) -> None:
        descriptors = []
        failure = OSError(errno.ENOSPC, "injected full disk")

        def fail_write(fd: int, data: bytes) -> int:
            descriptors.append(fd)
            raise failure

        with mock.patch.object(repo_backup.os, "write", side_effect=fail_write):
            with mock.patch.object(repo_backup.os, "fsync") as sync:
                with self.assertRaises(repo_backup.BackupError) as caught:
                    repo_backup._write_exclusive_json(self.root / "full.json", {"value": 1})
        self.assertIs(caught.exception.__cause__, failure)
        sync.assert_not_called()
        with self.assertRaises(OSError) as closed:
            os.fstat(descriptors[0])
        self.assertEqual(closed.exception.errno, errno.EBADF)

    def test_fsync_error_is_not_success(self) -> None:
        real_write = os.write
        descriptors = []
        failure = OSError(errno.EIO, "injected sync failure")

        def record_write(fd: int, data: bytes) -> int:
            descriptors.append(fd)
            return real_write(fd, data)

        with mock.patch.object(repo_backup.os, "write", side_effect=record_write):
            with mock.patch.object(repo_backup.os, "fsync", side_effect=failure):
                with self.assertRaises(repo_backup.BackupError) as caught:
                    repo_backup._write_exclusive_json(self.root / "sync.json", {"value": 1})
        self.assertIs(caught.exception.__cause__, failure)
        with self.assertRaises(OSError) as closed:
            os.fstat(descriptors[0])
        self.assertEqual(closed.exception.errno, errno.EBADF)

    def test_existing_file_is_unchanged(self) -> None:
        path = self.root / "existing.json"
        path.write_bytes(b"original bytes\n")
        with mock.patch.object(repo_backup.os, "write") as write:
            with self.assertRaises(repo_backup.BackupError):
                repo_backup._write_exclusive_json(path, {"replacement": True})
        write.assert_not_called()
        self.assertEqual(path.read_bytes(), b"original bytes\n")


class BackupShortWriteIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git(self.source, "init", "-b", "main")
        self.git(self.source, "config", "user.name", "backup-test")
        self.git(self.source, "config", "user.email", "backup-test@example.invalid")
        (self.source / "proof.txt").write_text("backup round trip\n", encoding="utf-8")
        self.git(self.source, "add", "proof.txt")
        self.git(self.source, "commit", "-m", "test fixture")
        self.git(self.source, "tag", "proof-v1")

    @staticmethod
    def git(repo: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
        ).stdout.strip()

    def test_short_written_snapshot_verifies_and_restores(self) -> None:
        real_write = os.write
        with mock.patch.object(repo_backup.os, "write", side_effect=lambda fd, data: real_write(fd, data[:7])):
            manifest = repo_backup.snapshot(self.source, self.root / "backup")
        self.assertEqual(repo_backup.verify(manifest)["state"], "VERIFIED")
        target = self.root / "restored"
        restored = repo_backup.restore(manifest, target)
        self.assertEqual(restored["restored_head_sha"], self.git(self.source, "rev-parse", "HEAD"))
        self.assertEqual((target / "proof.txt").read_text(encoding="utf-8"), "backup round trip\n")


if __name__ == "__main__":
    unittest.main()
