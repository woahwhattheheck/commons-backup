"""Receiver-recovery acceptance for an extracted Parcel fulfillment package.

The receiver deliberately applies one event and then drops its first response.  The
package must retain the event for retry, reuse the original Idempotency-Key after a
process restart, and leave an independently delivered event alone.  Receiver-side
deduplication is what prevents the ambiguous event from being applied twice.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import selectors
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
import zipfile

import bundle

ROOT = Path(__file__).resolve().parent
RUNNER = ROOT.parent / "intake-crm-workflow"
SOURCE_REVISION = "9f216e50135948488cb2d95dfaaca337b490d3f5"
FIELDS = ("name", "email", "phone", "address", "service", "preferred_date", "notes")


class AmbiguousReceiver(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, fail_key):
        super().__init__(address, ReceiverHandler)
        self.fail_key = fail_key
        self.requests: dict[str, list[dict]] = {}
        self.applications: dict[str, int] = {}
        self.lock = threading.Lock()


class ReceiverHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        event_id = self.headers.get("Idempotency-Key", "")
        self.assert_event(event_id, payload)
        with self.server.lock:
            requests = self.server.requests.setdefault(event_id, [])
            requests.append(payload)
            first_application = event_id not in self.server.applications
            if first_application:
                self.server.applications[event_id] = 1
            request_number = len(requests)

        # The event is already recorded by the receiver, but the sender receives no
        # acknowledgement.  A retry is therefore required and must carry the same key.
        if event_id == self.server.fail_key and request_number == 1:
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
            return

        body = json.dumps({"accepted": True, "duplicate": not first_application}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def assert_event(self, event_id, payload):
        if not event_id or payload.get("event_id") != event_id:
            self.send_error(400)
            raise AssertionError("Idempotency-Key must match event_id")


class ReceiverRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "package"
        self.output = self.root / "package.zip"
        self.deployment = self.root / "deployment.json"
        self.db_name = "receiver-recovery.sqlite3"
        self.server_processes: list[subprocess.Popen] = []
        self.addCleanup(self.stop_all_package_servers)

    def deployment_value(self):
        mapping = {field: field for field in FIELDS}
        return {
            "format": "parcel.intake-handoff",
            "version": 1,
            "preset": "client-intake",
            "agency": "Synthetic Agency",
            "client": "Synthetic Client",
            "title": "Receiver recovery acceptance",
            "support": "support@example.invalid",
            "scope": "Synthetic receiver-recovery acceptance only",
            "brand": "#345678",
            "fieldMapping": mapping,
            "tasks": ["Review intake", "Prepare handoff", "Close handoff"],
            "exampleIntake": {
                "id": "sample",
                "payload": self.payload("sample@example.invalid", "Sample Client"),
            },
        }

    def payload(self, email, name):
        return {
            "name": name,
            "email": email,
            "phone": "555-0100",
            "address": "1 Synthetic Way",
            "service": "Synthetic service",
            "preferred_date": "2026-09-10",
            "notes": "receiver recovery fixture",
        }

    def build_and_unpack(self):
        self.deployment.write_text(json.dumps(self.deployment_value()), encoding="utf-8")
        bundle.build(self.deployment, RUNNER, self.output, SOURCE_REVISION)
        with zipfile.ZipFile(self.output) as archive:
            archive.extractall(self.package)

    def start_package_server(self):
        proc = subprocess.Popen(
            [sys.executable, "-B", "run.py", "--db", self.db_name, "serve", "--host", "127.0.0.1", "--port", "0"],
            cwd=self.package,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.server_processes.append(proc)
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            self.assertTrue(selector.select(timeout=10), "package server did not start")
            line = proc.stdout.readline()
        if proc.poll() is not None:
            self.fail(line + proc.stderr.read())
        match = re.search(r"http://\S+", line)
        self.assertIsNotNone(match, line)
        return match.group(0), proc

    def stop_package_server(self, proc):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=5)

    def stop_all_package_servers(self):
        for proc in self.server_processes:
            self.stop_package_server(proc)

    def request_json(self, base, path, value=None):
        if value is None:
            with urlopen(base + path, timeout=5) as response:
                return json.load(response)
        request = Request(
            base + path,
            data=json.dumps(value).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def outbox_by_id(self, state):
        return {row["id"]: row for row in state["outbox"]}

    def test_ambiguous_receiver_retry_survives_restart_without_duplicate_application(self):
        self.build_and_unpack()
        recover_key = "intake:recover-me"
        delivered_key = "intake:already-delivered"
        receiver = AmbiguousReceiver(("127.0.0.1", 0), recover_key)
        self.addCleanup(receiver.server_close)
        receiver_thread = threading.Thread(target=receiver.serve_forever, daemon=True)
        receiver_thread.start()
        self.addCleanup(receiver.shutdown)
        endpoint = f"http://127.0.0.1:{receiver.server_port}/events"

        base, first_process = self.start_package_server()
        self.request_json(base, "/api/config", {"mapping": {f: f for f in FIELDS}, "endpoint": endpoint})
        self.request_json(base, "/api/intakes", {"id": "recover-me", "payload": self.payload("recover@example.invalid", "Recover Me")})
        self.request_json(base, "/api/intakes", {"id": "already-delivered", "payload": self.payload("delivered@example.invalid", "Already Delivered")})

        failed = self.request_json(base, "/api/process", {"id": recover_key})
        delivered = self.request_json(base, "/api/process", {"id": delivered_key})
        self.assertEqual((failed["id"], failed["state"], failed["transport"]), (recover_key, "retry", "http"))
        self.assertEqual((delivered["id"], delivered["state"], delivered["transport"]), (delivered_key, "delivered", "http"))

        before_restart = self.request_json(base, "/api/state")
        before_outbox = self.outbox_by_id(before_restart)
        self.assertEqual([len(before_restart[k]) for k in ("customers", "intakes", "jobs", "tasks")], [2, 2, 2, 6])
        self.assertEqual(before_outbox[recover_key]["state"], "retry")
        self.assertEqual(before_outbox[delivered_key]["state"], "delivered")
        delivered_at = before_outbox[delivered_key]["delivered_at"]
        self.stop_package_server(first_process)

        # A new run.py process opens the same extracted-package database.
        base, _ = self.start_package_server()
        retry = self.request_json(base, "/api/retry", {"id": recover_key})
        self.assertEqual(retry, {"id": recover_key, "state": "pending"})
        recovered = self.request_json(base, "/api/process", {"id": recover_key})
        self.assertEqual((recovered["id"], recovered["state"]), (recover_key, "delivered"))

        # Selecting the already delivered event cannot send it again.
        no_resend = self.request_json(base, "/api/process", {"id": delivered_key})
        self.assertEqual(no_resend, {"processed": False})
        after_restart = self.request_json(base, "/api/state")
        after_outbox = self.outbox_by_id(after_restart)
        self.assertEqual([len(after_restart[k]) for k in ("customers", "intakes", "jobs", "tasks")], [2, 2, 2, 6])
        self.assertEqual([row["state"] for row in after_restart["outbox"]], ["delivered", "delivered"])
        self.assertEqual(after_outbox[recover_key]["attempts"], 2)
        self.assertEqual(after_outbox[delivered_key]["attempts"], 1)
        self.assertEqual(after_outbox[delivered_key]["delivered_at"], delivered_at)
        self.assertEqual(after_restart["notifications"], [])

        with receiver.lock:
            self.assertEqual(len(receiver.requests[recover_key]), 2)
            self.assertEqual(len(receiver.requests[delivered_key]), 1)
            self.assertEqual(receiver.applications, {recover_key: 1, delivered_key: 1})
            self.assertEqual(receiver.requests[recover_key][0], receiver.requests[recover_key][1])
            self.assertTrue(all(payload["event_id"] == recover_key for payload in receiver.requests[recover_key]))
            self.assertEqual(receiver.requests[delivered_key][0]["event_id"], delivered_key)


if __name__ == "__main__":
    unittest.main()
