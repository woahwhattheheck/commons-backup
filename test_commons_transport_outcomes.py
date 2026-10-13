"""Real loopback transports and journals exercise the Deathstar repair port."""
import hashlib
import http.client
import io
import json
import socket
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from integrations.gemini_slack import peer_tool_gateway as gateway
from integrations.shared_equipment.outcomes import effect_uncertain, tool_failed
from integrations.shared_equipment.services import EquipmentError, ServiceEquipment


@contextmanager
def endpoint(dispatch):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(("POST", self.path, payload))
            response = dispatch(payload)
            if response is None:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            status, body, headers = response
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(headers.pop("length", len(raw))))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            calls.append(("GET", self.path, {}))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true,"unexpected_redirect":true}')
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port), calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class CommonsTransportOutcomesTests(unittest.TestCase):
    @staticmethod
    def _verified_slack_equipment(**kwargs):
        equipment = ServiceEquipment(**kwargs)
        equipment._verified_slack_route_checks = []
        equipment._slack_write_route_verified = lambda channel: (
            equipment._verified_slack_route_checks.append(channel) is None
            and channel == "C-fixture"
        )
        return equipment

    def test_native_failure_and_uncertainty_remain_distinct_from_job_status(self):
        value = {"isError": True, "structuredContent": {"ok": False,
                 "error": {"code": "submission_outcome_unknown", "uncertain": True}}}
        self.assertTrue(tool_failed(value))
        self.assertTrue(effect_uncertain(value))
        self.assertFalse(tool_failed({"status": "failed", "exit_code": 7}))
        self.assertFalse(effect_uncertain({"ok": False, "error": {"code": "unknown_tool"}}))

    def test_http_error_closes_response_and_does_not_echo_private_exception(self):
        stream = io.BytesIO(b"private-response")
        error = urllib.error.HTTPError("http://fixture.invalid/private", 500, "private-message", {}, stream)
        with patch.object(gateway._HTTP, "open", side_effect=error):
            with self.assertRaises(gateway.GatewayError) as caught:
                gateway._post_json("http://fixture.invalid", {"message": "task"})
        self.assertTrue(stream.closed)
        self.assertTrue(caught.exception.uncertain)
        self.assertNotIn("private", str(caught.exception))

    def test_redirect_partial_and_lost_post_are_unknown_without_repeat(self):
        cases = (
            lambda payload: (302, b"", {"Location": "/redirected"}),
            lambda payload: (200, b'{"ok":', {"length": 500}),
            lambda payload: None,
        )
        for dispatch in cases:
            with self.subTest(dispatch=dispatch), endpoint(dispatch) as (url, calls):
                with self.assertRaises(gateway.GatewayError) as caught:
                    gateway._post_json(url, {"message": "caller task"}, timeout=2)
                self.assertTrue(caught.exception.uncertain)
                self.assertEqual(1, len(calls))
                self.assertEqual("POST", calls[0][0])

    def test_multiline_sse_preserves_full_result_and_correlates(self):
        content = "original bytes \u03bb\n" * 9000
        def dispatch(payload):
            response = {"jsonrpc": "2.0", "id": payload["id"],
                        "result": {"isError": False, "content": [{"type": "text", "text": content}]}}
            text = json.dumps(response, ensure_ascii=False, indent=2)
            raw = ("event: message\n" + "\n".join("data: " + line for line in text.splitlines()) + "\n\n").encode()
            return 200, raw, {"Content-Type": "text/event-stream"}
        with endpoint(dispatch) as (url, calls):
            result = gateway.McpCatalog(url).call("read", {})
            self.assertEqual(content, result["content"][0]["text"])
            self.assertEqual(1, len(calls))

    def test_wrong_id_and_error_envelopes_keep_request_outcome(self):
        for mode, expected in (("wrong-id", True), ("invalid-params", False),
                               ("uncertain-params", True), ("internal-error", True)):
            def dispatch(payload):
                response = {"jsonrpc": "2.0", "id": payload["id"]}
                if mode == "wrong-id":
                    response.update(id="unrelated", result={"ok": True})
                else:
                    response["error"] = {"code": -32603 if mode == "internal-error" else -32602,
                                         "message": "provider detail",
                                         "data": {"uncertain": mode == "uncertain-params"}}
                return 200, response, {}
            with self.subTest(mode=mode), endpoint(dispatch) as (url, calls):
                with self.assertRaises(gateway.GatewayError) as caught:
                    gateway.McpCatalog(url).call("effect", {})
                self.assertIs(caught.exception.uncertain, expected)
                self.assertEqual(1, len(calls))
                if mode != "wrong-id":
                    self.assertEqual("provider detail", caught.exception.native_result["error"]["message"])

    def test_uncertain_result_replay_keeps_exact_handle_and_one_effect(self):
        for outcome in (
            {"ok": False, "request_id": "native-handle", "uncertain": True},
            {"isError": True, "structuredContent": {"error": {"uncertain": True}, "request_id": "native-handle"}},
        ):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as root:
                store = gateway.ToolCallStore(Path(root) / "calls.sqlite3")
                calls = []
                try:
                    def runner(name, args):
                        calls.append((name, args))
                        return outcome
                    first = store.execute_journaled("r", "c", "effect", {}, runner)
                    second = store.execute_journaled("r", "c", "effect", {}, runner)
                    self.assertEqual(outcome, first)
                    self.assertEqual(first, second)
                    self.assertEqual(1, len(calls))
                    self.assertEqual("started", store._db.execute("SELECT state FROM tool_calls").fetchone()[0])
                finally:
                    store.close()

    def test_definite_failure_is_error_and_interrupted_retry_is_unknown(self):
        with tempfile.TemporaryDirectory() as root:
            store = gateway.ToolCallStore(Path(root) / "calls.sqlite3")
            try:
                result = store.execute_journaled("r", "c", "effect", {},
                                                lambda *_: {"ok": False, "error": "pending_review_limit"})
                self.assertTrue(tool_failed(result))
                self.assertFalse(effect_uncertain(result))
                replay = store.execute_journaled("r", "c", "effect", {}, lambda *_: self.fail("no replay"))
                self.assertEqual(result, replay)
                self.assertEqual("error", store._db.execute("SELECT state FROM tool_calls").fetchone()[0])
                digest = hashlib.sha256(b"{}").hexdigest()
                store._db.execute("INSERT INTO tool_calls VALUES(?,?,?,?,?,?,?)",
                                  ("lost", "c", "effect", digest, "started", None, 1))
                store._db.commit()
                repeated = store.execute_journaled("lost", "c", "effect", {}, lambda *_: self.fail("no replay"))
                self.assertTrue(tool_failed(repeated))
                self.assertTrue(effect_uncertain(repeated))
            finally:
                store.close()

    def test_equipment_http_surfaces_nested_failure_without_repeating(self):
        with tempfile.TemporaryDirectory() as root:
            store = gateway.ToolCallStore(Path(root) / "calls.sqlite3")
            events = gateway.EventStore(Path(root) / "events.jsonl")
            effects = []
            class Catalog:
                def tools(self, **kwargs):
                    return [{"name": "effect"}]
                def call(self, name, args):
                    effects.append(args)
                    return {"isError": True, "result": {"ok": False, "uncertain": True,
                                                       "request_id": "provider-handle"}}
            catalog = Catalog()
            upstream = object()
            loop = gateway.ToolLoop(upstream, catalog, store)
            server = gateway.ToolGateway(("127.0.0.1", 0), loop, events, upstream, catalog)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
            thread.start()
            try:
                replies = []
                for _ in range(2):
                    request = urllib.request.Request("http://127.0.0.1:%s/v1/tools/call" % server.server_port,
                        data=json.dumps({"request_id": "http-r", "call_id": "c", "name": "effect", "arguments": {}}).encode(),
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(request, timeout=2) as response:
                        replies.append(json.load(response))
                self.assertFalse(replies[0]["ok"])
                self.assertTrue(replies[0]["uncertain"])
                self.assertEqual("provider-handle", replies[0]["result"]["result"]["request_id"])
                self.assertEqual(replies[0], replies[1])
                self.assertEqual(1, len(effects))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                store.close()

    def test_slack_post_handle_survives_failed_permalink_read(self):
        calls = []
        def opener(request, **kwargs):
            calls.append(request)
            if request.get_method() == "POST":
                return io.BytesIO(b'{"ok":true,"channel":"C-fixture","ts":"1.2","message":{"text":"sent"}}')
            raise OSError("fixture link failure")
        equipment = self._verified_slack_equipment(slack_token_loader=lambda: "fixture", opener=opener)
        result = equipment.call("slack_post_message", {"channel_id": "C-fixture", "text": "Completed fixture operation."})
        self.assertFalse(result["isError"])
        self.assertEqual(["C-fixture"], equipment._verified_slack_route_checks)
        self.assertEqual("1.2", result["result"]["ts"])
        self.assertEqual("permalink_unavailable", result["result"]["permalink_error"])
        self.assertEqual(["POST", "GET"], [request.get_method() for request in calls])

    def test_slack_post_handle_survives_nonobject_optional_message(self):
        for message in (None, [], "metadata"):
            def opener(request, **kwargs):
                if request.get_method() == "POST":
                    return io.BytesIO(json.dumps({"ok": True, "channel": "C-fixture",
                                                  "ts": "1.2", "message": message}).encode())
                raise OSError("fixture link failure")
            equipment = self._verified_slack_equipment(slack_token_loader=lambda: "fixture", opener=opener)
            result = equipment.call("slack_post_message", {"channel_id": "C-fixture",
                                     "text": "Completed fixture operation."})
            self.assertFalse(result["isError"])
            self.assertEqual(["C-fixture"], equipment._verified_slack_route_checks)
            self.assertEqual("1.2", result["result"]["ts"])
            self.assertEqual("permalink_unavailable", result["result"]["permalink_error"])

    def test_slack_http_error_closes_and_retains_retry_after_and_uncertainty(self):
        for status, uncertain in ((429, False), (500, True), (302, True)):
            stream = io.BytesIO(b"private")
            error = urllib.error.HTTPError("https://slack.com/api/chat.postMessage", status, "fixture",
                                          {"Retry-After": "17"}, stream)
            def opener(*args, **kwargs):
                raise error
            equipment = self._verified_slack_equipment(slack_token_loader=lambda: "fixture", opener=opener)
            result = equipment.call("slack_post_message", {"channel_id": "C-fixture", "text": "Completed fixture operation."})
            self.assertTrue(stream.closed)
            self.assertEqual(["C-fixture"], equipment._verified_slack_route_checks)
            self.assertTrue(result["isError"])
            self.assertIs(result["uncertain"], uncertain)
            self.assertEqual("17", result["result"]["retry_after"])

    def test_slack_partial_native_failures_preserve_uncertainty_and_replay(self):
        for error in ("internal_error", "fatal_error", "channel_not_found"):
            calls = []
            def opener(request, **kwargs):
                calls.append(request)
                return io.BytesIO(json.dumps({"ok": False, "error": error}).encode())
            equipment = self._verified_slack_equipment(slack_token_loader=lambda: "fixture", opener=opener)
            observed = equipment.slack("conversations.history", {"channel": "C-fixture"})
            self.assertFalse(effect_uncertain(observed))
            with tempfile.TemporaryDirectory() as root:
                store = gateway.ToolCallStore(Path(root) / "calls.sqlite3")
                try:
                    arguments = {"channel_id": "C-fixture", "text": "Completed fixture operation."}
                    result = store.execute_journaled("r", "c", "slack_post_message", arguments, equipment.call)
                    replay = store.execute_journaled("r", "c", "slack_post_message", arguments, equipment.call)
                    self.assertEqual(result, replay)
                    self.assertTrue(tool_failed(result))
                    self.assertEqual(error, result["result"]["error"])
                    self.assertEqual(error != "channel_not_found", effect_uncertain(result))
                    self.assertEqual(2, len(calls))
                finally:
                    store.close()

    def test_github_timeout_is_classified_without_repeating_or_echoing_payload(self):
        def runner(*args, **kwargs):
            raise subprocess.TimeoutExpired("private-command", 90)
        equipment = ServiceEquipment(gh_runner=runner)
        for method, uncertain in (("GET", False), ("POST", True)):
            with self.assertRaises(EquipmentError) as caught:
                equipment.github("repos/fixture/project/issues", method=method)
            self.assertIs(caught.exception.uncertain, uncertain)
            self.assertNotIn("private-command", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
