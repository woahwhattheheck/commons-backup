from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import make_server
from paceboard import Clock, PaceboardError, Store


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.value

    def advance(self, **kwargs: int) -> None:
        self.value += timedelta(**kwargs)


class ServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.clock = MutableClock()
        self.store = Store(Path(self.temporary.name) / "paceboard.sqlite3", clock=Clock(self.clock.now))
        self.server = make_server(self.store, "127.0.0.1", 0, csrf_token="test-csrf-token")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)
        self.port = self.server.server_port

    def _stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(
        self,
        method: str,
        path: str,
        body: object | bytes | None = None,
        *,
        headers: dict[str, str] | None = None,
        skip_host: bool = False,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        payload: bytes | None
        outgoing = dict(headers or {})
        if body is None:
            payload = None
        elif isinstance(body, bytes):
            payload = body
        else:
            payload = json.dumps(body, separators=(",", ":")).encode()
            outgoing.setdefault("Content-Type", "application/json")
        if skip_host:
            connection.putrequest(method, path, skip_host=True)
            for name, value in outgoing.items():
                connection.putheader(name, value)
            if payload is not None and "Content-Length" not in outgoing:
                connection.putheader("Content-Length", str(len(payload)))
            connection.endheaders(payload)
        else:
            connection.request(method, path, body=payload, headers=outgoing)
        response = connection.getresponse()
        data = response.read()
        result_headers = {name: value for name, value in response.getheaders()}
        status = response.status
        connection.close()
        return status, result_headers, data

    def state(self) -> dict:
        status, _, body = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        return json.loads(body)

    def change(self, action: str, operation_id: str, payload: dict, **header_overrides: str) -> tuple[int, dict]:
        headers = {"X-Paceboard-CSRF": "test-csrf-token", **header_overrides}
        status, _, body = self.request(
            "POST",
            "/api/change",
            {"action": action, "operation_id": operation_id, "payload": payload},
            headers=headers,
        )
        return status, json.loads(body)

    def test_static_state_and_security_headers(self) -> None:
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Paceboard", body)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        state = self.state()
        self.assertEqual(state["csrf_token"], "test-csrf-token")
        self.assertTrue(state["authority"]["local_only"])

    def test_host_origin_csrf_and_framing_fail_closed(self) -> None:
        status, _, body = self.request(
            "GET",
            "/api/state",
            headers={"Host": "evil.example"},
            skip_host=True,
        )
        self.assertEqual(status, 421)
        self.assertEqual(json.loads(body)["code"], "UNTRUSTED_HOST")

        status, _, body = self.request(
            "POST",
            "/api/change",
            {"action": "goal.create", "operation_id": "operation-no-csrf-0001", "payload": {}},
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["code"], "CSRF_REQUIRED")

        status, _, body = self.request(
            "POST",
            "/api/change",
            {"action": "goal.create", "operation_id": "operation-bad-origin-0001", "payload": {}},
            headers={"X-Paceboard-CSRF": "test-csrf-token", "Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["code"], "UNTRUSTED_ORIGIN")

        raw = b"{}"
        status, _, body = self.request(
            "POST",
            "/api/change",
            raw,
            headers={
                "Content-Type": "application/json",
                "X-Paceboard-CSRF": "test-csrf-token",
                "Transfer-Encoding": "chunked",
                "Content-Length": str(len(raw)),
            },
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["code"], "FRAMING_REJECTED")

    def test_retry_safe_http_workflow_export_restore_and_erase(self) -> None:
        status, created = self.change(
            "goal.create",
            "operation-http-goal-0001",
            {
                "title": "Write one paragraph",
                "intention": "Keep the next step visible",
                "reminder_minutes": 5,
                "target_focus_minutes": 5,
            },
        )
        self.assertEqual(status, 200)
        goal_id = created["goal_id"]
        status, repeated = self.change(
            "goal.create",
            "operation-http-goal-0001",
            {
                "title": "Write one paragraph",
                "intention": "Keep the next step visible",
                "reminder_minutes": 5,
                "target_focus_minutes": 5,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(created, repeated)

        self.clock.advance(minutes=5)
        self.assertEqual(self.state()["reminders"][0]["goal_id"], goal_id)
        self.assertEqual(self.change(
            "checkin.record",
            "operation-http-pause-0001",
            {"goal_id": goal_id, "kind": "PAUSED", "note": "The task was underspecified."},
        )[0], 200)
        self.clock.advance(days=1)
        self.assertEqual(self.change(
            "checkin.record",
            "operation-http-resume-0001",
            {"goal_id": goal_id, "kind": "RESUMED", "note": "Wrote a one-line outline."},
        )[0], 200)
        status, focus = self.change(
            "focus.start",
            "operation-http-focus-start-0001",
            {"goal_id": goal_id, "planned_minutes": 5},
        )
        self.assertEqual(status, 200)
        self.clock.advance(minutes=2)
        self.assertEqual(self.change(
            "focus.pause",
            "operation-http-focus-pause-0001",
            {"session_id": focus["session_id"]},
        )[1]["elapsed_seconds"], 120)
        self.clock.advance(minutes=20)
        self.assertEqual(self.change(
            "focus.resume",
            "operation-http-focus-resume-0001",
            {"session_id": focus["session_id"]},
        )[0], 200)
        self.clock.advance(minutes=3)
        self.assertEqual(self.change(
            "focus.finish",
            "operation-http-focus-finish-0001",
            {"session_id": focus["session_id"]},
        )[1]["elapsed_seconds"], 300)

        export_status, export_headers, export_body = self.request("GET", "/api/export.json")
        self.assertEqual(export_status, 200)
        self.assertEqual(len(export_headers["X-Content-SHA256"]), 64)
        backup = json.loads(export_body)
        csv_status, _, csv_body = self.request("GET", "/api/export.csv")
        self.assertEqual(csv_status, 200)
        self.assertIn(b"FOCUS_FINISHED", csv_body)

        self.assertEqual(self.change(
            "all.erase",
            "operation-http-erase-0001",
            {"confirm": "ERASE PACEBOARD"},
        )[0], 200)
        self.assertEqual(self.state()["goals"], [])
        self.assertEqual(self.change(
            "backup.restore",
            "operation-http-restore-0001",
            {"backup": backup},
        )[0], 200)
        restored = self.state()
        self.assertEqual(restored["goals"][0]["goal_id"], goal_id)
        self.assertEqual(restored["summary"]["finished_focus_minutes"], 5)

    def test_loopback_only_and_not_found(self) -> None:
        with self.assertRaisesRegex(PaceboardError, "loopback"):
            make_server(self.store, "0.0.0.0", 0)
        status, _, body = self.request("GET", "/../paceboard.py")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["code"], "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
