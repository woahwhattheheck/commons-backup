import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from host.cua_s1_cloud.server import REVISION, handler_for


class FakeScorer:
    def score(self, request):
        if not isinstance(request.get("options"), list):
            raise ValueError("options missing")
        return {"selected_index": 0, "executed": False, "revision": REVISION}


class CloudServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(FakeScorer()))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        conn.request(method, path, body=body)
        response = conn.getresponse()
        status, payload = response.status, json.loads(response.read())
        conn.close()
        return status, payload

    def test_health_and_score(self):
        status, health = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["revision"], REVISION)
        status, result = self.request("POST", "/score", b'{"options":["a","b"]}')
        self.assertEqual(status, 200)
        self.assertFalse(result["executed"])

    def test_invalid_and_oversize_requests(self):
        self.assertEqual(self.request("POST", "/score", b"{")[0], 400)
        self.assertEqual(self.request("POST", "/score", b"x" * 65537)[0], 413)
        self.assertEqual(self.request("POST", "/missing", b"{}")[0], 404)


if __name__ == "__main__":
    unittest.main()
