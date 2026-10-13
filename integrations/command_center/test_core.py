"""Meaningful backend tests. Run in cloud CI, not on the owner workstation."""
import copy
import json
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from integrations.command_center.core import CommandCenter, CoreError


SHA = "a" * 40


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.posts = []
        self.fail_sources = False
        self.fail_head = False
        self.fail_health = False
        self.uncertain_post = False
        self.tool_names = ["example_echo", "vault_retrieve_sealed"]
        self.result = {"ok": True, "result": {"ok": True, "value": "returned only to caller"}}
        self.adapter_sessions = []
        self.uptime_seconds = 1
        self.sha = SHA

    def __call__(self, method, url, payload=None):
        self.calls.append((method, url))
        if method == "POST":
            self.posts.append(copy.deepcopy(payload))
            if self.uncertain_post:
                # The request reached the provider; the response was lost.
                raise TimeoutError("secret detail must not appear in stored error")
            return copy.deepcopy(self.result)
        if url.endswith("/commits/main"):
            if self.fail_head:
                raise urllib.error.URLError("sensitive transport details")
            return {"sha": self.sha}
        if "raw.githubusercontent.com" in url:
            if self.fail_sources:
                raise TimeoutError("private request detail")
            if url.endswith("RESOURCE_LEDGER.json"):
                return {"snapshot": {"observed_at": "2026-09-01T00:00:00Z"},
                        "surfaces": [{"name": "cloud-session-vms", "kind": "COMPUTE",
                                      "capacity": "OWNER_REPORTED_IN_USE"}]}
            if url.endswith("connected_capabilities.json"):
                return {"providers": [{"id": "github", "capacity": "LIVE"}]}
            if url.endswith("/adapter.json"):
                return {"schema": "titan-command-center/v1", "status": "available",
                        "sessions": copy.deepcopy(self.adapter_sessions)}
        if url.endswith("/v1/tools"):
            return {"tools": [
                {"name": name, "description": "An existing shared tool.",
                 "inputSchema": {"type": "object", "properties": {
                     "value": {"type": "string", "default": "not-persisted"}}}}
                for name in self.tool_names]}
        if url.endswith("/health"):
            if self.fail_health:
                raise TimeoutError("health request details")
            return {"ok": True, "service": "shared-equipment",
                    "uptime_seconds": self.uptime_seconds,
                    "sensitive_extra": "not-persisted"}
        raise AssertionError("Unexpected provider request " + url)


class CommandCenterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.provider = FakeProvider()
        self.center = CommandCenter(self.path, fetcher=self.provider)

    def operation(self, operation_id="unit-tool-1", value="hello"):
        return {"operation_id": operation_id, "name": "example_echo",
                "arguments": {"value": value}}

    def test_tool_operation_is_durable_and_exactly_once_across_instances(self):
        first = self.center.call_tool(self.operation())
        second_center = CommandCenter(self.path, fetcher=self.provider)
        second = second_center.call_tool(self.operation())
        self.assertEqual("succeeded", first["status"])
        self.assertTrue(first["result_available"])
        self.assertTrue(second["replayed"])
        self.assertFalse(second["result_available"])
        self.assertIsNone(second["result"])
        self.assertEqual(1, len(self.provider.posts))
        self.assertEqual("command-center", self.provider.posts[0]["request_id"])
        self.assertEqual("unit-tool-1", self.provider.posts[0]["call_id"])
        self.assertNotIn("arguments", second["operation"])

    def test_same_id_with_changed_arguments_conflicts_without_dispatch(self):
        self.center.call_tool(self.operation())
        with self.assertRaises(CoreError) as caught:
            self.center.call_tool(self.operation(value="different"))
        self.assertEqual(409, caught.exception.status)
        self.assertEqual(1, len(self.provider.posts))

    def test_lost_response_is_uncertain_and_never_replayed(self):
        self.provider.uncertain_post = True
        first = self.center.call_tool(self.operation())
        self.provider.uncertain_post = False
        second = CommandCenter(self.path, fetcher=self.provider).call_tool(self.operation())
        self.assertEqual("uncertain", first["status"])
        self.assertEqual("uncertain", second["status"])
        self.assertTrue(second["replayed"])
        self.assertTrue(second["retry_blocked"])
        self.assertEqual(1, len(self.provider.posts))
        self.assertNotIn("secret detail", json.dumps(second))

    def test_gateway_uncertain_wins_over_ok_and_pending_is_not_success(self):
        self.provider.result = {"ok": True, "uncertain": True,
                                "result": {"status": "RECEIVED"}}
        result = self.center.call_tool(self.operation())
        self.assertEqual("uncertain", result["status"])
        self.provider.result = {"ok": True, "result": {
            "content": [{"type": "text", "text": json.dumps({"state": "RECEIVED"})}]}}
        result = self.center.call_tool(self.operation("unit-tool-2"))
        self.assertEqual("pending", result["status"])
        self.assertFalse(result["operation"]["summary"]["execution_complete"])
        self.provider.result = {"ok": False, "result": {"ok": False}}
        result = self.center.call_tool(self.operation("unit-tool-3"))
        self.assertEqual("failed", result["status"])

    def test_tool_secrets_never_enter_persistent_state(self):
        secret_argument = "unit-test-secret-argument-783624"
        secret_result = "unit-test-secret-result-927356"
        self.provider.result = {"ok": True, "result": {"secret": secret_result}}
        result = self.center.call_tool(self.operation(value=secret_argument))
        self.assertIn(secret_result, json.dumps(result))
        # Ordinary state and SQLite rows contain hashes/summaries, never tool bodies.
        state = self.center.state()
        serialized = json.dumps(state)
        with sqlite3.connect(str(self.center.database)) as db:
            dump = "\n".join(db.iterdump())
        for secret in (secret_argument, secret_result):
            self.assertNotIn(secret, serialized)
            self.assertNotIn(secret, dump)
        self.assertNotIn("not-persisted", dump)

    def test_pinned_sources_keep_last_good_data_on_failure_then_recover(self):
        first = self.center.state(refresh=True)
        original = next(s for s in first["sources"] if s["id"] == "resource-ledger")
        self.assertEqual("live", original["status"])
        self.provider.fail_sources = True
        failed = self.center.state(refresh=True)
        stale = next(s for s in failed["sources"] if s["id"] == "resource-ledger")
        self.assertEqual("stale", stale["status"])
        self.assertEqual(original["data"], stale["data"])
        self.assertEqual(original["observed_at"], stale["observed_at"])
        self.assertEqual(SHA, stale["sha"])
        self.assertNotIn("private request detail", stale["error"])
        self.assertEqual("cloud-session-vms", failed["resources"][0]["id"])
        self.provider.fail_sources = False
        recovered = self.center.state(refresh=True)
        fresh = next(s for s in recovered["sources"] if s["id"] == "resource-ledger")
        self.assertEqual("live", fresh["status"])
        self.assertIsNone(fresh["error"])
        raw_urls = [url for _, url in self.provider.calls if "raw.githubusercontent.com" in url]
        self.assertTrue(raw_urls)
        self.assertTrue(all("/" + SHA + "/" in url for url in raw_urls))

    def test_failed_head_does_not_read_unpinned_main_sources(self):
        self.center.state(refresh=True)
        self.provider.fail_head = True
        count = len([url for _, url in self.provider.calls if "raw.githubusercontent.com" in url])
        state = self.center.state(refresh=True)
        after = len([url for _, url in self.provider.calls if "raw.githubusercontent.com" in url])
        self.assertEqual(count, after)
        self.assertEqual("stale", next(s for s in state["sources"]
                                      if s["id"] == "github-main")["status"])

    def test_source_feed_tracks_changes_while_refresh_clocks_keep_advancing(self):
        def refresh(minute):
            with patch("integrations.command_center.core._now",
                       return_value="2026-09-07T01:%02d:00Z" % minute):
                return self.center.state(refresh=True)

        def events(state):
            return {event["id"]: event for event in state["feed"]
                    if event["kind"] == "source"}

        initial = refresh(1)
        originals = events(initial)
        self.provider.uptime_seconds = 62
        unchanged = refresh(2)
        self.assertEqual(originals, events(unchanged))
        for source in unchanged["sources"]:
            self.assertEqual("2026-09-07T01:02:00Z", source["attempted_at"])
            self.assertEqual("2026-09-07T01:02:00Z", source["observed_at"])
        runtime = self.center._source("runtime:shared-equipment")
        self.assertEqual("2026-09-07T01:02:00Z", runtime["data"]["tools_observed_at"])
        self.assertEqual("2026-09-07T01:02:00Z", runtime["data"]["health_observed_at"])
        self.assertEqual(62, runtime["data"]["health"]["uptime_seconds"])

        self.provider.tool_names.append("new_shared_tool")
        changed = refresh(3)
        added = [event for event_id, event in events(changed).items()
                 if event_id not in originals]
        self.assertEqual(1, len(added))
        self.assertEqual(runtime["id"], added[0]["source_id"])
        self.assertIn("new_shared_tool", added[0]["snapshot"]["tool_names"])

        self.provider.fail_health = True
        failed = refresh(4)
        failed_events = events(failed)
        self.assertEqual(len(originals) + 2, len(failed_events))
        failure = next(event for event_id, event in failed_events.items()
                       if event_id not in events(changed))
        self.assertEqual("degraded", failure["source_status"])
        self.assertIn("health:", failure["body"])
        repeated = refresh(5)
        self.assertEqual(failed_events, events(repeated))
        failed_runtime = self.center._source(runtime["id"])
        self.assertEqual("2026-09-07T01:05:00Z", failed_runtime["attempted_at"])

        self.provider.fail_health = False
        recovered = refresh(6)
        recovery = [event for event_id, event in events(recovered).items()
                    if event_id not in failed_events]
        self.assertEqual(1, len(recovery))
        self.assertEqual("live", recovery[0]["source_status"])
        self.assertEqual(len(originals) + 3, len(events(recovered)))
        for event_id, original in originals.items():
            self.assertEqual(original, events(recovered)[event_id])

        # A pinned revision is a useful new original link, even with equal content.
        self.provider.sha = "b" * 40
        revision = refresh(7)
        revision_events = [event for event_id, event in events(revision).items()
                           if event_id not in events(recovered)]
        self.assertTrue(revision_events)
        self.assertNotIn(runtime["id"], {event["source_id"] for event in revision_events})
        self.assertTrue(all(event["snapshot"]["sha"] == self.provider.sha
                            for event in revision_events))

    def test_state_poll_uses_ttl_and_expired_observation_refreshes(self):
        self.center.state()
        initial_requests = len(self.provider.calls)
        self.center.state()
        self.assertEqual(initial_requests, len(self.provider.calls))
        with sqlite3.connect(str(self.center.database)) as db:
            db.execute("UPDATE sources SET attempted_at='2000-01-01T00:00:00Z'")
        self.center.state()
        self.assertGreater(len(self.provider.calls), initial_requests)

    def test_catalog_is_dynamic_and_health_failure_does_not_gate_current_tools(self):
        self.assertEqual(2, len(self.center.tools()["tools"]))
        self.provider.tool_names.append("new_shared_tool")
        self.assertIn("new_shared_tool", {t["name"] for t in self.center.tools()["tools"]})
        self.provider.fail_health = True
        result = self.center.call_tool(self.operation())
        self.assertEqual("succeeded", result["status"])
        self.assertEqual(1, len(self.provider.posts))
        self.provider.tool_names = []
        with self.assertRaises(CoreError) as caught:
            self.center.call_tool(self.operation("unit-tool-removed"))
        self.assertEqual(404, caught.exception.status)
        self.assertEqual(1, len(self.provider.posts))

    def test_metadata_is_durable_and_same_id_content_conflicts(self):
        payload = {"operation_id": "focus-1", "objective": "Make fleet visible",
                   "next_action": "Connect real session VMs"}
        self.center.mutate("focus", payload)
        replay = self.center.mutate("focus", payload)
        self.assertTrue(replay["replayed"])
        with self.assertRaises(CoreError) as caught:
            self.center.mutate("focus", dict(payload, next_action="Other action"))
        self.assertEqual(409, caught.exception.status)
        state = CommandCenter(self.path, fetcher=self.provider).state()
        self.assertEqual(payload["objective"], state["focus"]["objective"])
        self.assertEqual(payload["next_action"], state["focus"]["next_action"])

    def test_vm_link_measurements_and_budget_units_are_preserved(self):
        self.center.mutate("sessions", {"operation_id": "session-1", "session": {
            "id": "gpt-vm-1", "provider": "ChatGPT", "url": "https://chatgpt.com/c/example",
            "cpu": {"vcpus": 8}, "ram_gib": 32, "gpu": None,
            "workspace": "/workspace", "status": "owner_reported_in_use",
            "observed_at": "2026-09-07T18:00:00Z"}})
        self.center.mutate("budgets", {"operation_id": "budget-1", "budget": {
            "id": "provider-quota", "label": "Quota", "limit": 100, "used": 18,
            "unit": "percent", "period": "7d", "kind": "provider_quota"}})
        state = self.center.state()
        self.assertEqual(32, state["sessions"][0]["ram_gib"])
        self.assertEqual("https://chatgpt.com/c/example", state["sessions"][0]["url"])
        self.assertEqual("provider_quota", state["budgets"][0]["kind"])
        self.assertEqual("percent", state["budgets"][0]["unit"])
        self.assertNotIn("authorized_spend", state["budgets"][0])

    def test_credential_metadata_is_rejected_but_sealed_tool_is_discoverable(self):
        with self.assertRaises(CoreError):
            self.center.mutate("sessions", {"operation_id": "bad-session",
                "session": {"id": "one", "api_key": "never-save"}})
        with self.assertRaises(CoreError):
            self.center.mutate("sessions", {"operation_id": "bad-url",
                "session": {"id": "two", "url": "https://example.com/?token=never-save"}})
        self.assertIn("vault_retrieve_sealed", {t["name"] for t in self.center.tools()["tools"]})

    def test_moderation_is_reversible_and_preserves_original_source(self):
        self.center.mutate("feed", {"operation_id": "feed-1", "title": "Original",
                                   "text": "Original observation", "source_url": "https://example.com/run"})
        self.center.mutate("janny", {"operation_id": "janny-1", "peer": "new-peer"})
        self.center.mutate("feed/moderate", {"operation_id": "hide-1", "event_id": "note:feed-1",
                                       "action": "hide", "reason": "Duplicate view", "peer": "new-peer"})
        hidden = next(x for x in self.center.state()["feed"] if x["id"] == "note:feed-1")
        self.assertTrue(hidden["hidden"])
        self.assertEqual("Original observation", hidden["body"])
        self.assertEqual("https://example.com/run", hidden["source_url"])
        # No identity/role check; another peer can restore the same source-preserving projection.
        self.center.mutate("feed/moderate", {"operation_id": "restore-1", "event_id": "note:feed-1",
                                       "action": "restore", "reason": "Needed again", "peer": "brand-new-peer"})
        state = CommandCenter(self.path, fetcher=self.provider).state()
        restored = next(x for x in state["feed"] if x["id"] == "note:feed-1")
        self.assertFalse(restored["hidden"])
        self.assertEqual(hidden["body"], restored["body"])
        self.assertEqual(hidden["source_url"], restored["source_url"])
        self.assertEqual("brand-new-peer", restored["moderation"]["peer"])
        self.assertEqual("new-peer", state["janny"]["peer"])

    def test_moderating_derived_source_does_not_rewrite_cached_document(self):
        state = self.center.state()
        source = next(x for x in state["sources"] if x["id"] == "resource-ledger")
        event = next(x for x in state["feed"] if x.get("source_id") == "resource-ledger")
        self.center.mutate("moderate", {"operation_id": "source-hide-1",
                                       "event_id": event["id"], "action": "hide", "reason": "Filtered view"})
        later = self.center.state()
        self.assertEqual(source["data"], next(x for x in later["sources"]
                                            if x["id"] == "resource-ledger")["data"])
        self.assertTrue(next(x for x in later["feed"] if x["id"] == event["id"])["hidden"])

    def test_runtime_registration_preserves_old_runtime_and_adds_shared_route(self):
        self.center.state()
        self.center.mutate("runtimes", {"operation_id": "runtime-1", "runtime": {
            "id": "cloud-equipment", "label": "Cloud equipment",
            "gateway_url": "https://example.com/equipment"}})
        runtimes = self.center.state()["runtimes"]
        self.assertEqual({"shared-equipment", "cloud-equipment"}, {x["id"] for x in runtimes})


    def test_explicit_failure_cancellation_and_unrecognized_receipts(self):
        cases = [
            ({"status": "failed"}, "failed"),
            ({"status": "ERROR"}, "failed"),
            ({"status": "cancelled"}, "cancelled"),
            ({"result": {"status": "canceled"}}, "cancelled"),
            ({"ok": True, "result": {"status": "interrupted"}}, "uncertain"),
            ({"ok": True, "result": {"status": "timed_out"}}, "uncertain"),
            ({"status": "completed"}, "succeeded"),
            ({"value": "unrecognized result"}, "uncertain"),
            ("a response is not a completion receipt", "uncertain"),
            (None, "uncertain"),
            ({"ok": True, "request_id": "other-request", "call_id": "other-call"}, "uncertain"),
        ]
        for index, (receipt, expected) in enumerate(cases):
            with self.subTest(receipt=receipt):
                self.provider.result = receipt
                result = self.center.call_tool(self.operation("receipt-" + str(index)))
                self.assertEqual(expected, result["status"])
        self.assertEqual(len(cases), len(self.provider.posts))

    def test_partial_runtime_catalog_survives_cached_reads_and_new_instance(self):
        self.provider.fail_health = True
        first = self.center.tools()
        runtime = first["runtimes"][0]
        self.assertEqual("degraded", runtime["status"])
        self.assertEqual(2, len(runtime["tools"]))
        self.assertTrue(runtime["catalog_live"])
        self.assertIsNotNone(runtime["tools_observed_at"])
        self.assertIsNone(runtime["health_observed_at"])
        self.assertIsNotNone(runtime["health_error"])
        tools_requests = sum(url.endswith("/v1/tools") for _, url in self.provider.calls)
        restarted = CommandCenter(self.path, fetcher=self.provider)
        cached = restarted.state()["runtimes"][0]
        self.assertEqual(runtime["tools"], cached["tools"])
        self.assertEqual(runtime["tools_observed_at"], cached["tools_observed_at"])
        self.assertTrue(cached["catalog_live"])
        self.assertEqual(tools_requests,
                         sum(url.endswith("/v1/tools") for _, url in self.provider.calls))
        self.assertEqual("succeeded", restarted.call_tool(self.operation())["status"])

    def test_source_history_preserves_hidden_original_across_refresh_and_view_limit(self):
        initial = self.center.state()
        original = next(x for x in initial["feed"] if x.get("source_id") == "resource-ledger")
        self.center.mutate("feed/moderate", {
            "operation_id": "hide-original", "event_id": original["id"],
            "action": "hide", "reason": "Hide this observation only"})
        self.provider.fail_sources = True  # A new failure is a distinct observation.
        refreshed = self.center.state(refresh=True)
        latest = next(x for x in refreshed["feed"] if x.get("source_id") == "resource-ledger")
        self.assertNotEqual(original["id"], latest["id"])
        self.assertFalse(latest["hidden"])
        self.assertTrue(self.center.event(original["id"])["hidden"])
        self.assertEqual(original["snapshot"], self.center.event(original["id"])["snapshot"])
        self.assertIn("/" + SHA + "/", original["source_url"])
        # Move the original outside the bounded view without deleting its journal row.
        with sqlite3.connect(str(self.center.database)) as db:
            for index in range(305):
                event = {"id": "history-" + str(index), "kind": "source",
                         "title": "Later observation", "body": "Later",
                         "source_url": "", "observed_at": "2999-01-01T00:00:00Z"}
                db.execute("INSERT INTO source_events VALUES(?,?,?)",
                           (event["id"], event["observed_at"], json.dumps(event)))
        self.assertNotIn(original["id"], {x["id"] for x in self.center._feed()})
        self.center.mutate("feed/moderate", {
            "operation_id": "restore-original", "event_id": original["id"],
            "action": "restore", "reason": "Return original to visible history"})
        retained = CommandCenter(self.path, fetcher=self.provider).event(original["id"])
        self.assertFalse(retained["hidden"])
        self.assertEqual(original["body"], retained["body"])
        self.assertEqual(original["source_url"], retained["source_url"])
        self.assertEqual(original["snapshot"], retained["snapshot"])
        self.assertNotIn("surfaces", retained["snapshot"])  # No copied full-document mirror.

    def test_titan_adapter_sessions_preserve_links_and_local_metadata_can_update(self):
        self.provider.adapter_sessions = [
            {"id": "titan-session", "label": "TITAN VM",
             "url": "https://claude.ai/chat/example", "provider": "Claude",
             "cpu": {"vcpus": 8}, "ram_gib": 32, "status": "owner_reported_in_use"},
            {"id": "bad-metadata", "api_key": "must-not-be-injected"},
        ]
        state = self.center.state()
        session = next(item for item in state["sessions"] if item["id"] == "titan-session")
        self.assertEqual("https://claude.ai/chat/example", session["url"])
        self.assertEqual("titan", session["source_id"])
        self.assertEqual(32, session["ram_gib"])
        self.assertNotIn("bad-metadata", {item["id"] for item in state["sessions"]})
        self.center.mutate("sessions", {"operation_id": "local-titan-update", "session": {
            "id": "titan-session", "label": "Current VM", "ram_gib": 48}})
        updated = next(item for item in self.center.state()["sessions"]
                       if item["id"] == "titan-session")
        self.assertEqual("Current VM", updated["label"])
        self.assertEqual(48, updated["ram_gib"])

    def test_cash_balance_and_quota_are_separate_and_zero_survives(self):
        self.center.mutate("budgets", {"operation_id": "cash-1", "budget": {
            "id": "stripe-available", "label": "Stripe available", "kind": "cash_balance",
            "balance": 0, "remaining": None, "committed": None, "unit": "USD",
            "source_url": "https://dashboard.stripe.com/balance"}})
        budget = self.center.state()["budgets"][0]
        self.assertEqual("cash_balance", budget["kind"])
        self.assertEqual(0, budget["balance"])
        self.assertNotIn("used", budget)
        self.assertNotIn("limit", budget)
        self.assertIsNone(budget["committed"])
        with self.assertRaises(CoreError):
            self.center.mutate("budgets", {"operation_id": "bad-cash-1", "budget": {
                "id": "bad", "balance": -1}})


    def test_real_equipment_callback_namespaces_self_metadata_and_preserves_originals(self):
        from integrations.command_center.equipment import CommandCenterEquipment

        equipment = CommandCenterEquipment(self.center)
        original_provider = self.provider
        dispatched = []

        def transport(method, url, payload=None):
            if url.endswith("/v1/tools") and method == "GET":
                return {"tools": equipment.tools()}
            if url.endswith("/health") and method == "GET":
                return {"ok": True, "service": "shared-equipment"}
            if method == "POST" and url.endswith("/v1/tools/call"):
                dispatched.append(copy.deepcopy(payload))
                receipt = equipment.call(payload["name"], payload["arguments"])
                return {"ok": True, "request_id": payload["request_id"],
                        "call_id": payload["call_id"], "uncertain": False, "result": receipt}
            return original_provider(method, url, payload)

        self.center.fetcher = transport

        def invoke(suffix, operation_id, **arguments):
            request = {"operation_id": operation_id, "name": "command_center_" + suffix,
                       "arguments": {"operation_id": operation_id, **arguments}}
            response = self.center.call_tool(request)
            self.assertEqual(operation_id, request["arguments"]["operation_id"])
            self.assertEqual("succeeded", response["status"])
            self.assertEqual(operation_id, dispatched[-1]["call_id"])
            child = response["operation"]["summary"]["child_operation_id"]
            self.assertNotEqual(operation_id, child)
            self.assertEqual(child, dispatched[-1]["arguments"]["operation_id"])
            return request, response["result"]["result"]

        focus_request, focus_receipt = invoke(
            "focus", "self-focus", objective="Observe the whole operation",
            next_action="Use real shared resources")
        self.assertTrue(focus_receipt["ok"])
        self.assertEqual("Observe the whole operation", self.center.state()["focus"]["objective"])
        before = len(dispatched)
        replay = self.center.call_tool(focus_request)
        self.assertTrue(replay["replayed"])
        self.assertFalse(replay["result_available"])
        self.assertEqual(before, len(dispatched))
        _, note = invoke("note", "self-note", title="Original event",
                         body="Keep the source intact", source_url="https://example.com/original")
        event_id = note["record"]["id"]
        original = self.center.event(event_id)
        invoke("moderate", "self-hide", event_id=event_id, action="hide", reason="Duplicate view")
        self.assertTrue(self.center.event(event_id)["hidden"])
        self.assertEqual(original["body"], self.center.event(event_id)["body"])
        self.assertEqual(original["source_url"], self.center.event(event_id)["source_url"])
        invoke("moderate", "self-restore", event_id=event_id, action="restore", reason="Needed again")
        self.assertFalse(self.center.event(event_id)["hidden"])
        self.assertEqual(original["body"], self.center.event(event_id)["body"])
        self.assertEqual(original["source_url"], self.center.event(event_id)["source_url"])

    def test_service_ids_and_noncolliding_metadata_ids_are_never_renamed(self):
        # A service may use operation_id itself; it is not our metadata namespace.
        request = {"operation_id": "external-op", "name": "example_echo",
                   "arguments": {"operation_id": "external-op", "value": "same"}}
        response = self.center.call_tool(request)
        self.assertEqual("external-op", self.provider.posts[-1]["arguments"]["operation_id"])
        self.assertNotIn("child_operation_id", response["operation"]["summary"])
        self.provider.tool_names.append("command_center_focus")
        request = {"operation_id": "outer-focus", "name": "command_center_focus",
                   "arguments": {"operation_id": "explicit-child", "objective": "Visible"}}
        response = self.center.call_tool(request)
        self.assertEqual("explicit-child", self.provider.posts[-1]["arguments"]["operation_id"])
        self.assertNotIn("child_operation_id", response["operation"]["summary"])


    def test_fresh_adapter_telemetry_beats_null_or_older_seed_and_newer_local_wins(self):
        self.center.mutate("sessions", {"operation_id": "old-seed", "session": {
            "id": "gpt-titan-vm", "label": "Owner label", "notes": "Owner note",
            "cpu": 4, "ram_gib": 8, "gpu": "Old GPU", "workspace": "/old",
            "status": "reported", "observed_at": None}})
        self.provider.adapter_sessions = [{"id": "gpt-titan-vm", "label": "Adapter label",
            "cpu": 16, "ram_gib": 64, "workspace": "/fresh", "status": "running",
            "observed_at": "2026-09-07T19:00:00Z"}]
        session = next(x for x in self.center.state(refresh=True)["sessions"]
                       if x["id"] == "gpt-titan-vm")
        self.assertEqual(16, session["cpu"])
        self.assertEqual(64, session["ram_gib"])
        self.assertEqual("/fresh", session["workspace"])
        self.assertEqual("running", session["status"])
        self.assertNotIn("gpu", session)  # Never stamp old GPU data with a fresh time.
        self.assertEqual("2026-09-07T19:00:00Z", session["observed_at"])
        self.assertEqual("Owner label", session["label"])
        self.assertEqual("Owner note", session["notes"])
        self.assertEqual("titan", session["telemetry_source"])
        self.center.mutate("sessions", {"operation_id": "older-local", "session": {
            "id": "gpt-titan-vm", "cpu": 2, "ram_gib": 4,
            "observed_at": "2026-09-06T19:00:00Z"}})
        session = next(x for x in self.center.state()["sessions"] if x["id"] == "gpt-titan-vm")
        self.assertEqual(64, session["ram_gib"])
        self.center.mutate("sessions", {"operation_id": "newer-local", "session": {
            "id": "gpt-titan-vm", "cpu": 32, "ram_gib": 128, "workspace": "/newest",
            "observed_at": "2026-09-08T19:00:00Z"}})
        session = next(x for x in self.center.state()["sessions"] if x["id"] == "gpt-titan-vm")
        self.assertEqual(128, session["ram_gib"])
        self.assertEqual("/newest", session["workspace"])
        self.assertEqual("local-session", session["telemetry_source"])
        # Fresh source fetches cannot manufacture hardware observation timestamps.
        self.provider.adapter_sessions[0]["observed_at"] = None
        session = next(x for x in self.center.state(refresh=True)["sessions"]
                       if x["id"] == "gpt-titan-vm")
        self.assertEqual(128, session["ram_gib"])
        self.assertEqual("2026-09-08T19:00:00Z", session["observed_at"])

    def test_pending_provider_handles_survive_restart_without_prompt_or_result_body(self):
        secret_prompt = "private prompt body should never survive"
        forbidden_text = "full freeform output should never survive"
        sealed_value = "opaque-encrypted-envelope-must-not-be-saved"
        self.provider.result = {"ok": True, "request_id": "command-center",
            "call_id": "async-gemini", "uncertain": False, "result": {
                "content": [{"type": "text", "text": json.dumps({
                    "state": "PENDING", "request_id": "gemini-request-42",
                    "run_id": "provider-run-7", "job_id": "job-8",
                    "html_url": "https://example.com/runs/provider-run-7",
                    "url": "https://example.com/callback?token=never-save-url-secret",
                    "prompt": secret_prompt, "text": forbidden_text,
                    "sealed_envelope": sealed_value})}]}}
        first = self.center.call_tool({"operation_id": "async-gemini", "name": "example_echo",
                                       "arguments": {"prompt": secret_prompt}})
        self.assertEqual("pending", first["status"])
        restarted = CommandCenter(self.path, fetcher=self.provider)
        replay = restarted.call_tool({"operation_id": "async-gemini", "name": "example_echo",
                                      "arguments": {"prompt": secret_prompt}})
        self.assertTrue(replay["replayed"])
        self.assertEqual(1, len(self.provider.posts))
        refs = replay["operation"]["summary"]["provider_refs"]
        self.assertTrue(any(ref["value"] == "command-center" and ref["path"] == "gateway.request_id"
                            for ref in refs))
        self.assertTrue(any(ref["value"] == "gemini-request-42" and
                            ref["path"] == "gateway.result.content[0].json.request_id" for ref in refs))
        self.assertTrue(any(ref["value"] == "provider-run-7" for ref in refs))
        self.assertTrue(any(ref["value"] == "https://example.com/runs/provider-run-7" for ref in refs))
        self.assertFalse(any("callback" in ref["value"] for ref in refs))
        state_operation = next(x for x in restarted.state()["operations"] if x["id"] == "async-gemini")
        self.assertEqual(refs, state_operation["summary"]["provider_refs"])
        self.assertEqual(refs, restarted.event("operation:async-gemini")["provider_refs"])
        with sqlite3.connect(str(restarted.database)) as db:
            persistent = "\n".join(db.iterdump())
        for sensitive in (secret_prompt, forbidden_text, sealed_value, "never-save-url-secret"):
            self.assertNotIn(sensitive, persistent)


if __name__ == "__main__":
    unittest.main()
