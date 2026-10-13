import multiprocessing
import tempfile
import unittest
from pathlib import Path

from broker import Broker, Lease, Upstream, dumps, loads, normalize, reset_delay, retry_after_seconds

PRINCIPAL = "a" * 64
PARAMS = {"owner": "octo-org", "repo": "demo"}


class Clock:
    def __init__(self, value=1000.0):
        self.value = float(value)
    def __call__(self):
        return self.value
    def advance(self, seconds):
        self.value += seconds


def process_read(path, start, output, count, different, index):
    clock = Clock(1000)
    broker = Broker(path, PRINCIPAL, clock=clock, burst_interval=0.001)
    output.put(("ready", index))
    start.wait(10)
    params = PARAMS if not different else {**PARAMS, "ref": f"branch-{index}"}
    route = "repo.get" if not different else "commit.get"
    def provider(*_):
        with count.get_lock():
            count.value += 1
        return Upstream(200, {"ok": True, "index": index})
    output.put(("result", broker.read(route, params, provider, 30)["state"]))


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "coord.db"
        self.clock = Clock()
        self.calls = 0
        self.broker = Broker(self.path, PRINCIPAL, clock=self.clock, burst_interval=0.5)
    def tearDown(self):
        self.tmp.cleanup()
    def good(self, *_):
        self.calls += 1
        return Upstream(200, {"ok": True, "value": 7})

    def test_cache_singleflight_and_burst(self):
        first = self.broker.read("repo.get", PARAMS, self.good)
        self.assertEqual("FETCHED", first["state"])
        self.assertEqual("CACHED", self.broker.read("repo.get", PARAMS, self.good)["state"])
        self.assertEqual(1, self.calls)
        self.assertEqual("COOLDOWN", self.broker.read("pull.get", {**PARAMS, "number": 1}, self.good)["state"])
        self.clock.advance(0.5)
        self.assertEqual("FETCHED", self.broker.read("pull.get", {**PARAMS, "number": 1}, self.good)["state"])

    def test_different_principals_have_independent_flight_and_cache_capacity(self):
        # Two independent GitHub credentials deliberately share the DB, but
        # each configures a one-entry in-flight/cache budget.
        first = Broker(self.path, PRINCIPAL, clock=self.clock, max_entries=1,
                       burst_interval=0.001)
        second = Broker(self.path, "b" * 64, clock=self.clock, max_entries=1,
                        burst_interval=0.001)
        first_lease = first.acquire("repo.get", PARAMS)
        self.assertIsInstance(first_lease, Lease)
        # The first active request must not consume the second token's slot.
        second_lease = second.acquire("repo.get", PARAMS)
        self.assertIsInstance(second_lease, Lease)
        self.assertEqual("FETCHED", first.finish(first_lease, Upstream(200, {"token": "a"}))["state"])
        self.assertEqual("FETCHED", second.finish(second_lease, Upstream(200, {"token": "b"}))["state"])
        # Filling the second namespace must not evict the first's cache.
        def unexpected_provider(*_):
            self.fail("cache eviction leaked across independent token namespaces")
        self.assertEqual("CACHED", first.read("repo.get", PARAMS, unexpected_provider)["state"])
        self.assertEqual("CACHED", second.read("repo.get", PARAMS, unexpected_provider)["state"])

    def test_pull_head_login_alias_reuses_same_pr_list_cache(self):
        mixed = {**PARAMS, "head": "WoahWhatTheHeck:Feat/MixedCase"}
        lowercase = {**PARAMS, "head": "woahwhattheheck:Feat/MixedCase"}
        other_branch = {**PARAMS, "head": "woahwhattheheck:feat/MixedCase"}
        self.assertEqual(normalize("pulls.list", mixed), normalize("pulls.list", lowercase))
        self.assertEqual("woahwhattheheck:Feat/MixedCase",
                         normalize("pulls.list", mixed)["head"])
        self.assertNotEqual(normalize("pulls.list", mixed), normalize("pulls.list", other_branch))
        self.assertEqual("Feat/MixedCase",
                         normalize("pulls.list", {**PARAMS, "head": "Feat/MixedCase"})["head"])
        self.assertEqual("FETCHED", self.broker.read("pulls.list", mixed, self.good)["state"])
        self.assertEqual("CACHED", self.broker.read("pulls.list", lowercase, self.good)["state"])
        self.assertEqual(1, self.calls)

    def test_secondary_403_blocks_all_buckets_and_persists(self):
        result = self.broker.read("repo.get", PARAMS, lambda *_: Upstream(403, retry_after="120", secondary_limited=True))
        self.assertEqual(("COOLDOWN", 120), (result["state"], result["retry_after_seconds"]))
        other = Broker(self.path, PRINCIPAL, clock=self.clock, burst_interval=0.5)
        self.clock.advance(10)
        blocked = other.read("search.issues", {"q": "repo:octo-org/demo bug"}, self.good)
        self.assertEqual(("COOLDOWN", 110), (blocked["state"], blocked["retry_after_seconds"]))
        self.assertEqual(0, self.calls)

    def test_secondary_default_is_conservative_and_never_shortens(self):
        lease = self.broker.acquire("repo.get", PARAMS)
        self.assertIsInstance(lease, Lease)
        self.clock.advance(46)
        newer = self.broker.acquire("repo.get", PARAMS)
        self.assertIsInstance(newer, Lease)
        self.broker.finish(lease, Upstream(403, retry_after="3600", secondary_limited=True))
        result = self.broker.finish(newer, Upstream(403, retry_after="1", secondary_limited=True))
        self.assertEqual(3600, result["retry_after_seconds"])

    def test_primary_limit_uses_reset_for_bucket_only(self):
        result = self.broker.read("repo.get", PARAMS, lambda *_: Upstream(403, rate_remaining="0", rate_reset="1120"))
        self.assertEqual(("COOLDOWN", 120), (result["state"], result["retry_after_seconds"]))
        self.clock.advance(1)
        search = self.broker.read("search.issues", {"q": "repo:octo-org/demo bug"}, self.good)
        self.assertEqual("FETCHED", search["state"])

    def test_headerless_primary_403_pauses_quota_bucket_without_pretending_secondary(self):
        result = self.broker.read(
            "repo.get", PARAMS,
            lambda *_: Upstream(403, primary_limited=True),
        )
        self.assertEqual(("COOLDOWN", 60), (result["state"], result["retry_after_seconds"]))
        self.clock.advance(1)
        # Core quota failures must stop another core-route read from retrying
        # immediately; search has its separately metered GitHub budget.
        other = self.broker.read(
            "pull.get", {**PARAMS, "number": 3}, self.good
        )
        self.assertEqual(("COOLDOWN", 59), (other["state"], other["retry_after_seconds"]))
        search = self.broker.read(
            "search.issues", {"q": "repo:octo-org/demo bug"}, self.good
        )
        self.assertEqual("FETCHED", search["state"])
        self.assertEqual(1, self.calls)

    def test_429_without_headers_is_principal_wide_60_seconds(self):
        result = self.broker.read("repo.get", PARAMS, lambda *_: Upstream(429))
        self.assertEqual(("COOLDOWN", 60), (result["state"], result["retry_after_seconds"]))
        self.clock.advance(1)
        search = self.broker.read("search.code", {"q": "repo:octo-org/demo token"}, self.good)
        self.assertEqual(("COOLDOWN", 59), (search["state"], search["retry_after_seconds"]))
        self.assertEqual(0, self.calls)

    def test_401_purges_namespace_and_token_rotation_recovers(self):
        self.broker.read("repo.get", PARAMS, self.good)
        self.clock.advance(1)
        result = self.broker.read("pull.get", {**PARAMS, "number": 2}, lambda *_: Upstream(401))
        self.assertEqual("AUTH_BLOCKED", result["state"])
        self.assertEqual("AUTH_BLOCKED", self.broker.read("repo.get", PARAMS, self.good)["state"])
        rotated = Broker(self.path, "b" * 64, clock=self.clock, burst_interval=0.5)
        self.assertEqual("FETCHED", rotated.read("repo.get", PARAMS, self.good)["state"])

    def test_failed_refresh_never_returns_stale_success(self):
        self.broker.read("repo.get", PARAMS, self.good)
        self.clock.advance(61)
        result = self.broker.read("repo.get", PARAMS, lambda *_: Upstream(503), 30)
        self.assertEqual("UPSTREAM_ERROR", result["state"])
        self.assertNotIn("data", result)

    def test_expired_owner_cannot_publish(self):
        lease = self.broker.acquire("repo.get", PARAMS)
        self.clock.advance(45)
        self.assertEqual("DISCARDED", self.broker.finish(lease, Upstream(200, {"ok": True}))["state"])

    def test_provider_exception_redacted(self):
        secret = "token ghp_DO_NOT_ECHO"
        def boom(*_):
            raise RuntimeError(secret)
        result = self.broker.read("repo.get", PARAMS, boom)
        self.assertEqual("UPSTREAM_ERROR", result["state"])
        self.assertNotIn(secret, dumps(result))

    def test_payload_must_be_finite_and_bounded(self):
        for payload in ({"x": float("nan")}, {"x": "x" * 1048576}, object()):
            self.clock.advance(1)
            result = self.broker.read("repo.get", PARAMS, lambda *_, p=payload: Upstream(200, p), 0)
            self.assertEqual("UPSTREAM_ERROR", result["state"])

    def test_real_multiprocess_identical_read_singleflight(self):
        context = multiprocessing.get_context("spawn")
        start, output, count = context.Event(), context.Queue(), context.Value("i", 0)
        workers = [context.Process(target=process_read, args=(str(self.path), start, output, count, False, i)) for i in range(8)]
        try:
            for worker in workers:
                worker.start()
            ready = [output.get(timeout=20) for _ in workers]
            self.assertTrue(all(row[0] == "ready" for row in ready), ready)
            start.set()
            rows = [output.get(timeout=20) for _ in workers]
            for worker in workers:
                worker.join(10)
                self.assertEqual(0, worker.exitcode)
            self.assertEqual(1, count.value)
            states = [row[1] for row in rows]
            self.assertEqual(1, states.count("FETCHED"))
            self.assertTrue(set(states) <= {"FETCHED", "CACHED", "BUSY"}, states)
        finally:
            start.set()
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                if worker.pid:
                    worker.join(10)
            output.close(); output.join_thread()


