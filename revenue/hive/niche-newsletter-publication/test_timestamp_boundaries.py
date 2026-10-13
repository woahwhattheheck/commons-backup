from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from http.server import ThreadingHTTPServer

from app import Problem, Store, iso_utc, make_handler

CLOCK = lambda: 1788868500.0
MIN_AWARE = "0001-01-01T00:00:00+14:00"
MAX_AWARE = "9999-12-31T23:59:59-14:00"


class IsoUtcBoundaryTests(unittest.TestCase):
    def test_minimum_datetime_offset_overflow_is_problem_422(self):
        with self.assertRaises(Problem) as caught:
            iso_utc(MIN_AWARE, "Observed at")
        self.assertEqual(caught.exception.status, 422)
        self.assertEqual(str(caught.exception), "Observed at must be an ISO date-time")

    def test_maximum_datetime_offset_overflow_is_problem_422(self):
        with self.assertRaises(Problem) as caught:
            iso_utc(MAX_AWARE, "Scheduled at")
        self.assertEqual(caught.exception.status, 422)
        self.assertEqual(str(caught.exception), "Scheduled at must be an ISO date-time")


class HttpIsoUtcBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "boundary.sqlite3", clock=CLOCK)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def request(self, path: str, payload: dict) -> tuple[int, dict]:
        data = json.dumps(payload).encode()
        request = urllib.request.Request(
            self.base + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_http_source_minimum_offset_overflow_returns_json_422(self):
        status, payload = self.request(
            "/api/sources",
            {
                "id": "boundary-min",
                "title": "Boundary min",
                "url": "self-authored:boundary-min",
                "observed_at": MIN_AWARE,
                "synthetic": True,
            },
        )
        self.assertEqual(status, 422)
        self.assertEqual(payload, {"error": "Observed at must be an ISO date-time"})

    def test_http_issue_maximum_offset_overflow_returns_json_422(self):
        status, _ = self.request(
            "/api/sources",
            {
                "id": "boundary-source",
                "title": "Boundary source",
                "url": "self-authored:boundary-source",
                "observed_at": "2026-09-08T12:00:00Z",
                "synthetic": True,
            },
        )
        self.assertEqual(status, 201)
        status, payload = self.request(
            "/api/issues",
            {
                "id": "boundary-max",
                "slug": "boundary-max",
                "title": "Boundary max",
                "subject": "Boundary max",
                "body": "Boundary max body",
                "topic": "operations",
                "scheduled_at": MAX_AWARE,
                "source_ids": ["boundary-source"],
            },
        )
        self.assertEqual(status, 422)
        self.assertEqual(payload, {"error": "Scheduled at must be an ISO date-time"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
