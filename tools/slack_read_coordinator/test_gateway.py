import concurrent.futures
import contextlib
import hashlib
import http.client
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from broker import Broker, Upstream, dumps
from gateway import Gateway, NoRedirect, SlackProvider, private_state, main
from test_broker import Clock, PRINCIPAL

KEY = "c" * 64
HERE = Path(__file__).resolve().parent


class Response(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body)
        self.status, self.headers = status, {}


class ProviderTests(unittest.TestCase):
    def test_only_fixed_origin_header_auth_and_read_method(self):
        provider = SlackProvider("synthetic-token-never-real")
        opener = mock.Mock()
        opener.open.return_value = Response(b'{"ok":true,"messages":[]}')
        provider._opener = opener
        result = provider("conversations.history", {"channel": "C123", "limit": 15})
        request = opener.open.call_args.args[0]
        self.assertEqual(200, result.status)
        self.assertTrue(request.full_url.startswith("https://slack.com/api/conversations.history?"))
        self.assertNotIn("synthetic-token", request.full_url)
        self.assertEqual("Bearer synthetic-token-never-real", request.get_header("Authorization"))
        self.assertEqual("GET", request.method)
        self.assertEqual(hashlib.sha256(b"synthetic-token-never-real").hexdigest(), provider.fingerprint)
        for method, params in (("chat.postMessage", {}), ("conversations.history", {"channel": "C123", "token": "override"})):
            with self.assertRaises(ValueError):
                provider(method, params)
        self.assertEqual(1, opener.open.call_count)

    def test_startup_identity_check_uses_documented_post_without_mutation(self):
        provider = SlackProvider("synthetic-token-never-real")
        provider._opener = mock.Mock()
        provider._opener.open.return_value = Response(b'{"ok":true,"team_id":"T123"}')
        provider.authenticate("T123")
        request = provider._opener.open.call_args.args[0]
        self.assertEqual("https://slack.com/api/auth.test", request.full_url)
        self.assertEqual("POST", request.method)
        self.assertEqual(b"{}", request.data)

    def test_redirect_handler_never_follows(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://elsewhere.invalid"))

    def test_http_rate_response_preserves_header_without_body(self):
        provider = SlackProvider("synthetic-token-never-real")
        error = urllib.error.HTTPError("https://slack.com", 429, "limited", {"Retry-After": "120"}, io.BytesIO(b"secret error body"))
        provider._opener = mock.Mock()
        provider._opener.open.side_effect = error
        result = provider("conversations.history", {"channel": "C123"})
        self.assertEqual((429, "120", None), (result.status, result.retry_after, result.payload))

    def test_workspace_mismatch_and_enterprise_token_rejected(self):
        provider = SlackProvider("synthetic-token-never-real")
        for body in ({"ok": True, "team_id": "T456"}, {"ok": True, "team_id": "T123", "is_enterprise_install": True}, {"ok": 1, "team_id": "T123"}):
            with mock.patch.object(provider, "_request", return_value=Upstream(200, body)):
                with self.assertRaises(ValueError):
                    provider.authenticate("T123")
        with mock.patch.object(provider, "_request", return_value=Upstream(200, {"ok": True, "team_id": "T123"})):
            provider.authenticate("T123")

    def test_invalid_oversize_and_slow_response_are_errors(self):
        for raw in (b"not-json", b'{"ok":true,"ok":false}', b'{"ok":true,"x":NaN}', b"x" * 524289, b"\xff"):
            provider = SlackProvider("synthetic-token-never-real")
            provider._opener = mock.Mock()
            provider._opener.open.return_value = Response(raw)
            self.assertEqual(502, provider("conversations.info", {"channel": "C123"}).status)
        provider._opener.open.return_value = Response(b'{"ok":true}')
        with mock.patch("gateway.time.monotonic", side_effect=[0, 21]):
            self.assertEqual(502, provider("conversations.info", {"channel": "C123"}).status)

    def test_token_is_opaque_but_cannot_inject_headers(self):
        SlackProvider(('xoxe.xoxb' + '-synthetic-rotated-token'))
        for token in ("", "short", "bad\r\nInjected: header", "has space in token", "x" * 2049):
            with self.assertRaises(ValueError):
                SlackProvider(token)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.broker = Broker(Path(self.tmp.name) / "reads.sqlite3", "T123", "A123", PRINCIPAL, clock=self.clock)
        self.calls = 0
        self.provider = self.good
        self.server = Gateway(0, self.broker, lambda *args: self.provider(*args), KEY)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05})
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.assertFalse(self.thread.is_alive())
        self.tmp.cleanup()

    def good(self, *args):
        self.calls += 1
        return Upstream(200, {"ok": True, "messages": [{"text": "synthetic-only", "ts": "999.000001"}], "response_metadata": {"next_cursor": "opaque-next"}})

    def request(self, body=None, key=KEY, path="/v1/read", method="POST", raw=None, headers=None):
        if raw is None:
            raw = dumps(body or {"method": "conversations.history", "params": {"channel": "C123"}}).encode()
        head = {"Content-Type": "application/json"}
        if key is not None:
            head["Authorization"] = "Bearer " + key
        head.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=raw, headers=head)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), json.loads(response.read())
        finally:
            connection.close()

    def test_authenticated_fetch_cache_and_cursor(self):
        code, headers, first = self.request()
        self.assertEqual(200, code)
        self.assertEqual("FETCHED", first["state"])
        self.assertEqual("opaque-next", first["data"]["response_metadata"]["next_cursor"])
        self.assertEqual("no-store", headers["Cache-Control"])
        self.assertIs(False, first["outbound_clearance"])
        self.assertEqual("CACHED", self.request()[2]["state"])
        self.assertEqual(1, self.calls)

    def test_missing_wrong_and_duplicate_auth_cannot_read(self):
        for key in (None, "wrong-key"):
            self.assertEqual(401, self.request(key=key)[0])
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.putrequest("GET", "/health")
            connection.putheader("Authorization", "Bearer " + KEY)
            connection.putheader("Authorization", "Bearer " + KEY)
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(401, response.status)
            response.read()
        finally:
            connection.close()
        self.assertEqual(0, self.calls)

    def test_health_requires_auth_and_contains_no_secret(self):
        code, _, body = self.request(path="/health", method="GET")
        self.assertEqual(200, code)
        self.assertNotIn(KEY, dumps(body))
        self.assertNotIn(PRINCIPAL, dumps(body))
        self.assertEqual(401, self.request(path="/health", method="GET", key=None)[0])

    def test_unknown_route_and_write_method_never_call_provider(self):
        self.assertEqual(404, self.request(path="/v1/send")[0])
        self.assertEqual(400, self.request({"method": "chat.postMessage", "params": {"channel": "C123", "text": "no-send"}})[0])
        self.assertEqual(0, self.calls)

    def test_strict_json_and_request_schema(self):
        raws = [b'{"method":"conversations.history","method":"chat.postMessage","params":{}}', b'{"method":"conversations.history","params":{"channel":"C123"},"max_age_seconds":NaN}', b"[]", b"{", b"\xff", b"x" * 32769]
        for raw in raws:
            self.assertEqual(400, self.request(raw=raw)[0])
        for body in ({"method": "conversations.history", "params": {"channel": "C123", "token": "no"}}, {"method": "conversations.history", "params": {"channel": "C123"}, "workspace": "T456"}, {"method": "conversations.history", "params": {"channel": "C123"}, "max_age_seconds": True}):
            self.assertEqual(400, self.request(body)[0])
        self.assertEqual(400, self.request(headers={"Content-Type": "text/plain"})[0])
        self.assertEqual(0, self.calls)

    def test_fresh_request_respects_retry_after(self):
        self.request()
        code, headers, result = self.request({"method": "conversations.history", "params": {"channel": "C123"}, "max_age_seconds": 0})
        self.assertEqual(429, code)
        self.assertEqual("60", headers["Retry-After"])
        self.assertNotIn("data", result)
        self.assertEqual(1, self.calls)

    def test_real_concurrent_http_calls_singleflight(self):
        entered, release = threading.Event(), threading.Event()
        def provider(*args):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test release timeout")
            return self.good(*args)
        self.provider = provider
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(self.request)
            try:
                self.assertTrue(entered.wait(5))
                other = self.request()
                self.assertEqual(202, other[0])
                self.assertEqual("BUSY", other[2]["state"])
            finally:
                release.set()
            self.assertEqual("FETCHED", future.result(timeout=5)[2]["state"])
        self.assertEqual(1, self.calls)

    def test_upstream_failure_and_storage_failure_not_success(self):
        def provider(*args):
            raise RuntimeError("do-not-reflect-secret")
        self.provider = provider
        code, _, result = self.request()
        self.assertEqual(502, code)
        self.assertNotIn("do-not-reflect-secret", dumps(result))
        self.assertNotIn("data", result)
        import sqlite3
        with mock.patch.object(self.broker, "read", side_effect=sqlite3.OperationalError("private path")):
            code, _, result = self.request()
            self.assertEqual(503, code)
            self.assertEqual("STORAGE_UNAVAILABLE", result["state"])
            self.assertNotIn("private path", dumps(result))

    def test_real_cli_client_exit_status_and_no_token_needed(self):
        env = dict(os.environ)
        env["SLACK_READ_GATEWAY_KEY"] = KEY
        env.pop("SLACK_READ_TOKEN", None)
        command = [sys.executable, str(HERE / "gateway.py"), "read", "--port", str(self.port)]
        body = dumps({"method": "conversations.history", "params": {"channel": "C123"}})
        first = subprocess.run(command, input=body, text=True, capture_output=True, env=env, timeout=10)
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual("FETCHED", json.loads(first.stdout)["state"])
        fresh = dumps({"method": "conversations.history", "params": {"channel": "C123"}, "max_age_seconds": 0})
        second = subprocess.run(command, input=fresh, text=True, capture_output=True, env=env, timeout=10)
        self.assertEqual(2, second.returncode)
        self.assertEqual("COOLDOWN", json.loads(second.stdout)["state"])
        self.assertNotIn(KEY, first.stdout + first.stderr + second.stdout + second.stderr)


