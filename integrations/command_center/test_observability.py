#!/usr/bin/env python3
"""Contract for the observability snapshot.

The property that matters here is degradation. A dashboard that renders "0 live
seats" because a file was missing is worse than one that says it could not read
the file, so every source keeps its own status and a missing source leaves its
section null rather than empty.
"""

import json
import os
import shutil
import tempfile
import unittest

from integrations.command_center import observability


class Repo(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-observability-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def put(self, rel, payload):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

    def complete(self):
        self.put("pulse.json", {
            "seq": 1708, "head": "abc123", "ts": "2026-09-10T19:59:02Z",
            "post_count": 12096,
            "feed": {"delta": "feed/head.json", "full": "recent.json"},
        })
        self.put("feed/head.json", {
            "count": 2,
            "covers": {"newest": "2026-09-10T19:49:51Z|newest-post"},
            "complete_since": "2026-09-09T22:03:40Z|older-post",
            "cursor_rule": "compare c as a string",
            "undated": ["no-clock"],
            "events": [
                {"c": "2026-09-10T19:49:51Z|newest-post", "from": "SEAT_A",
                 "to": "TABLE", "x": "the newest thing"},
                {"c": "2026-09-09T22:03:40Z|older-post", "from": "SEAT_B",
                 "state": "INTEGRATED", "kind": "SHIP_RECEIPT", "x": "older"},
            ],
        })
        self.put("seats.json", {
            # This reference is intentionally a historical bake reference. The
            # observability reader must not trust its liveness values as current.
            "reference_time": "2026-09-10T20:00:00Z",
            "reference_source": "newest input timestamp unless --now was given",
            "liveness_bands_s": {"LIVE": 900, "QUIET": 3600, "STALE": 86400},
            "totals": {"seats": 3, "declared": 2, "presence_only": 1},
            "by_liveness": {"LIVE": 1, "QUIET": 1, "COLD": 1},
            "by_harness": {"harness-a": 1, "UNKNOWN": 2},
            "by_kind": {"language-model": 2, "UNKNOWN": 1},
            "context_pressure": [{"seat": "HOT", "pct": 91.0}],
            "budget_watch": [{"seat": "HOT", "remaining_pct": 5}],
            "open_cants": [
                {"seat": "HOT", "what": "no push", "need": "scope",
                 "est_minutes": 5},
                {"seat": "COLDSEAT", "what": "unscoped", "est_minutes": "UNKNOWN"},
            ],
            "unreadable_seat_files": [],
            "seats": [
                {"seat": "HOT",
                 "declared": {"heartbeat": "2026-09-10T19:55:00Z"},
                 "derived": {"liveness": "LIVE", "heartbeat_age_s": 0}},
                {"seat": "COLDSEAT",
                 "declared": {"heartbeat": "2026-09-01T00:00:00Z"},
                 "derived": {"liveness": "COLD", "heartbeat_age_s": 0}},
            ],
            "roster": [
                {"seat": "NAMEONLY", "heartbeat": "2026-09-10T19:20:00Z",
                 "liveness": "LIVE", "heartbeat_age_s": 0}
            ],
        })
        self.put("feed/github.json", {
            "schema": "commons-github-state/v1",
            "repository": "o/r",
            "counts": {"open_pull_requests": 106, "open_issues": 3,
                       "runs_queued": 2275, "runs_in_progress": 18},
            "queue_depth_per_runner": 126.4,
            "pulls_listed": 100,
            "newest_pulls": [{"number": 12094, "title": "newest",
                              "author": "who", "draft": False,
                              "created_at": "2026-09-10T21:26:14Z",
                              "branch": "b"}],
            "longest_open": [],
            "drafts": 12,
            "undatable_pulls": [],
            "degraded": [],
            "unchanged_since": "2026-09-10T21:30:00Z",
        })


class TestCompleteSnapshot(Repo):
    def setUp(self):
        super().setUp()
        self.complete()
        self.now = "2026-09-10T20:05:00Z"
        self.snap = observability.snapshot(self.root, now=self.now)

    def test_every_source_reads_and_nothing_is_degraded(self):
        self.assertEqual(self.snap["degraded"], [])
        self.assertIsNone(self.snap["coordination"], "a checkout has no state branch")
        self.assertTrue(all(s["ok"] for s in self.snap["sources"]))
        self.assertEqual([s["path"] for s in self.snap["sources"]],
                         ["feed/github.json", "feed/head.json", "pulse.json",
                          "seats.json"])

    def test_repository_state_travels_through_untouched(self):
        repo = self.snap["repository"]
        self.assertEqual(repo["counts"]["runs_queued"], 2275)
        self.assertEqual(repo["queue_depth_per_runner"], 126.4)
        self.assertEqual(repo["newest_pulls"][0]["number"], 12094)
        self.assertNotIn("age_hours", repo["newest_pulls"][0])

    def test_pulse_carries_the_cursor_pointers(self):
        self.assertEqual(self.snap["pulse"]["seq"], 1708)
        self.assertEqual(self.snap["pulse"]["feed"]["delta"], "feed/head.json")

    def test_board_events_recover_their_ids_from_the_cursor(self):
        events = self.snap["board"]["events"]
        self.assertEqual(events[0]["id"], "newest-post")
        self.assertEqual(events[0]["from"], "SEAT_A")
        self.assertEqual(events[1]["kind"], "SHIP_RECEIPT")
        self.assertEqual(self.snap["board"]["undated"], ["no-clock"])
        self.assertEqual(events[0]["state"], "DURABLE_PAGE")

    def test_priced_and_unpriced_unblocks_are_separated(self):
        seats = self.snap["seats"]
        self.assertEqual([c["seat"] for c in seats["priced_unblocks"]], ["HOT"])
        self.assertEqual([c["seat"] for c in seats["unpriced_unblocks"]],
                         ["COLDSEAT"])

    def test_routable_seats_use_read_time_not_baked_liveness(self):
        seats = self.snap["seats"]
        self.assertEqual([s["seat"] for s in seats["routable"]], ["HOT"])
        self.assertEqual([r["seat"] for r in seats["awake_undeclared"]],
                         ["NAMEONLY"])
        self.assertEqual(seats["reference_time"], self.now)
        self.assertEqual(seats["baked_reference_time"], "2026-09-10T20:00:00Z")
        self.assertEqual(seats["reference_source"], "read-time heartbeat derivation")

    def test_headline_is_one_readable_line(self):
        self.assertEqual(
            self.snap["headline"],
            "1 live, 1 quiet, 2 events in the delta shard, 1 priced unblocks")

    def test_board_limit_caps_events_without_changing_the_count(self):
        snap = observability.snapshot(self.root, feed_limit=1, now=self.now)
        self.assertEqual(len(snap["board"]["events"]), 1)
        self.assertEqual(snap["board"]["count"], 2)


class TestReadTimeLiveness(Repo):
    def test_unchanged_bake_ages_live_to_quiet_to_stale_to_cold(self):
        self.complete()
        path = os.path.join(self.root, "seats.json")
        with open(path, "rb") as fh:
            before = fh.read()

        cases = [
            ("2026-09-10T20:05:00Z", "LIVE", True),
            ("2026-09-10T20:20:00Z", "QUIET", True),
            ("2026-09-10T21:00:01Z", "STALE", False),
            ("2026-09-11T19:55:01Z", "COLD", False),
        ]
        for now, expected, routable in cases:
            snap = observability.snapshot(self.root, now=now)
            hot = [s for s in snap["seats"]["seats"] if s["seat"] == "HOT"][0]
            self.assertEqual(hot["derived"]["liveness"], expected, now)
            routed = [s["seat"] for s in snap["seats"]["routable"]]
            self.assertEqual("HOT" in routed, routable, now)

        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), before,
                             "read-time aging must not mutate the stable bake")

    def with_heartbeat(self, heartbeat, skew=None):
        self.complete()
        with open(os.path.join(self.root, "seats.json"), encoding="utf-8") as fh:
            seats = json.load(fh)
        seats["seats"][0]["declared"]["heartbeat"] = heartbeat
        if skew is not None:
            seats["heartbeat_future_skew_s"] = skew
        self.put("seats.json", seats)

    def hot(self, snap):
        return [s for s in snap["seats"]["seats"] if s["seat"] == "HOT"][0]

    def test_a_heartbeat_within_clock_skew_reads_live_at_age_zero(self):
        self.with_heartbeat("2026-09-10T20:03:00Z")
        snap = observability.snapshot(self.root, now="2026-09-10T20:00:00Z")
        hot = self.hot(snap)
        self.assertEqual(hot["derived"]["liveness"], "LIVE")
        self.assertEqual(hot["derived"]["heartbeat_age_s"], 0)
        self.assertNotIn("heartbeat_future_s", hot["derived"])
        self.assertEqual(snap["seats"]["future_heartbeats"], [])

    def test_a_heartbeat_hours_ahead_is_unknown_and_not_routable(self):
        # Nothing can declare itself alive: +4h (or 2099) is not LIVE.
        for heartbeat, ahead in (("2026-09-11T00:00:00Z", 4 * 3600),
                                 ("2099-01-01T00:00:00Z", None)):
            self.with_heartbeat(heartbeat)
            snap = observability.snapshot(self.root, now="2026-09-10T20:00:00Z")
            hot = self.hot(snap)
            self.assertEqual(hot["derived"]["liveness"], "UNKNOWN", heartbeat)
            self.assertEqual(hot["derived"]["heartbeat_age_s"], "UNKNOWN")
            self.assertNotIn("HOT", [s["seat"] for s in snap["seats"]["routable"]])
            named = snap["seats"]["future_heartbeats"]
            self.assertEqual([f["seat"] for f in named], ["HOT"])
            if ahead is not None:
                self.assertEqual(named[0]["ahead_s"], ahead)
                self.assertEqual(hot["derived"]["heartbeat_future_s"], ahead)
            self.assertNotIn("LIVE", snap["seats"]["by_liveness"])

    def test_a_seat_recovers_once_it_writes_a_real_heartbeat(self):
        self.with_heartbeat("2099-01-01T00:00:00Z")
        before = observability.snapshot(self.root, now="2026-09-10T20:00:00Z")
        self.assertEqual(self.hot(before)["derived"]["liveness"], "UNKNOWN")
        self.with_heartbeat("2026-09-10T19:58:00Z")
        after = observability.snapshot(self.root, now="2026-09-10T20:00:00Z")
        self.assertEqual(self.hot(after)["derived"]["liveness"], "LIVE")
        self.assertIn("HOT", [s["seat"] for s in after["seats"]["routable"]])
        self.assertNotIn("heartbeat_future_s", self.hot(after)["derived"])

    def test_the_skew_comes_from_the_bake_and_bad_values_fall_back(self):
        # seats.json says 60 s: three minutes ahead is now beyond tolerance.
        self.with_heartbeat("2026-09-10T20:03:00Z", skew=60)
        snap = observability.snapshot(self.root, now="2026-09-10T20:00:00Z")
        self.assertEqual(snap["seats"]["heartbeat_future_skew_s"], 60)
        self.assertEqual(self.hot(snap)["derived"]["liveness"], "UNKNOWN")
        for bad in (-5, "soon", True, None):
            self.with_heartbeat("2026-09-10T20:03:00Z", skew=bad)
            snap = observability.snapshot(self.root, now="2026-09-10T20:00:00Z")
            self.assertEqual(snap["seats"]["heartbeat_future_skew_s"],
                             observability.FUTURE_SKEW_S, bad)
            self.assertEqual(self.hot(snap)["derived"]["liveness"], "LIVE", bad)


