#!/usr/bin/env python3
"""Contract for host/coordination_state.py (first draft; fix freely).

Offline throughout: verdict text comes from real review bodies, git runs
against throwaway repositories, and GitHub replies come from a fake transport.
"""

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from host import coordination_state as cs  # noqa: E402

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def sh(root, *args, input_text=None):
    env = dict(os.environ)
    env.update(ENV)
    done = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True,
                          env=env, input=input_text)
    if done.returncode != 0:
        raise AssertionError("git %s failed: %s" % (args, done.stderr))
    return done.stdout.strip()


def write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def commit_all(root, message):
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", message)
    return sh(root, "rev-parse", "HEAD")


class TempGit(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="coordination-state-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        sh(self.root, "init", "-q", "-b", "main")
        sh(self.root, "config", "core.autocrlf", "false")
        write(self.root, "a.txt", "a0\n")
        write(self.root, "b.txt", "b0\n")
        write(self.root, "docs/shared.md", "one\ntwo\nthree\n")
        self.base = commit_all(self.root, "base")
        self.git = cs.Git(self.root)

    def branch(self, name, start):
        sh(self.root, "checkout", "-q", "-B", name, start)


class VerdictParsing(unittest.TestCase):
    def test_source_and_current_main_read_as_separate_fields(self):
        text = ("SOURCE / CURRENT-MAIN COMPOSITION-CUSTODY PASS; HOSTED GATE PENDING.\n\n"
                "Exact rereview bound #12332 head `51596c41add10a956eb5f27df73f845c89fc1edf` ...")
        parsed = cs.parse_verdict(text)
        self.assertEqual(parsed["fields"]["source"], "PASS")
        self.assertEqual(parsed["fields"]["current_main"], "PASS")
        self.assertEqual(parsed["fields"]["hosted"], "PENDING")

    def test_bold_middots_and_not_green(self):
        text = ("EXACT-HEAD REREVIEW on `5dc97b2949596bb3b9da7bbc4d38181e94ad20e5`: **SOURCE / "
                "LIVE-a612 SUBMISSION-CUSTODY PASS · HOSTED NOT GREEN · CONDITIONAL ECONOMICS "
                "PENDING**.\n\nThis head closes review `5177283488`'s remaining gap.")
        parsed = cs.parse_verdict(text)
        self.assertEqual(parsed["fields"]["source"], "PASS")
        self.assertEqual(parsed["fields"]["current_main"], "PASS")
        self.assertEqual(parsed["fields"]["hosted"], "PENDING")
        self.assertEqual(parsed["fields"]["economics"], "PENDING")
        self.assertIn("5dc97b2949596bb3b9da7bbc4d38181e94ad20e5", parsed["heads"])

    def test_hold_closed_reads_pass_and_hold_reads_hold(self):
        text = ("Exact-head rebound review on `dd41984ec477d6a1b07bbab2779a2e9f54f879c4`: "
                "**SOURCE / PACKAGE-DELTA / SCORE-FACING CUSTODY PASS · PREBUILD-IMPORT HOLD "
                "CLOSED · HOSTED PENDING**.")
        parsed = cs.parse_verdict(text)
        verdicts = {s["label"]: s["verdict"] for s in parsed["segments"]}
        self.assertEqual(verdicts["PREBUILD-IMPORT"], "PASS")
        self.assertEqual(parsed["fields"]["composition"], "PASS")
        held = cs.parse_verdict("SOURCE / SEMANTIC PASS; CURRENT-MAIN COMPOSITION HOLD ONLY.")
        self.assertEqual(held["fields"]["current_main"], "HOLD")
        self.assertEqual(held["fields"]["source"], "PASS")

    def test_only_the_verdict_paragraph_is_read(self):
        text = ("SOURCE / COMPOSITION-CUSTODY PASS; HOSTED GATE PENDING.\n\n"
                "The prior HOLD on the old head is closed; an earlier FAIL came from a stale base.")
        parsed = cs.parse_verdict(text)
        self.assertEqual(parsed["fields"], {"source": "PASS", "composition": "PASS",
                                            "hosted": "PENDING"})

    def test_supersession_ids_are_collected(self):
        text = ("CORRECTION / CURRENT-MAIN HOLD — durable correction review `5175770895` "
                "supersedes review 5175764334 for integration.")
        parsed = cs.parse_verdict(text)
        self.assertIn("5175764334", parsed["mentions_ids"])

    def test_pull_verdicts_prefer_current_head_and_skip_superseded(self):
        head = "dd41984ec477d6a1b07bbab2779a2e9f54f879c4"
        pull = {"reviews": {"nodes": [
            {"databaseId": 1111111111, "submittedAt": "2026-09-11T09:46:57Z", "url": "u1",
             "commit": {"oid": "a595843f2ed64ec591cc1a1a2939897585f5b285"},
             "body": "SOURCE / PACKAGE-CUSTODY PASS · CLI PREBUILD PROOF HOLD · HOSTED PENDING"},
            {"databaseId": 2222222222, "submittedAt": "2026-09-11T09:51:11Z", "url": "u2",
             "commit": {"oid": head},
             "body": "SOURCE / PACKAGE-DELTA / CUSTODY PASS · HOSTED PENDING"},
            {"databaseId": 3333333333, "submittedAt": "2026-09-11T09:52:00Z", "url": "u3",
             "commit": {"oid": head},
             "body": "CORRECTION: review 2222222222 is superseded. SOURCE HOLD."},
        ]}, "comments": {"nodes": []}}
        out = cs.pull_verdicts(pull, head)
        self.assertEqual(out["current_head"]["source"]["id"], "3333333333")
        self.assertEqual(out["current_head"]["source"]["verdict"], "HOLD")
        superseded = {r["id"]: r["superseded"] for r in out["records"]}
        self.assertTrue(superseded["2222222222"])
        self.assertFalse(superseded["1111111111"])


class HostedChecks(unittest.TestCase):
    def test_enum_never_collapses_queued(self):
        run = lambda s, c=None: {"__typename": "CheckRun", "status": s, "conclusion": c}
        self.assertEqual(cs.check_enum(run("QUEUED")), "NOT_EXECUTED_QUEUED")
        self.assertEqual(cs.check_enum(run("IN_PROGRESS")), "RUNNING")
        self.assertEqual(cs.check_enum(run("COMPLETED", "ACTION_REQUIRED")), "APPROVAL_GATED")
        self.assertEqual(cs.check_enum(run("COMPLETED", "CANCELLED")), "CANCELLED_NOT_RUN")
        self.assertEqual(cs.check_enum(run("COMPLETED", "FAILURE")), "FAILED")
        self.assertEqual(cs.check_enum(run("COMPLETED", "SUCCESS")), "SUCCESS")
        self.assertEqual(cs.check_enum({"__typename": "StatusContext", "state": "PENDING"}),
                         "NOT_EXECUTED_QUEUED")

    def test_rollup_order(self):
        def pull(*states):
            nodes = [{"__typename": "CheckRun", "name": "c%d" % i, "status": s[0], "conclusion": s[1]}
                     for i, s in enumerate(states)]
            return {"commits": {"nodes": [{"commit": {"statusCheckRollup": {"contexts": {"nodes": nodes}}}}]}}
        self.assertEqual(cs.hosted_state(pull(("QUEUED", None), ("COMPLETED", "SUCCESS")))["rollup"],
                         "NOT_EXECUTED_QUEUED")
        self.assertEqual(cs.hosted_state(pull(("COMPLETED", "FAILURE"), ("QUEUED", None)))["rollup"],
                         "FAILED")
        self.assertEqual(cs.hosted_state(pull(("COMPLETED", "SUCCESS")))["rollup"], "SUCCESS")
        self.assertEqual(cs.hosted_state({"commits": {"nodes": []}})["rollup"], "NONE")


class LanesAndKeys(unittest.TestCase):
    def test_marker_family_strips_base_date_and_step(self):
        self.assertEqual(cs.marker_family("KCWATER-PR12310-MAIN4EC4-REFRESH-COMPOSE-20260911-01"),
                         cs.marker_family("KCWATER-PR12310-MAIN4EC-REFRESH-COMPOSE-20260911-02"))
        self.assertEqual(cs.change_key("OBSERVABILITY-PR12309-MAINB009-REFRESH-COMPOSE-20260911-02"),
                         "observability-pr12309")
        self.assertEqual(cs.change_key(pr=12546), "pr-12546")
        self.assertEqual(cs.change_key(content="ABCDEF0123456789FFFF"), "ck-abcdef0123456789")

    def test_links_from_titles_bodies_and_comments(self):
        pull = {"number": 12309, "title": "[SUPERSEDED BY #12316] observability refresh",
                "body": "", "comments": {"nodes": [{"body": "canonical target is draft Commons #12316"}]}}
        self.assertEqual(cs.pull_links(pull), [12316])

    def test_lanes_join_by_content_key_and_links(self):
        rows = [
            {"number": 1, "state": "CLOSED", "created_at": "t1", "content_key": "k" * 64, "links": [3], "markers": []},
            {"number": 2, "state": "CLOSED", "created_at": "t2", "content_key": "k" * 64, "links": [], "markers": []},
            {"number": 3, "state": "OPEN", "created_at": "t3", "content_key": "j" * 64, "links": [], "markers": []},
            {"number": 4, "state": "OPEN", "created_at": "t4", "content_key": "j" * 64, "links": [], "markers": []},
            {"number": 5, "state": "OPEN", "created_at": "t5", "content_key": cs.UNKNOWN, "links": [], "markers": []},
        ]
        lanes = cs.build_lanes(rows)
        joined = [l for l in lanes if 1 in l["chain"]][0]
        self.assertEqual(joined["chain"], [1, 2, 3, 4])
        self.assertEqual(joined["open"], [3, 4])
        self.assertEqual(joined["canonical"], 4)
        alone = [l for l in lanes if 5 in l["chain"]][0]
        self.assertEqual(alone["chain"], [5])


class Drift(TempGit):
    def test_disjoint_advance_composes_exactly(self):
        self.branch("pr", self.base)
        write(self.root, "a.txt", "a1 from the change\n")
        head = commit_all(self.root, "change a")
        self.branch("main", self.base)
        write(self.root, "b.txt", "b1 moved on main\n")
        write(self.root, "c.txt", "new on main\n")
        tip = commit_all(self.root, "main moves elsewhere")
        cert = cs.drift_certificate(self.git, tip, head)
        self.assertEqual(cert["status"], "disjoint")
        self.assertEqual(cert["paths"], ["a.txt"])
        self.assertEqual(cert["overlap"], [])
        self.assertEqual(cert["main_delta_count"], 2)
        merged = sh(self.root, "merge-tree", "--write-tree", tip, head).splitlines()[0]
        self.assertEqual(cert["composed_tree"], merged)

    def test_overlap_names_the_paths(self):
        self.branch("pr", self.base)
        write(self.root, "a.txt", "a1 from the change\n")
        head = commit_all(self.root, "change a")
        self.branch("main", self.base)
        write(self.root, "a.txt", "a2 on main\n")
        tip = commit_all(self.root, "main touches a")
        cert = cs.drift_certificate(self.git, tip, head)
        self.assertEqual(cert["status"], "overlap")
        self.assertEqual(cert["overlap"], ["a.txt"])
        self.assertNotIn("composed_tree", cert)

    def test_current_and_contained(self):
        self.branch("pr", self.base)
        write(self.root, "d.txt", "added\n")
        head = commit_all(self.root, "add d")
        cert = cs.drift_certificate(self.git, self.base, head)
        self.assertEqual(cert["status"], "current")
        same = cs.drift_certificate(self.git, head, self.base)
        self.assertEqual(same["status"], "contained")
        self.assertEqual(same["content_key"], cs.UNKNOWN)

    def test_carriers_of_the_same_change_share_a_content_key(self):
        self.branch("pr1", self.base)
        write(self.root, "a.txt", "same change\n")
        head1 = commit_all(self.root, "carrier one")
        self.branch("main", self.base)
        write(self.root, "b.txt", "main moved\n")
        tip = commit_all(self.root, "main moves")
        self.branch("pr2", tip)
        write(self.root, "a.txt", "same change\n")
        head2 = commit_all(self.root, "carrier two on the new main")
        one = cs.drift_certificate(self.git, tip, head1)
        two = cs.drift_certificate(self.git, tip, head2)
        self.assertEqual(one["content_key"], two["content_key"])
        self.assertEqual(one["composed_tree"], sh(self.root, "rev-parse", head2 + "^{tree}"))


class Holdings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="coordination-holdings-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.remote = os.path.join(self.tmp, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", self.remote], check=True)
        self.a = self.clone("a")
        self.b = self.clone("b")
        self.t0 = dt.datetime(2026, 9, 11, 12, 0, tzinfo=dt.timezone.utc)

    def clone(self, name):
        root = os.path.join(self.tmp, name)
        subprocess.run(["git", "init", "-q", root], check=True)
        sh(root, "remote", "add", "origin", self.remote)
        return cs.Git(root)

    def test_take_hold_release_and_lapse(self):
        first = cs.holding_write(self.a, "pr-12546", "OPUS", "take", ttl_s=600, now=self.t0)
        self.assertTrue(first["ok"])
        second = cs.holding_write(self.b, "pr-12546", "ASTRA", "take", ttl_s=600,
                                  now=self.t0 + dt.timedelta(seconds=30))
        self.assertFalse(second["ok"])
        self.assertEqual(second["held_by"], "OPUS")
        renew = cs.holding_write(self.b, "pr-12546", "ASTRA", "renew",
                                 now=self.t0 + dt.timedelta(seconds=40))
        self.assertFalse(renew["ok"])
        later = cs.holding_write(self.b, "pr-12546", "ASTRA", "take", ttl_s=600,
                                 now=self.t0 + dt.timedelta(seconds=900))
        self.assertTrue(later["ok"])
        self.assertEqual(later["record"]["previous_holder"], "OPUS")
        done = cs.holding_write(self.b, "pr-12546", "ASTRA", "release",
                                now=self.t0 + dt.timedelta(seconds=960))
        self.assertTrue(done["ok"])
        listing = cs.holdings_list(self.a, now=self.t0 + dt.timedelta(seconds=961))
        row = [r for r in listing["holdings"] if r["key"] == "pr-12546"][0]
        self.assertEqual(row["state"], "RELEASED")
        self.assertFalse(row["live"])

    def test_losing_a_race_rereads_and_reports_the_holder(self):
        base = cs.holding_write(self.a, "seed", "OPUS", "take", now=self.t0)
        self.assertTrue(base["ok"])
        stale_tip = base["commit"]
        won = cs.holding_write(self.a, "lane-x", "OPUS", "take", now=self.t0 + dt.timedelta(seconds=1))
        self.assertTrue(won["ok"])
        real = cs._remote_tip
        calls = {"n": 0}

        def stale_then_real(git, branch, remote="origin"):
            calls["n"] += 1
            return stale_tip if calls["n"] == 1 else real(git, branch, remote)

        cs._remote_tip = stale_then_real
        try:
            lost = cs.holding_write(self.b, "lane-x", "ASTRA", "take", now=self.t0 + dt.timedelta(seconds=2))
        finally:
            cs._remote_tip = real
        self.assertFalse(lost["ok"])
        self.assertEqual(lost["held_by"], "OPUS")
        self.assertGreaterEqual(calls["n"], 2)

    def test_future_heartbeat_is_live_and_blocks_take(self):
        future = self.t0 + dt.timedelta(seconds=60)
        first = cs.holding_write(self.a, "lane-future", "OPUS", "take", ttl_s=600, now=future)
        self.assertTrue(first["ok"])
        blocked = cs.holding_write(self.b, "lane-future", "ASTRA", "take", ttl_s=600, now=self.t0)
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["held_by"], "OPUS")
        listing = cs.holdings_list(self.b, now=self.t0)
        row = [r for r in listing["holdings"] if r["key"] == "lane-future"][0]
        self.assertTrue(row["live"])

    def test_same_holder_backward_clock_keeps_heartbeat_monotonic_and_renews_ttl(self):
        future = self.t0 + dt.timedelta(seconds=60)
        first = cs.holding_write(self.a, "lane-renew", "OPUS", "take", ttl_s=600, now=future)
        self.assertTrue(first["ok"])
        renewed = cs.holding_write(self.a, "lane-renew", "OPUS", "renew", ttl_s=1200, now=self.t0)
        self.assertTrue(renewed["ok"])
        self.assertEqual(renewed["record"]["heartbeat_at"], cs._iso(future))
        self.assertEqual(renewed["record"]["ttl_s"], 1200)

    def test_nff_retry_with_older_clock_preserves_future_winner(self):
        base = cs.holding_write(self.a, "seed-skew", "OPUS", "take", now=self.t0)
        self.assertTrue(base["ok"])
        stale_tip = base["commit"]
        won = cs.holding_write(self.a, "lane-skew", "OPUS", "take",
                               now=self.t0 + dt.timedelta(seconds=10))
        self.assertTrue(won["ok"])
        real = cs._remote_tip
        calls = {"n": 0}

        def stale_then_real(git, branch, remote="origin"):
            calls["n"] += 1
            return stale_tip if calls["n"] == 1 else real(git, branch, remote)

        cs._remote_tip = stale_then_real
        try:
            lost = cs.holding_write(self.b, "lane-skew", "ASTRA", "take",
                                    now=self.t0 + dt.timedelta(seconds=5))
        finally:
            cs._remote_tip = real
        self.assertFalse(lost["ok"])
        self.assertEqual(lost["held_by"], "OPUS")
        self.assertGreaterEqual(calls["n"], 2)

    def test_holding_liveness_keeps_invalid_expired_and_released_non_live(self):
        future = cs._iso(self.t0 + dt.timedelta(seconds=60))
        valid = {"state": "HELD", "heartbeat_at": future, "ttl_s": 600}
        self.assertTrue(cs._holding_live(valid, self.t0))
        expired = {"state": "HELD", "heartbeat_at": cs._iso(self.t0 - dt.timedelta(seconds=601)),
                   "ttl_s": 600}
        self.assertFalse(cs._holding_live(expired, self.t0))
        self.assertFalse(cs._holding_live({"state": "HELD", "heartbeat_at": "bogus", "ttl_s": 600}, self.t0))
        self.assertFalse(cs._holding_live({"state": "HELD", "heartbeat_at": future, "ttl_s": True}, self.t0))
        self.assertFalse(cs._holding_live({"state": "HELD", "heartbeat_at": future, "ttl_s": 7201}, self.t0))
        self.assertFalse(cs._holding_live({"state": "RELEASED", "heartbeat_at": future, "ttl_s": 600}, self.t0))

    def test_runtime_nff_retry_refreshes_clock_after_reread(self):
        base = cs.holding_write(self.a, "seed-runtime", "OPUS", "take", now=self.t0)
        self.assertTrue(base["ok"])
        stale_tip = base["commit"]
        winner_time = self.t0 + dt.timedelta(seconds=10)
        won = cs.holding_write(self.a, "lane-runtime", "OPUS", "take",
                               ttl_s=1, now=winner_time)
        self.assertTrue(won["ok"])
        real_tip = cs._remote_tip
        real_now = cs._now
        tip_calls = {"n": 0}
        clock_values = [self.t0, self.t0 + dt.timedelta(seconds=20)]
        clock_calls = []

        def stale_then_real(git, branch, remote="origin"):
            tip_calls["n"] += 1
            return stale_tip if tip_calls["n"] == 1 else real_tip(git, branch, remote)

        def advancing_now():
            value = clock_values[len(clock_calls)]
            clock_calls.append(value)
            return value

        cs._remote_tip = stale_then_real
        cs._now = advancing_now
        try:
            result = cs.holding_write(self.b, "lane-runtime", "ASTRA", "take", ttl_s=600)
        finally:
            cs._remote_tip = real_tip
            cs._now = real_now
        self.assertTrue(result["ok"])
        self.assertEqual(result["record"]["previous_holder"], "OPUS")
        self.assertEqual(result["record"]["heartbeat_at"], cs._iso(clock_values[1]))
        self.assertEqual(clock_calls, clock_values)
        self.assertGreaterEqual(tip_calls["n"], 2)

    def test_same_holder_backward_actions_keep_record_and_commit_time_monotonic(self):
        future = self.t0 + dt.timedelta(seconds=60)
        for action in ("take", "renew", "release"):
            key = "lane-commit-" + action
            first = cs.holding_write(self.a, key, "OPUS", "take", ttl_s=600, now=future)
            self.assertTrue(first["ok"])
            written = cs.holding_write(self.a, key, "OPUS", action, ttl_s=1200, now=self.t0)
            self.assertTrue(written["ok"])
            self.assertEqual(written["record"]["heartbeat_at"], cs._iso(future))
            self.assertEqual(written["record"]["taken_at"], cs._iso(future))
            commit_time = dt.datetime.fromisoformat(
                sh(self.a.root, "show", "-s", "--format=%cI", written["commit"]).replace("Z", "+00:00"))
            self.assertEqual(commit_time, future)

    def test_released_same_holder_backward_reactivation_is_monotonic(self):
        future = self.t0 + dt.timedelta(seconds=60)
        for action in ("renew", "take"):
            key = "lane-released-" + action
            first = cs.holding_write(self.a, key, "OPUS", "take", ttl_s=600, now=future)
            self.assertTrue(first["ok"])
            released = cs.holding_write(self.a, key, "OPUS", "release", ttl_s=600, now=future)
            self.assertTrue(released["ok"])
            reopened = cs.holding_write(self.a, key, "OPUS", action, ttl_s=1200, now=self.t0)
            self.assertTrue(reopened["ok"])
            self.assertEqual(reopened["record"]["state"], "HELD")
            self.assertEqual(reopened["record"]["heartbeat_at"], cs._iso(future))
            self.assertEqual(reopened["record"]["taken_at"], cs._iso(future))
            commit_time = dt.datetime.fromisoformat(
                sh(self.a.root, "show", "-s", "--format=%cI", reopened["commit"]).replace("Z", "+00:00"))
            self.assertEqual(commit_time, future)


