"""HTTP regression coverage for workbench static URLs with query parameters.

Uses the actual server with temporary synthetic static files and a recording
adapter. This checks HTTP routing, not Chromium behavior or real compilation.
"""
from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

import server


class RecordingAdapter:
    def __init__(self):
        self.calls = []

    def inspect(self, candidate, authority):
        self.calls.append((candidate, authority))
        return {"mode": "UNTRUSTED_INSPECTION", "fixture_only": True}


class WorkbenchStaticQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.contents = {}
        for filename, _ in server.STATIC_FILES.values():
            content = ("Synthetic HTTP fixture: " + filename + "\n").encode("utf-8")
            (cls.root / filename).write_bytes(content)
            cls.contents[filename] = content
        cls.adapter = RecordingAdapter()
        cls.httpd = server.create_server(port=0, adapter=cls.adapter, static_root=cls.root)
        cls.host, cls.port = cls.httpd.server_address[:2]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def request(self, method, target, body=None, headers=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=3)
        try:
            connection.request(method, target, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_plain_static_routes_remain_unchanged(self):
        for route, (filename, content_type) in server.STATIC_FILES.items():
            with self.subTest(route=route):
                status, headers, content = self.request("GET", route)
                self.assertEqual(status, 200)
                self.assertEqual(content, self.contents[filename])
                self.assertEqual(headers["Content-Type"], content_type)

    def test_root_demo_query_loads_index(self):
        status, _, content = self.request("GET", "/?demo=1")
        self.assertEqual(status, 200)
        self.assertEqual(content, self.contents["index.html"])

    def test_index_demo_query_loads_index(self):
        status, _, content = self.request("GET", "/index.html?demo=1")
        self.assertEqual(status, 200)
        self.assertEqual(content, self.contents["index.html"])

    def test_static_queries_preserve_bytes_types_and_response_headers(self):
        for route in server.STATIC_FILES:
            with self.subTest(route=route):
                plain = self.request("GET", route)
                queried = self.request("GET", route + "?demo=1&revision=synthetic%20A")
                self.assertEqual(queried[0], 200)
                self.assertEqual(queried[2], plain[2])
                for key in ("Content-Type", "Content-Length", "Cache-Control", "Content-Security-Policy"):
                    self.assertEqual(queried[1][key], plain[1][key])

    def test_empty_query_delimiter_is_not_part_of_filename(self):
        self.assertEqual(self.request("GET", "/index.html?")[0], 200)

    def test_head_query_returns_get_metadata_without_body(self):
        get_status, get_headers, _ = self.request("GET", "/?demo=1")
        status, headers, content = self.request("HEAD", "/?demo=1")
        self.assertEqual(get_status, 200)
        self.assertEqual(status, 200)
        self.assertEqual(content, b"")
        self.assertEqual(headers["Content-Length"], get_headers["Content-Length"])
        self.assertEqual(headers["Content-Type"], get_headers["Content-Type"])

    def test_unknown_static_path_stays_not_found(self):
        status, _, content = self.request("GET", "/not-a-workbench-asset.js?demo=1")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(content), {"error": "not found"})

    def test_query_does_not_add_a_new_post_endpoint(self):
        before = len(self.adapter.calls)
        status, _, _ = self.request("POST", "/api/inspect?demo=1", body=b"{}")
        self.assertEqual(status, 404)
        self.assertEqual(len(self.adapter.calls), before)

    def test_existing_inspection_endpoint_is_unchanged(self):
        payload = {"candidate": {"fixture": "candidate"}, "authority": {"fixture": "authority"}}
        raw = json.dumps(payload).encode("utf-8")
        status, _, content = self.request("POST", "/api/inspect", body=raw, headers={
            "Content-Type": "application/json",
            "Origin": f"http://{self.host}:{self.port}",
        })
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(content), {"report": {"mode": "UNTRUSTED_INSPECTION", "fixture_only": True}})
        self.assertEqual(self.adapter.calls[-1], (payload["candidate"], payload["authority"]))


if __name__ == "__main__":
    unittest.main()
