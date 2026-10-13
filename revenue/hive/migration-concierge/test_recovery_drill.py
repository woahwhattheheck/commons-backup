# SPDX-License-Identifier: Apache-2.0
"""Synthetic drill + unchanged real desk HTTP integration; not native-browser QA."""
from __future__ import annotations

import http.client
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import desk
import recovery_drill as drill
from intake import MigrationError, digest
from migrate import apply_plan, read_state
from workspace_backup import DATABASE, restore_workspace

HERE = Path(__file__).resolve().parent


@contextmanager
def serve(database, assets):
    server = desk.server_for(database, assets, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        if thread.is_alive():
            raise RuntimeError("Test HTTP service did not stop")


def request(port, method, path, body=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        raw = None if body is None else json.dumps(body).encode()
        connection.request(method, path, raw, {"Content-Type": "application/json"} if raw is not None else {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


class RecoveryDrill(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.destination = self.root / "demo with spaces"

    def run_drill(self):
        return drill.run_drill(self.destination)

    def test_usable_drill_retains_both_source_versions_and_plans(self):
        report = self.run_drill()
        self.assertTrue(report["completed"])
        self.assertTrue(report["synthetic_only"])
        self.assertEqual(len(report["steps"]), 10)
        self.assertFalse(report["http_exercised_by_this_command"])
        self.assertFalse((self.destination / drill.INCOMPLETE).exists())
        self.assertEqual((self.destination / "source-v1/original.bin").read_bytes(), drill.INITIAL)
        self.assertEqual((self.destination / "source-v2/original.bin").read_bytes(), drill.REPLACEMENT)
        for name in ("plan-v1.json", "plan-v2.json"):
            self.assertEqual(json.loads((self.destination / name).read_bytes())["format"], "migration-concierge-plan-v1")
        recovered = read_state(self.destination / report["paths"]["database"])
        original = read_state(self.destination / "original.sqlite3")
        self.assertEqual(len(recovered), 5)
        self.assertEqual(recovered[report["attachment_id"]]["data"]["sha256"], digest(drill.INITIAL))
        self.assertEqual(original[report["attachment_id"]]["data"]["sha256"], digest(drill.REPLACEMENT))
        self.assertEqual(recovered[report["edited_task_id"]]["data"]["status"], "done")
        self.assertEqual(original[report["edited_task_id"]]["data"]["status"], "open")
        self.assertEqual(report, json.loads((self.destination / "DRILL.json").read_bytes()))

    def test_real_existing_http_records_history_attachment_edit_and_export(self):
        report = self.run_drill()
        database = self.destination / report["paths"]["database"]
        assets = self.destination / report["paths"]["assets"]
        original_before = read_state(self.destination / "original.sqlite3")
        with serve(database, assets) as port:
            status, headers, html = request(port, "GET", "/")
            self.assertEqual(status, 200)
            self.assertEqual(html, desk.PAGE.encode())
            status, _, raw = request(port, "GET", "/api/records")
            self.assertEqual(status, 200)
            records = json.loads(raw)
            self.assertEqual(len(records), 5)
            task = next(row for row in records if row["kind"] == "tasks" and row["data"]["status"] == "open")
            status, _, raw = request(port, "GET", "/api/runs")
            self.assertEqual(status, 200)
            self.assertEqual({r["operation"]: r["status"] for r in json.loads(raw)},
                             {"synthetic-import-1": "applied", "synthetic-import-2": "rolled_back"})
            status, headers, raw = request(port, "GET", "/files/" + report["attachment_id"])
            self.assertEqual(status, 200)
            self.assertEqual(raw, drill.INITIAL)
            self.assertEqual(int(headers["Content-Length"]), len(drill.INITIAL))
            self.assertIn("attachment;", headers["Content-Disposition"])
            body = {"id": task["id"], "revision": task["revision"], "fields": {"status": "in_progress"}}
            status, _, raw = request(port, "POST", "/api/edit", body)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)["revision"], task["revision"] + 1)
            self.assertEqual(request(port, "POST", "/api/edit", body)[0], 409)
            status, headers, raw = request(port, "POST", "/api/export", {})
            self.assertEqual(status, 200)
            self.assertEqual(headers["Content-Type"], "application/zip")
            with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
                exported = json.loads(bundle.read("tasks.json"))
                self.assertEqual(next(r for r in exported if r["id"] == task["id"])["data"]["status"], "in_progress")
                self.assertEqual(bundle.read("attachments/" + digest(drill.INITIAL)), drill.INITIAL)
                for name, metadata in json.loads(bundle.read("MANIFEST.json")).items():
                    content = bundle.read(name)
                    self.assertEqual(metadata, {"sha256": digest(content), "bytes": len(content)})
        self.assertEqual(read_state(self.destination / "original.sqlite3"), original_before)

    def test_http_restart_uses_same_recovered_state(self):
        report = self.run_drill()
        database = self.destination / report["paths"]["database"]
        assets = self.destination / report["paths"]["assets"]
        task = read_state(database)[report["edited_task_id"]]
        with serve(database, assets) as port:
            status, _, _ = request(port, "POST", "/api/edit", {
                "id": task["id"], "revision": task["revision"], "fields": {"title": "SYNTHETIC after restart"}})
            self.assertEqual(status, 200)
        with serve(database, assets) as port:
            status, _, raw = request(port, "GET", "/api/records")
            self.assertEqual(status, 200)
            reopened = next(r for r in json.loads(raw) if r["id"] == task["id"])
            self.assertEqual(reopened["data"]["title"], "SYNTHETIC after restart")
            self.assertEqual(reopened["revision"], task["revision"] + 1)

    def test_preserved_source_allows_original_idempotent_retry(self):
        report = self.run_drill()
        database = self.destination / report["paths"]["database"]
        assets = self.destination / report["paths"]["assets"]
        before = read_state(database)
        plan = json.loads((self.destination / "plan-v1.json").read_bytes())
        result = apply_plan(plan, self.destination / "source-v1", database, assets)
        self.assertTrue(result["repeated"])
        self.assertEqual(read_state(database), before)

    def test_retained_archive_can_restore_independent_pre_rollback_desk(self):
        report = self.run_drill()
        destination = self.root / "second-restore"
        restore_workspace(self.destination / report["paths"]["archive"], destination)
        state = read_state(destination / DATABASE)
        self.assertEqual(state[report["attachment_id"]]["data"]["sha256"], digest(drill.REPLACEMENT))
        self.assertEqual(state[report["edited_task_id"]]["data"]["status"], "open")
        self.assertEqual((destination / "assets" / digest(drill.REPLACEMENT)).read_bytes(), drill.REPLACEMENT)

    def test_existing_destination_preserved_and_failure_marked(self):
        self.destination.mkdir()
        (self.destination / "preserve").write_bytes(b"original")
        with self.assertRaises(MigrationError):
            self.run_drill()
        self.assertEqual(list(self.destination.iterdir()), [self.destination / "preserve"])
        failed = self.root / "failed"
        with patch.object(drill, "backup_workspace", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                drill.run_drill(failed)
        self.assertTrue((failed / drill.INCOMPLETE).is_file())
        self.assertFalse((failed / "DRILL.json").exists())

    def test_source_pins_bind_executed_runtime(self):
        report = self.run_drill()
        for name, metadata in report["source_pins"].items():
            raw = (HERE / name).read_bytes()
            self.assertEqual(metadata, {"sha256": digest(raw), "bytes": len(raw)})
        argv = report["start_argv"]
        self.assertEqual(argv[1], str(HERE / "desk.py"))
        self.assertTrue(Path(argv[argv.index("--database") + 1]).is_file())
        self.assertTrue(Path(argv[argv.index("--assets") + 1]).is_dir())

    def test_actual_cli_success_and_repeat_refusal(self):
        args = [sys.executable, "-B", str(HERE / "recovery_drill.py"), str(self.destination)]
        result = subprocess.run(args, text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["completed"])
        again = subprocess.run(args, text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(again.returncode, 2)
        self.assertFalse(json.loads(again.stdout)["completed"])
        self.assertEqual(again.stderr, "")


if __name__ == "__main__":
    unittest.main()
