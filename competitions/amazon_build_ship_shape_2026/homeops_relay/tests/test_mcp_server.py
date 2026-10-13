from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request

from homeops_relay.mcp_server import (
    Dispatcher,
    MCP_PROTOCOL_VERSION,
    TOOL_CALLS_PER_WINDOW,
    _strict_json_loads,
    make_server,
)


class DispatcherTests(unittest.TestCase):
    def test_initialize_negotiates_required_protocol(self) -> None:
        dispatcher = Dispatcher()
        response = dispatcher.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "unit-test", "version": "1.0"},
                },
            }
        )
        self.assertEqual(response["result"]["protocolVersion"], MCP_PROTOCOL_VERSION)
        self.assertIn("tools", response["result"]["capabilities"])

    def test_initialize_rejects_missing_client_info(self) -> None:
        response = Dispatcher().handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {}},
            }
        )
        self.assertEqual(response["error"]["code"], -32602)

    def test_initialize_negotiates_back_to_server_version(self) -> None:
        response = Dispatcher().handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2099-01-01",
                    "capabilities": {},
                    "clientInfo": {"name": "future-client", "version": "1"},
                },
            }
        )
        self.assertEqual(response["result"]["protocolVersion"], MCP_PROTOCOL_VERSION)

    def test_tools_list_exposes_runtime_tools_and_accepts_null_cursor(self) -> None:
        dispatcher = Dispatcher()
        response = dispatcher.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"cursor": None}})
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("homeops.intake_issue", names)
        self.assertIn("homeops.request_action", names)
        self.assertIn("homeops.snapshot", names)

    def test_tools_list_rejects_unissued_cursor(self) -> None:
        response = Dispatcher().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"cursor": "made-up"}})
        self.assertEqual(response["error"]["code"], -32602)

    def test_tool_validation_error_is_mcp_tool_error(self) -> None:
        dispatcher = Dispatcher()
        response = dispatcher.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "homeops.propose_plan", "arguments": {"issue_id": "missing"}},
            }
        )
        self.assertTrue(response["result"]["isError"])
        self.assertIn("unknown issue_id", response["result"]["structuredContent"]["error"])

    def test_unknown_rpc_method(self) -> None:
        response = Dispatcher().handle({"jsonrpc": "2.0", "id": 2, "method": "nope", "params": {}})
        self.assertEqual(response["error"]["code"], -32601)

    def test_notification_has_no_response(self) -> None:
        self.assertIsNone(Dispatcher().handle({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}))

    def test_duplicate_json_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _strict_json_loads(b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}')

    def test_nonfinite_json_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _strict_json_loads(b'{"x":NaN}')


class HttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = make_server("127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(
        self,
        payload: dict,
        *,
        origin: str | None = None,
        session_id: str | None = None,
        protocol_version: str | None = None,
        accept: str = "application/json, text/event-stream",
    ) -> tuple[int, dict | None, dict[str, str]]:
        data = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json", "Accept": accept}
        if origin is not None:
            headers["Origin"] = origin
        if session_id is not None:
            headers["MCP-Session-Id"] = session_id
        if protocol_version is not None:
            headers["MCP-Protocol-Version"] = protocol_version
        request = urllib.request.Request(self.base + "/mcp", data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                body = response.read()
                return response.status, json.loads(body) if body else None, dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            body = exc.read()
            return exc.code, json.loads(body) if body else None, dict(exc.headers.items())

    def initialize(self) -> str:
        status, body, headers = self.request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "http-test", "version": "1.0"},
                },
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["protocolVersion"], MCP_PROTOCOL_VERSION)
        session_id = headers.get("MCP-Session-Id")
        self.assertTrue(session_id)
        return session_id

    def ready(self) -> str:
        session_id = self.initialize()
        status, body, _ = self.request(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            session_id=session_id,
            protocol_version=MCP_PROTOCOL_VERSION,
        )
        self.assertEqual(status, 202)
        self.assertIsNone(body)
        return session_id

    def test_http_initialize_creates_secure_session(self) -> None:
        session_id = self.initialize()
        self.assertGreaterEqual(len(session_id), 24)

    def test_origin_rejected(self) -> None:
        status, body, _ = self.request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            origin="https://evil.example",
        )
        self.assertEqual(status, 403)
        self.assertIn("Origin rejected", body["error"]["message"])

    def test_local_origin_allowed(self) -> None:
        status, body, _ = self.request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            origin="http://localhost:9000",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["protocolVersion"], MCP_PROTOCOL_VERSION)

    def test_post_requires_both_accept_types(self) -> None:
        status, body, _ = self.request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            accept="application/json",
        )
        self.assertEqual(status, 406)
        self.assertIn("Accept header", body["error"]["message"])

    def test_subsequent_request_requires_session_and_protocol_headers(self) -> None:
        session_id = self.initialize()
        status, _, _ = self.request({"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}})
        self.assertEqual(status, 400)
        status, _, _ = self.request(
            {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}},
            session_id=session_id,
        )
        self.assertEqual(status, 400)
        status, body, _ = self.request(
            {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}},
            session_id=session_id,
            protocol_version=MCP_PROTOCOL_VERSION,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["result"], {})

    def test_tools_blocked_until_initialized_notification(self) -> None:
        session_id = self.initialize()
        status, body, _ = self.request(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            session_id=session_id,
            protocol_version=MCP_PROTOCOL_VERSION,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], -32002)

    def test_end_to_end_tool_call(self) -> None:
        session_id = self.ready()
        status, issue_response, _ = self.request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "homeops.intake_issue",
                    "arguments": {
                        "title": "Outlet is warm",
                        "area": "office",
                        "severity": "URGENT",
                        "details": "Outlet plate is warm to touch",
                        "evidence": ["observation:demo"],
                    },
                },
            },
            session_id=session_id,
            protocol_version=MCP_PROTOCOL_VERSION,
        )
        self.assertEqual(status, 200)
        issue_id = issue_response["result"]["structuredContent"]["issue_id"]
        status, plan_response, _ = self.request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "homeops.propose_plan", "arguments": {"issue_id": issue_id}},
            },
            session_id=session_id,
            protocol_version=MCP_PROTOCOL_VERSION,
        )
        self.assertEqual(status, 200)
        self.assertFalse(plan_response["result"]["structuredContent"]["authority"]["external_effect"])

    def test_unknown_session_is_404(self) -> None:
        status, _, _ = self.request(
            {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}},
            session_id="not-a-real-session",
            protocol_version=MCP_PROTOCOL_VERSION,
        )
        self.assertEqual(status, 404)

    def test_delete_session(self) -> None:
        session_id = self.ready()
        request = urllib.request.Request(
            self.base + "/mcp",
            headers={"MCP-Session-Id": session_id},
            method="DELETE",
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, 204)
        status, _, _ = self.request(
            {"jsonrpc": "2.0", "id": 9, "method": "ping", "params": {}},
            session_id=session_id,
            protocol_version=MCP_PROTOCOL_VERSION,
        )
        self.assertEqual(status, 404)

    def test_rate_limit_is_session_scoped_and_fail_closed(self) -> None:
        session_id = self.ready()
        for idx in range(TOOL_CALLS_PER_WINDOW):
            self.assertTrue(self.server.permit_tool_call(session_id, now=1000.0 + idx * 0.001))
        self.assertFalse(self.server.permit_tool_call(session_id, now=1001.0))
        self.assertTrue(self.server.permit_tool_call(session_id, now=1061.0))

    def test_healthz(self) -> None:
        with urllib.request.urlopen(self.base + "/healthz", timeout=3) as response:
            body = json.loads(response.read())
        self.assertEqual(response.status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["protocolVersion"], MCP_PROTOCOL_VERSION)

    def test_mcp_get_is_method_not_allowed_and_origin_checked(self) -> None:
        request = urllib.request.Request(
            self.base + "/mcp",
            headers={"Accept": "text/event-stream", "Origin": "http://localhost:9999"},
            method="GET",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(ctx.exception.code, 405)

        request = urllib.request.Request(
            self.base + "/mcp",
            headers={"Accept": "text/event-stream", "Origin": "https://evil.example"},
            method="GET",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