class TestDegradation(Repo):
    def test_a_missing_source_is_named_not_rendered_as_empty(self):
        self.complete()
        os.remove(os.path.join(self.root, "seats.json"))
        snap = observability.snapshot(self.root)
        self.assertIsNone(snap["seats"])
        self.assertEqual(snap["degraded"], ["seats.json"])
        self.assertIn("could not read seats.json", snap["headline"])
        self.assertIsNotNone(snap["board"])
        self.assertEqual(snap["pulse"]["seq"], 1708)

    def test_a_malformed_source_is_named_with_its_error(self):
        self.complete()
        with open(os.path.join(self.root, "pulse.json"), "w",
                  encoding="utf-8") as fh:
            fh.write("{ not json")
        snap = observability.snapshot(self.root)
        self.assertIsNone(snap["pulse"])
        entry = [s for s in snap["sources"] if s["path"] == "pulse.json"][0]
        self.assertFalse(entry["ok"])
        self.assertEqual(entry["error"], "JSONDecodeError")

    def test_an_empty_repository_degrades_everywhere_without_raising(self):
        snap = observability.snapshot(self.root)
        self.assertEqual(sorted(snap["degraded"]),
                         ["feed/github.json", "feed/head.json", "pulse.json",
                          "seats.json"])
        self.assertIsNone(snap["pulse"])
        self.assertIsNone(snap["board"])
        self.assertIsNone(snap["seats"])
        self.assertIsNone(snap["repository"])
        self.assertTrue(snap["headline"].startswith("Partial"))

    def test_repository_state_can_be_absent_while_the_rest_reads(self):
        self.complete()
        os.remove(os.path.join(self.root, "feed", "github.json"))
        snap = observability.snapshot(self.root, now="2026-09-10T20:05:00Z")
        self.assertIsNone(snap["repository"])
        self.assertEqual(snap["degraded"], ["feed/github.json"])
        self.assertIsNotNone(snap["board"])
        self.assertIsNotNone(snap["seats"])

    def test_snapshot_never_mutates_the_repository(self):
        self.complete()
        before = sorted(
            (os.path.relpath(os.path.join(dirpath, name), self.root),
             os.path.getsize(os.path.join(dirpath, name)))
            for dirpath, _, names in os.walk(self.root) for name in names)
        observability.snapshot(self.root)
        after = sorted(
            (os.path.relpath(os.path.join(dirpath, name), self.root),
             os.path.getsize(os.path.join(dirpath, name)))
            for dirpath, _, names in os.walk(self.root) for name in names)
        self.assertEqual(before, after)


