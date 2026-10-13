#!/usr/bin/env python3
"""Live regression for CSV preview inside the existing waste console."""
from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BIG = "9007199254740993"
CSV = (
    "customer_id,customer_name,currency,site_id,site_name,container_id,"
    "container_label,container_type,plan_id,weekday,service_code,price_minor\n"
    "ACME,Acme Coffee Group,USD,DOWNTOWN,Downtown Cafe,DOWNTOWN-8YD,Rear 8yd,"
    f"front-load 8yd,P-DOWNTOWN-MON,Monday,RECURRENT_PICKUP,{BIG}\n"
)
BAD = CSV.replace("Monday", "Notaday")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CsvConsolePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(HERE))
        from csv_manifest import preview

        cls.expected = preview(CSV, "UTC")
        cls.db = tempfile.NamedTemporaryFile(prefix="waste-preview-", suffix=".sqlite3", delete=False)
        cls.db.close()
        cls.port = free_port()
        cls.proc = subprocess.Popen(
            [sys.executable, str(HERE / "web_console.py"), "--db", cls.db.name, "--port", str(cls.port)],
            cwd=HERE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        line = cls.proc.stdout.readline()
        if "http://" not in line:
            err = cls.proc.stderr.read()
            raise RuntimeError(f"console did not start: {line!r} {err!r}")
        cls.origin = line.split("Waste Route Desk:", 1)[-1].strip().rstrip("/")
        page = urllib.request.urlopen(cls.origin + "/", timeout=5).read().decode()
        cls.key = re.search(r'name="console-key" content="([^"]+)"', page).group(1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)
        Path(cls.db.name).unlink(missing_ok=True)

    def call(self, path, body=None, key=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            self.origin + path,
            data=data,
            method="POST" if body is not None else "GET",
        )
        if key is not None:
            req.add_header("X-Console-Key", key)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_preview_keeps_exact_manifest_text_and_does_not_initialize(self):
        status, raw = self.call("/api/csv-preview", {"csv_text": CSV, "timezone_policy": "UTC"}, self.key)
        self.assertEqual(status, 200)
        body = json.loads(raw)
        self.assertEqual(body["manifest_text"], self.expected["manifest_text"])
        self.assertIn(f'"price_minor": {BIG}', body["manifest_text"])
        self.assertEqual(body["counts"], {"customers": 1, "sites": 1, "containers": 1, "plans": 1})
        state = json.loads(self.call("/api/state", key=self.key)[1])
        self.assertFalse(state["initialized"])
        self.assertEqual(state["counts"]["plans"], 0)

    def test_rejected_preview_reports_the_line_and_leaves_the_database_empty(self):
        status, raw = self.call("/api/csv-preview", {"csv_text": BAD, "timezone_policy": "UTC"}, self.key)
        self.assertEqual(status, 400)
        body = json.loads(raw)
        self.assertEqual(body["error"], "CSVIntakeError")
        self.assertIn("line 2", body["message"])
        state = json.loads(self.call("/api/state", key=self.key)[1])
        self.assertFalse(state["initialized"])

    def test_browser_keeps_a_reviewed_manifest_when_later_input_fails(self):
        script = (HERE / "web_console.js").read_text(encoding="utf-8")
        preview = script.split('on("csv-preview"', 1)[1].split('on("csv-download"', 1)[0]
        self.assertNotIn("csvManifestText = null", preview)
        self.assertLess(preview.index("await json("), preview.index('csvManifestText = result.manifest_text'))
        self.assertLess(preview.index('csv-preview-out").textContent = error.message'), preview.index("throw error"))
        self.assertLess(preview.index('csvManifestText = result.manifest_text'), preview.index('manifest").value = result.manifest_text'))
        loader = script.split('on("csv-file"', 1)[1].split('on("csv-preview"', 1)[0]
        self.assertIn('new TextDecoder("utf-8", {fatal: true})', loader)
        self.assertLess(loader.index("decode(bytes)"), loader.index('csv-text").value = text'))
        self.assertNotIn("file.text()", loader)


if __name__ == "__main__":
    unittest.main(verbosity=2)