class FakeGitHub:
    """Canned replies keyed by what the producer asks for."""

    def __init__(self, repo_root, tip, heads):
        self.tip = tip
        self.heads = heads

    def __call__(self, method, url, body=None):
        if url.endswith("/graphql"):
            query = body["query"]
            if "pullRequests(states:OPEN" in query:
                nodes = []
                for n, head in self.heads.items():
                    nodes.append({
                        "number": n, "title": "change %d" % n, "url": "https://x/%d" % n,
                        "isDraft": True, "createdAt": "2026-09-11T10:%02d:00Z" % (n % 60),
                        "updatedAt": "2026-09-11T10:%02d:00Z" % (n % 60), "author": {"login": "seat"},
                        "headRefName": "b%d" % n, "headRefOid": head, "baseRefName": "main",
                        "baseRefOid": self.tip, "body": "",
                        "reviews": {"nodes": [{"databaseId": 5000000000 + n, "state": "COMMENTED",
                                               "submittedAt": "2026-09-11T10:30:00Z", "url": "r",
                                               "commit": {"oid": head},
                                               "body": "SOURCE / COMPOSITION-CUSTODY PASS; HOSTED GATE PENDING."}]},
                        "comments": {"nodes": []},
                        "commits": {"nodes": [{"commit": {"oid": head, "statusCheckRollup": {"contexts": {"nodes": [
                            {"__typename": "CheckRun", "name": "tests", "status": "QUEUED", "conclusion": None}]}}}}]},
                    })
                return {"data": {"repository": {"pullRequests": {
                    "totalCount": len(nodes), "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": nodes}}}}
            if "search(query" in query:
                return {"data": {"search": {"issueCount": 0, "pageInfo": {"hasNextPage": False}, "nodes": []}}}
            if "ref(qualifiedName" in query:
                return {"data": {"repository": {"b0": {"target": {
                    "oid": self.tip, "committedDate": "2026-09-11T10:00:00Z", "messageHeadline": "main"}}}}}
        if "/actions/runs" in url:
            if "status=queued" in url and "&page=" in url:
                return {"workflow_runs": [{"created_at": "2026-09-11T08:00:00Z"}]}
            if "status=queued" in url:
                return {"total_count": 7}
            return {"total_count": 2}
        raise AssertionError("unexpected request %s %s" % (method, url))


