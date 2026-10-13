"""Exercise the actual HTTP API and persistent usage/ingest state."""
import json
import tempfile
import threading
import unittest
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from integrations.command_center.core import CommandCenter
from integrations.command_center.server import Server


class SwarmAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        def unavailable(*_):
            raise OSError("direct provider route unavailable")
        self.center = CommandCenter(Path(self.tmp.name), fetcher=unavailable)
        self.server = Server(("127.0.0.1", 0), self.center)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = "http://127.0.0.1:" + str(self.server.server_address[1])

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def call(self, path, value=None):
        data = None if value is None else json.dumps(value).encode()
        request = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    def ingest(self, observed):
        return self.call("/api/work/ingest", {
            "operation_id": "test-observation", "source": {
                "id": "commons-swarm:woahwhattheheck/commons", "provider": "github",
                "observed_at": observed, "scope": "one selected PR",
                "url": "https://github.com/woahwhattheheck/commons/pulls",
                "coverage": {"complete": False}},
            "items": [{"id": "pr-1", "title": "Observed work", "kind": "build",
                       "metadata": {"number": 1, "head": "a" * 40,
                                    "swarm": {"work": {"seat": "ASTRA", "family": "gpt"},
                                              "review": {"state": "WAIT_GPT"}}}}]})

    def test_absent_source_is_stale_and_read_usage_is_persistent(self):
        self.assertTrue(self.call("/health")["ok"])
        first = self.call("/api/swarm"); second = self.call("/api/swarm")
        self.assertTrue(first["stale"]); self.assertIsNone(first["swarm"])
        self.assertEqual(first["usage"]["reads"] + 1, second["usage"]["reads"])
        with self.center._db() as db:
            count = db.execute("SELECT COUNT(*) FROM records WHERE kind='usage'").fetchone()[0]
        self.assertEqual(1, count)

    def test_real_ingest_and_owner_update_are_visible_without_direct_route(self):
        stamp = datetime.now(timezone.utc).isoformat()
        self.assertTrue(self.ingest(stamp)["ok"])
        self.call("/api/work/item", {"operation_id": "test-priority", "source_id": "commons-swarm:woahwhattheheck/commons",
                  "item_id": "pr-1", "priority": 1, "next_action": "Finish actual review"})
        result = self.call("/api/swarm")
        self.assertEqual("connector-ingest", result["source_road"])
        self.assertFalse(result["coverage"]["complete"])
        self.assertFalse(result["stale"])
        self.assertEqual(1, result["swarm"]["counts"]["WAIT_GPT"])
        stored = self.center._work_store_instance().state()["items"][0]
        self.assertEqual("Finish actual review", stored["owner_work"]["next_action"])
        self.assertEqual(stamp, result["observed_at"])

    def test_old_provider_observation_is_not_refreshed_by_ingest_or_ui_read(self):
        self.ingest("2026-09-01T00:00:00Z")
        result = self.call("/api/swarm")
        self.assertTrue(result["stale"])
        self.assertEqual("2026-09-01T00:00:00Z", result["observed_at"])


if __name__ == "__main__":
    unittest.main()
