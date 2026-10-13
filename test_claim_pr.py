#!/usr/bin/env python3
"""Offline contract tests for host/claim_pr.py."""

import datetime as dt
import os
import shutil
import subprocess
import tempfile
import unittest

from host import claim_pr
from host import coordination_state as cs


class CanonicalPrClaimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="claim-pr-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.remote = os.path.join(self.tmp, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", self.remote], check=True)
        self.a = self._client("a")
        self.b = self._client("b")
        self.t0 = dt.datetime(2026, 9, 12, 23, 30, tzinfo=dt.timezone.utc)

    def _client(self, name):
        root = os.path.join(self.tmp, name)
        subprocess.run(["git", "init", "-q", root], check=True)
        subprocess.run(["git", "-C", root, "remote", "add", "origin", self.remote], check=True)
        return cs.Git(root)

    def test_pr_key_is_canonical_and_rejects_alias_inputs(self):
        self.assertEqual("pr-13492", claim_pr.pr_key(13492))
        for value in (0, -1, True, "13492"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                claim_pr.pr_key(value)

    def test_same_pr_two_seats_has_one_live_holder(self):
        first = claim_pr.write_pr_holding(
            self.a, 13492, "ASTRA-A", "take", ttl_s=600, now=self.t0
        )
        self.assertTrue(first["ok"])
        self.assertEqual("pr-13492", first["key"])

        second = claim_pr.write_pr_holding(
            self.b, 13492, "ASTRA-B", "take", ttl_s=600,
            now=self.t0 + dt.timedelta(seconds=30),
        )
        self.assertFalse(second["ok"])
        self.assertEqual("pr-13492", second["key"])
        self.assertEqual("ASTRA-A", second["held_by"])

    def test_different_prs_do_not_collide(self):
        one = claim_pr.write_pr_holding(
            self.a, 13492, "ASTRA-A", "take", ttl_s=600, now=self.t0
        )
        two = claim_pr.write_pr_holding(
            self.b, 13493, "ASTRA-B", "take", ttl_s=600,
            now=self.t0 + dt.timedelta(seconds=1),
        )
        self.assertTrue(one["ok"])
        self.assertTrue(two["ok"])
        self.assertEqual(("pr-13492", "pr-13493"), (one["key"], two["key"]))

    def test_release_allows_successor_to_take_same_pr(self):
        first = claim_pr.write_pr_holding(
            self.a, 13492, "ASTRA-A", "take", ttl_s=600, now=self.t0
        )
        self.assertTrue(first["ok"])
        released = claim_pr.write_pr_holding(
            self.a, 13492, "ASTRA-A", "release", ttl_s=600,
            now=self.t0 + dt.timedelta(seconds=10),
        )
        self.assertTrue(released["ok"])
        successor = claim_pr.write_pr_holding(
            self.b, 13492, "ASTRA-B", "take", ttl_s=600,
            now=self.t0 + dt.timedelta(seconds=20),
        )
        self.assertTrue(successor["ok"])
        self.assertEqual("ASTRA-A", successor["record"]["previous_holder"])

    def test_invalid_action_holder_ttl_and_attempts_fail_before_git_write(self):
        bad = [
            {"action": "steal", "holder": "ASTRA", "ttl_s": 600},
            {"action": "take", "holder": "", "ttl_s": 600},
            {"action": "take", "holder": "ASTRA", "ttl_s": 0},
            {"action": "take", "holder": "ASTRA", "ttl_s": 7201},
            {"action": "take", "holder": "ASTRA", "ttl_s": True},
            {"action": "take", "holder": "ASTRA", "ttl_s": 600, "attempts": 0},
            {"action": "take", "holder": "ASTRA", "ttl_s": 600, "attempts": True},
            {"action": "take", "holder": "ASTRA", "ttl_s": 600, "attempts": 11},
        ]
        for kwargs in bad:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                claim_pr.write_pr_holding(self.a, 13492, now=self.t0, **kwargs)

    def test_runtime_retry_refreshes_clock_before_reread(self):
        seed = cs.holding_write(self.a, "seed", "SEED", "take", now=self.t0)
        self.assertTrue(seed["ok"])
        stale_tip = seed["commit"]
        winner_time = self.t0 + dt.timedelta(seconds=1)
        winner = cs.holding_write(
            self.a, "pr-13492", "ASTRA-A", "take", ttl_s=600, now=winner_time
        )
        self.assertTrue(winner["ok"])

        real_tip = cs._remote_tip
        real_now = cs._now
        tip_calls = {"n": 0}
        clock = iter((self.t0, self.t0 + dt.timedelta(seconds=2)))

        def stale_then_real(git, branch, remote="origin"):
            tip_calls["n"] += 1
            if tip_calls["n"] == 1:
                return stale_tip
            return real_tip(git, branch, remote)

        cs._remote_tip = stale_then_real
        cs._now = lambda: next(clock)
        try:
            lost = claim_pr.write_pr_holding(
                self.b, 13492, "ASTRA-B", "take", ttl_s=600
            )
        finally:
            cs._remote_tip = real_tip
            cs._now = real_now

        self.assertFalse(lost["ok"])
        self.assertEqual("ASTRA-A", lost["held_by"])
        self.assertGreaterEqual(tip_calls["n"], 2)

    def test_future_winner_heartbeat_is_live_not_expired(self):
        winner = claim_pr.write_pr_holding(
            self.a,
            13492,
            "WINNER",
            "take",
            ttl_s=600,
            now=self.t0 + dt.timedelta(seconds=10),
        )
        self.assertTrue(winner["ok"])

        loser = claim_pr.write_pr_holding(
            self.b, 13492, "LOSER", "take", ttl_s=600, now=self.t0
        )
        self.assertFalse(loser["ok"])
        self.assertEqual("WINNER", loser["held_by"])

    def test_same_holder_clock_skew_does_not_move_heartbeat_backwards(self):
        first = claim_pr.write_pr_holding(
            self.a,
            13492,
            "ASTRA-A",
            "take",
            ttl_s=600,
            now=self.t0 + dt.timedelta(seconds=10),
        )
        self.assertTrue(first["ok"])
        renewed = claim_pr.write_pr_holding(
            self.a, 13492, "ASTRA-A", "renew", ttl_s=1200, now=self.t0
        )
        self.assertTrue(renewed["ok"])
        self.assertEqual(
            "2026-09-12T23:30:10Z", renewed["record"]["heartbeat_at"]
        )
        self.assertEqual(1200, renewed["record"]["ttl_s"])

    def test_explicit_time_never_reads_runtime_clock(self):
        winner = claim_pr.write_pr_holding(
            self.a,
            13492,
            "WINNER",
            "take",
            ttl_s=600,
            now=self.t0 + dt.timedelta(seconds=10),
        )
        self.assertTrue(winner["ok"])

        real_now = cs._now
        cs._now = lambda: (_ for _ in ()).throw(AssertionError("runtime clock used"))
        try:
            result = claim_pr.write_pr_holding(
                self.b, 13492, "LOSER", "take", ttl_s=600, now=self.t0
            )
        finally:
            cs._now = real_now

        self.assertFalse(result["ok"])
        self.assertEqual("WINNER", result["held_by"])


if __name__ == "__main__":
    unittest.main()
