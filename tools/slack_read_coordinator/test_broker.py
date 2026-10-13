import multiprocessing
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from broker import Broker, Lease, Upstream, dumps, loads, normalize, retry_seconds

PRINCIPAL = "a" * 64
HISTORY = "conversations.history"
PARAMS = {"channel": "C123"}


class Clock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def process_read(path, start, output, count, different, index):
    try:
        broker = Broker(path, "T123", "A123", PRINCIPAL, clock=lambda: 1000.0)
        output.put(("ready", index))
        if not start.wait(15):
            raise RuntimeError("start timeout")

        def provider(method, params):
            with count.get_lock():
                count.value += 1
            time.sleep(0.2)
            return Upstream(200, {"ok": True, "messages": [{"text": "synthetic", "ts": "999.123"}]})

        result = broker.read(HISTORY, {"channel": "C%d" % (100 + index) if different else "C123"}, provider)
        output.put(("result", result["state"]))
    except Exception as error:
        output.put(("error", type(error).__name__))
        raise


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "reads.sqlite3"
        self.clock = Clock()
        self.broker = Broker(self.path, "T123", "A123", PRINCIPAL, clock=self.clock)
        self.calls = 0

    def tearDown(self):
        self.tmp.cleanup()

    def good(self, method, params):
        self.calls += 1
        return Upstream(200, {"ok": True, "messages": ["synthetic"]})

    def test_normalized_identical_reads_have_one_fetch(self):
        first = self.broker.read(HISTORY, PARAMS, self.good)
        second = self.broker.read(HISTORY, {"limit": 15, "channel": "C123"}, self.good)
        self.assertEqual(("FETCHED", "CACHED"), (first["state"], second["state"]))
        self.assertEqual(first["data"], second["data"])
        self.assertEqual(1, self.calls)
        self.assertIs(False, first["outbound_clearance"])

    def test_documented_false_defaults_share_cached_reads(self):
        cases = (
            ("conversations.history", {"channel": "C123"}, ("include_all_metadata",)),
            ("conversations.info", {"channel": "C123"}, ("include_locale", "include_num_members")),
            ("search.messages", {"query": "paid bounty"}, ("highlight",)),
        )
        for method, params, flags in cases:
            with self.subTest(method=method):
                baseline = self.broker.read(method, params, self.good)
                duplicate = self.broker.read(
                    method, {**params, **{flag: False for flag in flags}}, self.good)
                self.assertEqual(("FETCHED", "CACHED"), (baseline["state"], duplicate["state"]))
                self.assertEqual(baseline["data"], duplicate["data"])
                self.assertEqual(
                    normalize(method, params),
                    normalize(method, {**params, **{flag: False for flag in flags}}),
                )
                # True options remain separate response views, never cache aliases.
                for flag in flags:
                    self.assertTrue(normalize(method, {**params, flag: True})[flag])
        self.assertEqual(len(cases), self.calls)

    def test_fresh_only_cannot_bypass_rate_interval(self):
        self.broker.read(HISTORY, PARAMS, self.good)
        result = self.broker.read(HISTORY, PARAMS, self.good, 0)
        self.assertEqual("COOLDOWN", result["state"])
        self.assertNotIn("data", result)
        self.assertEqual(60, result["retry_after_seconds"])
        self.clock.advance(60)
        self.assertEqual("FETCHED", self.broker.read(HISTORY, PARAMS, self.good, 0)["state"])
        self.assertEqual(2, self.calls)

    def test_different_query_and_cursor_share_method_quota(self):
        self.broker.read(HISTORY, PARAMS, self.good)
        for params in ({"channel": "C456"}, {**PARAMS, "cursor": "opaque-page-2"}, {**PARAMS, "inclusive": True}):
            self.assertEqual("COOLDOWN", self.broker.read(HISTORY, params, self.good)["state"])
        self.assertEqual(1, self.calls)
        self.assertEqual("FETCHED", self.broker.read("conversations.info", PARAMS, self.good)["state"])

    def test_distinct_cursor_never_reuses_first_page(self):
        self.broker.read(HISTORY, PARAMS, self.good)
        self.clock.advance(60)
        result = self.broker.read(HISTORY, {**PARAMS, "cursor": "next-page"}, self.good)
        self.assertEqual("FETCHED", result["state"])
        self.assertEqual(2, self.calls)

    def test_workspace_and_app_separate_cache_and_quota(self):
        self.broker.read(HISTORY, PARAMS, self.good)
        for workspace, app in (("T456", "A123"), ("T123", "A456")):
            other = Broker(self.path, workspace, app, PRINCIPAL, clock=self.clock)
            self.assertEqual("FETCHED", other.read(HISTORY, PARAMS, self.good)["state"])
        self.assertEqual(3, self.calls)

    def test_token_namespaces_isolate_cache_but_share_app_quota(self):
        self.broker.read(HISTORY, PARAMS, self.good)
        other = Broker(self.path, "T123", "A123", "b" * 64, clock=self.clock)
        self.assertEqual("COOLDOWN", other.read(HISTORY, PARAMS, self.good)["state"])
        self.clock.advance(60)
        self.assertEqual("FETCHED", other.read(HISTORY, PARAMS, self.good)["state"])
        self.assertEqual(2, self.calls)

    def test_retry_after_persists_across_restart(self):
        first = self.broker.read(HISTORY, PARAMS, lambda *_: Upstream(429, retry_after="7200"))
        self.assertEqual("COOLDOWN", first["state"])
        self.assertEqual(7200, first["retry_after_seconds"])
        other = Broker(self.path, "T123", "A123", PRINCIPAL, clock=self.clock)
        self.clock.advance(100)
        result = other.read(HISTORY, {"channel": "C456"}, self.good)
        self.assertEqual(7100, result["retry_after_seconds"])
        self.assertEqual(0, self.calls)

    def test_short_429_does_not_shorten_reserved_method_interval(self):
        result = self.broker.read(HISTORY, PARAMS, lambda *_: Upstream(429, retry_after="1"))
        self.assertEqual(60, result["retry_after_seconds"])
        self.assertEqual(60, self.broker.read(HISTORY, {"channel": "C456"}, self.good)["retry_after_seconds"])

    def test_new_429_cannot_shorten_earlier_late_429(self):
        old = self.broker.acquire(HISTORY, PARAMS)
        self.clock.advance(61)
        new = self.broker.acquire(HISTORY, PARAMS)
        self.broker.finish(old, Upstream(429, retry_after="3600"))
        result = self.broker.finish(new, Upstream(429, retry_after="10"))
        self.assertEqual(3600, result["retry_after_seconds"])

    def test_http_unauthorized_purges_cached_namespace(self):
        self.broker.read(HISTORY, PARAMS, self.good)
        result = self.broker.read("conversations.info", PARAMS, lambda *_: Upstream(401))
        self.assertEqual("AUTH_BLOCKED", result["state"])
        self.assertEqual("AUTH_BLOCKED", self.broker.read(HISTORY, PARAMS, self.good)["state"])
        self.assertNotIn("data", result)

    def test_malformed_retry_after_is_conservative(self):
        for value in (None, "", "-1", "1.5", True, float("nan"), "secret"):
            self.assertEqual(60, retry_seconds(value))
        self.assertEqual(1, retry_seconds("0"))
        self.assertEqual(123456, retry_seconds("123456"))

    def test_slack_json_rate_error_is_not_success(self):
        result = self.broker.read(HISTORY, PARAMS, lambda *_: Upstream(200, {"ok": False, "error": "ratelimited"}))
        self.assertEqual("COOLDOWN", result["state"])
        self.assertNotIn("data", result)

    def test_busy_lease_does_not_call_provider(self):
        lease = self.broker.acquire(HISTORY, PARAMS)
        self.assertIsInstance(lease, Lease)
        self.assertEqual("BUSY", self.broker.read(HISTORY, PARAMS, self.good)["state"])
        self.assertEqual(0, self.calls)

    def test_crashed_owner_expires_and_cannot_overwrite_new_generation(self):
        old = self.broker.acquire(HISTORY, PARAMS)
        self.clock.advance(61)
        new = self.broker.acquire(HISTORY, PARAMS)
        self.assertIsInstance(new, Lease)
        self.assertNotEqual(old.nonce, new.nonce)
        self.assertEqual("DISCARDED", self.broker.finish(old, Upstream(200, {"ok": True, "messages": ["stale"]}))["state"])
        self.assertEqual("FETCHED", self.broker.finish(new, Upstream(200, {"ok": True, "messages": ["new"]}))["state"])
        self.assertEqual(["new"], self.broker.read(HISTORY, PARAMS, self.good)["data"]["messages"])
        self.assertEqual(0, self.calls)

    def test_expired_reply_is_discarded_without_successor(self):
        lease = self.broker.acquire(HISTORY, PARAMS)
        self.clock.advance(45)
        self.assertEqual("DISCARDED", self.broker.finish(lease, Upstream(200, {"ok": True}))["state"])
        with self.broker.connect() as db:
            self.assertEqual(0, db.execute("SELECT count(*) FROM cache").fetchone()[0])

    def test_late_429_still_extends_method_backoff(self):
        old = self.broker.acquire(HISTORY, PARAMS)
        self.clock.advance(61)
        new = self.broker.acquire(HISTORY, PARAMS)
        self.broker.finish(old, Upstream(429, retry_after="120"))
        self.broker.finish(new, Upstream(200, {"ok": True}))
        result = self.broker.read(HISTORY, {"channel": "C456"}, self.good)
        self.assertEqual("COOLDOWN", result["state"])
        self.assertEqual(120, result["retry_after_seconds"])

    def test_failed_read_never_becomes_an_empty_success(self):
        result = self.broker.read(HISTORY, PARAMS, lambda *_: Upstream(200, {"ok": False, "error": "missing_scope"}))
        self.assertEqual("UPSTREAM_ERROR", result["state"])
        self.assertEqual("missing_scope", result["error"])
        self.assertNotIn("data", result)
        self.clock.advance(60)
        self.assertEqual("FETCHED", self.broker.read(HISTORY, PARAMS, self.good)["state"])

    def test_provider_exception_is_redacted_and_releases_lease(self):
        secret = "DO-NOT-LOG-secret-query-or-token"
        def boom(*_):
            raise RuntimeError(secret)
        result = self.broker.read(HISTORY, PARAMS, boom)
        self.assertEqual("UPSTREAM_ERROR", result["state"])
        self.assertNotIn(secret, dumps(result))
        self.clock.advance(60)
        self.assertIsInstance(self.broker.acquire(HISTORY, PARAMS), Lease)

    def test_auth_failure_purges_namespace_and_blocks_cached_success(self):
        self.broker.read(HISTORY, PARAMS, self.good)
        bad = self.broker.read("conversations.info", PARAMS, lambda *_: Upstream(200, {"ok": False, "error": "token_revoked"}))
        self.assertEqual("AUTH_BLOCKED", bad["state"])
        after = Broker(self.path, "T123", "A123", PRINCIPAL, clock=self.clock)
        self.assertEqual("AUTH_BLOCKED", after.read(HISTORY, PARAMS, self.good)["state"])
        with after.connect() as db:
            self.assertEqual(0, db.execute("SELECT count(*) FROM cache").fetchone()[0])
        self.clock.advance(60)
        rotated = Broker(self.path, "T123", "A123", "b" * 64, clock=self.clock)
        self.assertEqual("FETCHED", rotated.read(HISTORY, PARAMS, self.good)["state"])

    def test_inflight_success_cannot_repopulate_revoked_namespace(self):
        lease = self.broker.acquire(HISTORY, PARAMS)
        self.broker.read("conversations.info", PARAMS, lambda *_: Upstream(200, {"ok": False, "error": "invalid_auth"}))
        self.assertEqual("AUTH_BLOCKED", self.broker.finish(lease, Upstream(200, {"ok": True}))["state"])

    def test_literal_ok_and_bounded_finite_payload_required(self):
        for payload in ({"ok": 1}, {"ok": True, "x": float("nan")}, {"ok": True, "x": "x" * 524288}, []):
            self.clock.advance(60)
            result = self.broker.read(HISTORY, PARAMS, lambda *_, p=payload: Upstream(200, p))
            self.assertEqual("UPSTREAM_ERROR", result["state"])
            self.assertNotIn("data", result)

    def test_unknown_error_text_is_not_reflected(self):
        result = self.broker.read(HISTORY, PARAMS, lambda *_: Upstream(200, {"ok": False, "error": "secret token"}))
        self.assertEqual("upstream_error", result["error"])

    def test_old_cache_is_not_returned_when_refresh_fails(self):
        self.broker.read(HISTORY, PARAMS, self.good)
        self.clock.advance(61)
        result = self.broker.read(HISTORY, PARAMS, lambda *_: Upstream(503))
        self.assertEqual("UPSTREAM_ERROR", result["state"])
        self.assertNotIn("data", result)
        with self.broker.connect() as db:
            self.assertEqual(0, db.execute("SELECT count(*) FROM cache").fetchone()[0])

    def test_clock_rollback_does_not_make_future_cache_fresh(self):
        self.broker.read(HISTORY, PARAMS, self.good)
        self.clock.advance(-5)
        result = self.broker.read(HISTORY, PARAMS, self.good)
        self.assertEqual("COOLDOWN", result["state"])
        self.assertNotIn("data", result)

    def test_cache_row_bound(self):
        bounded = Broker(self.path, "T123", "A123", PRINCIPAL, clock=self.clock, max_entries=2)
        for channel in ("C111", "C222", "C333"):
            self.clock.advance(4)
            bounded.read("conversations.info", {"channel": channel}, self.good)
        with bounded.connect() as db:
            self.assertEqual(2, db.execute("SELECT count(*) FROM cache").fetchone()[0])

    def test_unknown_database_version_is_not_overwritten(self):
        with self.broker.connect() as db:
            db.execute("PRAGMA user_version=99")
        with self.assertRaises(ValueError):
            Broker(self.path, "T123", "A123", PRINCIPAL)
        with self.broker.connect() as db:
            self.assertEqual(99, db.execute("PRAGMA user_version").fetchone()[0])

    def test_age_bool_and_invalid_configuration_rejected(self):
        for value in (True, -1, 301, 0.5, "0"):
            with self.assertRaises(ValueError):
                self.broker.acquire(HISTORY, PARAMS, value)
        with self.assertRaises(ValueError):
            Broker(self.path, "T123", "A123", "raw-token")
        with self.assertRaises(ValueError):
            Broker(self.path, "T123", "A123", PRINCIPAL, lease_seconds=float("inf"))

    def test_internal_profile_is_explicit(self):
        internal = Broker(self.path, "T123", "A123", PRINCIPAL, clock=self.clock, internal_app=True)
        self.assertEqual(100, internal.page_limit)
        self.assertEqual(1.25, internal.intervals[HISTORY])
        self.assertEqual(15, self.broker.page_limit)
        self.assertEqual(60, self.broker.intervals[HISTORY])

    def run_processes(self, different):
        context = multiprocessing.get_context("spawn")
        start, output, count = context.Event(), context.Queue(), context.Value("i", 0)
        workers = [context.Process(target=process_read, args=(str(self.path), start, output, count, different, i)) for i in range(8)]
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
            self.assertTrue(all(row[0] == "result" for row in rows), rows)
            self.assertEqual(1, count.value)
            states = [row[1] for row in rows]
            self.assertEqual(1, states.count("FETCHED"))
            allowed = {"FETCHED", "COOLDOWN"} if different else {"FETCHED", "CACHED", "BUSY"}
            self.assertTrue(set(states) <= allowed, states)
        finally:
            start.set()
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                if worker.pid:
                    worker.join(10)
            output.close()
            output.join_thread()

    def test_real_eight_process_identical_read_singleflight(self):
        self.run_processes(False)

    def test_real_eight_process_distinct_reads_share_method_quota(self):
        self.run_processes(True)


