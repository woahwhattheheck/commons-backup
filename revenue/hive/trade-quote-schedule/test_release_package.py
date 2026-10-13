"""Exercise actual release archives and their extracted quote/HTTP workflow."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import build_release as release


class ReleasePackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        original = Path(__file__).resolve().parent
        for name in release.FILES:
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original / name, target)
        self.output = self.root / "product.zip"

    def build(self):
        return release.build_release(self.output, root=self.source)

    def test_archive_members_and_manifest_match_exact_source_bytes(self):
        result = self.build()
        self.assertEqual(result["files"], 10)
        self.assertEqual(result["sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        manifest = release.verify_archive(self.output)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(set(archive.namelist()), set(release.FILES) | {"START_HERE.txt", "MANIFEST.json"})
            for name in release.FILES:
                data = (self.source / name).read_bytes()
                self.assertEqual(archive.read(name), data)
                self.assertEqual(manifest["files"][name], {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()))
            self.assertNotIn(str(self.source), archive.read("MANIFEST.json").decode())

    def test_identical_inputs_produce_identical_archives(self):
        self.build()
        first = self.output.read_bytes()
        release.build_release(self.root / "again.zip", root=self.source)
        self.assertEqual(first, (self.root / "again.zip").read_bytes())

    def test_generated_or_customer_files_are_never_collected(self):
        for name in ("out/schedule.csv", "out/Q-PRIVATE-acceptance.json", "out/.schedule.csv.lock.sqlite3", ".env", "examples/customer-photo.jpg", "customer.sqlite3"):
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"EXCLUDE-THIS-SYNTHETIC-MARKER")
        self.build()
        with zipfile.ZipFile(self.output) as archive:
            self.assertFalse(any(b"EXCLUDE-THIS-SYNTHETIC-MARKER" in archive.read(name) for name in archive.namelist()))

    def test_missing_input_leaves_existing_destination_unchanged(self):
        self.output.write_bytes(b"previous release")
        (self.source / "trade_quote.py").unlink()
        with self.assertRaisesRegex(release.ReleaseError, "missing"):
            self.build()
        self.assertEqual(self.output.read_bytes(), b"previous release")
        self.assertEqual(list(self.root.glob(".trade-release-*.zip")), [])

    def test_linked_payload_is_not_followed(self):
        original = self.source / "examples/request.json"
        data = original.read_bytes()
        external = self.root / "private.json"
        external.write_bytes(data)
        original.unlink()
        original.symlink_to(external)
        with self.assertRaisesRegex(release.ReleaseError, "linked"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_output_cannot_replace_source_via_path_or_hardlink(self):
        source = self.source / "trade_quote.py"
        before = source.read_bytes()
        for output in (source, self.root / "alias.zip"):
            with self.subTest(output=output.name):
                if output != source:
                    os.link(source, output)
                with self.assertRaisesRegex(release.ReleaseError, "replace a release source"):
                    release.build_release(output, root=self.source)
                self.assertEqual(source.read_bytes(), before)

    def test_changed_payload_fails_verification(self):
        self.build()
        with zipfile.ZipFile(self.output) as archive:
            contents = {name: archive.read(name) for name in archive.namelist()}
        contents["trade_quote.py"] += b"\n# changed\n"
        with zipfile.ZipFile(self.output, "w") as archive:
            for name, data in contents.items():
                archive.writestr(name, data)
        with self.assertRaisesRegex(release.ReleaseError, "manifest mismatch: trade_quote.py"):
            release.verify_archive(self.output)

    def test_failed_publication_preserves_archive_and_cleans_staging(self):
        self.output.write_bytes(b"previous release")
        with mock.patch.object(release.os, "replace", side_effect=OSError("injected replace failure")):
            with self.assertRaisesRegex(OSError, "injected"):
                self.build()
        self.assertEqual(self.output.read_bytes(), b"previous release")
        self.assertEqual(list(self.root.glob(".trade-release-*.zip")), [])

    def test_invalid_archive_members_and_manifest_are_rejected(self):
        self.build()
        original = self.output.read_bytes()
        with zipfile.ZipFile(self.output, "a") as archive:
            archive.writestr("unexpected.txt", "unexpected")
        with self.assertRaisesRegex(release.ReleaseError, "file list"):
            release.verify_archive(self.output)
        self.output.write_bytes(original)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.output, "a") as archive:
                archive.writestr("README.md", "duplicate")
        with self.assertRaisesRegex(release.ReleaseError, "file list"):
            release.verify_archive(self.output)
        with zipfile.ZipFile(self.root / "invalid.zip", "w") as archive:
            for name in (*release.FILES, "START_HERE.txt"):
                archive.writestr(name, "fixture")
            archive.writestr("MANIFEST.json", "[]")
        with self.assertRaisesRegex(release.ReleaseError, "unsupported"):
            release.verify_archive(self.root / "invalid.zip")

    def test_extracted_package_runs_quote_missing_measurement_and_http_acceptance(self):
        self.build()
        extracted = self.root / "extracted"
        with zipfile.ZipFile(self.output) as archive:
            archive.extractall(extracted)
        self.assertFalse((extracted / ".git").exists())

        def command(*args):
            result = subprocess.run([sys.executable, "-B", *args], cwd=extracted, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

        complete = command("trade_quote.py", "quote", "--request", "examples/request.json", "--rules", "examples/pricing-rules.json", "--issued-on", "2026-09-08", "--out-dir", "out")
        quote = json.loads((extracted / complete["quote"]).read_text())
        self.assertEqual(quote["total"], "1118.15")
        self.assertTrue((extracted / complete["pdf"]).read_bytes().startswith(b"%PDF-1.4"))
        missing = command("trade_quote.py", "quote", "--request", "examples/request-missing.json", "--rules", "examples/pricing-rules.json", "--issued-on", "2026-09-08", "--out-dir", "missing")
        incomplete = json.loads((extracted / missing["quote"]).read_text())
        self.assertEqual(incomplete["status"], "NEEDS_MEASUREMENTS")
        self.assertIsNone(incomplete["acceptance_url"])
        self.assertNotIn("pdf", missing)
        self.assertFalse(list((extracted / "missing").glob("*.pdf")))
        verified = command("build_release.py", "--verify", str(self.output))
        self.assertEqual(verified["schema"], "commons-trade-release-v1")

        spec = importlib.util.spec_from_file_location("trade_quote_release_fixture", extracted / "trade_quote.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(module)
        schedule = extracted / "out/schedule.csv"
        server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.make_handler(module.ServeConfig(extracted / "out", schedule)))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = "http://127.0.0.1:%d/accept" % server.server_address[1]
            query = urlencode({"quote": quote["quote_id"], "token": quote["acceptance_token"]})
            with urlopen(url + "?" + query, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"Accept and schedule", response.read())
            data = urlencode({"quote": quote["quote_id"], "token": quote["acceptance_token"], "date": "2026-09-15", "start": "09:00"}).encode()
            with urlopen(Request(url, data=data), timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"Accepted", response.read())
            with schedule.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["duration_hours"], "8")
            receipt = json.loads(schedule.with_name(quote["quote_id"] + "-acceptance.json").read_text())
            self.assertEqual(receipt["schedule"], rows[0])
            self.assertEqual([receipt[k] for k in ("messages_sent", "external_calendar_writes", "payments_collected")], [0, 0, 0])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(5)


if __name__ == "__main__":
    unittest.main()
