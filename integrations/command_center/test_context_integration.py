"""Context API integration contracts. Stage privately; execute in cloud CI only."""
import copy
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

from .context_view import FILTER_LIMITS
from .core import CommandCenter, CoreError
from .equipment import CommandCenterEquipment
from .server import Server
from .workstreams import WorkstreamStore


OBSERVED = "2026-09-13T00:00:00Z"


class ContextIntegration(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.provider = Mock(side_effect=AssertionError("Context reads must not call a provider"))
        self.center = CommandCenter(Path(self.directory.name), fetcher=self.provider)
        self.store = self.center._work_store_instance()
        self.equipment = CommandCenterEquipment(self.center)
        self.refresh = self.enterContext(patch.object(
            self.center, "refresh_work", side_effect=AssertionError("No provider refresh")))
        self.auto_refresh = self.enterContext(patch.object(
            self.center, "_refresh_work_if_due", side_effect=AssertionError("No automatic refresh")))

    def tearDown(self):
        self.provider.assert_not_called()
        self.refresh.assert_not_called()
        self.auto_refresh.assert_not_called()

    def ingest(self, operation, source_id, items, provider="GitHub", store=None):
        return (store or self.store).ingest({
            "operation_id": operation,
            "source": {"id": source_id, "provider": provider, "observed_at": OBSERVED,
                       "coverage": {"complete": False}, "stale_after_seconds": 900},
            "items": items,
        })

    def seed(self):
        common = {"kind": "issue", "status": "open", "owner": "Ann",
                  "updated_at": OBSERVED, "next_action": "Review the recorded artifact"}
        self.ingest("context-a", "source-a", [
            {**common, "id": "same", "title": "Alpha repair", "metadata": {"note": "Original"}},
            {**common, "id": "a-2", "title": "Alpha second repair"},
            {**common, "id": "a-closed", "title": "Alpha closed repair", "status": "closed"},
            {**common, "id": "a-joanne", "title": "Alpha repair by another label", "owner": "Joanne"},
        ])
        self.ingest("context-b", "source-b", [
            {**common, "id": "same", "title": "Beta repair", "kind": "task", "status": "blocked"},
        ], provider="Slack")
        self.ingest("context-mail", "mail-source", [{
            "id": "m1", "kind": "email", "status": "received", "title": "Mail fixture",
            "labels": ["INBOX", "UNREAD"],
            "refs": {"gmail_message_id": "m1", "gmail_thread_id": "t1",
                     "mailbox": "owner@example.test"},
            "metadata": {"email_ts": OBSERVED},
        }], provider="Gmail")

    @staticmethod
    def identities(result):
        return [(row["source_id"], row["item_id"]) for row in result["items"]]

    @contextmanager
    def http(self):
        server = Server(("127.0.0.1", 0), self.center)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield "http://127.0.0.1:%s" % server.server_port
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    @staticmethod
    def get(base, path, **query):
        url = base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.load(response)

    def test_default_bounded_pages_reach_every_record(self):
        self.ingest("context-pages", "source-a", [
            {"id": "row-%03d" % n, "title": "Record %03d" % n, "kind": "issue",
             "status": "open", "owner": "Ann", "updated_at": OBSERVED}
            for n in range(47)])
        pages = [self.center.work_context(offset=offset) for offset in (0, 20, 40)]
        self.assertEqual([20, 20, 7], [len(page["items"]) for page in pages])
        self.assertEqual([20, 40, None], [page["pagination"]["next_offset"] for page in pages])
        self.assertEqual(47, pages[0]["counts"]["inventory_records"])
        self.assertEqual(47, pages[0]["counts"]["matching_records"])
        self.assertEqual(47, len({key for page in pages for key in self.identities(page)}))
        self.assertTrue(all(page["pagination"]["limit"] == 20 for page in pages))
        self.assertTrue(all(page["provider_requests"] == 0 for page in pages))
        self.assertEqual(47, len(self.center.work_context(limit=100)["items"]))

    def test_combined_filters_and_revision_are_selection_specific(self):
        self.seed()
        options = {"limit": 1, "query": "ALPHA", "owner": "ANN", "provider": "github",
                   "source": "source-a", "kind": "ISSUE", "status": "OPEN"}
        first = self.equipment.call("command_center_context", options)
        self.assertEqual(2, first["counts"]["matching_records"])
        self.assertEqual(1, len(first["items"]))
        self.assertEqual(1, first["pagination"]["next_offset"])
        self.assertEqual(64, len(first["revision"]))
        repeated = self.center.work_context(**options, if_revision=first["revision"])
        self.assertTrue(repeated["unchanged"])
        self.assertEqual([], repeated["items"])
        self.assertEqual(0, repeated["counts"]["returned_records"])
        self.assertEqual(1, repeated["counts"]["page_records"])
        self.assertEqual(1, repeated["omissions"]["unchanged_records"])
        second = self.center.work_context(**options, offset=1, if_revision=first["revision"])
        self.assertFalse(second["unchanged"])
        self.assertNotEqual(first["revision"], second["revision"])
        self.assertEqual({("source-a", "same"), ("source-a", "a-2")},
                         set(self.identities(first) + self.identities(second)))
        different = self.center.work_context(owner="Joanne", if_revision=first["revision"])
        self.assertFalse(different["unchanged"])
        self.assertEqual([("source-a", "a-joanne")], self.identities(different))
        self.assertEqual([], self.center.work_context(source="SOURCE-A")["items"])

    def test_detail_uses_exact_source_and_item_without_filtered_access_loss(self):
        self.seed()
        self.assertEqual([], self.center.work_context(owner="not present")["items"])
        first = self.center.work_context_item("source-a", "same")
        second = self.equipment.call("command_center_context_item",
                                     {"source_id": "source-b", "item_id": "same"})
        self.assertEqual("Alpha repair", first["item"]["title"])
        self.assertEqual("Beta repair", second["item"]["title"])
        for result, source_id in ((first, "source-a"), (second, "source-b")):
            self.assertEqual("same", result["item"]["id"])
            self.assertEqual(source_id, result["item"]["source_id"])
            self.assertEqual(source_id, result["source"]["id"])
            self.assertEqual(0, result["provider_requests"])
            self.assertIn("cache", result)
        for source_id, item_id in (("missing-source", "same"), ("source-a", "missing-item")):
            with self.subTest(source_id=source_id, item_id=item_id), self.assertRaises(CoreError) as error:
                self.center.work_context_item(source_id, item_id)
            self.assertEqual(404, error.exception.status)

    def test_malformed_core_and_tool_arguments_are_400(self):
        bad = [{"limit": value} for value in (0, 101, True, "20")]
        bad += [{"offset": value} for value in (-1, True, 1.5)]
        bad += [{"if_revision": value} for value in ({}, True, "x" * 65)]
        for name, size in FILTER_LIMITS.items():
            bad.extend(({name: []}, {name: "x" * (size + 1)}))
        for options in bad:
            with self.subTest(options=options), self.assertRaises(CoreError) as error:
                self.equipment.call("command_center_context", options)
            self.assertEqual(400, error.exception.status)
        for key in ("source_id", "item_id"):
            for value in ("", None, True, [], {}, "x" * 2001):
                options = {"source_id": "source-a", "item_id": "same", key: value}
                with self.subTest(key=key, value=value), self.assertRaises(CoreError) as error:
                    self.equipment.call("command_center_context_item", options)
                self.assertEqual(400, error.exception.status)

    def test_shared_snapshot_coalesces_views_and_expires_at_five_seconds(self):
        self.seed()
        clock = [100.0]
        with patch("integrations.command_center.core.time.monotonic", side_effect=lambda: clock[0]), \
                patch.object(self.store, "state", wraps=self.store.state) as reads:
            self.center.work_summary()
            self.center.work_mail()
            first = self.center.work_context()
            detail = self.center.work_context_item("source-a", "same")
            self.assertEqual(1, reads.call_count, "All four read surfaces share one normalized snapshot")
            self.assertTrue(first["cache"]["hit"])
            self.assertTrue(detail["cache"]["hit"])
            clock[0] = 104.9
            self.center.work_context(owner="Ann")
            self.assertEqual(1, reads.call_count)
            clock[0] = 105.0
            expired = self.center.work_context()
            self.assertEqual(2, reads.call_count)
            self.assertFalse(expired["cache"]["hit"])
            self.center.work_summary()
            self.center.work_mail()
            latest = self.center.work_context_item("source-a", "same")
            self.assertEqual(2, reads.call_count)
            self.assertEqual(detail["source"]["last_good_observed_at"],
                             latest["source"]["last_good_observed_at"])

    def test_concurrent_cold_views_share_one_state_read(self):
        self.seed()
        gate = threading.Barrier(4)
        calls = [self.center.work_summary, self.center.work_mail, self.center.work_context,
                 lambda: self.center.work_context_item("source-a", "same")]

        def read(call):
            gate.wait(timeout=5)
            return call()

        with patch("integrations.command_center.core.time.monotonic", return_value=100.0), \
                patch.object(self.store, "state", wraps=self.store.state) as reads:
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(read, calls))
            self.assertEqual(1, reads.call_count)
            self.assertTrue(all(result["provider_requests"] == 0 for result in results))

    def test_external_ingest_invalidates_all_views_without_waiting_for_ttl(self):
        self.seed()
        external = WorkstreamStore(self.directory.name)
        with patch("integrations.command_center.core.time.monotonic", return_value=100.0), \
                patch.object(self.store, "state", wraps=self.store.state) as reads:
            first = self.center.work_context(limit=1)
            self.center.work_summary()
            self.center.work_mail()
            self.assertEqual(1, reads.call_count)
            self.ingest("context-mail-new", "mail-source", [{
                "id": "m2", "kind": "email", "status": "received", "title": "New mail fixture",
                "labels": ["INBOX"],
                "refs": {"gmail_message_id": "m2", "gmail_thread_id": "t2",
                         "mailbox": "owner@example.test"},
                "metadata": {"email_ts": OBSERVED},
            }], provider="Gmail", store=external)
            changed = self.center.work_context(limit=1, if_revision=first["revision"])
            self.assertFalse(changed["unchanged"])
            self.assertNotEqual(first["revision"], changed["revision"])
            self.assertEqual(7, changed["counts"]["inventory_records"])
            self.assertEqual(7, self.center.work_summary()["work"]["total"])
            self.assertEqual(2, self.center.work_mail()["counts"]["threads"])
            self.assertEqual("m2", self.center.work_context_item("mail-source", "m2")["item"]["id"])
            self.assertEqual(2, reads.call_count, "One replacement snapshot serves every invalidated view")

    def test_returned_results_are_independent_of_shared_cached_state(self):
        self.seed()
        page = self.center.work_context(source="source-a")
        original = copy.deepcopy(page)
        detail = self.center.work_context_item("source-a", "same")
        original_detail = copy.deepcopy(detail)
        page["items"][0]["title"] = "Caller-only title"
        page["items"][0]["detail_ref"]["source_id"] = "Caller-only source"
        page["sources"][0]["coverage"]["complete"] = True
        detail["item"]["title"] = "Caller-only detail"
        detail["item"].setdefault("metadata", {})["caller_added"] = True
        detail["source"]["coverage"]["complete"] = True
        summary = self.center.work_summary()
        summary["work"]["total"] = -1
        mail = self.center.work_mail()
        mail["threads"].clear()
        again = self.center.work_context(source="source-a")
        exact = self.center.work_context_item("source-a", "same")
        self.assertEqual(original["items"], again["items"])
        self.assertEqual(original["sources"], again["sources"])
        self.assertEqual(original_detail["item"], exact["item"])
        self.assertEqual(original_detail["source"], exact["source"])
        self.assertEqual(6, self.center.work_summary()["work"]["total"])
        self.assertEqual(1, len(self.center.work_mail()["threads"]))

    def test_http_filters_revision_detail_and_catalog_are_read_only(self):
        self.seed()
        specs = {tool["name"]: tool for tool in self.equipment.tools()}
        for name in ("command_center_context", "command_center_context_item"):
            self.assertIn(name, specs)
            self.assertNotIn("operation_id", specs[name]["inputSchema"]["properties"])
            self.assertNotIn("operation_id", specs[name]["inputSchema"].get("required", []))
        self.assertEqual(100, specs["command_center_context"]["inputSchema"]["properties"]["limit"]["maximum"])
        with self.http() as base:
            query = {"limit": 1, "offset": 1, "q": "Alpha", "owner": "Ann",
                     "provider": "GitHub", "source": "source-a", "kind": "issue", "status": "open"}
            result = self.get(base, "/api/context", **query)
            direct = self.center.work_context(**{("query" if key == "q" else key): value
                                                 for key, value in query.items()})
            self.assertEqual(self.identities(direct), self.identities(result))
            self.assertEqual(2, result["counts"]["matching_records"])
            self.assertEqual(0, result["provider_requests"])
            same = self.get(base, "/api/context", **query, if_revision=result["revision"])
            self.assertTrue(same["unchanged"])
            self.assertEqual([], same["items"])
            for source_id, title in (("source-a", "Alpha repair"), ("source-b", "Beta repair")):
                detail = self.get(base, "/api/context/item", source_id=source_id, item_id="same")
                self.assertEqual(title, detail["item"]["title"])
                self.assertEqual(source_id, detail["source"]["id"])
                self.assertEqual(0, detail["provider_requests"])
            failures = [
                ("/api/context", {"limit": "no"}, 400),
                ("/api/context", {"limit": 101}, 400),
                ("/api/context", {"offset": -1}, 400),
                ("/api/context", {"q": "x" * 241}, 400),
                ("/api/context", {"owner": "x" * (FILTER_LIMITS["owner"] + 1)}, 400),
                ("/api/context", {"if_revision": "x" * 65}, 400),
                ("/api/context/item", {}, 400),
                ("/api/context/item", {"source_id": "source-a"}, 400),
                ("/api/context/item", {"source_id": "x" * 2001, "item_id": "same"}, 400),
                ("/api/context/item", {"source_id": "source-a", "item_id": "missing"}, 404),
            ]
            for path, query, code in failures:
                with self.subTest(path=path, code=code), self.assertRaises(urllib.error.HTTPError) as error:
                    self.get(base, path, **query)
                self.assertEqual(code, error.exception.code)
                error.exception.close()


if __name__ == "__main__":
    unittest.main()