class ValidationTests(unittest.TestCase):
    def test_unknown_write_methods_and_token_overrides_rejected(self):
        for method, params in (("chat.postMessage", PARAMS), (HISTORY, {**PARAMS, "token": "secret"}), (HISTORY, {**PARAMS, "url": "http://other"}), ("auth.test", {}), ([], {})):
            with self.assertRaises(ValueError):
                normalize(method, params)

    def test_strict_types_and_required_fields(self):
        for params in ({}, {"channel": True}, {**PARAMS, "limit": True}, {**PARAMS, "limit": 0}, {**PARAMS, "limit": 16}, {**PARAMS, "ts": "1"}, {**PARAMS, "oldest": 1.2}, {**PARAMS, "inclusive": 1}, {**PARAMS, "cursor": "bad\nvalue"}):
            with self.assertRaises(ValueError):
                normalize(HISTORY, params)
        with self.assertRaises(ValueError):
            normalize("conversations.replies", PARAMS)
        with self.assertRaises(ValueError):
            normalize("search.messages", {"query": "foo", "sort": "random"})

    def test_cursor_exactness_and_type_normalization(self):
        self.assertEqual(" opaque= ", normalize(HISTORY, {**PARAMS, "cursor": " opaque= "})["cursor"])
        self.assertEqual("im,public_channel", normalize("conversations.list", {"types": "public_channel,im,im"})["types"])
        self.assertEqual("10.000001", normalize("conversations.replies", {**PARAMS, "ts": "10.000001"})["ts"])

    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ValueError):
                loads(text)


if __name__ == "__main__":
    unittest.main()
