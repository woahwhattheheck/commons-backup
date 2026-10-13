#!/usr/bin/env python3
from __future__ import annotations

import http.client
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from http.server import ThreadingHTTPServer

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("warranty_rma_app", HERE / "app.py")
app = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(app)


class PublicationHardeningTest(unittest.TestCase):
    def test_positive_short_writes_are_drained_to_exact_bytes(self):
        raw = (b"warranty-export\n" * 19) + b"tail"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "export.json"
            real_write = app._os.write
            calls = []

            def short_write(fd, view):
                n = real_write(fd, view[:7])
                calls.append(n)
                return n

            with mock.patch.object(app._os, "write", short_write):
                app._publish_bytes(out, raw)
            self.assertGreater(len(calls), 1)
            self.assertEqual(out.read_bytes(), raw)

    def test_zero_write_progress_fails_without_pathname_deletion(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "export.json"
            with mock.patch.object(app._os, "unlink", side_effect=AssertionError("publication failure must never unlink")):
                with mock.patch.object(app._os, "write", lambda fd, view: 0):
                    with self.assertRaises(OSError):
                        app._publish_bytes(out, b"abc")
            self.assertTrue(out.exists())
            self.assertEqual(out.read_bytes(), b"")

    def test_foreign_path_replacement_is_preserved_on_failure(self):
        raw = b"exact-export-bytes"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "export.json"
            displaced = Path(td) / "displaced-created-inode"
            real_fsync = app._os.fsync
            fired = False

            def replace_during_fsync(fd):
                nonlocal fired
                real_fsync(fd)
                if not fired:
                    fired = True
                    os.replace(out, displaced)
                    out.write_bytes(b"FOREIGN")

            with mock.patch.object(app._os, "fsync", replace_during_fsync):
                with self.assertRaises(OSError):
                    app._publish_bytes(out, raw)
            self.assertEqual(out.read_bytes(), b"FOREIGN")
            self.assertEqual(displaced.read_bytes(), raw)

    def test_replacement_during_readback_is_detected_and_foreign_preserved(self):
        raw = b"exact-export-bytes-readback"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "export.json"
            displaced = Path(td) / "displaced-created-inode"
            real_read = app._os.read
            fired = False

            def replace_during_read(fd, size):
                nonlocal fired
                data = real_read(fd, size)
                if not fired:
                    fired = True
                    os.replace(out, displaced)
                    out.write_bytes(b"FOREIGN-DURING-READBACK")
                return data

            with mock.patch.object(app._os, "read", replace_during_read):
                with self.assertRaises(OSError):
                    app._publish_bytes(out, raw)
            self.assertEqual(out.read_bytes(), b"FOREIGN-DURING-READBACK")
            self.assertEqual(displaced.read_bytes(), raw)

    def test_hardlink_during_readback_fails_without_deleting_either_name(self):
        raw = b"exact-export-bytes-hardlink"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "export.json"
            alias = Path(td) / "hardlink-alias"
            real_read = app._os.read
            fired = False

            def link_during_read(fd, size):
                nonlocal fired
                data = real_read(fd, size)
                if not fired:
                    fired = True
                    os.link(out, alias)
                return data

            with mock.patch.object(app._os, "unlink", side_effect=AssertionError("publication failure must never unlink")):
                with mock.patch.object(app._os, "read", link_during_read):
                    with self.assertRaises(OSError):
                        app._publish_bytes(out, raw)
            self.assertEqual(out.read_bytes(), raw)
            self.assertEqual(alias.read_bytes(), raw)
            out_stat = os.stat(out)
            alias_stat = os.stat(alias)
            self.assertEqual((out_stat.st_dev, out_stat.st_ino), (alias_stat.st_dev, alias_stat.st_ino))
            self.assertEqual(out_stat.st_nlink, 2)

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "export.json"
            out.write_bytes(b"old")
            with self.assertRaises(FileExistsError):
                app._publish_bytes(out, b"new")
            self.assertEqual(out.read_bytes(), b"old")


class LoopbackHTTPHardeningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = app.Store(Path(self.tmp.name) / "desk.sqlite3")
        self.store.create_product(
            {
                "sku": "P1",
                "model": "Synthetic Product",
                "serial_required": False,
                "warranty_days": 365,
                "instructions": "Merchant reviews evidence before any decision.",
            }
        )
        handler = app.make_handler(self.store, app.OperatorAuth("operator-secret-123456"), b"<html>ok</html>")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.store.close()
        self.tmp.cleanup()

    def _raw(self, method, path, raw=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        conn.request(method, path, body=raw, headers=headers or {})
        response = conn.getresponse()
        body = response.read()
        status = response.status
        conn.close()
        return status, body

    def _intake_doc(self):
        return {
            "idempotency_key": "hardening-1",
            "sku": "P1",
            "serial": "",
            "purchase_ref": "ORDER-1",
            "purchase_date": "2026-09-01",
            "issue": "Synthetic defect report",
        }

    def test_non_loopback_host_is_rejected_before_render(self):
        status, body = self._raw("GET", "/", headers={"Host": "attacker.example"})
        self.assertEqual(status, 421)
        self.assertEqual(json.loads(body)["error"], "LOOPBACK_HOST_REQUIRED")

    def test_text_plain_json_mutation_is_rejected_without_state_change(self):
        raw = json.dumps(self._intake_doc(), separators=(",", ":")).encode()
        status, body = self._raw(
            "POST",
            "/api/customer/cases",
            raw,
            {
                "Host": f"127.0.0.1:{self.server.server_port}",
                "Content-Type": "text/plain",
                "Content-Length": str(len(raw)),
            },
        )
        self.assertEqual(status, 415)
        self.assertEqual(json.loads(body)["error"], "JSON_CONTENT_TYPE_REQUIRED")
        self.assertEqual(self.store.list_cases(), [])

    def test_loopback_application_json_mutation_remains_compatible(self):
        raw = json.dumps(self._intake_doc(), separators=(",", ":")).encode()
        status, body = self._raw(
            "POST",
            "/api/customer/cases",
            raw,
            {
                "Host": f"localhost:{self.server.server_port}",
                "Content-Type": "application/json; charset=utf-8",
                "Content-Length": str(len(raw)),
            },
        )
        self.assertEqual(status, 201)
        self.assertTrue(json.loads(body)["created"])
        self.assertEqual(len(self.store.list_cases()), 1)


if __name__ == "__main__":
    unittest.main()
