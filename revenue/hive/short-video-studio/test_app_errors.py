#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import app


class AppErrorContractTests(unittest.TestCase):
    def test_render_subprocess_failure_returns_json_422_and_cleans_temp_project(self):
        with tempfile.TemporaryDirectory(prefix="short-video-http-error-") as td:
            root = pathlib.Path(td)
            failure = subprocess.CalledProcessError(
                7,
                ["ffmpeg", "synthetic-render"],
                stderr="synthetic render failure",
            )
            with patch.object(app, "ROOT", root), patch.object(
                app, "render_project", side_effect=failure
            ):
                server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    body = json.dumps({"title": "synthetic"}).encode("utf-8")
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/render",
                        data=body,
                        headers={"Content-Type": "application/json"},
                    )
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(request, timeout=5)
                    response = caught.exception
                    self.assertEqual(response.code, 422)
                    payload = json.loads(response.read())
                    self.assertIn("returned non-zero exit status 7", payload["error"])
                    self.assertEqual(list(root.glob("tmp*.json")), [])
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

    def test_json_integer_digit_limit_returns_json_400(self):
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            body = ('{"title":' + ("9" * 5000) + "}").encode("utf-8")
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/validate",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=5)
            response = caught.exception
            self.assertEqual(response.code, 400)
            payload = json.loads(response.read())
            self.assertTrue(payload["error"].startswith("invalid JSON:"))
            self.assertIn("Exceeds the limit", payload["error"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