class BuildOffline(TempGit):
    def test_build_payload_and_head_tier(self):
        self.branch("p1", self.base)
        write(self.root, "a.txt", "reviewed change\n")
        h1 = commit_all(self.root, "carrier one")
        self.branch("main", self.base)
        write(self.root, "b.txt", "main moved\n")
        tip = commit_all(self.root, "main moves")
        self.branch("p2", tip)
        write(self.root, "a.txt", "reviewed change\n")
        h2 = commit_all(self.root, "carrier two")
        self.branch("main", tip)
        github = cs.GitHub("o/r", transport=FakeGitHub(self.root, tip, {101: h1, 102: h2}))
        now = dt.datetime(2026, 9, 11, 11, 0, tzinfo=dt.timezone.utc)
        payload = cs.build(self.git, github, now=now, producer="TEST")
        self.assertEqual(payload["counts"]["drift"]["disjoint"], 1)
        self.assertEqual(payload["counts"]["drift"]["current"], 1)
        self.assertEqual(payload["counts"]["hosted"], {"NOT_EXECUTED_QUEUED": 2})
        self.assertEqual(payload["counts"]["lanes_with_several_open"], 1)
        self.assertEqual(payload["queue"]["queued"], 7)
        self.assertEqual(payload["queue"]["oldest_queued_age_s"], 3 * 3600)
        row = [r for r in payload["prs"] if r["number"] == 102][0]
        self.assertEqual(row["verdicts"]["current_head"]["source"]["verdict"], "PASS")
        out = tempfile.mkdtemp(prefix="coordination-out-")
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        head = cs.write_outputs(payload, out)
        self.assertLessEqual(len(cs._compact(head).encode("utf-8")), cs.HEAD_LIMIT)
        with open(os.path.join(out, cs.STATE_FILE), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["schema"], cs.SCHEMA)

    def test_publish_without_push_builds_a_state_commit(self):
        remote = tempfile.mkdtemp(prefix="coordination-remote-")
        self.addCleanup(shutil.rmtree, remote, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "--bare", remote], check=True)
        sh(self.root, "remote", "add", "origin", remote)
        payload = {"schema": cs.SCHEMA, "observed_at": "2026-09-11T11:00:00Z", "main": {"sha": self.base},
                   "queue": {}, "counts": {"open_prs": 0}, "lanes": [], "degraded": []}
        result = cs.publish(self.git, payload, "o/r", push=False)
        self.assertFalse(result["pushed"])
        names = sh(self.root, "ls-tree", "--name-only", result["commit"]).split()
        self.assertEqual(sorted(names), sorted(["README.md", cs.HEAD_FILE, cs.STATE_FILE,
                                                cs.LANES_FILE, cs.PATHS_FILE]))
        self.assertIn(":refs/heads/%s" % cs.STATE_BRANCH, result["push_line"])

    def test_split_publish_is_a_chain_adding_one_file_per_commit(self):
        remote = tempfile.mkdtemp(prefix="coordination-remote-")
        self.addCleanup(shutil.rmtree, remote, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "--bare", remote], check=True)
        sh(self.root, "remote", "add", "origin", remote)
        payload = {"schema": cs.SCHEMA, "observed_at": "2026-09-11T11:00:00Z", "main": {"sha": self.base},
                   "queue": {}, "counts": {"open_prs": 0}, "lanes": [], "degraded": []}
        result = cs.publish(self.git, payload, "o/r", push=False, split=True)
        chain = result["chain"]
        self.assertEqual(len(chain), 5)
        sizes = [len(sh(self.root, "ls-tree", "--name-only", c).split()) for c in chain]
        self.assertEqual(sizes, [1, 2, 3, 4, 5])
        for older, newer in zip(chain, chain[1:]):
            self.assertEqual(sh(self.root, "rev-parse", newer + "^"), older)
        self.assertEqual(len(result["push_lines"]), 10)
        self.assertIn("push --no-thin", result["push_lines"][0])

    def test_rows_are_one_per_line_and_valid_json(self):
        doc = {"schema": "s", "prs": [{"number": 1}, {"number": 2}], "counts": {"a": 1}}
        text = cs._dump_rows(doc)
        self.assertEqual(json.loads(text), doc)
        self.assertIn('\n  {"number":1},\n  {"number":2}\n', text)


