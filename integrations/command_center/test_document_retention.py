"""Malformed canonical rows retain source work; valid empty documents still clear.

Fixture GitHub responses exercise the actual collector, SQLite store and owner
metadata. No live document, account or provider mutation is involved.
"""
from __future__ import annotations

import base64
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from integrations.command_center.collectors import LiveCollectors
from integrations.command_center.workstreams import WorkstreamStore

SHA = "a" * 40
SPEC = {"repository": "fixture/project", "path": "catalog.json", "collections": ["features"]}
SOURCE = "github:document:fixture/project:catalog.json"
SAVED = {"id": "saved-work", "name": "Existing work", "updated_at": "2026-09-08T01:00:00Z"}


class DocumentProvider:
    def __init__(self, document):
        self.document = copy.deepcopy(document)
        self.calls = []

    def github(self, endpoint, *, method="GET"):
        if method != "GET":
            raise AssertionError("Document collection is read-only")
        self.calls.append(endpoint)
        if endpoint == "repos/fixture/project/commits/main":
            return {"sha": SHA}
        if endpoint != "repos/fixture/project/contents/catalog.json?ref=" + SHA:
            raise AssertionError("Document read must use the resolved commit")
        return {"encoding": "base64", "content": base64.b64encode(
            json.dumps(self.document).encode("utf-8")).decode("ascii")}


class DocumentRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = WorkstreamStore(self.temp.name)
        self.tick = datetime(2026, 9, 8, 2, tzinfo=timezone.utc)
        self.collect({"features": [SAVED]})
        self.item_id = self.store.state()["items"][0]["id"]
        self.store.update_work({"operation_id": "owner:keep", "source_id": SOURCE,
            "item_id": self.item_id, "priority": "high", "next_action": "Keep owner direction"})
        self.before = self.store.state()

    def collect(self, document, *, collections=None):
        self.tick += timedelta(minutes=1)
        provider = DocumentProvider(document)
        spec = copy.deepcopy(SPEC)
        if collections is not None:
            spec["collections"] = collections
        collector = LiveCollectors(self.store,
            {"github": {"enabled": False}, "documents": [spec]},
            equipment=provider, clock=lambda: self.tick.isoformat())
        return collector.collect(), provider

    def retained(self, document, *, code="document_item_shape", collections=None):
        result, provider = self.collect(document, collections=collections)
        receipt = result["receipts"][0]
        current = self.store.state()
        self.assertEqual(receipt["status"], "source_error")
        self.assertEqual((receipt["removed"], receipt["retained"]), (0, 1))
        self.assertFalse(receipt["coverage"]["complete"])
        self.assertTrue(receipt["coverage"]["pagination_remaining"])
        self.assertEqual(current["items"], self.before["items"])
        self.assertEqual(current["sources"][0]["error"], code)
        self.assertTrue(current["sources"][0]["retained_last_good"])
        self.assertEqual(current["sources"][0]["last_good_observed_at"],
                         self.before["sources"][0]["last_good_observed_at"])
        self.assertEqual(len(provider.calls), 2)
        return result

    def test_null_row_is_not_empty_document(self):
        self.retained({"features": [None]})

    def test_string_row_is_not_empty_document(self):
        self.retained({"features": ["unkeyed private source text"]})
        self.assertNotIn("unkeyed private source text", str(self.store.state()))

    def test_unkeyed_object_cannot_disappear(self):
        self.retained({"features": [{"name": "Unkeyed work"}]})

    def test_empty_object_cannot_disappear(self):
        self.retained({"features": [{}]})

    def test_false_row_cannot_disappear(self):
        self.retained({"features": [False]})

    def test_mixed_rows_do_not_partially_replace_saved_work(self):
        self.retained({"features": [{"id": "new-work", "name": "Valid new row"}, None]})

    def test_bad_later_collection_does_not_replace_earlier_source(self):
        self.retained({"features": [{"id": "new-work"}], "operations": [{}]},
                      collections=["features", "operations"])

    def test_missing_collection_keeps_existing_error(self):
        self.retained({}, code="document_collection_missing")

    def test_nonlist_collection_keeps_existing_error(self):
        self.retained({"features": {}}, code="document_collection_shape")

    def test_valid_empty_collection_can_clear_source(self):
        result, provider = self.collect({"features": []})
        self.assertEqual(result["receipts"][0]["removed"], 1)
        self.assertTrue(result["receipts"][0]["coverage"]["complete"])
        self.assertEqual(self.store.state()["items"], [])
        self.assertEqual(len(provider.calls), 2)

    def test_recovery_preserves_owner_direction_and_updates_source(self):
        self.retained({"features": [None]})
        result, _ = self.collect({"features": [{**SAVED, "name": "Updated work"}]})
        self.assertEqual(result["receipts"][0]["status"], "ingested")
        current = self.store.state()
        self.assertEqual(current["items"][0]["title"], "Updated work")
        self.assertEqual(current["items"][0]["owner_work"], self.before["items"][0]["owner_work"])
        self.assertFalse(current["sources"][0]["retained_last_good"])

    def test_alternate_id_fields_keep_existing_mapping(self):
        result, _ = self.collect({"features": [
            {"id": "normal", "name": "Normal"},
            {"subject_id": "subject", "data": {"description": "Subject"}},
            {"record_id": "record", "label": "Record"},
        ]})
        self.assertTrue(result["receipts"][0]["coverage"]["complete"])
        rows = self.store.state()["items"]
        self.assertEqual({r["id"].rsplit(":", 1)[-1] for r in rows}, {"normal", "subject", "record"})
        self.assertEqual({r["title"] for r in rows}, {"Normal", "Subject", "Record"})
        self.assertTrue(all(r["refs"]["source_sha"] == SHA for r in rows))

    def test_multiple_valid_collections_keep_collection_identity(self):
        result, provider = self.collect({"features": [{"id": "same"}], "operations": [{"id": "same"}]},
                                       collections=["features", "operations"])
        self.assertEqual(result["receipts"][0]["received"], 2)
        rows = self.store.state()["items"]
        self.assertEqual({r["kind"] for r in rows}, {"feature", "task"})
        self.assertEqual(len({r["id"] for r in rows}), 2)
        self.assertEqual(len(provider.calls), 2)


if __name__ == "__main__":
    unittest.main()
