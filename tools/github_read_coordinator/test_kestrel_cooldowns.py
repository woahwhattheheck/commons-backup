"""Independent offline rate-limit regression contract; no upstream requests."""
import io
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from broker import Broker, Lease, Upstream
from gateway import API_ROOT, GitHubProvider

PARAMS = {"owner": "example", "repo": "sample"}


class CooldownRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state.sqlite"
        self.now = 1000.0
        self.calls = 0
        self.broker = self.open_broker()

    def open_broker(self):
        return Broker(self.path, "c" * 64, clock=lambda: self.now)

    def good(self, *_):
        self.calls += 1
        return Upstream(200, {"ok": True})

    def test_ambiguous_429_core_blocks_search_after_restart(self):
        self.broker.read("repo.get", PARAMS, lambda *_: Upstream(429, retry_after="120"))
        self.now += 10
        result = self.open_broker().read("search.issues", {"q": "example"}, self.good)
        self.assertEqual("COOLDOWN", result["state"])
        self.assertEqual(110, result["retry_after_seconds"])
        self.assertEqual(0, self.calls)

    def test_ambiguous_429_search_blocks_core(self):
        self.broker.read("search.issues", {"q": "example"}, lambda *_: Upstream(429))
        self.now += 1
        result = self.broker.read("repo.get", PARAMS, self.good)
        self.assertEqual("COOLDOWN", result["state"])
        self.assertEqual(0, self.calls)

    def test_403_retry_after_non_json_body_blocks_all_routes(self):
        provider = GitHubProvider("synthetic-offline-fixture")
        error = urllib.error.HTTPError(
            API_ROOT + "/repos/example/sample", 403, "Forbidden",
            {"Retry-After": "120", "X-RateLimit-Remaining": "99"},
            io.BytesIO(b"temporarily rate limited"),
        )
        provider._opener = mock.Mock()
        provider._opener.open.side_effect = error
        first = self.broker.read("repo.get", PARAMS, provider)
        self.assertEqual("COOLDOWN", first["state"])
        self.now += 1
        result = self.broker.read("search.issues", {"q": "example"}, self.good)
        self.assertEqual("COOLDOWN", result["state"])
        self.assertEqual(0, self.calls)

    def test_success_exhaustion_persists_primary_without_losing_success(self):
        first = self.broker.read("repo.get", PARAMS,
            lambda *_: Upstream(200, {"ok": True}, rate_remaining="0", rate_reset="1120"))
        self.assertEqual("FETCHED", first["state"])
        self.assertEqual({"ok": True}, first["data"])
        self.now += 1
        other = self.open_broker()
        core = other.read("pull.get", {**PARAMS, "number": 1}, self.good)
        self.assertEqual("COOLDOWN", core["state"])
        self.assertEqual(119, core["retry_after_seconds"])
        self.assertEqual(0, self.calls)
        self.assertEqual("FETCHED", other.read("search.issues", {"q": "example"}, self.good)["state"])

    def test_success_exhaustion_keeps_cache_available(self):
        self.broker.read("repo.get", PARAMS,
            lambda *_: Upstream(200, {"ok": True}, rate_remaining="0", rate_reset="1120"))
        self.now += 1
        cached = self.open_broker().read("repo.get", PARAMS, self.good)
        self.assertEqual("CACHED", cached["state"])
        self.assertEqual({"ok": True}, cached["data"])
        self.assertEqual(0, self.calls)

    def test_success_search_exhaustion_blocks_only_search(self):
        self.broker.read("search.issues", {"q": "example"},
            lambda *_: Upstream(200, {"ok": True}, rate_remaining="0", rate_reset="1120"))
        self.now += 1
        other = self.open_broker()
        blocked = other.read("search.code", {"q": "example"}, self.good)
        self.assertEqual("COOLDOWN", blocked["state"])
        self.assertEqual(119, blocked["retry_after_seconds"])
        self.assertEqual("FETCHED", other.read("repo.get", PARAMS, self.good)["state"])
        self.assertEqual(1, self.calls)

    def test_expired_success_cannot_publish_but_preserves_quota_observation(self):
        lease = self.broker.acquire("repo.get", PARAMS)
        self.assertIsInstance(lease, Lease)
        self.now += 46
        result = self.broker.finish(lease,
            Upstream(200, {"old": True}, rate_remaining="0", rate_reset="1120"))
        self.assertEqual("DISCARDED", result["state"])
        self.assertNotIn("data", result)
        blocked = self.open_broker().read("pull.get", {**PARAMS, "number": 1}, self.good)
        self.assertEqual("COOLDOWN", blocked["state"])
        self.assertEqual(74, blocked["retry_after_seconds"])
        self.assertEqual(0, self.calls)

    def test_success_exhaustion_does_not_shorten_existing_primary_pause(self):
        first = self.broker.acquire("repo.get", PARAMS)
        self.now += 1
        second = self.broker.acquire("pull.get", {**PARAMS, "number": 1})
        self.assertIsInstance(first, Lease)
        self.assertIsInstance(second, Lease)
        self.broker.finish(first, Upstream(200, {}, rate_remaining="0", rate_reset="1400"))
        self.broker.finish(second, Upstream(200, {}, rate_remaining="0", rate_reset="1002"))
        blocked = self.open_broker().read("pull.get", {**PARAMS, "number": 2}, self.good)
        self.assertEqual("COOLDOWN", blocked["state"])
        self.assertEqual(399, blocked["retry_after_seconds"])
        self.assertEqual(0, self.calls)

    def test_success_exhaustion_missing_reset_uses_conservative_fallback(self):
        self.broker.read("repo.get", PARAMS,
            lambda *_: Upstream(200, {}, rate_remaining="0", rate_reset="invalid"))
        self.now += 1
        blocked = self.open_broker().read("pull.get", {**PARAMS, "number": 1}, self.good)
        self.assertEqual("COOLDOWN", blocked["state"])
        self.assertEqual(59, blocked["retry_after_seconds"])
        self.assertEqual(0, self.calls)

    def test_success_exhaustion_respects_both_retry_and_reset_floors(self):
        for retry, reset, expected in (("5", "1120", 120), ("180", "1120", 180)):
            with self.subTest(retry=retry, reset=reset):
                self.now += 1000
                target = str(int(self.now) + int(reset) - 1000)
                result = self.broker.read("repo.get", PARAMS,
                    lambda *_: Upstream(200, {}, retry_after=retry,
                                        rate_remaining="0", rate_reset=target), 0)
                self.assertEqual("FETCHED", result["state"])
                blocked = self.broker.read("pull.get", {**PARAMS, "number": 1}, self.good)
                self.assertEqual("COOLDOWN", blocked["state"])
                self.assertEqual(expected, blocked["retry_after_seconds"])
        self.assertEqual(0, self.calls)

    def test_success_exhaustion_allows_new_upstream_at_reset(self):
        self.broker.read("repo.get", PARAMS,
            lambda *_: Upstream(200, {}, rate_remaining="0", rate_reset="1120"))
        self.now = 1120
        result = self.open_broker().read("pull.get", {**PARAMS, "number": 1}, self.good)
        self.assertEqual("FETCHED", result["state"])
        self.assertEqual(1, self.calls)

    def test_invalid_success_payload_still_preserves_primary_exhaustion(self):
        first = self.broker.read("repo.get", PARAMS,
            lambda *_: Upstream(200, {"bad": float("nan")}, rate_remaining="0", rate_reset="1120"))
        self.assertEqual("UPSTREAM_ERROR", first["state"])
        self.now += 1
        result = self.open_broker().read("pull.get", {**PARAMS, "number": 1}, self.good)
        self.assertEqual("COOLDOWN", result["state"])
        self.assertEqual(0, self.calls)

    def test_non_exhausted_success_keeps_core_available_after_burst(self):
        self.broker.read("repo.get", PARAMS,
            lambda *_: Upstream(200, {}, rate_remaining="1", rate_reset="1120"))
        self.now += 1
        result = self.open_broker().read("pull.get", {**PARAMS, "number": 1}, self.good)
        self.assertEqual("FETCHED", result["state"])
        self.assertEqual(1, self.calls)

    def test_known_primary_exhaustion_does_not_block_search(self):
        self.broker.read("repo.get", PARAMS,
            lambda *_: Upstream(403, rate_remaining="0", rate_reset="1120"))
        self.now += 1
        self.assertEqual("FETCHED", self.broker.read("search.issues", {"q": "example"}, self.good)["state"])
        self.assertEqual(1, self.calls)

    def test_permission_denial_without_rate_evidence_stays_an_error(self):
        first = self.broker.read("repo.get", PARAMS, lambda *_: Upstream(403))
        self.assertEqual("UPSTREAM_ERROR", first["state"])
        self.now += 1
        self.assertEqual("FETCHED", self.broker.read("search.issues", {"q": "example"}, self.good)["state"])
        self.assertEqual(1, self.calls)


if __name__ == "__main__":
    unittest.main()
