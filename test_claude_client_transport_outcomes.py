#!/usr/bin/env python3
"""Regressions for the real Claude peer transport; loopback only, no model use."""
from __future__ import annotations

import base64
import http.client
import importlib.util
import io
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SPEC = importlib.util.spec_from_file_location(
    "claude_client_transport", Path(__file__).parent / "integrations/claude_headless/client.py")
client_mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = client_mod
SPEC.loader.exec_module(client_mod)


class Response(io.BytesIO):
    def __init__(self, raw, status=200):
        super().__init__(raw)
        self.status = status


class PartialResponse(Response):
    def read(self, *args):
        raise http.client.IncompleteRead(self.getvalue(), 7)


class TransportTests(unittest.TestCase):
    def client(self, response=None, error=None):
        calls = []

        def opener(request, **kwargs):
            calls.append(request)
            if error is not None:
                raise error
            return response

        return client_mod.HeadlessClient("http://127.0.0.1:1", opener=opener), calls

    def assert_unknown(self, value):
        self.assertIs(value["ok"], False)
        self.assertIs(value["uncertain"], True)

    def assert_raw(self, value, raw):
        self.assertEqual(raw, base64.b64decode(value["response_bytes_base64"], validate=True))

    def test_http_error_closes_body_and_cannot_promote_native_ok(self):
        native = {"ok": True, "run_id": "native-request", "http_status": 200,
                  "details": ["\u2264", None, False, 0]}
        raw = json.dumps(native, ensure_ascii=False).encode("utf-8")
        body = io.BytesIO(raw)
        client, calls = self.client(error=urllib.error.HTTPError(
            "http://127.0.0.1:1/v1/runs", 500, "Synthetic error", {}, body))
        value = client.submit("synthetic")
        self.assert_unknown(value)
        self.assertEqual(500, value["http_status"])
        self.assertEqual("native-request", value["run_id"])
        self.assertEqual(native, value["native_response"])
        self.assert_raw(value, raw)
        self.assertTrue(body.closed)
        self.assertEqual(1, len(calls))

    def test_malformed_status_on_http_error_preserves_unknown_outcome(self):
        for status in ([], {}):
            native = {"ok": True, "run_id": "known", "status": status}
            raw = json.dumps(native).encode()
            client, calls = self.client(response=Response(raw, 500))
            value = client.submit("synthetic")
            self.assert_unknown(value)
            self.assertEqual(native, value["native_response"])
            self.assert_raw(value, raw)
            self.assertEqual(1, len(calls))

    def test_partial_success_and_error_responses_close_and_keep_exact_partial_bytes(self):
        raw = b'{"ok":true,"run_id":"partial"'
        for http_error in (False, True):
            with self.subTest(http_error=http_error):
                body = PartialResponse(raw, 500 if http_error else 200)
                error = urllib.error.HTTPError("http://127.0.0.1:1", 500, "Synthetic", {}, body)
                client, calls = self.client(response=body, error=error if http_error else None)
                value = client.submit("synthetic")
                self.assert_unknown(value)
                self.assertEqual("incomplete_response", value["reason"])
                self.assert_raw(value, raw)
                self.assertTrue(body.closed)
                self.assertEqual(1, len(calls))
                error.close()

    def test_malformed_empty_and_nonobject_responses_are_exact_unknown_outcomes(self):
        for raw in (b"\xff\x80\x00", b"x" * 8192, b"", b"null", b"[false,0,null]", b"{}"):
            with self.subTest(raw_length=len(raw)):
                body = Response(raw)
                client, calls = self.client(response=body)
                value = client.submit("synthetic")
                self.assert_unknown(value)
                self.assert_raw(value, raw)
                self.assertTrue(body.closed)
                self.assertEqual(1, len(calls))

    def test_missing_or_blank_native_handle_never_acknowledges_submission(self):
        for native in ({"ok": True}, {"ok": True, "run_id": ""},
                       {"ok": True, "request_id": " "}):
            with self.subTest(native=native):
                raw = json.dumps(native).encode()
                client, _ = self.client(response=Response(raw, 202))
                value = client.submit("synthetic")
                self.assert_unknown(value)
                self.assertEqual("missing_native_handle", value["reason"])
                self.assertEqual(native, value["native_response"])
                self.assert_raw(value, raw)

    def test_lost_submission_followup_resume_cancel_and_recover_never_repeat(self):
        for name, args in (("submit", ("synthetic",)), ("followup", ("run", "synthetic")),
                           ("resume", ("session", "synthetic")), ("cancel", ("run",)),
                           ("recover", ())):
            with self.subTest(operation=name):
                client, calls = self.client(error=OSError("Synthetic lost reply"))
                value = getattr(client, name)(*args)
                self.assert_unknown(value)
                self.assertEqual("submission_outcome_unknown", value["error"])
                self.assertEqual(1, len(calls))
                self.assertEqual("POST", calls[0].get_method())

    def test_read_outage_is_a_read_failure(self):
        client, calls = self.client(error=OSError("Synthetic unavailable read"))
        value = client.health()
        self.assertIs(value["ok"], False)
        self.assertIs(value["uncertain"], False)
        self.assertEqual("unreachable", value["error"])
        self.assertEqual(1, len(calls))

    def test_definite_rejection_and_acknowledged_terminal_outcome_remain_distinct(self):
        cases = [
            (400, {"ok": False, "error": {"code": "invalid_argument", "uncertain": False}}),
            (502, {"ok": False, "run_id": "known", "status": "error",
                   "run": {"result_text": "actual failure", "exit_code": 7}}),
            (409, {"ok": False, "error": "already_terminal", "status": "cancelled"}),
            (200, {"ok": False, "error": "unknown_tool"}),
        ]
        for status, native in cases:
            with self.subTest(status=status, native=native):
                raw = json.dumps(native).encode()
                client, _ = self.client(response=Response(raw, status))
                value = client.cancel("known")
                self.assertIs(value["ok"], False)
                self.assertIs(value["uncertain"], False)
                if status >= 300:
                    self.assertEqual(native, value["native_response"])
                    self.assert_raw(value, raw)

    def test_generic_400_after_enqueue_is_not_claimed_definite(self):
        native = {"ok": False, "error": "ValueError", "run_id": "persisted", "status": "queued"}
        client, _ = self.client(response=Response(json.dumps(native).encode(), 400))
        value = client.submit("synthetic")
        self.assert_unknown(value)
        self.assertEqual("persisted", value["run_id"])
        self.assertEqual(native, value["native_response"])

    def test_native_uncertainty_under_http200_is_preserved(self):
        for nested in (False, True):
            native = {"ok": True, "request_id": "native-handle",
                      "error": {"code": "submission_outcome_unknown"}}
            (native["error"] if nested else native)["uncertain"] = True
            raw = json.dumps(native).encode()
            client, _ = self.client(response=Response(raw))
            value = client.submit("synthetic")
            self.assert_unknown(value)
            self.assertEqual(native, value["native_response"])
            self.assertEqual("native-handle", value["request_id"])
            self.assert_raw(value, raw)

    def test_acknowledgement_and_failed_job_read_preserve_native_data(self):
        native = {"ok": True, "run_id": "known", "session_id": "conversation", "status": "queued"}
        client, _ = self.client(response=Response(json.dumps(native).encode(), 202))
        self.assertEqual({**native, "http_status": 202}, client.submit("synthetic"))
        native = {"ok": True, "run": {"run_id": "known", "status": "error", "exit_code": 7,
                                     "result_text": "\u2264 \u96ea", "result": {"retained": [False, 0, None]}}}
        client, _ = self.client(response=Response(json.dumps(native).encode()))
        self.assertEqual({**native, "http_status": 200}, client.status("known"))

    def gateway(self, status, raw, *, redirect=False, partial=False):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.respond()

            def do_GET(self):
                self.respond()

            def respond(self):
                self.server.requests.append((self.command, self.path))
                self.send_response(self.server.reply_status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw) + (7 if partial else 0)))
                self.send_header("Connection", "close")
                if redirect:
                    self.send_header("Location", "/redirected")
                self.end_headers()
                self.wfile.write(raw)
                self.wfile.flush()
                self.close_connection = True

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.requests = []
        server.reply_status = status
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def cleanup():
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
            self.assertFalse(thread.is_alive())

        self.addCleanup(cleanup)
        return server, client_mod.HeadlessClient("http://127.0.0.1:" + str(server.server_port))

    def test_actual_http_redirect_does_not_send_a_second_request(self):
        raw = b'{"ok":true,"run_id":"redirect-body"}'
        server, client = self.gateway(302, raw, redirect=True)
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                server.reply_status = status
                server.requests.clear()
                value = client.submit("synthetic")
                self.assert_unknown(value)
                self.assertEqual(status, value["http_status"])
                self.assert_raw(value, raw)
                self.assertEqual([("POST", "/v1/runs")], server.requests)

    def test_actual_partial_http_reply_is_unknown_even_when_json_prefix_is_complete(self):
        raw = b'{"ok":true,"run_id":"native-handle"}'
        server, client = self.gateway(200, raw, partial=True)
        value = client.submit("synthetic")
        self.assert_unknown(value)
        self.assertEqual("incomplete_response", value["reason"])
        self.assert_raw(value, raw)
        self.assertEqual([("POST", "/v1/runs")], server.requests)

    def test_cli_wait_does_not_replace_http_failure_with_a_successful_read(self):
        native = {"ok": True, "run_id": "native-handle"}
        client, _ = self.client(response=Response(json.dumps(native).encode(), 500))
        out = io.StringIO()
        with patch.object(client_mod, "HeadlessClient", return_value=client), \
                patch.object(client, "wait", side_effect=AssertionError("Unexpected wait after failed response")):
            code = client_mod.main(["submit", "synthetic", "--wait", "1"], out=out)
        self.assertEqual(1, code)
        self.assert_unknown(json.loads(out.getvalue()))

    def test_cli_default_output_is_utf8_even_with_a_legacy_stream(self):
        native = {"ok": True, "service": "\u2264 \u96ea"}
        client, _ = self.client(response=Response(json.dumps(native).encode()))
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252")
        try:
            with patch.object(client_mod, "HeadlessClient", return_value=client), \
                    patch.object(client_mod.sys, "stdout", stream):
                code = client_mod.main(["health"])
            stream.flush()
            self.assertEqual(0, code)
            self.assertEqual(native["service"], json.loads(raw.getvalue().decode("utf-8"))["service"])
        finally:
            stream.detach()
            raw.close()

    def test_follow_returns_status_error_without_repeating_the_loop(self):
        calls = []

        def opener(request, **kwargs):
            calls.append(request)
            if len(calls) == 1:
                return Response(b'{"ok":true,"events":[]}')
            if len(calls) == 2:
                raise OSError("Synthetic status reply lost")
            raise AssertionError("Follow repeated after the failed status read")

        client = client_mod.HeadlessClient("http://127.0.0.1:1", opener=opener)
        value = client.follow("known", out=io.StringIO(), wait_ms=0)
        self.assertIs(value["ok"], False)
        self.assertEqual("unreachable", value["error"])
        self.assertEqual(2, len(calls))


if __name__ == "__main__":
    unittest.main()