class BakeFetcher:
    """Stands in for GitHub: a commit SHA for main, and the bakes at a SHA."""

    def __init__(self, bakes, sha="a" * 40):
        self.bakes = bakes
        self.sha = sha
        self.calls = []
        self.fail_head = False
        self.missing = set()
        self.coordination = None

    def __call__(self, method, url, payload=None):
        self.calls.append(url)
        if url.endswith("/commits/main"):
            if self.fail_head:
                raise OSError("network down")
            return {"sha": self.sha}
        if url.endswith("/state/coordination/coordination-head.json"):
            if self.coordination is None:
                raise OSError("no state branch yet")
            return json.loads(json.dumps(self.coordination))
        if "raw.githubusercontent.com" in url:
            for rel, value in self.bakes.items():
                if url.endswith("/" + self.sha + "/" + rel):
                    if rel in self.missing:
                        raise OSError("not there")
                    return json.loads(json.dumps(value))
            # The resource-ledger sources this app also pins.
            return {}
        raise OSError("unexpected " + url)

    def bake_calls(self):
        return [u for u in self.calls if "raw.githubusercontent.com" in u
                and any(u.endswith(rel) for rel in self.bakes)]


class TestPinnedMainReads(Repo):
    """The owner's checkout is only as current as its last pull; the panel
    reads the bakes from main at the commit the rest of the app pins."""

    def setUp(self):
        super().setUp()
        from integrations.command_center.core import CommandCenter
        self.complete()                       # the stale local checkout
        self.state = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.state.cleanup)
        main_seats = json.loads(open(os.path.join(self.root, "seats.json"),
                                     encoding="utf-8").read())
        main_seats["seats"][0]["seat"] = "ONMAIN"
        self.fetcher = BakeFetcher({
            "pulse.json": {"seq": 2000, "head": "mainhead", "ts": "2026-09-11T00:00:00Z"},
            "feed/head.json": {"count": 1, "events": [
                {"c": "2026-09-11T00:00:00Z|fresh", "from": "M", "x": "on main"}]},
            "seats.json": main_seats,
            "feed/github.json": {"schema": "commons-github-state/v1",
                                 "counts": {"open_pull_requests": 150}},
        })
        self.center = CommandCenter(self.state.name, fetcher=self.fetcher)

    def test_every_bake_comes_from_main_at_the_pinned_commit(self):
        snap = self.center.observability(20, self.root)
        self.assertEqual(snap["roads"], ["main"])
        self.assertEqual(snap["main"]["sha"], "a" * 40)
        self.assertEqual(snap["pulse"]["seq"], 2000, "not the checkout's 1708")
        self.assertEqual(snap["board"]["events"][0]["id"], "fresh")
        self.assertEqual(snap["seats"]["seats"][0]["seat"], "ONMAIN")
        self.assertEqual(snap["repository"]["counts"]["open_pull_requests"], 150)
        for source in snap["sources"]:
            self.assertEqual(source["road"], "main")
            self.assertEqual(source["sha"], "a" * 40)
            self.assertNotIn("value", source)

    def test_coordination_head_comes_from_the_state_branch_beside_sources(self):
        self.fetcher.coordination = {"schema": "commons-coordination-head/v1",
                                     "counts": {"open_prs": 264,
                                                "drift": {"disjoint": 40, "overlap": 3}}}
        snap = self.center.observability(20, self.root)
        self.assertEqual(snap["coordination"]["counts"]["open_prs"], 264)
        self.assertEqual(snap["coordination_source"]["road"], "state-branch")
        self.assertEqual(snap["coordination_source"]["branch"], "state/coordination")
        self.assertNotIn("coordination-head.json", [s["path"] for s in snap["sources"]])
        self.assertEqual(snap["degraded"], [])

    def test_a_missing_state_branch_is_absent_not_degraded(self):
        snap = self.center.observability(20, self.root)
        self.assertIsNone(snap["coordination"])
        self.assertFalse(snap["coordination_source"]["ok"])
        self.assertIn("error", snap["coordination_source"])
        self.assertEqual(snap["degraded"], [])

    def test_bakes_are_cached_until_main_moves_or_the_ttl(self):
        self.center.observability(20, self.root)
        first = len(self.fetcher.bake_calls())
        self.assertEqual(first, 4)
        self.center.observability(20, self.root)
        self.assertEqual(len(self.fetcher.bake_calls()), 4, "cached inside the TTL")
        # main moves: the next forced read re-reads every bake at the new SHA.
        self.fetcher.sha = "b" * 40
        snap = self.center.observability(20, self.root, refresh=True)
        self.assertEqual(snap["main"]["sha"], "b" * 40)
        self.assertEqual(len(self.fetcher.bake_calls()), 8)

    def test_a_bake_main_cannot_supply_falls_back_to_the_checkout_labelled(self):
        self.fetcher.missing.add("seats.json")
        snap = self.center.observability(20, self.root)
        seats = [s for s in snap["sources"] if s["path"] == "seats.json"][0]
        self.assertEqual(seats["road"], "checkout")
        self.assertIn("main_error", seats)
        self.assertEqual(snap["roads"], ["checkout", "main"])
        self.assertEqual(snap["seats"]["seats"][0]["seat"], "HOT", "checkout copy")
        self.assertEqual(snap["pulse"]["seq"], 2000, "the other bakes still from main")

    def test_main_unreachable_reads_the_checkout_and_says_why(self):
        self.fetcher.fail_head = True
        snap = self.center.observability(20, self.root)
        self.assertEqual(snap["roads"], ["checkout"])
        self.assertIsNone(snap["main"]["sha"])
        self.assertEqual(snap["pulse"]["seq"], 1708)
        for source in snap["sources"]:
            self.assertTrue(source["main_error"].startswith("main unavailable"))

    def test_neither_road_is_degraded_not_empty(self):
        self.fetcher.missing.add("feed/github.json")
        os.remove(os.path.join(self.root, "feed", "github.json"))
        snap = self.center.observability(20, self.root)
        self.assertIn("feed/github.json", snap["degraded"])
        self.assertIsNone(snap["repository"])


class RouteCenter:
    """Only what the observability route and the manifest touch."""

    def __init__(self):
        self.calls = []

    def observability(self, limit, repo_root, refresh=False):
        self.calls.append((limit, bool(repo_root), refresh))
        return {"schema": observability.SCHEMA, "roads": ["main"]}


class TestHTTPRoute(unittest.TestCase):
    def setUp(self):
        import threading
        from integrations.command_center.server import Server
        self.center = RouteCenter()
        self.server = Server(("127.0.0.1", 0), self.center)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = "http://127.0.0.1:%d" % self.server.server_port

    def get(self, path):
        import urllib.request
        with urllib.request.urlopen(self.base + path, timeout=5) as response:
            return json.load(response)

    def test_the_route_reads_through_the_center_with_limit_and_refresh(self):
        self.assertEqual(self.get("/api/observability?limit=500&refresh=1")["roads"],
                         ["main"])
        self.get("/api/observability?limit=nonsense")
        self.assertEqual(self.center.calls, [(200, True, True), (20, True, False)])

    def test_the_manifest_says_how_fresh_work_and_observability_are(self):
        manifest = self.get("/api/manifest")
        self.assertIn("freshness", manifest["work"])
        self.assertIn("from main at the current commit", manifest["observability"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