class ValidationTests(unittest.TestCase):
    def test_pull_list_default_open_deduplicates_requests(self):
        # Omitting state and explicitly sending GitHub's default must share
        # the broker's normalized cache/singleflight key, not spend two GETs.
        request = {"owner": "WoahWhatTheHeck", "repo": "Sanctifier"}
        implicit = normalize("pulls.list", request)
        explicit = normalize("pulls.list", {**request, "state": "open"})
        self.assertEqual("open", implicit["state"])
        self.assertEqual(implicit, explicit)
        for other_state in ("closed", "all"):
            self.assertNotEqual(implicit, normalize("pulls.list", {
                **request, "state": other_state,
            }))

    def test_write_and_unknown_routes_rejected(self):
        for route in ("repo.update", "pull.merge", "git.ref.create", "", [], None):
            with self.assertRaises(ValueError):
                normalize(route, PARAMS)

    def test_owner_repo_path_and_types_are_strict(self):
        bad = [
            ("repo.get", {"owner": "bad/name", "repo": "x"}),
            ("repo.get", {"owner": "ok", "repo": "../x"}),
            ("contents.get", {**PARAMS, "path": "../secret"}),
            ("contents.get", {**PARAMS, "path": "/absolute"}),
            ("pull.get", {**PARAMS, "number": True}),
            ("pull.get", {**PARAMS, "number": 0}),
            ("search.code", {"q": "x\nheader"}),
            ("repo.get", {**PARAMS, "token": "secret"}),
        ]
        for route, params in bad:
            with self.assertRaises(ValueError, msg=(route, params)):
                normalize(route, params)

    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ValueError):
                loads(text)

    def test_retry_and_reset_parsing(self):
        self.assertEqual(120, retry_after_seconds("120"))
        self.assertEqual(1, retry_after_seconds("0"))
        self.assertIsNone(retry_after_seconds("1.5"))
        self.assertIsNone(retry_after_seconds("secret"))
        self.assertEqual(120, reset_delay("1120", 1000))
        self.assertEqual(1, reset_delay("999", 1000))


if __name__ == "__main__":
    unittest.main()
