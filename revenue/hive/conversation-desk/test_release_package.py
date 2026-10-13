"""Deterministic release-builder tests plus extracted Conversation Desk smoke."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
import zipfile

import build_release as release

HERE = Path(__file__).resolve().parent


class ReleaseBuilderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="conversation-release-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        for name in release.SOURCE_FILES:
            (self.source / name).write_bytes(("fixture: " + name + "\n").encode())

    def archive(self, data=None):
        payload = release.release_bytes(self.source) if data is None else data
        return zipfile.ZipFile(io.BytesIO(payload))

    def test_exact_allowlist_and_one_root(self):
        with self.archive() as archive:
            expected = {
                f"{release.ROOT_NAME}/{name}"
                for name in (*release.SOURCE_FILES, "START_HERE.md", "manifest.json")
            }
            self.assertEqual(set(archive.namelist()), expected)
            self.assertTrue(all(".." not in Path(name).parts for name in archive.namelist()))

    def test_private_runtime_and_restore_files_are_not_swept(self):
        for name in (
            "conversation-desk.sqlite3", "conversation-desk.sqlite3-wal",
            "customer-screenshot.png", "conversation-desk-export.json", ".env",
            "__pycache__/app.pyc", "restore_export.py", "test_restore_export.py",
            "private-backup.zip", "server.log",
        ):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"PRIVATE-NOT-A-RELEASE-INPUT")
        data = release.release_bytes(self.source)
        self.assertNotIn(b"PRIVATE-NOT-A-RELEASE-INPUT", data)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            self.assertFalse(any("restore_export" in name for name in names))

    def test_manifest_hashes_exact_payload(self):
        with self.archive() as archive:
            manifest = json.loads(archive.read(f"{release.ROOT_NAME}/manifest.json"))
            self.assertEqual(manifest["schema"], release.SCHEMA)
            self.assertEqual(len(manifest["files"]), len(release.SOURCE_FILES) + 1)
            for item in manifest["files"]:
                content = archive.read(f"{release.ROOT_NAME}/{item['path']}")
                self.assertEqual(item["bytes"], len(content))
                self.assertEqual(item["sha256"], hashlib.sha256(content).hexdigest())

    def test_reproducible_across_source_location_and_mtime(self):
        before = release.release_bytes(self.source)
        other = self.root / "other"
        other.mkdir()
        for name in reversed(release.SOURCE_FILES):
            target = other / name
            target.write_bytes((self.source / name).read_bytes())
            os.utime(target, (1234567890, 1234567890))
        self.assertEqual(before, release.release_bytes(other))

    def test_payload_change_changes_archive_and_manifest(self):
        before = release.release_bytes(self.source)
        (self.source / "desk.js").write_bytes(b"changed ui")
        after = release.release_bytes(self.source)
        self.assertNotEqual(before, after)
        with self.archive(after) as archive:
            self.assertEqual(
                archive.read(f"{release.ROOT_NAME}/desk.js"), b"changed ui"
            )

    def test_fixed_file_modes_timestamps_and_storage(self):
        with self.archive() as archive:
            for item in archive.infolist():
                self.assertEqual(item.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(item.external_attr >> 16, 0o100644)
                self.assertEqual(item.compress_type, zipfile.ZIP_STORED)

    def test_missing_source_leaves_no_output(self):
        (self.source / "app.py").unlink()
        output = self.root / "delivery.zip"
        with self.assertRaises(OSError):
            release.build_release(self.source, output)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.glob(".conversation-release-*")), [])

    def test_directory_in_place_of_source_is_rejected(self):
        path = self.source / "index.html"
        path.unlink()
        path.mkdir()
        with self.assertRaisesRegex(release.ReleaseError, "regular file"):
            release.release_bytes(self.source)

    def test_symlink_source_is_rejected(self):
        path = self.source / "README.md"
        path.unlink()
        private = self.root / "private.txt"
        private.write_text("private", encoding="utf-8")
        path.symlink_to(private)
        with self.assertRaisesRegex(release.ReleaseError, "symlink"):
            release.release_bytes(self.source)

    def test_file_and_total_size_limits(self):
        with patch.object(release, "MAX_FILE_BYTES", 8):
            with self.assertRaisesRegex(release.ReleaseError, "too large"):
                release.release_bytes(self.source)
        with patch.object(release, "MAX_TOTAL_BYTES", 1):
            with self.assertRaisesRegex(release.ReleaseError, "total size"):
                release.release_bytes(self.source)

    def test_existing_destination_is_preserved(self):
        output = self.root / "existing.zip"
        output.write_bytes(b"keep peer delivery")
        with self.assertRaisesRegex(release.ReleaseError, "already exists"):
            release.build_release(self.source, output)
        self.assertEqual(output.read_bytes(), b"keep peer delivery")

    def test_dangling_destination_symlink_is_preserved(self):
        output = self.root / "delivery.zip"
        target = self.root / "not-created"
        output.symlink_to(target)
        with self.assertRaisesRegex(release.ReleaseError, "already exists"):
            release.build_release(self.source, output)
        self.assertTrue(output.is_symlink())
        self.assertFalse(target.exists())

    def test_competing_publisher_wins_without_overwrite(self):
        output = self.root / "delivery.zip"
        real_link = os.link

        def compete(source, destination):
            Path(destination).write_bytes(b"completed peer release")
            return real_link(source, destination)

        with patch.object(release.os, "link", side_effect=compete):
            with self.assertRaises(FileExistsError):
                release.build_release(self.source, output)
        self.assertEqual(output.read_bytes(), b"completed peer release")
        self.assertEqual(list(self.root.glob(".conversation-release-*")), [])

    def test_real_builder_cli_and_repeat_error(self):
        output = self.root / "delivery.zip"
        command = [
            sys.executable, "-B", str(Path(release.__file__).resolve()),
            "--source-dir", str(self.source), "--out", str(output),
        ]
        first = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(first.returncode, 0, first.stderr)
        report = json.loads(first.stdout)
        content = output.read_bytes()
        self.assertEqual(report["sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(report["bytes"], len(content))
        second = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(second.returncode, 2)
        self.assertNotIn("Traceback", second.stderr)
        self.assertEqual(output.read_bytes(), content)


class ExtractedProductTests(unittest.TestCase):
    """Runs only when the actual allowlisted product files are beside this test."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="conversation-extracted-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        archive = self.root / "conversation-desk.zip"
        release.build_release(HERE, archive)
        with zipfile.ZipFile(archive) as packed:
            packed.extractall(self.root / "fresh extraction")
        self.product = self.root / "fresh extraction" / release.ROOT_NAME
        self.env = {
            key: value for key, value in os.environ.items()
            if key not in ("PYTHONPATH", "PYTHONHOME")
        }
        self.env["PYTHONNOUSERSITE"] = "1"

    @contextmanager
    def server(self, database):
        process = subprocess.Popen(
            [sys.executable, "-B", "app.py", "--db", str(database), "--port", "0"],
            cwd=self.product, env=self.env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )
        output = queue.Queue()
        thread = threading.Thread(target=lambda: output.put(process.stdout.readline()), daemon=True)
        thread.start()
        try:
            try:
                banner = output.get(timeout=10)
            except queue.Empty:
                self.fail("extracted Conversation Desk did not report a listening port")
            self.assertIn("Conversation Desk: http://127.0.0.1:", banner)
            url = "http://" + banner.split("http://", 1)[1].split(" ", 1)[0]
            yield url
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
            thread.join(timeout=2)

    def request(self, url, body=None, method=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.headers, response.read()

    def test_extracted_package_has_only_curated_runtime(self):
        names = {path.name for path in self.product.iterdir()}
        self.assertEqual(
            names,
            {*release.SOURCE_FILES, "START_HERE.md", "manifest.json"},
        )
        self.assertNotIn("test_app.py", names)
        self.assertNotIn("browser_smoke.py", names)
        self.assertNotIn("restore_export.py", names)

    def test_extracted_app_create_draft_export_restart_and_erase(self):
        database = self.root / "workspace.sqlite3"
        with self.server(database) as url:
            status, _, home = self.request(url + "/")
            self.assertEqual(status, 200)
            self.assertEqual(home, (self.product / "index.html").read_bytes())
            status, _, state_raw = self.request(url + "/api/state")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(state_raw)["conversations"], [])
            created = json.loads(self.request(url + "/api/conversations", {
                "title": "Fictional release smoke",
                "transcript": "Alex: Would Tuesday work?",
                "context": "Synthetic package test only.",
                "intent": "respond",
                "reply": "Tuesday works for me",
                "question": "Would 6 pm work",
            })[2])
            cid = created["id"]
            suggestions = json.loads(self.request(
                url + f"/api/conversations/{cid}/suggest",
                {"expected_revision": created["revision"]},
            )[2])
            self.assertEqual(len(suggestions["suggestions"]), 3)
            selected = suggestions["suggestions"][1]["text"]
            saved = json.loads(self.request(
                url + f"/api/conversations/{cid}",
                {"expected_revision": created["revision"], "draft": selected},
            )[2])
            self.assertEqual(saved["draft"], selected)
            self.assertEqual(saved["revision"], 2)
            exported = json.loads(self.request(url + "/api/export")[2])
            self.assertEqual(exported["format"], "conversation-desk-export-v1")
            self.assertEqual(len(exported["conversations"]), 1)
        with self.server(database) as url:
            reopened = json.loads(self.request(url + f"/api/conversations/{cid}")[2])
            self.assertEqual(reopened["draft"], selected)
            erased = json.loads(self.request(
                url + "/api/erase", {"confirmation": "ERASE"}
            )[2])
            self.assertTrue(erased["deleted"])
            self.assertEqual(json.loads(self.request(url + "/api/state")[2])["conversations"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
