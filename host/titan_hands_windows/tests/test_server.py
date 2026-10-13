from __future__ import annotations

import unittest

from host.titan_hands_windows.mcp_server import dispatch
from host.titan_hands_windows.server import TitanHandsServer


class FakeBackend:
    def __init__(self):
        self.name = "Idle"
        self.closed = False

    def request(self, message):
        op = message.get("op")
        if op == "capabilities":
            return {"ok": True, "actions": ["invoke"]}
        if op == "snapshot":
            return {
                "ok": True,
                "nodes": [{"id": "button", "role": "Button", "name": self.name}],
                "focus_id": "button",
            }
        if op == "action":
            self.name = "Done"
            return {"ok": True, "kind": "action_outcome", "action": message["action"]["type"]}
        if op == "capture":
            return {"ok": True, "kind": "pixel_capture", "pixel_ref": "shot.png"}
        raise AssertionError(message)

    def close(self):
        self.closed = True


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.server = TitanHandsServer(self.backend)

    def tearDown(self):
        self.server.close()

    def test_action_returns_resulting_delta(self):
        self.server.handle({"op": "observe"})
        result = self.server.handle({"op": "act", "action": {"type": "invoke", "id": "button"}})
        self.assertTrue(result["ok"])
        self.assertEqual(result["observation"]["updated"][0]["name"], "Done")

    def test_mcp_lists_and_calls_tools(self):
        listed = dispatch(self.server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertIn("hands_observe", [tool["name"] for tool in listed["result"]["tools"]])
        called = dispatch(
            self.server,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "hands_observe", "arguments": {}},
            },
        )
        self.assertFalse(called["result"]["isError"])

    def test_unknown_operation_is_typed(self):
        result = self.server.handle({"op": "mystery"})
        self.assertEqual(result["failure_reason"], "UNKNOWN_OPERATION")


if __name__ == "__main__":
    unittest.main()
