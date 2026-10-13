from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from mail_coordinator import MailCoordinator
from mail_coordinator.server import CoordinatorHandler


class HttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        coordinator = MailCoordinator(Path(self.directory.name) / "http.sqlite3")
        coordinator.initialize()
        handler = type("TestHandler", (CoordinatorHandler,), {"coordinator": coordinator})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def request(self, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.base + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if body is None else "POST",
        )
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)

    def test_health_and_full_happy_path(self) -> None:
        status, health = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")
        _, inbound = self.request(
            "/v1/inbounds",
            {
                "operation_id": "inbound-1",
                "mailbox": "sales@example.com",
                "conversation_key": "lead-1",
                "provider_message_id": "incoming-1",
                "received_at": 100,
            },
        )
        self.assertEqual(inbound["status"], "RECORDED")
        _, queued = self.request(
            "/v1/messages",
            {
                "operation_id": "queue-1",
                "message_id": "message-1",
                "mailbox": "sales@example.com",
                "conversation_key": "lead-1",
                "inbound_message_id": "incoming-1",
                "inbound_received_at": 100,
                "envelope": {
                    "sender": "sales@example.com",
                    "to": ["lead@example.com"],
                    "subject": "Re: hello",
                    "body": "Thanks",
                },
            },
        )
        self.assertEqual(queued["status"], "QUEUED")
        _, claim = self.request(
            "/v1/claims",
            {
                "operation_id": "claim-1",
                "message_id": "message-1",
                "worker_id": "worker-1",
                "claim_id": "claim-1",
            },
        )
        self.assertEqual(claim["envelope"]["body"], "Thanks")
        _, attempt = self.request(
            "/v1/attempts",
            {"operation_id": "attempt-op", "claim_id": "claim-1", "attempt_id": "attempt-1"},
        )
        self.assertEqual(attempt["status"], "ATTEMPTING")
        _, receipt = self.request(
            "/v1/receipts",
            {
                "operation_id": "receipt-op",
                "attempt_id": "attempt-1",
                "provider_message_id": "provider-1",
                "accepted_at": 120,
            },
        )
        self.assertEqual(receipt["status"], "SENT")
        _, readback = self.request("/v1/messages/message-1")
        self.assertEqual(readback["state"], "SENT")
        self.assertNotIn("body", readback)


if __name__ == "__main__":
    unittest.main()