class BloblessPublishPush(unittest.TestCase):
    """Hosted coordination-state publish checks out blob:none, then pushes
    onto state/coordination. A thin pack asks for parent blobs the clone
    never fetched; GIT_NO_LAZY_FETCH blocks the promisor read and send-pack
    hangs up. --no-thin sends only the new objects."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="coordination-blobless-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.remote = os.path.join(self.tmp, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", self.remote], check=True)
        sh(self.remote, "config", "uploadpack.allowFilter", "true")
        sh(self.remote, "config", "uploadpack.allowAnySHA1InWant", "true")
        self.seed = os.path.join(self.tmp, "seed")
        os.makedirs(self.seed)
        sh(self.seed, "init", "-q", "-b", "main")
        sh(self.seed, "config", "core.autocrlf", "false")
        write(self.seed, "a.txt", "a\n")
        commit_all(self.seed, "base")
        sh(self.seed, "remote", "add", "origin", "file://" + self.remote)
        sh(self.seed, "push", "-q", "origin", "HEAD:refs/heads/main")

    def _payload(self, n):
        return {"schema": cs.SCHEMA, "observed_at": "2026-09-11T11:00:0%dZ" % n,
                "main": {"sha": "a" * 40}, "queue": {}, "counts": {"open_prs": n},
                "lanes": [], "degraded": []}

    def _blobless_clone(self):
        clone = os.path.join(self.tmp, "clone")
        os.makedirs(clone)
        sh(clone, "init", "-q", "-b", "main")
        sh(clone, "remote", "add", "origin", "file://" + self.remote)
        done = subprocess.run(
            ["git", "-C", clone, "fetch", "--filter=blob:none", "--depth=20",
             "origin", "+refs/heads/main:refs/remotes/origin/main"],
            capture_output=True, text=True)
        if done.returncode != 0:
            raise AssertionError("blob:none fetch failed: %s" % done.stderr)
        sh(clone, "checkout", "-q", "-B", "main", "origin/main")
        return clone

    def test_thin_push_from_blobless_clone_misses_parent_blobs(self):
        first = cs.publish(cs.Git(self.seed), self._payload(0), "o/r", push=True)
        self.assertTrue(first["pushed"])
        clone = self._blobless_clone()
        git = cs.Git(clone)
        git.fetch([first["commit"]])
        tree = git.out("ls-tree", "-r", first["commit"])
        missing = []
        for line in tree.splitlines():
            sha = line.split()[2]
            if git.run("cat-file", "-e", sha, check=False).returncode != 0:
                missing.append(sha)
        self.assertTrue(missing, "parent blobs should be absent in a blob:none clone")
        commit = cs.state_commit(git, {"README.md": "x\n"}, cs.STATE_BRANCH, "x",
                                 first["commit"])
        thin = git.run("push", "origin",
                       "%s:refs/heads/%s" % (commit, cs.STATE_BRANCH), check=False)
        self.assertNotEqual(thin.returncode, 0, thin.stderr)
        joined = (thin.stderr or "") + (thin.stdout or "")
        self.assertTrue(
            "promisor" in joined or "unpack" in joined or "hung up" in joined
            or "failed to push" in joined,
            joined)

    def test_publish_from_blobless_clone_pushes_without_parent_blobs(self):
        first = cs.publish(cs.Git(self.seed), self._payload(0), "o/r", push=True)
        self.assertTrue(first["pushed"])
        clone = self._blobless_clone()
        git = cs.Git(clone)
        result = cs.publish(git, self._payload(1), "o/r", push=True)
        self.assertTrue(result["pushed"], result.get("stderr"))
        self.assertEqual(result["parent"], first["commit"])
        self.assertEqual(cs._remote_tip(git, cs.STATE_BRANCH), result["commit"])

    def test_materialize_blobs_fills_parent_files_in_blobless_clone(self):
        first = cs.publish(cs.Git(self.seed), self._payload(0), "o/r", push=True)
        self.assertTrue(first["pushed"])
        clone = self._blobless_clone()
        git = cs.Git(clone)
        git.fetch([first["commit"]])
        head_blob = None
        for line in git.out("ls-tree", "-r", first["commit"]).splitlines():
            if line.endswith("\t" + cs.HEAD_FILE):
                head_blob = line.split()[2]
        self.assertTrue(head_blob)
        self.assertNotEqual(git.run("cat-file", "-e", head_blob, check=False).returncode, 0)
        cs._materialize_blobs(git, first["commit"])
        self.assertEqual(git.run("cat-file", "-e", head_blob, check=False).returncode, 0)

    def test_push_retries_promisor_hangup_then_lands(self):
        remote = tempfile.mkdtemp(prefix="coordination-retry-remote-")
        self.addCleanup(shutil.rmtree, remote, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "--bare", remote], check=True)
        seed = os.path.join(self.tmp, "retry-seed")
        os.makedirs(seed)
        sh(seed, "init", "-q", "-b", "main")
        write(seed, "a.txt", "a\n")
        commit_all(seed, "base")
        sh(seed, "remote", "add", "origin", remote)
        sleeps = []
        real_sleep = cs._PUSH_RETRY_SLEEP
        cs._PUSH_RETRY_SLEEP = sleeps.append
        real_run = cs.Git.run
        pushes = {"n": 0}

        def flaky(self, *args, **kw):
            if args and "push" in args:
                pushes["n"] += 1
                if pushes["n"] == 1:
                    return cs._Done(
                        1, "",
                        "not fetch e3ee4c7252d2f6f8c2c9d75ede5e0d2f1ba7187d "
                        "from promisor remote\n"
                        "fatal: the remote end hung up unexpectedly\n"
                        "send-pack: unexpected disconnect while reading sideband packet\n"
                        "error: failed to push some refs to "
                        "'https://github.com/woahwhattheheck/commons'")
            return real_run(self, *args, **kw)

        cs.Git.run = flaky
        try:
            result = cs.publish(cs.Git(seed), self._payload(0), "o/r", push=True)
        finally:
            cs.Git.run = real_run
            cs._PUSH_RETRY_SLEEP = real_sleep
        self.assertTrue(result["pushed"], result.get("stderr"))
        self.assertEqual(pushes["n"], 2)
        self.assertEqual(sleeps, [2])


if __name__ == "__main__":
    unittest.main()
