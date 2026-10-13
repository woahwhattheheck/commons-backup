"""Mail projection API: cached, bounded and read-only."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from .core import CommandCenter, CoreError
from .equipment import CommandCenterEquipment
from .server import Server
from .workstreams import WorkstreamStore

class MailIntegration(unittest.TestCase):
    def test_projection_pagination_filters_and_cache_invalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            center = CommandCenter(Path(directory))
            store = WorkstreamStore(directory)
            batch = {"operation_id": "mail-fixture", "source": {
                "id": "mail-s", "provider": "Gmail", "observed_at": "2026-09-13T00:00:00Z",
                "scope": {"mailbox": "owner@example.test"}, "coverage": {"complete": False}},
                "items": [{"id": str(n), "kind": "email", "title": "Thread " + str(n),
                           "labels": ["INBOX", "UNREAD"], "status": "received",
                           "refs": {"gmail_message_id": str(n), "gmail_thread_id": str(n), "mailbox": "owner@example.test"},
                           "metadata": {"email_ts": "2026-09-12T23:00:00Z"}}
                          for n in range(3)]}
            store.ingest(batch)
            with patch.object(center, "refresh_work", side_effect=AssertionError("must not refresh")):
                first = center.work_mail(limit=2)
                self.assertEqual(2, len(first["threads"]))
                self.assertEqual(2, first["pagination"]["next_offset"])
                self.assertFalse(first["cache"]["hit"])
                second = CommandCenterEquipment(center).call("command_center_mail", {"limit": 2, "offset": 2})
                self.assertEqual(1, len(second["threads"]))
                self.assertTrue(second["cache"]["hit"])
                self.assertEqual(1, len(center.work_mail(query="Thread 1")["threads"]))
                self.assertEqual(3, len(center.work_mail(mode="unread")["threads"]))
                first["threads"].clear()
                self.assertEqual(3, len(center.work_mail()["threads"]))
                store.ingest({**batch, "operation_id": "mail-next", "items": [
                    {**batch["items"][0], "id": "four", "refs": {"gmail_message_id": "four", "gmail_thread_id": "four", "mailbox": "owner@example.test"}}]})
                self.assertEqual(4, center.work_mail()["counts"]["threads"])
                for args in ({"limit": 0}, {"limit": True}, {"offset": -1}, {"mode": "sent"}, {"mode": []}, {"mode": {}}, {"query": "x" * 241}):
                    with self.assertRaises(CoreError):
                        center.work_mail(**args)

    def test_http_and_catalog_are_read_only_and_validate_query(self):
        with tempfile.TemporaryDirectory() as directory:
            center = CommandCenter(Path(directory))
            spec = next(t for t in CommandCenterEquipment(center).tools() if t["name"] == "command_center_mail")
            self.assertNotIn("operation_id", spec["inputSchema"]["properties"])
            server = Server(("127.0.0.1", 0), center)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            url = "http://127.0.0.1:%s/api/mail" % server.server_port
            try:
                with urllib.request.urlopen(url) as response:
                    result = json.load(response)
                self.assertEqual([], result["threads"])
                self.assertEqual(0, result["provider_requests"])
                for query in ("?limit=no", "?limit=201", "?offset=-1", "?mode=no"):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(url + query)
                    self.assertEqual(400, error.exception.code)
            finally:
                server.shutdown(); server.server_close(); thread.join()
