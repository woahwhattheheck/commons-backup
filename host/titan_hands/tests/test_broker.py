from __future__ import annotations

import unittest

from host.titan_hands.broker import TitanHandsBroker
from host.titan_hands.mcp_server import dispatch


class FakeServer:
    def __init__(self, platform):
        self.platform = platform
        self.closed = False

    def handle(self, request):
        return {"ok": True, "kind": request["op"], "platform": self.platform}

    def close(self):
        self.closed = True


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.windows = FakeServer("windows")
        self.android = FakeServer("android")
        self.broker = TitanHandsBroker(
            factories={"windows": lambda: self.windows, "android": lambda: self.android}
        )

    def tearDown(self):
        self.broker.close()

    def test_routes_target_and_defaults_to_windows(self):
        self.assertEqual(self.broker.handle({"op": "observe"})["platform"], "windows")
        self.assertEqual(
            self.broker.handle({"op": "observe", "target": "android"})["platform"], "android"
        )

    def test_target_catalog_contains_both_adapters(self):
        result = self.broker.handle({"op": "targets"})
        self.assertEqual([target["target"] for target in result["targets"]], ["android", "windows"])

    def test_mcp_advertises_instructions_and_five_tools(self):
        initialized = dispatch(
            self.broker, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        self.assertIn("semantic", initialized["result"]["instructions"])
        listed = dispatch(self.broker, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(len(listed["result"]["tools"]), 5)
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
        action_schema = tools["hands_act"]["inputSchema"]["properties"]["action"]
        self.assertIn("type", action_schema["required"])
        self.assertIn("file", action_schema["properties"])
        self.assertIn("package", action_schema["properties"])


if __name__ == "__main__":
    unittest.main()
