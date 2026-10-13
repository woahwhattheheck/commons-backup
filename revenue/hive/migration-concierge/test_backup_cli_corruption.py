# SPDX-License-Identifier: Apache-2.0
"""CLI failure reporting for corrupt synthetic recovery ZIP streams."""
from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from intake import digest
from migrate import connect
from workspace_backup import DATABASE, MANIFEST, backup_workspace

HERE = Path(__file__).resolve().parent


class BackupCliCorruption(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "synthetic.sqlite3"
        connect(self.database).close()
        self.archive = self.root / "intact.zip"
        backup_workspace(self.database, self.root / "no-assets", self.archive)
        self.original_hash = digest(self.database.read_bytes())

    def malformed_stream(self, member):
        raw = bytearray(self.archive.read_bytes())
        with zipfile.ZipFile(self.archive) as bundle:
            info = bundle.getinfo(member)
            self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)
            self.assertGreater(info.compress_size, 0)
            offset = info.header_offset
        name_bytes, extra_bytes = struct.unpack_from("<HH", raw, offset + 26)
        start = offset + 30 + name_bytes + extra_bytes
        # Local fault injection: a reserved DEFLATE block type, with ZIP directory intact.
        raw[start] = (raw[start] & 0xF8) | 7
        damaged = self.root / (member + ".damaged.zip")
        damaged.write_bytes(raw)
        return damaged

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(HERE / "workspace_backup.py"), *map(str, args)],
                              capture_output=True, text=True, check=False, timeout=10)

    def assert_json_failure(self, result):
        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        self.assertEqual(result.stderr, "")
        value = json.loads(result.stdout)
        self.assertIs(value["completed"], False)
        self.assertIsInstance(value["error"], str)
        self.assertTrue(value["error"])
        self.assertEqual(digest(self.database.read_bytes()), self.original_hash)

    def test_verify_corrupt_manifest_and_database_streams_return_json(self):
        for member in (MANIFEST, DATABASE):
            with self.subTest(member=member):
                self.assert_json_failure(self.cli("verify", self.malformed_stream(member)))

    def test_restore_corrupt_streams_does_not_reserve_destination(self):
        for member in (MANIFEST, DATABASE):
            with self.subTest(member=member):
                destination = self.root / (member + "-restored")
                result = self.cli("restore", self.malformed_stream(member), destination)
                self.assertFalse(destination.exists())
                self.assertEqual(list(self.root.glob(".migration-restore-*")), [])
                self.assert_json_failure(result)

    def test_intact_archive_still_verifies_and_restores(self):
        result = self.cli("verify", self.archive)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)["verified"])
        destination = self.root / "intact-restore"
        result = self.cli("restore", self.archive, destination)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)["restored"])
        self.assertTrue((destination / DATABASE).is_file())
        self.assertEqual(digest(self.database.read_bytes()), self.original_hash)

    def test_truncated_zip_has_same_structured_failure_contract(self):
        truncated = self.root / "truncated.zip"
        truncated.write_bytes(self.archive.read_bytes()[:-10])
        self.assert_json_failure(self.cli("verify", truncated))
        destination = self.root / "truncated-restore"
        self.assert_json_failure(self.cli("restore", truncated, destination))
        self.assertFalse(destination.exists())

    def test_existing_destination_preserved_for_corrupt_input(self):
        destination = self.root / "existing"
        destination.mkdir()
        sentinel = destination / "preserve.txt"
        sentinel.write_bytes(b"SYNTHETIC existing work")
        self.assert_json_failure(self.cli("restore", self.malformed_stream(DATABASE), destination))
        self.assertEqual(list(destination.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"SYNTHETIC existing work")


if __name__ == "__main__":
    unittest.main()
