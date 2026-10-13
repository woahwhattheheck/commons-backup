#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import pathlib
import threading
import unittest
from http.server import ThreadingHTTPServer

from app import Handler
from studio import ProjectError, validate_project

ROOT = pathlib.Path(__file__).resolve().parent
HUGE = 10 ** 400


def project(**overrides):
    value = {
        "title": "numeric boundary",
        "preset": "vertical",
        "fps": 12,
        "audio": {"kind": "tone", "frequency": 220, "volume": 0.03},
        "segments": [
            {"duration": 10, "text": "one", "color": "#123456"},
            {"duration": 10, "text": "two", "color": "#234567"},
            {"duration": 10, "text": "three", "color": "#345678"},
        ],
    }
    value.update(overrides)
    return value


class NumericBoundaryTests(unittest.TestCase):
    def test_huge_duration_is_project_error_not_overflow(self):
        value = project()
        value["segments"][0]["duration"] = HUGE
        with self.assertRaisesRegex(ProjectError, "finite number"):
            validate_project(value, ROOT)

    def test_huge_tone_numbers_are_project_errors(self):
        for field in ("frequency", "volume"):
            with self.subTest(field=field):
                value = project()
                value["audio"][field] = HUGE
                with self.assertRaisesRegex(ProjectError, "finite number"):
                    validate_project(value, ROOT)

    def test_nonfinite_and_boolean_numeric_values_are_rejected(self):
        for value in (float("nan"), float("inf"), True):
            with self.subTest(value=repr(value)):
                payload = project()
                payload["audio"]["volume"] = value
                with self.assertRaises(ProjectError):
                    validate_project(payload, ROOT)

    def test_normal_project_remains_normalized(self):
        normalized = validate_project(project(), ROOT)
        self.assertEqual(normalized["duration"], 30.0)
        self.assertEqual(normalized["audio"], {"kind": "tone", "frequency": 220.0, "volume": 0.03})

    def test_http_validate_returns_json_422_for_huge_integer(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = project()
            payload["segments"][0]["duration"] = HUGE
            body = json.dumps(payload).encode("utf-8")
            client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                client.request("POST", "/api/validate", body, {"Content-Type": "application/json", "Content-Length": str(len(body))})
                response = client.getresponse()
                result = json.loads(response.read().decode("utf-8"))
            finally:
                client.close()
            self.assertEqual(response.status, 422)
            self.assertIn("finite number", result["error"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
