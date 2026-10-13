#!/usr/bin/env python3
"""Unreadable manifest encodings use the backup CLI's ordinary error path."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from host import repo_backup


class BackupManifestEncodingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "backup.manifest.json"
        self.tool = Path(repo_backup.__file__).resolve()

    def test_invalid_utf8_raises_backup_error_with_decode_cause(self) -> None:
        for data in (b"\xff", b'{"source": "\xe2\x82"}'):
            with self.subTest(data=data):
                self.manifest.write_bytes(data)
                with self.assertRaises(repo_backup.BackupError) as caught:
                    repo_backup.read_manifest(self.manifest)
                self.assertIsInstance(caught.exception.__cause__, UnicodeDecodeError)
                self.assertIn("manifest unreadable:", str(caught.exception))

    def test_verify_cli_reports_invalid_utf8_without_traceback(self) -> None:
        self.manifest.write_bytes(b"\xff")
        result = subprocess.run(
            [sys.executable, str(self.tool), "verify", str(self.manifest)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("BACKUP_ERROR: manifest unreadable:"))
        self.assertNotIn("Traceback", result.stderr)

    def test_restore_cli_reports_decode_error_without_creating_target(self) -> None:
        self.manifest.write_bytes(b"\xff")
        target = self.root / "restored"
        result = subprocess.run(
            [sys.executable, str(self.tool), "restore", str(self.manifest), str(target)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("BACKUP_ERROR: manifest unreadable:"))
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(target.exists())

    def test_read_manifest_preserves_valid_utf8(self) -> None:
        # This fixture tests parsing only; it is not a verified Git bundle.
        bundle = self.root / "backup.bundle"
        bundle.write_bytes(b"read-manifest fixture")
        payload = {
            "created_at": "2026-09-07T00:00:00Z",
            "head_sha": "a" * 40,
            "bundle": bundle.name,
            "bundle_sha256": "b" * 64,
            "refs": [{"ref": "HEAD", "sha": "a" * 40}],
            "source": "/cloud/caf\u00e9/\u6570\u636e",
        }
        for version, head_fields in (
            (repo_backup.LEGACY_SCHEMA_VERSION, {}),
            (repo_backup.SCHEMA_VERSION, {"head_ref": None}),
        ):
            with self.subTest(schema_version=version):
                versioned = {**payload, "schema_version": version, **head_fields}
                self.manifest.write_text(json.dumps(versioned, ensure_ascii=False), encoding="utf-8")
                actual, actual_bundle = repo_backup.read_manifest(self.manifest)
                self.assertEqual(actual, versioned)
                self.assertEqual(actual_bundle, bundle.resolve())

    def test_missing_and_malformed_json_keep_existing_error_path(self) -> None:
        with self.assertRaises(repo_backup.BackupError) as missing:
            repo_backup.read_manifest(self.manifest)
        self.assertIsInstance(missing.exception.__cause__, OSError)
        self.manifest.write_text('{"source":', encoding="utf-8")
        with self.assertRaises(repo_backup.BackupError) as malformed:
            repo_backup.read_manifest(self.manifest)
        self.assertIsInstance(malformed.exception.__cause__, json.JSONDecodeError)


if __name__ == "__main__":
    unittest.main()
