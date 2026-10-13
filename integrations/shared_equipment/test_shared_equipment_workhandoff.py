from __future__ import annotations
import sys
import tempfile
import unittest
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from integrations.shared_equipment.services import ServiceEquipment, build_capability_manifest
from integrations.shared_equipment.slack_carrier import CLOSE, OPEN, SlackEquipmentCarrier
from integrations.shared_equipment.services import CombinedCatalog
from integrations.shared_equipment.workhandoff import (
    DEFAULT_CHANNEL_ID, DEFAULT_THREAD_TS, SENDER_USER_ID, SENDER_BOT_ID, TEAM_ID,
)

class FakeEquipment(ServiceEquipment):
    def __init__(self, journal_path, *, external=False, footer=""):
        super().__init__(slack_token_loader=lambda: "secret-never-returned", workhandoff_journal_path=journal_path)
        self.external = external
        self.footer = footer
        self.patch_bytes = None
        self.file_id = "F0HANDOFF1234"
        self.filename = None
        self.message = None
        self.upload_count = 0
        self.api_calls = []
        self.fresh_reads = []
        self.chat_posts = []

    def slack(self, method, payload, *, fresh=False):
        self.api_calls.append((method, payload))
        if fresh:
            self.fresh_reads.append(method)
        if method == "auth.test":
            return {"ok": True, "team_id": TEAM_ID, "user_id": SENDER_USER_ID, "bot_id": SENDER_BOT_ID}
        if method == "conversations.info":
            shared = [TEAM_ID, "T0EXTERNAL"] if self.external else [TEAM_ID]
            return {"ok": True, "channel": {"id": payload["channel"], "context_team_id": TEAM_ID,
                "shared_team_ids": shared, "is_shared": self.external, "is_ext_shared": self.external,
                "is_org_shared": False, "is_pending_ext_shared": False,
                "pending_connected_team_ids": ["T0EXTERNAL"] if self.external else [], "is_archived": False}}
        if method == "files.getUploadURLExternal":
            self.filename = payload["filename"]
            return {"ok": True, "upload_url": "https://files.slack.com/upload/v1/test", "file_id": self.file_id}
        if method == "files.completeUploadExternal":
            self.message = {"user": SENDER_USER_ID, "ts": "1790859999.100001",
                "text": payload["initial_comment"] + self.footer,
                "files": [{"id": self.file_id, "name": self.filename}]}
            return {"ok": True, "files": [{"id": self.file_id}]}
        if method == "conversations.replies":
            root = {"user": "U0BTGV2G589", "ts": payload["ts"], "text": "Bounty team thread"}
            return {"ok": True, "messages": [root, *([self.message] if self.message else [])]}
        if method == "files.info":
            return {"ok": True, "file": {"id": self.file_id, "user": SENDER_USER_ID,
                "name": "handoff-test-op-001.patch", "title": "handoff-test-op-001.patch",
                "permalink": "https://slack.invalid/file", "url_private_download": "https://files.slack.com/files-pri/test"}}
        if method == "chat.getPermalink":
            return {"ok": True, "permalink": "https://slack.invalid/thread/message"}
        if method == "chat.postMessage":
            self.chat_posts.append(payload)
            return {"ok": True, "channel": payload["channel"], "ts": "1790861111.200002",
                    "message": {"text": payload["text"]}}
        raise AssertionError("unexpected Slack API method: " + method)

    def slack_upload_bytes(self, upload_url, body):
        self.upload_count += 1
        self.patch_bytes = body
        return {"ok": True, "bytes_uploaded": len(body)}

    def slack_download_file(self, file_info, *, max_bytes=10 * 1024 * 1024):
        return self.patch_bytes or b""


def request(**overrides):
    value = {
        "operation_id": "test-op-0001", "work_id": "cloud-work-42",
        "objective": "Move the exact candidate to the bounty team.",
        "summary": "Routes a work package to the internal team thread.",
        "patch": "diff --git a/example.py b/example.py\n+print('ready')\n",
        "tests": "18 tests passed in the applied bundle.",
        "result": "Ready for team submission.",
    }
    value.update(overrides)
    return value


