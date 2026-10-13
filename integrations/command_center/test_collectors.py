"""Collector behavior tests: synthetic providers only, intended for cloud CI."""
import base64
import copy
import json
import threading
import tempfile
import time
import unittest
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from integrations.command_center.collectors import LiveCollectors
from integrations.command_center.workstreams import WorkstreamStore

SHA = "a" * 40
OBSERVED = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class RecordingStore:
    def __init__(self):
        self.batches = []

    def ingest(self, payload):
        self.batches.append(copy.deepcopy(payload))
        return {"ok": True, "source_id": payload["source"]["id"]}

    def source(self, source_id):
        return next(batch for batch in self.batches if batch["source"]["id"] == source_id)


class FakeEquipment:
    def __init__(self):
        self.requests = []
        self.fail_slack = False
        self.fail_search = False
        self.page_full = False
        self.incomplete_search = False
        self.concurrent = 0
        self.peak = 0
        self.lock = threading.Lock()
        self.document = {"features": [
            {"id": "f1", "name": "Actual feature", "rollup": "SOURCE_BUILT",
             "live_status": "UNKNOWN", "test_status": "TESTS_PRESENT",
             "owner_subsystem": "sales", "capability": "A source feature",
             "next_gap": "Connect the existing inbox", "last_change": "2026-01-01T00:00:00Z"}
        ], "sessions": [
            {"id": "vm1", "label": "Existing VM", "status": "observed",
             "observed_at": OBSERVED, "cpu": 9, "objective": "Owner's current work"}
        ]}

    def github(self, endpoint, *, method="GET"):
        self.requests.append((method, endpoint))
        if method != "GET":
            raise AssertionError("Collector attempted a provider write.")
        parsed = urlsplit("/" + endpoint)
        path, query = parsed.path[1:], parse_qs(parsed.query)
        if path == "user":
            return {"login": "operator"}
        if path == "user/repos":
            return [{"full_name": "operator/alpha", "owner": {"login": "operator"},
                     "html_url": "https://github.com/operator/alpha", "pushed_at": OBSERVED,
                     "default_branch": "main", "archived": False, "open_issues_count": 3}]
        if path == "search/issues":
            if self.fail_search:
                raise TimeoutError("Private transport detail must not be saved")
            owner = "operator/alpha" if "user:operator" in query["q"][0] else "external/project"
            rows = [{"id": 1 if owner.startswith("external") else 2, "number": 7,
                "repository_url": "https://api.github.com/repos/" + owner,
                "html_url": "https://github.com/" + owner + "/pull/7",
                "title": "Existing work", "body": "Current PR contents",
                "state": "closed", "pull_request": {}, "updated_at": OBSERVED,
                "user": {"login": "operator"}, "labels": [], "assignees": []}]
            return {"total_count": 1, "incomplete_results": self.incomplete_search, "items": rows}
        if path.endswith("/actions/runs"):
            repo = path.removeprefix("repos/").removesuffix("/actions/runs")
            return {"total_count": 1, "workflow_runs": [
                {"id": 99, "display_title": "Actual build", "name": "Unit checks",
                 "status": "completed", "conclusion": "failure", "updated_at": OBSERVED,
                 "html_url": "https://github.com/" + repo + "/actions/runs/99",
                 "actor": {"login": "operator"}, "head_sha": SHA, "run_attempt": 2}]}
        if "/commits/" in path:
            return {"sha": SHA}
        if "/contents/" in path:
            if query.get("ref") != [SHA]:
                raise AssertionError("Document read was not pinned to fetched commit.")
            return {"encoding": "base64", "sha": "b" * 40,
                    "content": base64.b64encode(json.dumps(self.document).encode()).decode()}
        raise AssertionError("Unexpected GET " + endpoint)

    def slack(self, method, payload):
        self.requests.append((method, copy.deepcopy(payload)))
        if method != "conversations.history":
            raise AssertionError("Unexpected Slack method.")
        with self.lock:
            self.concurrent += 1
            self.peak = max(self.peak, self.concurrent)
        try:
            time.sleep(0.01)
            if self.fail_slack:
                return {"ok": False, "error": "not_in_channel"}
            return {"ok": True, "messages": [
                {"type": "message", "subtype": "channel_join", "ts": "1788815000.000001",
                 "text": "joined"},
                {"type": "message", "ts": "1788810000.123456", "user": "U1",
                 "text": "Shipped source\nActual work details", "reply_count": 2,
                 "latest_reply": "1788814000.123456", "edited": {"ts": "1788811000.123456"}}
            ], "has_more": self.page_full,
               "response_metadata": {"next_cursor": "next-page" if self.page_full else ""}}
        finally:
            with self.lock:
                self.concurrent -= 1


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.store, self.provider = RecordingStore(), FakeEquipment()

    def collect(self, config):
        return LiveCollectors(self.store, config, equipment=self.provider,
                              clock=lambda: OBSERVED).collect()

    def test_current_work_crosses_owned_repositories_and_external_prs(self):
        result = self.collect({"github": {"max_action_repositories": 3}})
        prs = self.store.source("github:prs")["items"]
        self.assertEqual({"operator/alpha", "external/project"}, {row["project"] for row in prs})
        self.assertTrue(all(row["status"] == "closed" for row in prs))
        self.assertTrue(all(row["summary"] == "Current PR contents" for row in prs))
        builds = [row for batch in self.store.batches for row in batch["items"] if row["kind"] == "build"]
        self.assertEqual({"operator/alpha", "external/project"}, {row["project"] for row in builds})
        self.assertTrue(all(row["status"] == "failure" and row["refs"]["run_attempt"] == 2 for row in builds))
        self.assertTrue(all(method == "GET" for method, _ in self.provider.requests))
        self.assertGreater(result["items_observed"], 0)

    def test_action_repository_cap_names_omitted_work_and_search_caps_stay_visible(self):
        self.provider.incomplete_search = True
        self.collect({"github": {"max_action_repositories": 1}})
        coverage = self.store.source("github:repositories")["source"]["metadata"]
        self.assertEqual(1, len(coverage["action_repositories_selected"]))
        self.assertEqual(1, len(coverage["action_repositories_pending"]))
        self.assertFalse(self.store.source("github:prs")["source"]["coverage"]["complete"])

    def test_slack_housekeeping_is_excluded_and_original_thread_details_preserved(self):
        self.collect({"github": {"enabled": False}, "slack": {
            "workspace_url": "https://workspace.slack.com", "channels": [{"id": "C1", "label": "builds"}]}})
        batch = self.store.source("slack:C1")
        self.assertEqual(1, len(batch["items"]))
        item = batch["items"][0]
        self.assertEqual("slack:C1:1788810000.123456", item["id"])
        self.assertEqual("U1", item["owner"])
        self.assertEqual("slack_thread", item["kind"])
        self.assertEqual("https://workspace.slack.com/archives/C1/p1788810000123456", item["url"])
        self.assertIn("Actual work details", item["summary"])
        self.assertEqual(2, item["refs"]["reply_count"])
        self.assertNotEqual(OBSERVED, item["updated_at"])
        coverage = batch["source"]["coverage"]
        self.assertTrue(batch["source"]["metadata"]["history_complete"])
        self.assertFalse(coverage["complete"])
        self.assertEqual("1788810000.123456", batch["source"]["metadata"]["threads_pending"][0]["thread_ts"])

    def test_slack_page_cap_and_read_failure_never_publish_empty_complete_snapshot(self):
        config = {"github": {"enabled": False}, "max_pages": 1, "slack": {
            "channels": [{"id": "C1"}]}}
        self.provider.page_full = True
        self.collect(config)
        coverage = self.store.source("slack:C1")["source"]["coverage"]
        self.assertFalse(coverage["complete"])
        self.assertEqual("next-page", self.store.source("slack:C1")["source"]["metadata"]["next_cursor"])
        self.store.batches.clear()
        self.provider.fail_slack = True
        self.collect(config)
        failed = self.store.source("slack:C1")
        self.assertEqual("error", failed["source"]["status"])
        self.assertEqual("not_in_channel", failed["source"]["error"])
        self.assertFalse(failed["source"]["coverage"]["complete"])
        self.assertEqual([], failed["items"])

    def test_source_activity_summary_ignores_newer_metadata_timestamp(self):
        collector = LiveCollectors(self.store, {"github": {"enabled": False}},
                                   equipment=self.provider, clock=lambda: OBSERVED)
        source = collector._source("synthetic", "GitHub", "Synthetic", {"scope": "test"})
        batch = collector._batch(source, [{
            "id": "work", "updated_at": "2026-09-07T21:00:00Z",
            "activity_observed_at": "2026-09-07T20:00:00Z",
        }])
        self.assertEqual("2026-09-07T20:00:00Z", batch["source"]["activity_as_of"])
        metadata_only = collector._batch(source, [{
            "id": "metadata-only", "updated_at": "2026-09-07T21:00:00Z",
            "activity_observed_at": None,
        }])
        self.assertIsNone(metadata_only["source"]["activity_as_of"])

    def test_canonical_feature_and_vm_freshness_remain_source_grounded(self):
        self.collect({"github": {"enabled": False}, "documents": [{
            "repository": "operator/alpha", "path": "feature-tracker.json",
            "collections": ["features", "sessions"], "project": "Whole operation"}]})
        batch = self.store.source("github:document:operator/alpha:feature-tracker.json")
        feature, vm = batch["items"]
        self.assertEqual("SOURCE_BUILT", feature["status"])
        self.assertEqual("UNKNOWN", feature["refs"]["live_status"])
        self.assertEqual("Connect the existing inbox", feature["next_action"])
        self.assertEqual("sales", feature["owner"])
        self.assertIn("/blob/" + SHA + "/", feature["url"])
        self.assertEqual("2026-01-01T00:00:00Z", feature["updated_at"])
        self.assertIsNone(vm["activity_observed_at"])
        self.assertIsNone(vm["updated_at"])
        self.assertEqual(OBSERVED, vm["refs"]["resource_observed_at"])
        self.assertEqual("2026-01-01T00:00:00Z", batch["source"]["activity_as_of"])

    def test_missing_document_collection_is_visible_error_not_false_empty_success(self):
        self.collect({"github": {"enabled": False}, "documents": [{
            "repository": "operator/alpha", "path": "adapter.json", "collections": ["missing"]}]})
        source = self.store.batches[0]["source"]
        self.assertEqual("document_collection_missing", source["error"])
        self.assertFalse(source["coverage"]["complete"])

    def test_source_failure_and_recovery_keep_identical_scope_and_private_errors_out(self):
        self.provider.fail_search = True
        self.collect({"github": {"max_action_repositories": 1}})
        failed = self.store.source("github:prs")
        self.assertEqual("TimeoutError", failed["source"]["error"])
        self.assertFalse(failed["source"]["coverage"]["complete"])
        self.assertNotIn("Private transport", json.dumps(failed))
        self.store.batches.clear()
        self.provider.fail_search = False
        self.collect({"github": {"max_action_repositories": 1}})
        recovered = self.store.source("github:prs")
        self.assertEqual(failed["source"]["scope"], recovered["source"]["scope"])
        self.assertEqual("live", recovered["source"]["status"])
        self.assertTrue(recovered["items"])

    def test_actual_store_accepts_collector_payloads_and_retains_work_after_provider_failure(self):
        config = {"github": {"max_action_repositories": 1},
                  "slack": {"channels": [{"id": "C1"}]}}
        with tempfile.TemporaryDirectory() as directory:
            store = WorkstreamStore(directory)
            collector = LiveCollectors(store, config, equipment=self.provider,
                                       clock=lambda: OBSERVED)
            first = collector.collect()
            self.assertTrue(first["receipts"])
            self.assertTrue(all(receipt["ok"] for receipt in first["receipts"]))
            self.provider.fail_slack = True
            second = collector.collect()
            failed = next(receipt for receipt in second["receipts"]
                          if receipt["source_id"] == "slack:C1")
            self.assertEqual("source_error", failed["status"])
            self.assertEqual(1, failed["retained"])
            self.assertEqual(0, failed["removed"])

    def test_cooperative_deadline_and_cancellation_stop_new_provider_calls(self):
        config = {"refresh_deadline_seconds": 1,
                  "slack": {"channels": [{"id": "C1"}]}}
        ticks = iter(range(0, 100, 2))
        with patch("integrations.command_center.collectors.monotonic",
                   side_effect=lambda: next(ticks)):
            result = self.collect(config)
        self.assertEqual([], self.provider.requests)
        self.assertTrue(all(source["error"] == "refresh_deadline_reached"
                            for source in result["sources"]))
        stopped = threading.Event()
        stopped.set()
        result = LiveCollectors(self.store, config, equipment=self.provider,
                                cancel_event=stopped).collect()
        self.assertEqual([], self.provider.requests)
        self.assertTrue(all(source["error"] == "refresh_cancelled"
                            for source in result["sources"]))

    def test_provider_concurrency_is_bounded_and_no_connector_is_fabricated(self):
        self.collect({"github": {"enabled": False}, "max_workers": 3, "slack": {
            "channels": [{"id": "C" + str(index)} for index in range(8)]}})
        self.assertGreater(self.provider.peak, 1)
        self.assertLessEqual(self.provider.peak, 3)
        self.assertEqual(8, len(self.store.batches))
        self.assertTrue(all(batch["source"]["provider"] == "Slack" for batch in self.store.batches))
        self.assertFalse(any("gmail" in str(request).lower() for request in self.provider.requests))
        with self.assertRaises(ValueError):
            LiveCollectors(self.store, {"max_workers": 5}, equipment=self.provider)


    def test_default_equipment_uses_provider_io(self):
        from integrations.shared_equipment.provider_io import GitHubSlackEquipment
        collector = LiveCollectors(self.store, {"github": {"enabled": False}, "slack": {"channels": []}})
        self.assertIsInstance(collector.equipment, GitHubSlackEquipment)
        self.assertTrue(callable(collector.equipment.github))
        self.assertTrue(callable(collector.equipment.slack))

if __name__ == "__main__":
    unittest.main()
