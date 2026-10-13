import base64
import importlib.util
import json
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.parse
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MODULE_PATH = Path(__file__).parent / "integrations" / "gemini_slack" / "peer_tool_gateway.py"
SPEC = importlib.util.spec_from_file_location("gemini_peer_tool_gateway", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class UpstreamHandler(BaseHTTPRequestHandler):
    replies = []
    prompts = []
    payloads = []
    pending = {}
    next_id = 0

    def log_message(self, _format, *_args):
        return

    def _send(self, value, status=200):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path in ("/", "/health"):
            self._send(
                {
                    "ok": True,
                    "mode": "fake",
                    "peers": [{"name": "TESSERA"}, {"name": "MERIDIAN"}],
                }
            )
            return
        prefix = "/v1/requests/"
        if parsed.path.startswith(prefix):
            request_id = parsed.path[len(prefix) :]
            reply = self.pending.get(request_id)
            if reply is None:
                self._send({"ok": False, "error": "request_not_found"}, status=404)
                return
            encoded = base64.b64encode(reply.encode()).decode()
            self._send(
                {
                    "ok": True,
                    "request_id": request_id,
                    "event": {
                        "request_id": request_id,
                        "status": "completed",
                        "reply": reply,
                        "reply_utf8_base64": encoded,
                    },
                }
            )
            return
        self._send({"ok": False, "error": "not_found"}, status=404)

    def do_POST(self):
        size = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(size))
        self.payloads.append(payload)
        text = base64.b64decode(payload["message_utf8_base64"]).decode()
        self.prompts.append(text)
        reply = self.replies.pop(0)
        UpstreamHandler.next_id += 1
        request_id = "up%d" % UpstreamHandler.next_id
        self.pending[request_id] = reply
        self._send(
            {
                "ok": True,
                "request_id": request_id,
                "status": "queued",
            }
        )