class TeamWorkHandoffTests(unittest.TestCase):
    def test_combined_catalog_advertises_each_tool_once_with_dispatch_precedence(self):
        from integrations.shared_equipment.services import CombinedCatalog

        class Commons:
            def tools(self, **_kwargs):
                return [
                    {"name": "shared_name", "description": "public duplicate"},
                    {"name": "public_only", "description": "public"},
                ]
            def call(self, name, arguments):
                return {"route": "commons", "name": name}

        class Services:
            def tools(self):
                return [
                    {"name": "shared_name", "description": "private service wins"},
                    {"name": "private_only", "description": "private"},
                ]
            def call(self, name, arguments):
                return {"route": "services", "name": name}

        class Extension:
            def tools(self):
                return [{"name": "shared_name", "description": "extension wins"}]
            def call(self, name, arguments):
                return {"route": "extension", "name": name}

        catalog = CombinedCatalog(Commons(), Services())
        catalog.extensions = [Extension()]
        tools = catalog.tools()
        names = [tool["name"] for tool in tools]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(next(tool for tool in tools if tool["name"] == "shared_name")["description"],
                         "extension wins")
        self.assertEqual(catalog.call("shared_name", {})["route"], "extension")
        self.assertEqual(catalog.call("private_only", {})["route"], "services")
        self.assertEqual(catalog.call("public_only", {})["route"], "commons")

    def test_manifest_exposes_handoff_and_direct_file_fetch_to_new_peers(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = FakeEquipment(Path(tmp) / "ledger.sqlite3")
            class Catalog:
                def tools(self): return svc.tools()
                def call(self, name, args): return svc.call(name, args)
            newcomer = build_capability_manifest(catalog=Catalog(), peer="new-arrived-peer")
            another = build_capability_manifest(catalog=Catalog(), peer="another-provider")
            names = {row["name"] for row in newcomer["operations"]}
            self.assertEqual(names, {row["name"] for row in another["operations"]})
            self.assertTrue({"commons_team_workhandoff", "commons_team_workhandoff_status",
                             "slack_read_file", "credential_references", "credential_retrieve_sealed"}.issubset(names))
            self.assertFalse((Path(tmp) / "ledger.sqlite3").exists(), "tool discovery must not create a journal")

    def test_dynamic_mcp_bridge_exposes_and_dispatches_shared_workhandoff(self):
        from integrations.shared_equipment.services import _EmptyCommonsCatalog
        bridge = _EmptyCommonsCatalog()
        catalog = CombinedCatalog(bridge)
        names = {tool["name"] for tool in catalog.tools()}
        self.assertTrue({"commons_team_workhandoff", "commons_team_workhandoff_status", "slack_read_file",
                         "credential_references", "credential_retrieve_sealed"}.issubset(names))
        status = catalog.call("commons_team_workhandoff_status", {"operation_id": "new-peer-status-1"})
        self.assertEqual(status["result"]["state"], "NOT_FOUND")

    def test_internal_handoff_upload_readback_footer_and_new_peer_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = FakeEquipment(Path(tmp) / "ledger.sqlite3", footer="\nSent using Claude")
            sent = svc.call("commons_team_workhandoff", request())
            self.assertFalse(sent["isError"])
            result = sent["result"]
            self.assertEqual(result["state"], "DELIVERED")
            receipt = result["receipt"]
            self.assertTrue(receipt["sender_verified"])
            self.assertTrue(receipt["body_verified"])
            self.assertTrue(receipt["patch_verified"])
            self.assertTrue(receipt["provider_footer_present"])
            self.assertEqual(receipt["sender_user_id"], SENDER_USER_ID)
            self.assertEqual(svc.upload_count, 1)
            self.assertTrue({"auth.test", "conversations.info", "conversations.replies", "files.info"}.issubset(svc.fresh_reads))
            fetched = svc.call("slack_read_file", {"file_id": receipt["file_id"]})["result"]
            self.assertEqual(fetched["content"], request()["patch"])
            retry = svc.call("commons_team_workhandoff", request())["result"]
            self.assertTrue(retry["replayed"])
            self.assertEqual(svc.upload_count, 1)
            changed = svc.call("commons_team_workhandoff", request(patch="different"))["result"]
            self.assertEqual(changed["state"], "IDEMPOTENCY_CONFLICT")
            svc._work_handoff.close()

    def test_external_or_pending_destination_stops_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = FakeEquipment(Path(tmp) / "ledger.sqlite3", external=True)
            result = svc.call("commons_team_workhandoff", request())["result"]
            self.assertEqual(result["state"], "PUBLISHER_ROUTE_REQUIRED")
            self.assertEqual(svc.upload_count, 0)
            self.assertFalse(any(name.startswith("files.") for name, _ in svc.api_calls))

    def test_any_verified_internal_channel_is_usable_without_channel_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = FakeEquipment(Path(tmp) / "ledger.sqlite3")
            result = svc.call("commons_team_workhandoff", request(channel_id="C0TEAMALT123", thread_ts="1790860000.100001"))["result"]
            self.assertEqual(result["state"], "DELIVERED")
            self.assertEqual(result["receipt"]["channel_id"], "C0TEAMALT123")
            svc._work_handoff.close()

    def test_unknown_identity_and_malformed_sender_inputs_are_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = FakeEquipment(Path(tmp) / "ledger.sqlite3")
            result = svc.call("commons_team_workhandoff", request(author="Claude"))
            self.assertTrue(result["isError"])
            self.assertFalse(result.get("uncertain", False))
            self.assertEqual(svc.upload_count, 0)

    def test_new_peer_can_call_carrier_tool_and_fetch_shared_patch(self):
        class Calls:
            def __init__(self): self.rows = {}
            def execute_journaled(self, request_id, call_id, name, arguments, runner):
                key = (request_id, call_id)
                if key not in self.rows:
                    self.rows[key] = runner(name, arguments)
                return self.rows[key]
        class Catalog:
            def __init__(self, services): self.services = services
            def tools(self): return self.services.tools()
            def call(self, name, arguments): return self.services.call(name, arguments)
        with tempfile.TemporaryDirectory() as tmp:
            svc = FakeEquipment(Path(tmp) / "ledger.sqlite3")
            catalog = Catalog(svc)
            carrier = SlackEquipmentCarrier(catalog, Calls(),
                {"channel_id": DEFAULT_CHANNEL_ID, "thread_ts": "1788567066.179399"},
                Path(tmp) / "carrier-cursor.json")
            envelope = {"request_id": "new-peer-request-1", "call_id": "handoff-1",
                        "name": "commons_team_workhandoff", "arguments": request()}
            carrier.process({"ts": "1790861111.300003", "text": OPEN + json.dumps(envelope) + CLOSE})
            self.assertEqual(svc.upload_count, 1)
            self.assertTrue(svc.chat_posts)
            returned = svc.chat_posts[-1]["text"]
            self.assertIn('"state": "DELIVERED"', returned)
            self.assertIn('"sender_verified": true', returned)
            fetched = catalog.call("slack_read_file", {"file_id": svc.file_id})["result"]
            self.assertEqual(fetched["content"], request()["patch"])
            retry = {**envelope, "request_id": "new-peer-request-2", "call_id": "handoff-2"}
            carrier.process({"ts": "1790861111.400004", "text": OPEN + json.dumps(retry) + CLOSE})
            self.assertEqual(svc.upload_count, 1)
            svc._work_handoff.close()
            svc._work_handoff.close()

if __name__ == "__main__":
    unittest.main(verbosity=2)
