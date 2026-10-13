"""HTTP and shared-carrier contracts; run on cloud compute."""
import json
import threading
import unittest
import tempfile
from pathlib import Path
import urllib.request
import urllib.parse
import urllib.error
from .server import Server
from .equipment import CommandCenterEquipment
from .core import CommandCenter
class FakeCenter:
    def __init__(self):
        self.state_dir = Path(tempfile.gettempdir())
        self.calls = []
    def state(self, refresh=False):
        return {"resources": [], "refresh": refresh}
    def tools(self):
        return {"tools": []}
    def call_tool(self, payload):
        self.calls.append(payload)
        return {"operation_id": payload["operation_id"], "status": "completed"}
    def mutate(self, kind, payload):
        self.calls.append((kind, payload))
        return {"status": "completed", "operation_id": payload["operation_id"]}
class HTTPTest(unittest.TestCase):
    def setUp(self):
        self.center = FakeCenter()
        self.server = Server(("127.0.0.1", 0), self.center)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
    def request(self, path, payload=None, headers=None):
        req = urllib.request.Request(self.base + path, data=None if payload is None else json.dumps(payload).encode(), headers={"Content-Type": "application/json", **(headers or {})})
        return urllib.request.urlopen(req, timeout=5)
    def test_manifest_and_refresh(self):
        with self.request("/api/manifest") as r:
            self.assertEqual(json.load(r)["call"], "POST /api/tools/call")
        with self.request("/api/state?refresh=1") as r:
            self.assertTrue(json.load(r)["refresh"])
    def test_same_payload_reaches_tool_gateway(self):
        payload = {"operation_id": "real-id", "name": "tool", "arguments": {"x": 1}}
        with self.request("/api/tools/call", payload) as r:
            self.assertEqual(json.load(r)["operation_id"], "real-id")
        self.assertEqual(self.center.calls, [payload])
    def test_unrelated_browser_origin_cannot_send(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.request("/api/tools/call", {"operation_id": "x"}, {"Origin": "https://unrelated.example"})
        self.assertEqual(cm.exception.code, 400)
        self.assertEqual(self.center.calls, [])
    def test_web_and_no_traversal(self):
        with self.request("/") as r:
            self.assertIn("frame-ancestors 'none'", r.headers["Content-Security-Policy"])
            self.assertIn(b"<html", r.read().lower())
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.request("/../core.py")
        self.assertEqual(cm.exception.code, 404)
    def test_peer_and_human_share_center(self):
        equipment = CommandCenterEquipment(self.center)
        self.assertIn("command_center_session", [t["name"] for t in equipment.tools()])
        equipment.call("command_center_focus", {"operation_id": "peer-focus", "objective": "TITAN"})
        self.assertEqual(self.center.calls[0][0], "focus")

class InstalledCatalogTest(unittest.TestCase):
    def test_every_combined_catalog_has_command_center_tools(self):
        from integrations.shared_equipment.services import CombinedCatalog
        class Empty:
            def tools(self, **kwargs):
                return []
        catalog = CombinedCatalog(Empty(), services=Empty())
        names = {tool["name"] for tool in catalog.tools()}
        self.assertEqual(len({name for name in names if name.startswith("command_center_")}), 19)

class FeedHTTPIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        def no_provider_calls(*_args):
            raise AssertionError("Feed metadata routes must not call an external provider")

        self.center = CommandCenter(Path(self.directory.name), fetcher=no_provider_calls)
        self.server = Server(("127.0.0.1", 0), self.center)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base = "http://127.0.0.1:" + str(self.server.server_port)

    def stop_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)

    def request_json(self, path, payload=None):
        request = urllib.request.Request(
            self.base + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_note_hide_read_original_and_restore_share_durable_state(self):
        note = {"operation_id": "http-note", "title": "Original observation",
                "body": "Useful source result", "source_url": "https://example.com/run/1",
                "source_ref": "run-1"}
        created = self.request_json("/api/feed", note)
        event_id = created["record"]["id"]
        self.assertEqual("note:http-note", event_id)
        event_path = "/api/event?event_id=" + urllib.parse.quote(event_id, safe="")
        original = self.request_json(event_path)
        self.assertFalse(original["hidden"])

        self.request_json("/api/feed/moderate", {
            "operation_id": "http-hide", "event_id": event_id,
            "action": "hide", "reason": "Duplicate derived view"})
        hidden = self.request_json(event_path)
        self.assertTrue(hidden["hidden"])
        self.assertEqual("Duplicate derived view", hidden["moderation"]["reason"])
        for key in ("title", "body", "source_url", "source_ref"):
            self.assertEqual(note[key], hidden[key])

        self.request_json("/api/feed/moderate", {
            "operation_id": "http-restore", "event_id": event_id,
            "action": "restore", "reason": "Needed for the current objective"})
        restored = self.request_json(event_path)
        self.assertFalse(restored["hidden"])
        self.assertEqual("Needed for the current objective", restored["moderation"]["reason"])
        for key in ("title", "body", "source_url", "source_ref"):
            self.assertEqual(original[key], restored[key])
        # Another center instance sees the same retained original and moderation.
        reopened = CommandCenter(Path(self.directory.name)).event(event_id)
        self.assertEqual(restored, reopened)


    def test_boolean_visibility_preserves_original_and_rejects_non_boolean(self):
        created = self.request_json("/api/feed", {
            "operation_id": "boolean-note", "title": "Retained original",
            "body": "Useful evidence", "source_ref": "source-boolean"})
        event_id = created["record"]["id"]
        event_path = "/api/event?event_id=" + urllib.parse.quote(event_id, safe="")
        original = self.request_json(event_path)
        hidden_payload = {
            "operation_id": "boolean-hide", "event_id": event_id,
            "hidden": True, "reason": "Duplicate derived entry"}
        self.request_json("/api/feed/moderate", hidden_payload)
        replay = self.request_json("/api/feed/moderate", hidden_payload)
        self.assertTrue(replay["replayed"])
        hidden = self.request_json(event_path)
        self.assertTrue(hidden["hidden"])
        self.assertEqual(original["body"], hidden["body"])
        self.request_json("/api/feed/moderate", {
            "operation_id": "boolean-restore", "event_id": event_id,
            "hidden": False, "reason": "Restore for current work"})
        restored = self.request_json(event_path)
        self.assertFalse(restored["hidden"])
        for key in ("title", "body", "source_ref"):
            self.assertEqual(original[key], restored[key])
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request_json("/api/feed/moderate", {
                "operation_id": "boolean-invalid", "event_id": event_id,
                "hidden": "false", "reason": "Invalid typed observation"})
        self.assertEqual(error.exception.code, 400)
        self.assertFalse(self.request_json(event_path)["hidden"])


if __name__ == "__main__":
    unittest.main()