class McpHandler(BaseHTTPRequestHandler):
    calls = []
    tools = [
        {"name": "alpha", "description": "first", "inputSchema": {"type": "object"}},
        {
            "name": "brand_new_dynamic_tool",
            "description": "second",
            "inputSchema": {"type": "object"},
        },
    ]

    def log_message(self, _format, *_args):
        return

    def do_POST(self):
        size = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(size))
        if payload["method"] == "tools/list":
            result = {"tools": self.tools}
        else:
            arguments = payload["params"]
            self.calls.append(arguments)
            result = {
                "content": [{"type": "text", "text": "ran " + arguments["name"]}]
            }
        raw = json.dumps(
            {"jsonrpc": "2.0", "id": payload["id"], "result": result}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class Fixture:
    def __enter__(self):
        UpstreamHandler.replies = []
        UpstreamHandler.prompts = []
        UpstreamHandler.payloads = []
        UpstreamHandler.pending = {}
        UpstreamHandler.next_id = 0
        McpHandler.calls = []
        self.upstream_server = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        self.mcp_server = ThreadingHTTPServer(("127.0.0.1", 0), McpHandler)
        self.threads = []
        for server in (self.upstream_server, self.mcp_server):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.threads.append(thread)
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        upstream_url = "http://%s:%s" % self.upstream_server.server_address
        mcp_url = "http://%s:%s/mcp" % self.mcp_server.server_address
        self.upstream = module.UpstreamClient(upstream_url)
        self.catalog = module.McpCatalog(mcp_url, ttl_seconds=60)
        self.store = module.ToolCallStore(self.root / "calls.sqlite3")
        self.events = module.EventStore(self.root / "events.jsonl")
        self.loop = module.ToolLoop(
            self.upstream, self.catalog, self.store, max_steps=8
        )
        self.gateway = module.ToolGateway(
            ("127.0.0.1", 0),
            self.loop,
            self.events,
            self.upstream,
            self.catalog,
        )
        self.gateway_thread = threading.Thread(
            target=self.gateway.serve_forever, daemon=True
        )
        self.gateway_thread.start()
        self.base_url = "http://%s:%s" % self.gateway.server_address
        return self

    def __exit__(self, *_args):
        self.gateway.shutdown()
        self.gateway.server_close()
        self.gateway_thread.join(timeout=2)
        self.store.close()
        for server, thread in zip(
            (self.upstream_server, self.mcp_server), self.threads
        ):
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.directory.cleanup()

    def post(self, payload):
        request = urllib.request.Request(
            self.base_url + "/v1/message",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read())


class ToolGatewayTests(unittest.TestCase):
    @staticmethod
    def wait_terminal(fixture, request_id):
        event = None
        for _ in range(100):
            with urllib.request.urlopen(
                fixture.base_url + "/v1/requests/" + request_id,
                timeout=2,
            ) as response:
                event = json.loads(response.read())["event"]
            if event["status"] in {"completed", "error", "cancelled", "interrupted"}:
                return event
            time.sleep(0.02)
        raise AssertionError(f"request {request_id} did not complete: {event}")

    @classmethod
    def wait_for(cls, fixture, request_id):
        event = cls.wait_terminal(fixture, request_id)
        if event["status"] != "completed":
            raise AssertionError(event)
        return event

    def test_plain_reply_passes_through_and_catalog_is_dynamic(self):
        with Fixture() as fixture:
            UpstreamHandler.replies = ["plain final"]
            response = fixture.post(
                {"peer": "TESSERA", "message": "hello secret-input"}
            )
            self.assertTrue(response["ok"])
            self.assertEqual(response["reply"], "plain final")
            self.assertIn("brand_new_dynamic_tool", UpstreamHandler.prompts[0])
            self.assertEqual(McpHandler.calls, [])
            self.assertNotIn(
                "hello secret-input",
                (fixture.root / "events.jsonl").read_text(),
            )
            self.assertTrue(UpstreamHandler.payloads[0]["async"])
            self.assertNotIn("message", UpstreamHandler.payloads[0])
            latest = fixture.events.last("TESSERA")
            self.assertEqual(latest["status"], "completed")
            self.assertTrue(str(latest["upstream_request_id"]).startswith("up"))
            self.assertIn("/v1/requests/", latest["upstream_status_url"])

    def test_multiple_arbitrary_tools_feed_results_through_same_upstream(self):
        with Fixture() as fixture:
            UpstreamHandler.replies = [
                '<commons_tool_call>{"call_id":"c1","name":"alpha","arguments":{"x":1}}</commons_tool_call>',
                '<commons_tool_call>{"call_id":"c2","name":"brand_new_dynamic_tool","arguments":{"y":2}}</commons_tool_call>',
                "all done",
            ]
            response = fixture.post({"peer": "MERIDIAN", "message": "use tools"})
            self.assertEqual(response["reply"], "all done")
            self.assertEqual(
                [item["name"] for item in McpHandler.calls],
                ["alpha", "brand_new_dynamic_tool"],
            )
            self.assertIn("ran alpha", UpstreamHandler.prompts[1])
            self.assertIn("ran brand_new_dynamic_tool", UpstreamHandler.prompts[2])

    def test_malformed_envelope_gets_one_correction_turn(self):
        with Fixture() as fixture:
            UpstreamHandler.replies = [
                "<commons_tool_call>{bad}</commons_tool_call>",
                "recovered",
            ]
            response = fixture.post({"peer": "TESSERA", "message": "recover"})
            self.assertEqual(response["reply"], "recovered")
            self.assertIn("malformed", UpstreamHandler.prompts[1])

    def test_async_reply_is_retained_and_byte_safe(self):
        with Fixture() as fixture:
            UpstreamHandler.replies = ["async ✓"]
            accepted = fixture.post(
                {"peer": "MERIDIAN", "message": "later", "async": True}
            )
            request_id = accepted["request_id"]
            event = self.wait_for(fixture, request_id)
            self.assertEqual(event["status"], "completed")
            self.assertEqual(
                base64.b64decode(event["reply_utf8_base64"]).decode(),
                "async ✓",
            )
            with urllib.request.urlopen(
                fixture.base_url + "/v1/last?peer=MERIDIAN",
                timeout=2,
            ) as response:
                last = json.loads(response.read())["event"]
            self.assertEqual(last["request_id"], request_id)
            self.assertEqual(last["reply"], "async ✓")

    def test_call_id_deduplicates_within_request_without_retaining_arguments(self):
        with Fixture() as fixture:
            first = fixture.store.execute_journaled(
                "r1",
                "same",
                "alpha",
                {"secret": "do-not-store"},
                fixture.catalog.call,
            )
            second = fixture.store.execute_journaled(
                "r1",
                "same",
                "alpha",
                {"secret": "do-not-store"},
                fixture.catalog.call,
            )
            self.assertEqual(first, second)
            self.assertEqual(len(McpHandler.calls), 1)
            database = sqlite3.connect(fixture.root / "calls.sqlite3")
            dump = "\n".join(database.iterdump())
            database.close()
            self.assertNotIn("do-not-store", dump)

    def test_any_named_peer_is_admitted_without_identity_allowlisting(self):
        with Fixture() as fixture:
            UpstreamHandler.replies = ["new peer works"]
            response = fixture.post({"peer": "AURORA", "message": "hello"})
            self.assertEqual(response["peer"], "AURORA")
            self.assertEqual(response["reply"], "new peer works")

    def test_concurrent_same_peer_submissions_execute_fifo(self):
        with Fixture() as fixture:
            UpstreamHandler.replies = ["first reply", "second reply"]
            work = fixture.gateway._queue_for("AURORA")
            original_put = work.put
            first_put_entered = threading.Event()
            release_first_put = threading.Event()
            put_count = []
            count_lock = threading.Lock()

            def controlled_put(item, *args, **kwargs):
                with count_lock:
                    index = len(put_count)
                    put_count.append(item.request_id)
                if index == 0:
                    first_put_entered.set()
                    release_first_put.wait(timeout=2)
                return original_put(item, *args, **kwargs)

            work.put = controlled_put
            accepted = {}

            def submit(label, message):
                accepted[label] = fixture.post(
                    {"peer": "AURORA", "message": message, "async": True}
                )

            first_thread = threading.Thread(
                target=submit, args=("first", "first message")
            )
            second_thread = threading.Thread(
                target=submit, args=("second", "second message")
            )
            try:
                first_thread.start()
                self.assertTrue(first_put_entered.wait(timeout=2))
                second_thread.start()
                time.sleep(0.05)
                self.assertTrue(second_thread.is_alive())
            finally:
                release_first_put.set()
                first_thread.join(timeout=3)
                second_thread.join(timeout=3)
                work.put = original_put

            first = accepted["first"]
            second = accepted["second"]
            first_event = self.wait_for(fixture, first["request_id"])
            second_event = self.wait_for(fixture, second["request_id"])
            self.assertEqual(first_event["reply"], "first reply")
            self.assertEqual(second_event["reply"], "second reply")
            self.assertIn("MESSAGE:\nfirst message", UpstreamHandler.prompts[0])
            self.assertIn("MESSAGE:\nsecond message", UpstreamHandler.prompts[1])

    def test_permanently_malformed_turn_is_bounded_and_next_turn_runs(self):
        with Fixture() as fixture:
            fixture.loop.max_protocol_retries = 2
            UpstreamHandler.replies = [
                "<commons_tool_call>{bad}</commons_tool_call>",
                "<commons_tool_call>{still bad}</commons_tool_call>",
                "<commons_tool_call>{bad forever}</commons_tool_call>",
                "later turn completed",
            ]
            stuck = fixture.post(
                {"peer": "AURORA", "message": "malformed forever", "async": True}
            )
            later = fixture.post(
                {"peer": "AURORA", "message": "do not starve", "async": True}
            )
            stuck_event = self.wait_terminal(fixture, stuck["request_id"])
            later_event = self.wait_for(fixture, later["request_id"])
            self.assertEqual(stuck_event["status"], "error")
            self.assertIn("exceeded 2 malformed", stuck_event["message"])
            self.assertEqual(later_event["reply"], "later turn completed")
            self.assertIn("MESSAGE:\ndo not starve", UpstreamHandler.prompts[-1])

    def test_started_call_reports_unknown_effect_without_rerunning(self):
        with Fixture() as fixture:
            arguments = {"x": 1}
            digest = module.hashlib.sha256(
                json.dumps(
                    arguments,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
            with fixture.store._db:
                fixture.store._db.execute(
                    "INSERT INTO tool_calls VALUES(?,?,?,?,?,?,?)",
                    ("r1", "c1", "alpha", digest, "started", None, time.time()),
                )
            ran = []
            result = fixture.store.execute_journaled(
                "r1", "c1", "alpha", arguments, lambda *_args: ran.append(True)
            )
            self.assertEqual(result["error"], "tool_effect_unknown_after_interruption")
            self.assertEqual(ran, [])

    def test_tool_call_bound_rejects_seventeenth_without_executing_it(self):
        with Fixture() as fixture:
            fixture.loop.max_steps = 16
            UpstreamHandler.replies = [
                '<commons_tool_call>{"call_id":"c%d","name":"alpha","arguments":{}}</commons_tool_call>'
                % index
                for index in range(1, 18)
            ]
            with self.assertRaisesRegex(module.GatewayError, "exceeded 16"):
                fixture.loop.run("r1", "AURORA", "bounded")
            self.assertEqual(len(McpHandler.calls), 16)

    def test_restart_retains_upstream_handle_without_replay(self):
        directory = tempfile.TemporaryDirectory()
        try:
            events = module.EventStore(Path(directory.name) / "events.jsonl")
            events.append(
                request_id="local-1",
                peer="AURORA",
                status="running",
                upstream_request_id="up9",
                upstream_status_url="http://127.0.0.1:9/v1/requests/up9",
                upstream_status="running",
                upstream_terminal=False,
            )
            gateway = module.ToolGateway(
                ("127.0.0.1", 0),
                object(),
                events,
                module.UpstreamClient("http://127.0.0.1:9"),
                object(),
            )
            try:
                latest = events.request("local-1", 0)
                self.assertEqual(latest["status"], "interrupted")
                self.assertEqual(latest["upstream_request_id"], "up9")
                self.assertEqual(
                    latest["upstream_status_url"],
                    "http://127.0.0.1:9/v1/requests/up9",
                )
                self.assertEqual(latest["upstream_status"], "unknown")
                self.assertIs(latest["upstream_terminal"], False)
                self.assertIn("retained upstream handle", latest["message"])
            finally:
                gateway.server_close()
        finally:
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
