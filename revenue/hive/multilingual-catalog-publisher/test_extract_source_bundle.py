#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real-filesystem tests for the catalog source extractor's no-overwrite contract."""
from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

import extract_source_bundle as extractor


PREFIX = Path("revenue/hive/multilingual-catalog-publisher")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        self.destination = self.root / "destination"
        self.product = self.destination / PREFIX
        self.members = {"first.txt": b"first\n", "nested/second.bin": b"\x00\xffsecond\n"}
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:xz") as archive:
            for name, data in self.members.items():
                member = tarfile.TarInfo((PREFIX / name).as_posix())
                member.size = len(data)
                member.mode = 0o640
                archive.addfile(member, io.BytesIO(data))
        payload = stream.getvalue()
        encoded = base64.b64encode(payload)
        (self.bundle / "part-00").write_bytes(encoded)
        self.manifest = {
            "schema": "hive.multilingual-catalog-source-bundle.v1",
            "parts": [{"path": "part-00", "bytes": len(encoded), "sha256": sha256(encoded)}],
            "archive_bytes": len(payload),
            "archive_sha256": sha256(payload),
            "members": [
                {"path": name, "bytes": len(data), "sha256": sha256(data)}
                for name, data in self.members.items()
            ],
        }
        self.save_manifest()

    def save_manifest(self):
        (self.bundle / "BUNDLE.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def run_extractor(self):
        argv = ["extract_source_bundle.py", "--bundle-dir", str(self.bundle),
                "--destination", str(self.destination)]
        output = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(output):
            self.assertEqual(extractor.main(), 0)
        return json.loads(output.getvalue())

    def refused(self):
        return self.assertRaisesRegex(SystemExit, "refusing to replace existing path")

    def late_arrival(self, target, create):
        """Insert a competing path after preflight, at the real write-phase mkdir."""
        target.parent.mkdir(parents=True, exist_ok=True)
        original = Path.mkdir
        fired = []

        def mkdir_then_create(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == target.parent and not fired:
                fired.append(True)
                create(target)
            return result

        return mock.patch.object(Path, "mkdir", mkdir_then_create)

    def test_roundtrip_preserves_bytes_and_modes(self):
        result = self.run_extractor()
        self.assertEqual(result, {
            "status": "extracted", "archive_sha256": self.manifest["archive_sha256"],
            "member_count": 2, "destination": str(self.product),
        })
        for name, data in self.members.items():
            target = self.product / name
            self.assertEqual(target.read_bytes(), data)
            if sys.platform != "win32":
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)

    def test_real_cli_reports_success(self):
        result = subprocess.run(
            [sys.executable, "-B", str(Path(extractor.__file__).resolve()),
             "--bundle-dir", str(self.bundle), "--destination", str(self.destination)],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["member_count"], 2)
        self.assertEqual((self.product / "nested/second.bin").read_bytes(),
                         self.members["nested/second.bin"])

    def test_existing_later_file_refuses_before_first_write(self):
        target = self.product / "nested/second.bin"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"existing work")
        with self.refused():
            self.run_extractor()
        self.assertEqual(target.read_bytes(), b"existing work")
        self.assertFalse((self.product / "first.txt").exists())

    def test_existing_directory_is_preserved(self):
        target = self.product / "nested/second.bin"
        target.mkdir(parents=True)
        with self.refused():
            self.run_extractor()
        self.assertTrue(target.is_dir())
        self.assertFalse((self.product / "first.txt").exists())

    def test_existing_dangling_link_refuses_before_first_write(self):
        target = self.product / "nested/second.bin"
        target.parent.mkdir(parents=True)
        elsewhere = self.root / "not-created.bin"
        target.symlink_to(elsewhere)
        with self.refused():
            self.run_extractor()
        self.assertTrue(target.is_symlink())
        self.assertFalse(elsewhere.exists())
        self.assertFalse((self.product / "first.txt").exists())

    def test_existing_live_link_preserves_referent(self):
        target = self.product / "first.txt"
        target.parent.mkdir(parents=True)
        elsewhere = self.root / "existing.bin"
        elsewhere.write_bytes(b"keep referent")
        target.symlink_to(elsewhere)
        with self.refused():
            self.run_extractor()
        self.assertTrue(target.is_symlink())
        self.assertEqual(elsewhere.read_bytes(), b"keep referent")

    def test_file_arriving_after_preflight_is_not_replaced(self):
        target = self.product / "first.txt"

        def create(path):
            path.write_bytes(b"concurrent work")
            path.chmod(0o600)

        with self.late_arrival(target, create), self.refused():
            self.run_extractor()
        self.assertEqual(target.read_bytes(), b"concurrent work")
        if sys.platform != "win32":
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertFalse((self.product / "nested/second.bin").exists())

    def test_directory_arriving_after_preflight_is_preserved(self):
        target = self.product / "first.txt"
        with self.late_arrival(target, lambda path: path.mkdir()), self.refused():
            self.run_extractor()
        self.assertTrue(target.is_dir())

    def test_dangling_link_arriving_after_preflight_is_preserved(self):
        target = self.product / "first.txt"
        elsewhere = self.root / "late-referent.bin"
        create = lambda path: path.symlink_to(elsewhere)
        with self.late_arrival(target, create), self.refused():
            self.run_extractor()
        self.assertTrue(target.is_symlink())
        self.assertFalse(elsewhere.exists())

    def test_later_collision_preserves_completed_and_competing_files(self):
        target = self.product / "nested/second.bin"
        create = lambda path: path.write_bytes(b"another extractor")
        with self.late_arrival(target, create), self.refused():
            self.run_extractor()
        self.assertEqual((self.product / "first.txt").read_bytes(), b"first\n")
        self.assertEqual(target.read_bytes(), b"another extractor")

    def test_invalid_part_writes_nothing(self):
        (self.bundle / "part-00").write_bytes(b"changed")
        with self.assertRaisesRegex(SystemExit, "bundle part mismatch"):
            self.run_extractor()
        self.assertFalse(self.destination.exists())

    def test_invalid_last_member_writes_nothing(self):
        self.manifest["members"][-1]["sha256"] = "0" * 64
        self.save_manifest()
        with self.assertRaisesRegex(SystemExit, "archive member mismatch"):
            self.run_extractor()
        self.assertFalse(self.destination.exists())

    def test_unrelated_existing_work_survives_success(self):
        self.product.mkdir(parents=True)
        unrelated = self.product / "merchant-notes.txt"
        unrelated.write_bytes(b"unrelated work")
        self.run_extractor()
        self.assertEqual(unrelated.read_bytes(), b"unrelated work")

    def test_second_extraction_refuses_without_changing_outputs(self):
        self.run_extractor()
        before = {name: (self.product / name).read_bytes() for name in self.members}
        with self.refused():
            self.run_extractor()
        after = {name: (self.product / name).read_bytes() for name in self.members}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
