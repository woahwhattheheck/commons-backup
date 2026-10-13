"""Deathstar observation contracts, exercised in cloud CI."""
import json
import tempfile
import threading
import unittest
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from .summary import build_summary
from .core import CommandCenter
from .server import Server
from .workstreams import WorkstreamStore

NOW = "2026-09-12T23:00:00Z"
WHEN = datetime.fromisoformat(NOW.replace("Z", "+00:00"))


def source(**extra):
    return {"id": "s", "provider": "GitHub", "observed_at": NOW,
            "last_good_observed_at": NOW, "last_success_at": NOW,
            "coverage": {"complete": False}, "stale_after_seconds": 900, **extra}


def item(key="1", **extra):
    return {"id": key, "source_id": "s", "kind": "pull_request",
            "status": "open", "title": "Useful work", "last_seen_at": NOW, **extra}


class SummaryContracts(unittest.TestCase):
    def test_completed_priorities_do_not_hide_current_work(self):
        rows = [item(str(n), status="completed", owner_work={"priority": 0}) for n in range(12)]
        result = self.summarize(rows + [item("working")])
        self.assertEqual(["working"], [r["id"] for r in result["work"]["top_attention"]])

    def test_mixed_pr_references_and_unknown_identity(self):
        rows = [item("by-number", status="merged", project="Owner/Repo", refs={"number": 7, "merged_at": NOW}),
                item("by-url", status="merged", url="https://github.com/owner/repo/pull/7", refs={"merged_at": NOW}),
                item("elsewhere", status="merged", project="Owner/Other", refs={"number": 7, "merged_at": NOW}),
                item("unresolved", status="merged", refs={"merged_at": NOW})]
        result = self.summarize(rows)
        self.assertEqual(2, result["throughput"]["merged_prs"]["1h"])
        self.assertEqual(1, result["throughput"]["unresolved_identity_records"])

    def test_retained_payment_does_not_advance_on_source_refresh(self):
        rows = [item("a", kind="payment", status="pending", amount=2.5, currency="USD",
                     last_seen_at="2026-09-12T20:00:00Z", refs={"payment_id": "payment"}),
                item("b", kind="payment", status="paid", amount=2.5, currency="USD",
                     last_seen_at="2026-09-12T22:00:00Z", refs={"payment_id": "payment"})]
        result = self.summarize(rows)
        self.assertEqual("paid", result["revenue"]["observed_amounts"][0]["status"])
        rows[0]["last_seen_at"] = rows[1]["last_seen_at"]
        conflict = self.summarize(rows)
        self.assertEqual(1, conflict["revenue"]["conflicting_records"])
        self.assertEqual([], conflict["revenue"]["observed_amounts"])

    def test_budget_expiry_and_nested_metadata_are_bounded(self):
        huge = {"ignored": "PRIVATE" * 10000}
        result = self.summarize([], sources=[source(coverage={"complete": False, "pagination_remaining": huge})],
            refresh={"request_budget": {"scopes": [{"scope": "slack", "retry_not_before": "2026-09-12T22:00:00Z", "unused": huge}]},
                     "deferred_sources": [{"source_id": "s", "unused": huge}]})
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertEqual("ready", result["refresh"]["request_budget"]["scopes"][0]["state"])
        self.assertEqual(0, result["refresh"]["request_budget"]["scopes"][0]["retry_remaining_seconds"])


    def summarize(self, rows, **extra):
        return build_summary({"sources": [source()], "items": rows, **extra}, WHEN)

    def test_partial_retention_does_not_invent_current_work(self):
        result = self.summarize([item(), item("2", last_seen_at="2026-09-11T23:00:00Z")])
        self.assertEqual({"fresh": 1, "retained": 1, "stale": 0, "unknown": 0}, result["work"]["open"])
        self.assertEqual(1, result["sources"]["coverage_debt"][0]["retained_records"])

    def test_failed_attempt_does_not_freshen_old_data(self):
        result = self.summarize([item()], sources=[source(error="429",
            last_good_observed_at="2026-09-11T00:00:00Z", retained_last_good=True)])
        self.assertEqual(0, result["work"]["open"]["fresh"])
        self.assertEqual(1, result["work"]["open"]["retained"])

    def test_zero_priority_preserved_and_current_precedes_stale_unprioritized(self):
        result = self.summarize([item("stale", status="blocked", last_seen_at="old"),
             item("current"), item("zero", owner_work={"priority": 0}, last_seen_at="old")])
        self.assertEqual(["zero", "current", "stale"], [r["id"] for r in result["work"]["top_attention"]])

    def test_merge_windows_use_merged_at_never_updated_at_and_dedupe(self):
        rows = [item("1", status="merged", project="o/r", refs={"number": 7, "merged_at": "2026-09-12T22:50:00Z"}),
                item("copy", status="merged", project="o/r", refs={"number": 7, "merged_at": "2026-09-12T22:50:00Z"}),
                item("2", status="merged", updated_at=NOW)]
        result = self.summarize(rows)
        self.assertEqual({"15m": 1, "1h": 1, "24h": 1}, result["throughput"]["merged_prs"])
        self.assertEqual(1, result["throughput"]["missing_merge_timestamps"])
        self.assertEqual("observed_lower_bound", result["throughput"]["basis"])
        self.assertEqual(result["throughput"], self.summarize(rows)["throughput"])

    def test_heartbeat_is_not_claim_timestamp(self):
        result = self.summarize([item("claim", updated_at=NOW),
            item("seat", metadata={"heartbeat_at": "2026-09-10T23:00:00Z"})])
        self.assertEqual({"COLD": 1}, result["workers"]["liveness"])

    def test_payment_prices_prose_and_duplicate_observations(self):
        rows = [item("paid", kind="payment", status="paid", amount=2.5, currency="USD"),
                item("paid", kind="payment", status="paid", amount=2.5, currency="USD"),
                item("offer", kind="deal", status="paid", amount=199, currency="USD"),
                item("message", kind="slack_thread", summary="paid $900", amount=900, currency="USD")]
        result = self.summarize(rows)
        self.assertEqual([{"currency": "USD", "status": "paid", "amount": "2.5"}], result["revenue"]["observed_amounts"])
        self.assertEqual(1, result["revenue"]["records"])

    def test_bounded_output_excludes_bodies_and_preserves_unknown(self):
        result = self.summarize([item(str(n), summary="PRIVATE " * 500) for n in range(2000)])
        self.assertEqual(12, len(result["work"]["top_attention"]))
        self.assertLess(len(json.dumps(result)), 15000)
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertEqual("unknown", result["revenue"]["coverage"])
        self.assertEqual("unknown", result["workers"]["coverage"])
        self.assertEqual(0, result["provider_requests"])

    def test_unknown_observation_and_future_skew(self):
        result = self.summarize([item()], sources=[source(last_good_observed_at="2026-09-13T23:00:00Z")])
        self.assertEqual(1, result["work"]["open"]["unknown"])

    def test_http_and_equipment_are_cache_only_and_observe_new_ingest(self):
        from .equipment import CommandCenterEquipment
        with tempfile.TemporaryDirectory() as directory:
            def forbidden(*args, **kwargs):
                raise AssertionError("summary must not call a provider")
            center = CommandCenter(Path(directory), fetcher=forbidden)
            store = WorkstreamStore(directory)
            payload = {"operation_id": "summary-fixture", "source": {
                "id": "s", "provider": "GitHub", "observed_at": NOW,
                "coverage": {"complete": False}}, "items": [{"id": "1", "status": "open"}]}
            store.ingest(payload)
            with patch.object(center, "refresh_work", side_effect=forbidden):
                first = center.work_summary()
                second = CommandCenterEquipment(center).call("command_center_summary", {})
                self.assertEqual(1, first["work"]["total"])
                self.assertTrue(second["cache"]["hit"])
                store.ingest({**payload, "operation_id": "summary-next",
                              "items": [{"id": "2", "status": "open"}]})
                self.assertEqual(2, center.work_summary()["work"]["total"])
                server = Server(("127.0.0.1", 0), center)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    with urllib.request.urlopen("http://127.0.0.1:%s/api/summary" % server.server_port) as response:
                        received = json.load(response)
                    self.assertEqual(2, received["work"]["total"])
                    self.assertEqual(0, received["provider_requests"])
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()
