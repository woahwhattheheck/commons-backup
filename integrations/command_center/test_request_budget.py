"""Provider cooldown regressions with actual SQLite stores and fake transport IO."""
import io
import json
import subprocess
import tempfile
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.message import Message

from .collectors import LiveCollectors
from .request_budget import RequestBudget, RequestDeferred, retry_seconds
from .workstreams import WorkstreamStore
from integrations.shared_equipment.provider_io import GitHubSlackEquipment, EquipmentError


class RequestBudgetTests(unittest.TestCase):
    def test_cooldown_survives_restart_and_does_not_block_another_method(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [1789257000.0]
            first = RequestBudget(directory, clock=lambda: now[0])
            first.acquire("slack:conversations.history")
            deadline = first.rate_limited("slack:conversations.history", "120")
            second = RequestBudget(directory, clock=lambda: now[0])
            with self.assertRaises(RequestDeferred) as held:
                second.acquire("slack:conversations.history")
            self.assertEqual(deadline["retry_not_before"], held.exception.retry_not_before)
            second.acquire("github:GET")
            second.acquire("slack:conversations.replies")
            now[0] += 120
            second.acquire("slack:conversations.history")
            metrics = second.metrics()
            self.assertEqual(3, metrics["observed_attempts"])
            self.assertEqual(1, metrics["deferred_reads"])
            history = next(row for row in metrics["scopes"] if row["scope"].endswith("history"))
            self.assertEqual("ready", history["state"])
            self.assertEqual(2, history["total_observed_attempts"])
            self.assertEqual(1, history["total_deferred_reads"])

    def test_concurrent_instances_preserve_deadline_and_all_deferred_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            first = RequestBudget(directory, clock=lambda: 1789257000)
            first.rate_limited("slack:conversations.history", 120)
            budgets = [RequestBudget(directory, clock=lambda: 1789257001) for _ in range(8)]
            def read(budget):
                try:
                    budget.acquire("slack:conversations.history")
                except RequestDeferred:
                    return "deferred"
                return "read"
            with ThreadPoolExecutor(max_workers=8) as executor:
                self.assertEqual(["deferred"] * 8, list(executor.map(read, budgets)))
            budgets[0].rate_limited("slack:conversations.history", 10)
            row = first.metrics()["scopes"][0]
            self.assertEqual(8, row["total_deferred_reads"])
            self.assertEqual(0, row["total_observed_attempts"])
            self.assertEqual(120, row["retry_remaining_seconds"])

    def test_shorter_fallback_preserves_winning_provider_reset_basis_and_delay(self):
        with tempfile.TemporaryDirectory() as directory:
            now, reset = 1789257000, 1789259378
            first = RequestBudget(directory, clock=lambda: now)
            original = first.rate_limited("github:GET", reset_at=reset)
            later = RequestBudget(directory, clock=lambda: now + 1)
            retained = later.rate_limited("github:GET")
            self.assertEqual(original["retry_not_before"], retained["retry_not_before"])
            self.assertEqual("provider_reset", retained["retry_basis"])
            self.assertEqual(reset - now - 1, retained["retry_after_seconds"])
            row = later.metrics()["scopes"][0]
            self.assertEqual("provider_reset", row["retry_basis"])
            self.assertEqual(retained["retry_after_seconds"], row["retry_remaining_seconds"])
            self.assertEqual(2, row["total_rate_limit_responses"])

    def test_retry_after_parsing_and_explicit_fallback_do_not_store_raw_values(self):
        now = 1789257000
        self.assertEqual((90.0, "provider"), retry_seconds("90", now, 60))
        date = datetime.fromtimestamp(now + 120, timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        self.assertEqual((120.0, "provider"), retry_seconds(date, now, 60))
        for value in (None, True, -1, "NaN", "inf", "private-header-value"):
            self.assertEqual((60, "configured_fallback"), retry_seconds(value, now, 60))
        budget = RequestBudget(clock=lambda: now)
        budget.rate_limited("slack:conversations.history", "private-header-value")
        self.assertNotIn("private-header-value", json.dumps(budget.metrics()))

    def test_slack_http_retry_after_crosses_real_adapter_and_retains_source(self):
        with tempfile.TemporaryDirectory() as directory:
            store = WorkstreamStore(directory)
            old = "2026-09-01T00:00:00Z"
            store.ingest({"operation_id": "old", "source": {
                "id": "slack:C1", "provider": "Slack", "label": "C1",
                "scope": {"channel_id": "C1"}, "sync_mode": "direct",
                "observed_at": old, "activity_as_of": old,
                "coverage": {"complete": True}, "status": "live"},
                "items": [{"id": "old-message", "kind": "slack_thread",
                           "activity_observed_at": old}]})
            calls = []
            def opener(request, **kwargs):
                calls.append(request.get_method())
                headers = Message()
                headers["Retry-After"] = "120"
                raise urllib.error.HTTPError(request.full_url, 429, "rate limited", headers,
                                             io.BytesIO(b"private provider response"))
            equipment = GitHubSlackEquipment(slack_token_loader=lambda: "synthetic", opener=opener)
            config = {"github": {"enabled": False}, "max_workers": 1,
                      "slack": {"channels": [{"id": "C1"}, {"id": "C2"}]}}
            result = LiveCollectors(store, config, equipment=equipment).collect()
            self.assertEqual(["GET"], calls)
            self.assertEqual(1, result["request_budget"]["observed_attempts"])
            self.assertEqual(1, result["request_budget"]["rate_limit_responses"])
            self.assertEqual(1, result["request_budget"]["deferred_reads"])
            self.assertEqual("slack:C2", result["deferred_sources"][0]["source_id"])
            self.assertEqual("slack_rate_limited", result["sources"][0]["error"])
            state = store.state()
            self.assertEqual(["old-message"], [row["id"] for row in state["items"]])
            source = state["sources"][0]
            self.assertEqual(old, source["last_good_observed_at"])
            self.assertTrue(source["retained_last_good"])
            self.assertNotIn("private provider response", json.dumps(state))

            previous_attempt = source["last_attempt_at"]
            previous_observed = source["observed_at"]
            restarted = LiveCollectors(WorkstreamStore(directory), config, equipment=equipment).collect()
            self.assertEqual(["GET"], calls)
            self.assertEqual(0, restarted["request_budget"]["observed_attempts"])
            self.assertEqual(2, restarted["request_budget"]["deferred_reads"])
            self.assertEqual([], restarted["sources"])
            self.assertEqual([], restarted["receipts"])
            after = store.state()["sources"][0]
            self.assertEqual(previous_attempt, after["last_attempt_at"])
            self.assertEqual(previous_observed, after["observed_at"])

    def test_another_provider_collects_while_slack_is_cooling_down(self):
        with tempfile.TemporaryDirectory() as directory:
            store = WorkstreamStore(directory)
            budget = RequestBudget(directory)
            budget.rate_limited("slack:conversations.history", 120)
            class Equipment:
                def github(self, endpoint, **kwargs):
                    if endpoint == "user":
                        return {"login": "owner"}
                    if endpoint.startswith("user/repos"):
                        return []
                    return {"items": [], "total_count": 0}
                def slack(self, method, payload):
                    raise AssertionError("Slack cooldown should defer the collector read")
            result = LiveCollectors(store, {"slack": {"channels": [{"id": "C1"}]}},
                                    equipment=Equipment()).collect()
            self.assertGreater(result["request_budget"]["observed_attempts"], 0)
            self.assertEqual(1, result["request_budget"]["deferred_reads"])
            self.assertEqual({"GitHub"}, {row["provider"] for row in result["sources"]})

    def test_annotated_github_rate_limit_uses_existing_equipment_error_interface(self):
        with tempfile.TemporaryDirectory() as directory:
            class Equipment:
                def github(self, endpoint, **kwargs):
                    raise EquipmentError("private provider error", code="github_request_failed",
                                         http_status=429)
            result = LiveCollectors(WorkstreamStore(directory), {}, equipment=Equipment()).collect()
            self.assertEqual(1, result["request_budget"]["rate_limit_responses"])
            self.assertEqual("github_rate_limited", result["sources"][0]["error"])
            self.assertNotIn("private provider error", json.dumps(result))

    def test_pr_transition_times_remain_separate_from_comment_update_time(self):
        with tempfile.TemporaryDirectory() as directory:
            created, merged, updated = ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z",
                                        "2026-09-12T00:00:00Z")
            class Equipment:
                def github(self, endpoint, **kwargs):
                    return {"items": [{"id": 1, "number": 7, "title": "change",
                        "repository_url": "https://api.github.com/repos/owner/repo",
                        "html_url": "https://github.com/owner/repo/pull/7",
                        "created_at": created, "closed_at": merged, "updated_at": updated,
                        "pull_request": {"merged_at": merged}, "user": {"login": "owner"}}],
                        "total_count": 1}
            row = LiveCollectors(WorkstreamStore(directory), {}, equipment=Equipment())._pull_requests("owner")["items"][0]
            self.assertEqual(created, row["created_at"])
            self.assertEqual(merged, row["refs"]["merged_at"])
            self.assertEqual(merged, row["refs"]["closed_at"])
            self.assertEqual(updated, row["updated_at"])


    def test_real_gh_include_core_exhaustion_honors_reset_and_redacts_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            now, reset = 1789257000, 1789259378
            output = ("HTTP/2.0 403 Forbidden\r\nX-RateLimit-Remaining: 0\r\n"
                      "X-RateLimit-Reset: 1789259378\r\n"
                      "Set-Cookie: private-header-value\r\n\r\n" +
                      json.dumps({"message": "API rate limit exceeded for account."}))
            calls = []
            def runner(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command, 1, output, "private stderr")
            equipment = GitHubSlackEquipment(gh_runner=runner)
            collector = LiveCollectors(WorkstreamStore(directory), {}, equipment=equipment)
            collector.request_budget.clock = lambda: now
            result = collector.collect()
            self.assertEqual(1, len(calls))
            command = calls[0]
            # --include sits after `api` (not between --method and endpoint).
            # github_create_branch callers parse endpoint as the token after --method.
            self.assertEqual(["gh", "api", "--include", "--hostname", "github.com"], command[:5])
            self.assertEqual("GET", command[command.index("--method") + 1])
            self.assertEqual(command[-1], command[command.index("--method") + 2])
            source = result["sources"][0]
            metadata = source["metadata"]["request_budget"]
            self.assertEqual(403, metadata["http_status"])
            self.assertEqual(0, metadata["rate_limit_remaining"])
            self.assertEqual(reset, metadata["rate_limit_reset"])
            self.assertEqual("2026-09-13T00:29:38Z", metadata["retry_not_before"])
            self.assertEqual("provider_reset", metadata["retry_basis"])
            self.assertNotIn("private", json.dumps(result))
            reopened = LiveCollectors(WorkstreamStore(directory), {}, equipment=equipment)
            reopened.request_budget.clock = lambda: now + 10
            again = reopened.collect()
            self.assertEqual(1, len(calls))
            self.assertEqual(0, again["request_budget"]["observed_attempts"])
            self.assertEqual("github:GET:core", again["deferred_sources"][0]["scope"])

    def test_gh_secondary_limit_and_plain_permission_denial_are_distinct(self):
        for message, remaining, limited in (
                ("You have exceeded a secondary rate limit.", 1000, True),
                ("Resource not accessible by integration", 1000, False)):
            output = ("HTTP/2.0 403 Forbidden\nX-RateLimit-Remaining: " + str(remaining) +
                      "\n\n" + json.dumps({"message": message}))
            equipment = GitHubSlackEquipment(gh_runner=lambda command, **kwargs:
                subprocess.CompletedProcess(command, 1, output, ""))
            with self.assertRaises(EquipmentError) as caught:
                equipment.github("user")
            self.assertEqual("github_rate_limited" if limited else "github_request_failed",
                             caught.exception.code)
            self.assertEqual(403, caught.exception.http_status)
            self.assertIsNone(caught.exception.retry_after)

    def test_gh_include_stays_after_api_so_endpoint_follows_method(self):
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(
                command, 1,
                "HTTP/2.0 403 Forbidden\r\nX-RateLimit-Remaining: 0\r\n"
                "X-RateLimit-Reset: 1\r\n\r\n{}",
                "private stderr")
        with self.assertRaises(EquipmentError):
            GitHubSlackEquipment(gh_runner=runner).github("user")
        command = calls[0]
        self.assertEqual(
            ["gh", "api", "--include", "--hostname", "github.com", "--method", "GET", "user"],
            command)
        self.assertNotEqual(command[command.index("--method") + 1], "--include")

    def test_gh_success_headers_and_write_command_remain_compatible(self):
        calls = []
        def runner(command, **kwargs):
            calls.append((command, kwargs))
            body = '{"sha":"abc"}'
            stdout = "HTTP/2.0 200 OK\nContent-Type: application/json\n\n" + body if "--include" in command else body
            return subprocess.CompletedProcess(command, 0, stdout, "")
        equipment = GitHubSlackEquipment(gh_runner=runner)
        self.assertEqual({"sha": "abc"}, equipment.github("repos/owner/repo/commits/main"))
        self.assertEqual(
            ["gh", "api", "--include", "--hostname", "github.com", "--method", "GET",
             "repos/owner/repo/commits/main"],
            calls[0][0])
        self.assertEqual({"sha": "abc"}, equipment.github("repos/owner/repo/git/trees",
                                                        method="POST", payload={"tree": []}))
        # Writes keep --include after api so cooldown headers stay available.
        # Endpoint remains the token after --method for existing parsers.
        write = calls[1][0]
        self.assertEqual(
            ["gh", "api", "--include", "--hostname", "github.com", "--method", "POST",
             "repos/owner/repo/git/trees", "--input", "-"],
            write)
        self.assertEqual("POST", write[write.index("--method") + 1])
        self.assertEqual("repos/owner/repo/git/trees", write[write.index("--method") + 2])
        self.assertEqual({"tree": []}, json.loads(calls[1][1]["input"]))
        self.assertNotIn("shell", calls[1][1])
        incomplete = GitHubSlackEquipment(gh_runner=lambda command, **kwargs:
            subprocess.CompletedProcess(command, 0, "HTTP/2.0 200 OK\nContent-Type: application/json", ""))
        with self.assertRaises(EquipmentError) as caught:
            incomplete.github("repos/owner/repo/commits/main")
        self.assertEqual("github_response_invalid", caught.exception.code)

    def test_zero_retry_after_has_a_small_collector_delay_and_summary_is_bounded(self):
        budget = RequestBudget(clock=lambda: 1789257000)
        metadata = budget.rate_limited("slack:conversations.history", 0)
        self.assertEqual(1, metadata["retry_after_seconds"])
        self.assertEqual("provider_minimum_delay", metadata["retry_basis"])
        with self.assertRaises(RequestDeferred):
            budget.acquire("slack:conversations.history")
        for index in range(101):
            budget.acquire("future:" + str(index))
        metrics = budget.metrics()
        self.assertEqual(100, len(metrics["scopes"]))
        self.assertEqual(102, metrics["scope_count"])
        self.assertTrue(metrics["scopes_truncated"])


if __name__ == "__main__":
    unittest.main()
