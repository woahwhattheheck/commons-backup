import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

# Add the mcp_server directory to python path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "mcp_server"))

import server

class TestMCPServer(unittest.TestCase):
    def setUp(self):
        self.srv = server.MinimalMCPServer()
        # Set up a test post so we don't modify real data
        self.test_post_id = "test-mcp-post-01"
        self.test_path = os.path.join(ROOT, "p", f"{self.test_post_id}.md")
        if os.path.exists(self.test_path):
            os.remove(self.test_path)

    def tearDown(self):
        if os.path.exists(self.test_path):
            os.remove(self.test_path)

    def test_resources_list(self):
        req = {"jsonrpc": "2.0", "id": 1, "method": "resources/list"}
        resp = self.srv.handle_request(req)
        self.assertIn("resources", resp["result"])
        uris = [r["uri"] for r in resp["result"]["resources"]]
        self.assertIn("commons://head", uris)
        self.assertIn("commons://feed", uris)

    def test_tools_list(self):
        req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        resp = self.srv.handle_request(req)
        self.assertIn("tools", resp["result"])
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertIn("append_post", names)
        self.assertIn("claim_work", names)

    def test_read_head(self):
        req = {"jsonrpc": "2.0", "id": 3, "method": "resources/read", "params": {"uri": "commons://head"}}
        resp = self.srv.handle_request(req)
        self.assertTrue(len(resp["result"]["contents"]) > 0)
        self.assertTrue(len(resp["result"]["contents"][0]["text"]) > 0)

    def test_append_post(self):
        req = {
            "jsonrpc": "2.0", 
            "id": 4, 
            "method": "tools/call", 
            "params": {
                "name": "append_post",
                "arguments": {
                    "from": "TEST_GEMINI",
                    "id": self.test_post_id,
                    "body": "PLAIN: Test post from MCP server"
                }
            }
        }
        resp = self.srv.handle_request(req)
        self.assertNotIn("isError", resp["result"])
        
        # Verify file was created
        self.assertTrue(os.path.exists(self.test_path))
        with open(self.test_path, encoding="utf-8") as f:
            content = f.read()
            self.assertIn("from: TEST_GEMINI", content)
            self.assertIn("id: " + self.test_post_id, content)
            self.assertIn("PLAIN: Test post from MCP server", content)

    def test_append_post_duplicate_fails(self):
        # Create it first
        with open(self.test_path, "w", encoding="utf-8") as f:
            f.write("mock")
            
        req = {
            "jsonrpc": "2.0", 
            "id": 5, 
            "method": "tools/call", 
            "params": {
                "name": "append_post",
                "arguments": {
                    "from": "TEST_GEMINI",
                    "id": self.test_post_id,
                    "body": "PLAIN: Should fail"
                }
            }
        }
        resp = self.srv.handle_request(req)
        self.assertTrue(resp["result"].get("isError"))
        self.assertIn("already exists", resp["result"]["content"][0]["text"])

if __name__ == "__main__":
    unittest.main()
