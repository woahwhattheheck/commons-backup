"""Builder unit tests and real extracted-product subprocess/HTTP smoke tests."""
from __future__ import annotations

from contextlib import contextmanager
import csv
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
import urllib.error
import urllib.request
import zipfile

import build_release as app

HERE = Path(__file__).resolve().parent


class ReleaseBuilderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="reorder-release-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        for name in app.SOURCE_FILES:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("fixture: " + name + "\n").encode())

    def archive(self, data=None):
        return zipfile.ZipFile(io.BytesIO(app.release_bytes(self.source) if data is None else data))

    def test_exact_allowlist_and_one_root(self):
        with self.archive() as archive:
            expected = {f"{app.ROOT_NAME}/{name}" for name in (*app.SOURCE_FILES, "START_HERE.md", "manifest.json")}
            self.assertEqual(set(archive.namelist()), expected)
            self.assertEqual(len(archive.namelist()), len(expected))
            self.assertTrue(all(".." not in Path(name).parts for name in archive.namelist()))

    def test_databases_secrets_exports_and_caches_are_not_swept_in(self):
        for name in ("workspace.sqlite3", "workspace.sqlite3-wal", ".env", "exports/customer.csv",
                     "__pycache__/private.pyc", "examples/customer-stock.csv", "private-backup.zip"):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"NOT DISTRIBUTION INPUT")
        data = app.release_bytes(self.source)
        self.assertNotIn(b"NOT DISTRIBUTION INPUT", data)
        self.assertNotIn(b"customer-stock.csv", data)

    def test_manifest_describes_exact_payload_not_itself(self):
        with self.archive() as archive:
            manifest = json.loads(archive.read(f"{app.ROOT_NAME}/manifest.json"))
            self.assertEqual(manifest["schema"], app.SCHEMA)
            self.assertEqual(len(manifest["files"]), len(app.SOURCE_FILES) + 1)
            for item in manifest["files"]:
                content = archive.read(f"{app.ROOT_NAME}/{item['path']}")
                self.assertEqual(item["bytes"], len(content))
                self.assertEqual(item["sha256"], hashlib.sha256(content).hexdigest())

    def test_reproducible_across_mtime_and_source_location(self):
        original = app.release_bytes(self.source)
        other = self.root / "other"
        for name in reversed(app.SOURCE_FILES):
            path = other / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((self.source / name).read_bytes())
            os.utime(path, (1234567890, 1234567890))
        self.assertEqual(original, app.release_bytes(other))

    def test_payload_change_changes_archive_and_manifest(self):
        before = app.release_bytes(self.source)
        (self.source / "desk.html").write_bytes(b"changed UI")
        after = app.release_bytes(self.source)
        self.assertNotEqual(before, after)
        with self.archive(after) as archive:
            self.assertEqual(archive.read(f"{app.ROOT_NAME}/desk.html"), b"changed UI")

    def test_fixed_regular_file_modes_and_timestamps(self):
        with self.archive() as archive:
            for item in archive.infolist():
                self.assertEqual(item.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(item.external_attr >> 16, 0o100644)
                self.assertEqual(item.compress_type, zipfile.ZIP_STORED)

    def test_missing_required_source_leaves_no_output(self):
        (self.source / "desk.py").unlink()
        output = self.root / "delivery.zip"
        with self.assertRaises(OSError):
            app.build_release(self.source, output)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.glob(".reorder-release-*")), [])

    def test_directory_in_place_of_source_is_rejected(self):
        path = self.source / "desk.html"
        path.unlink()
        path.mkdir()
        with self.assertRaisesRegex(app.ReleaseError, "regular file"):
            app.release_bytes(self.source)

    def test_symlink_source_is_rejected(self):
        path = self.source / "desk.html"
        path.unlink()
        private = self.root / "private.txt"
        private.write_text("private", encoding="utf-8")
        path.symlink_to(private)
        with self.assertRaisesRegex(app.ReleaseError, "symlink"):
            app.release_bytes(self.source)

    def test_symlink_source_directory_is_rejected(self):
        examples = self.source / "examples"
        actual = self.root / "elsewhere"
        examples.rename(actual)
        examples.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(app.ReleaseError, "symlink"):
            app.release_bytes(self.source)

    def test_file_size_limit(self):
        with patch.object(app, "MAX_FILE_BYTES", 8):
            with self.assertRaisesRegex(app.ReleaseError, "too large"):
                app.release_bytes(self.source)

    def test_total_size_limit(self):
        with patch.object(app, "MAX_TOTAL_BYTES", 1):
            with self.assertRaisesRegex(app.ReleaseError, "total size"):
                app.release_bytes(self.source)

    def test_existing_destination_is_preserved(self):
        output = self.root / "existing.zip"
        output.write_bytes(b"keep this delivery")
        with self.assertRaisesRegex(app.ReleaseError, "already exists"):
            app.build_release(self.source, output)
        self.assertEqual(output.read_bytes(), b"keep this delivery")

    def test_dangling_destination_symlink_is_preserved(self):
        output = self.root / "delivery.zip"
        target = self.root / "not-created"
        output.symlink_to(target)
        with self.assertRaisesRegex(app.ReleaseError, "already exists"):
            app.build_release(self.source, output)
        self.assertTrue(output.is_symlink())
        self.assertFalse(target.exists())

    def test_competing_publisher_wins_without_overwrite(self):
        output = self.root / "delivery.zip"
        link = os.link
        def compete(source, destination):
            Path(destination).write_bytes(b"completed peer release")
            link(source, destination)
        with patch.object(app.os, "link", side_effect=compete):
            with self.assertRaises(FileExistsError):
                app.build_release(self.source, output)
        self.assertEqual(output.read_bytes(), b"completed peer release")
        self.assertEqual(list(self.root.glob(".reorder-release-*")), [])

    def test_unsupported_publication_cleans_staging(self):
        output = self.root / "delivery.zip"
        with patch.object(app.os, "link", side_effect=OSError("no hard links")):
            with self.assertRaises(OSError):
                app.build_release(self.source, output)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.glob(".reorder-release-*")), [])

    def test_real_builder_cli_and_repeat_error(self):
        output = self.root / "delivery.zip"
        command = [sys.executable, "-B", str(Path(app.__file__).resolve()),
                   "--source-dir", str(self.source), "--out", str(output)]
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
    """Requires the real allowlisted product files; missing inputs fail, not skip."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="reorder-extracted-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        archive = self.root / "release.zip"
        app.build_release(HERE, archive)
        with zipfile.ZipFile(archive) as packed:
            packed.extractall(self.root / "standalone folder")
        self.product = self.root / "standalone folder" / app.ROOT_NAME
        self.env = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")}
        self.env["PYTHONNOUSERSITE"] = "1"

    def run_cli(self, script, *args):
        result = subprocess.run([sys.executable, "-B", script, *map(str, args)], cwd=self.product,
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_extracted_core_cli_receives_and_replays(self):
        self.run_cli("reorder_assistant.py", "plan", "--stock", "examples/stock.csv",
                     "--rules", "examples/rules.csv", "--catalog", "examples/catalog.csv",
                     "--as-of", "2026-09-08", "--out", "plan.json")
        plan = json.loads((self.product / "plan.json").read_text())
        self.assertEqual(plan["summary"]["orders_sent"], 0)
        self.assertGreater(len(plan["purchase_orders"]), 0)
        self.assertTrue(all(order["status"] == "DRAFT_NOT_SENT" for order in plan["purchase_orders"]))
        self.run_cli("reorder_assistant.py", "receive", "--stock", "examples/stock.csv",
                     "--plan", "plan.json", "--receipts", "examples/receipts.csv",
                     "--out-stock", "updated.csv", "--out-log", "log.json")
        log = json.loads((self.product / "log.json").read_text())
        self.assertGreater(log["new_count"], 0)
        self.run_cli("reorder_assistant.py", "receive", "--stock", "updated.csv", "--plan", "plan.json",
                     "--receipts", "examples/receipts.csv", "--prior-log", "log.json",
                     "--out-stock", "replayed.csv", "--out-log", "replayed.json")
        self.assertEqual((self.product / "updated.csv").read_bytes(), (self.product / "replayed.csv").read_bytes())
        self.assertEqual(json.loads((self.product / "replayed.json").read_text())["new_count"], 0)

    @contextmanager
    def server(self, database):
        process = subprocess.Popen([sys.executable, "-B", "desk.py", "--db", str(database), "--port", "0"],
                                   cwd=self.product, env=self.env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        output = queue.Queue()
        thread = threading.Thread(target=lambda: output.put(process.stdout.readline()), daemon=True)
        thread.start()
        try:
            try:
                banner = output.get(timeout=10)
            except queue.Empty:
                self.fail("extracted desk did not report a listening port")
            self.assertIn("http://127.0.0.1:", banner)
            url = banner.split("http://", 1)[1].split(" | ", 1)[0].strip()
            yield "http://" + url
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
            thread.join(timeout=2)

    def request(self, url, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.read()

    def inputs(self):
        return {**{kind: (self.product / "examples" / f"{kind}.csv").read_text(encoding="utf-8")
                   for kind in ("stock", "rules", "catalog")},
                "as_of": "2026-09-08", "currency": "USD", "pipeline_includes_draft": False}

    def create(self, url):
        return json.loads(self.request(url + "/api/runs", {
            "operation_id": "package-create", "title": "Fictional standalone acceptance", "inputs": self.inputs()}))

    def test_extracted_http_receipt_persists_after_restart(self):
        database = self.root / "workspace.sqlite3"
        with self.server(database) as url:
            self.assertEqual(self.request(url + "/"), (self.product / "desk.html").read_bytes())
            created = self.create(url)
            self.assertEqual(created["plan"]["summary"]["orders_sent"], 0)
            path = "/api/runs/" + created["id"]
            change = {"operation_id": "package-receive", "expected_revision": 1,
                      "csv": (self.product / "examples/receipts.csv").read_text(encoding="utf-8")}
            received = json.loads(self.request(url + path + "/receipts", change))
            self.assertEqual(received["revision"], 2)
            self.assertEqual(json.loads(self.request(url + path + "/receipts", change)), received)
        with self.server(database) as url:
            reopened = json.loads(self.request(url + path))
            self.assertEqual(reopened, received)
            self.assertEqual(json.loads(self.request(url + path + "/history")), [1, 2])
            self.assertEqual(json.loads(self.request(url + path + "/export.json")), received)
            self.assertEqual(self.request(url + path + "/source/stock"), self.inputs()["stock"].encode())
            # Replaying after restart must preserve stock and revision exactly.
            self.assertEqual(json.loads(self.request(url + path + "/receipts", change)), received)
            first_row = next(csv.DictReader(io.StringIO(change["csv"])))
            drafted = sum(line["quantity"] for order in created["plan"]["purchase_orders"]
                          if order["supplier_id"] == first_row["supplier_id"]
                          for line in order["lines"] if line["sku"] == first_row["sku"]
                          and line["supplier_sku"] == first_row["supplier_sku"])
            remaining = drafted - int(first_row["quantity"])
            self.assertGreater(remaining, 0)
            def next_receipt(quantity):
                output = io.StringIO(newline="")
                writer = csv.DictWriter(output, fieldnames=list(first_row))
                writer.writeheader()
                writer.writerow(dict(first_row, receipt_id="package-second", quantity=str(quantity)))
                return output.getvalue()
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(url + path + "/receipts", {
                    "operation_id": "package-too-many", "expected_revision": 2,
                    "csv": next_receipt(remaining + 1)})
            with failure.exception as response:
                self.assertEqual(response.code, 400)
                self.assertIn(b"exceeds drafted quantity", response.read())
            self.assertEqual(json.loads(self.request(url + path)), received)
            completed = json.loads(self.request(url + path + "/receipts", {
                "operation_id": "package-remaining", "expected_revision": 2,
                "csv": next_receipt(remaining)}))
            self.assertEqual(completed["revision"], 3)
            self.assertEqual(completed["receipt_log"]["count"], 2)
            repeated = json.loads(self.request(url + path + "/receipts", {
                "operation_id": "package-remaining-retry", "expected_revision": 3,
                "csv": next_receipt(remaining)}))
            self.assertEqual(repeated, completed)

    def test_extracted_backup_restores_the_same_browser_workspace(self):
        database = self.root / "workspace.sqlite3"
        with self.server(database) as url:
            created = self.create(url)
            path = "/api/runs/" + created["id"]
            change = {"operation_id": "backup-receipt", "expected_revision": 1,
                      "csv": (self.product / "examples/receipts.csv").read_text(encoding="utf-8")}
            received = json.loads(self.request(url + path + "/receipts", change))
        archive, restored = self.root / "backup.zip", self.root / "restored.sqlite3"
        self.run_cli("workspace_backup.py", "snapshot", "--db", database, "--out", archive)
        self.run_cli("workspace_backup.py", "restore", "--archive", archive, "--db", restored)
        with self.server(restored) as url:
            self.assertEqual(json.loads(self.request(url + path)), received)
            self.assertEqual(json.loads(self.request(url + path + "/history")), [1, 2])
            self.assertEqual(json.loads(self.request(url + path + "/receipts", change)), received)

    def test_manifest_matches_every_extracted_distribution_file(self):
        manifest = json.loads((self.product / "manifest.json").read_text())
        for item in manifest["files"]:
            content = (self.product / item["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), item["sha256"])
        self.assertTrue((self.product / "START_HERE.md").is_file())
        self.assertFalse((self.product / "workspace.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
