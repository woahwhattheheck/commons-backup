from __future__ import annotations

import json
import unittest
from pathlib import Path

from host.titan_hands.mcp_one import dispatch
from host.titan_hands.one_tool import TitanHandsOne


ROOT = Path(__file__).resolve().parents[3]
ENTRYPOINT = ["-m", "host.titan_hands.mcp_one"]
CLIENTS = ("codex", "chatgpt-desktop", "cursor", "claude-code", "gemini-cli")


class PeerConfigTests(unittest.TestCase):
    def _server(self, path: str) -> dict:
        document = json.loads((ROOT / path).read_text(encoding="utf-8"))
        return document["mcpServers"]["titan_hands"]

    def test_project_carriers_share_the_one_tool_entrypoint(self):
        for path in (".cursor/mcp.json", ".mcp.json", ".gemini/settings.json"):
            with self.subTest(path=path):
                server = self._server(path)
                self.assertEqual(server["command"], "python")
                self.assertEqual(server["args"], ENTRYPOINT)
                self.assertEqual(server["env"]["TITAN_HANDS_DEFAULT_TARGET"], "windows")

    def test_codex_registration_uses_the_same_entrypoint(self):
        script = (ROOT / "host" / "titan_hands" / "register_codex.ps1").read_text(encoding="utf-8")
        self.assertIn("'host.titan_hands.mcp_one'", script)
        self.assertNotIn("'host.titan_hands.mcp_server'", script)

    def test_every_local_carrier_negotiates_exactly_one_tool(self):
        router = TitanHandsOne(factories={})
        self.addCleanup(router.close)
        for index, client in enumerate(CLIENTS, start=1):
            with self.subTest(client=client):
                initialized = dispatch(
                    router,
                    {
                        "jsonrpc": "2.0",
                        "id": index,
                        "method": "initialize",
                        "params": {"clientInfo": {"name": client, "version": "proof"}},
                    },
                )
                self.assertEqual(initialized["result"]["serverInfo"]["name"], "titan-hands-one")
                listed = dispatch(router, {"jsonrpc": "2.0", "id": index, "method": "tools/list"})
                self.assertEqual([tool["name"] for tool in listed["result"]["tools"]], ["hands"])


if __name__ == "__main__":
    unittest.main()