@unittest.skipUnless(os.name == "posix", "POSIX service storage contract")
class StateTests(unittest.TestCase):
    def test_private_directory_and_database_creation(self):
        with tempfile.TemporaryDirectory() as root:
            path = private_state(Path(root) / "state")
            self.assertEqual(0o700, path.parent.stat().st_mode & 0o777)
            self.assertEqual(0o600, path.stat().st_mode & 0o777)
            self.assertEqual(path, private_state(path.parent))

    def test_unsafe_permissions_and_symlinks_rejected_without_changes(self):
        with tempfile.TemporaryDirectory() as root:
            public = Path(root) / "public"
            public.mkdir(mode=0o755)
            with self.assertRaises(ValueError):
                private_state(public)
            self.assertEqual(0o755, public.stat().st_mode & 0o777)
            target = Path(root) / "target"
            target.mkdir(mode=0o700)
            link = Path(root) / "link"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                private_state(link)
            (target / "reads.sqlite3").symlink_to(Path(root) / "elsewhere")
            with self.assertRaises(ValueError):
                private_state(target)
            self.assertFalse((Path(root) / "elsewhere").exists())

    def test_upstream_credential_cannot_be_reused_as_gateway_key(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.dict(os.environ, {"SLACK_READ_TOKEN": KEY, "SLACK_READ_GATEWAY_KEY": KEY}):
                with mock.patch("gateway.SlackProvider") as provider, contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(2, main(["serve", "--state-dir", root, "--workspace", "T123", "--app-id", "A123"]))
                    provider.assert_not_called()
                    self.assertNotIn(KEY, err.getvalue())
                    self.assertFalse((Path(root) / "reads.sqlite3").exists())

    def test_bad_key_prevents_gateway_start(self):
        with self.assertRaises(ValueError):
            Gateway(0, None, None, "short")


if __name__ == "__main__":
    unittest.main()
