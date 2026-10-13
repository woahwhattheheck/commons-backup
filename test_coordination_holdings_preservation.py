#!/usr/bin/env python3
"""Holdings writer contract: untouched holdings keep their exact bytes across every take, renew and release.

Offline throughout. The bare remote honours partial-clone filters, so writer B works
from a blobless clone exactly like a hosted or cloud seat: it can see every holding's
blob id but holds no blob content until it fetches one on purpose.
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

from host import claim_pr  # noqa: E402
from host import coordination_state as cs  # noqa: E402


def sh(root, *args):
    done = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True)
    if done.returncode != 0:
        raise AssertionError("git %s failed: %s" % (args, done.stderr))
    return done.stdout.strip()


class BloblessWriters(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="holdings-preserve-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.remote = os.path.join(self.tmp, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", self.remote], check=True)
        # The remote honours blob filters and serves single blobs on demand, as GitHub does.
        sh(self.remote, "config", "uploadpack.allowFilter", "true")
        sh(self.remote, "config", "uploadpack.allowAnySHA1InWant", "true")
        self.a = self.clone("a")
        self.b = self.clone("b")
        self.t0 = dt.datetime(2026, 9, 16, 22, 0, tzinfo=dt.timezone.utc)

    def clone(self, name):
        root = os.path.join(self.tmp, name)
        subprocess.run(["git", "init", "-q", root], check=True)
        sh(root, "remote", "add", "origin", self.remote)
        return cs.Git(root)

    def tip(self):
        return sh(self.remote, "rev-parse", "refs/heads/" + cs.HOLDINGS_BRANCH)

    def blob_at(self, commit, key):
        line = sh(self.remote, "ls-tree", commit, "holdings/%s.json" % key)
        self.assertTrue(line, "holdings/%s.json missing at %s" % (key, commit))
        return line.split()[2]

    def bytes_at(self, commit, key):
        done = subprocess.run(["git", "-C", self.remote, "cat-file", "-p", "%s:holdings/%s.json" % (commit, key)],
                              capture_output=True)
        self.assertEqual(0, done.returncode)
        return done.stdout

    def has_blob(self, git, blob):
        return git.run("cat-file", "-e", blob, check=False).returncode == 0

    def seconds(self, n):
        return self.t0 + dt.timedelta(seconds=n)

    def test_writer_without_the_blob_carries_the_other_holding_byte_for_byte(self):
        first = cs.holding_write(self.a, "work-alpha", "SEAT-A", "take", ttl_s=1800, now=self.t0,
                                 note="alpha lane")
        self.assertTrue(first["ok"])
        alpha_commit = self.tip()
        alpha_blob = self.blob_at(alpha_commit, "work-alpha")
        alpha_bytes = self.bytes_at(alpha_commit, "work-alpha")

        second = cs.holding_write(self.b, "pr-15162", "SEAT-B", "take", ttl_s=1800, now=self.seconds(1))
        self.assertTrue(second["ok"], second)
        # B never needed alpha's content: the blob is still absent from its object store.
        self.assertFalse(self.has_blob(self.b, alpha_blob))
        after = self.tip()
        self.assertNotEqual(alpha_commit, after)
        self.assertEqual(alpha_blob, self.blob_at(after, "work-alpha"))
        self.assertEqual(alpha_bytes, self.bytes_at(after, "work-alpha"))
        self.assertEqual(json.loads(alpha_bytes)["holder"], "SEAT-A")

        renewed = cs.holding_write(self.b, "pr-15162", "SEAT-B", "renew", ttl_s=1800, now=self.seconds(2))
        released = cs.holding_write(self.b, "pr-15162", "SEAT-B", "release", now=self.seconds(3))
        self.assertTrue(renewed["ok"] and released["ok"])
        final = self.tip()
        self.assertEqual(alpha_blob, self.blob_at(final, "work-alpha"))
        self.assertEqual(alpha_bytes, self.bytes_at(final, "work-alpha"))
        self.assertEqual("RELEASED", json.loads(self.bytes_at(final, "pr-15162"))["state"])
        self.assertFalse(self.has_blob(self.b, alpha_blob))

    def test_pr_claim_from_a_blobless_clone_carries_work_holdings_byte_for_byte(self):
        held = cs.holding_write(self.a, "work-beta", "SEAT-A", "take", ttl_s=1800, now=self.t0)
        self.assertTrue(held["ok"])
        beta_commit = self.tip()
        beta_blob = self.blob_at(beta_commit, "work-beta")
        beta_bytes = self.bytes_at(beta_commit, "work-beta")
        result = claim_pr.write_pr_holding(self.b, 15165, "GOAT", "take", now=self.seconds(1))
        self.assertTrue(result["ok"], result)
        self.assertFalse(self.has_blob(self.b, beta_blob))
        after = self.tip()
        self.assertEqual(beta_blob, self.blob_at(after, "work-beta"))
        self.assertEqual(beta_bytes, self.bytes_at(after, "work-beta"))
        self.assertEqual("HELD", json.loads(self.bytes_at(after, "pr-15165"))["state"])

    def test_target_held_elsewhere_is_fetched_on_demand_and_refused_to_a_second_holder(self):
        first = cs.holding_write(self.a, "work-gamma", "SEAT-A", "take", ttl_s=1800, now=self.t0)
        self.assertTrue(first["ok"])
        gamma_blob = self.blob_at(self.tip(), "work-gamma")
        self.assertFalse(self.has_blob(self.b, gamma_blob))
        refused = cs.holding_write(self.b, "work-gamma", "SEAT-B", "take", ttl_s=1800, now=self.seconds(5))
        self.assertFalse(refused["ok"])
        self.assertEqual("SEAT-A", refused["held_by"])
        self.assertTrue(self.has_blob(self.b, gamma_blob))
        second_pr = claim_pr.write_pr_holding(self.b, 777, "GOAT", "take", now=self.seconds(6))
        self.assertTrue(second_pr["ok"])
        again = claim_pr.write_pr_holding(self.a, 777, "SEAT-A", "take", now=self.seconds(7))
        self.assertFalse(again["ok"])
        self.assertEqual("GOAT", again["held_by"])

    def test_unreadable_target_refuses_the_write_and_leaves_the_branch_untouched(self):
        first = cs.holding_write(self.a, "work-delta", "SEAT-A", "take", ttl_s=1800, now=self.t0)
        self.assertTrue(first["ok"])
        before = self.tip()
        real = cs._read_holding

        def unreadable(git, commit, path, blob):
            if path.endswith("work-delta.json"):
                raise cs.HoldingUnreadable("simulated: %s" % path)
            return real(git, commit, path, blob)

        cs._read_holding = unreadable
        try:
            refused = cs.holding_write(self.b, "work-delta", "SEAT-B", "take", ttl_s=1800, now=self.seconds(1))
            self.assertFalse(refused["ok"])
            self.assertIn("could not be read", refused["reason"])
            self.assertEqual(before, self.tip())
            other = cs.holding_write(self.b, "work-epsilon", "SEAT-B", "take", ttl_s=1800, now=self.seconds(2))
            self.assertTrue(other["ok"], other)
            listing = cs.holdings_list(self.b, now=self.seconds(3))
            rows = {row["key"]: row for row in listing["holdings"]}
            self.assertTrue(rows["work-delta"]["unreadable"])
            self.assertFalse(rows["work-delta"]["live"])
            self.assertNotIn("unreadable", rows["work-epsilon"])
            self.assertEqual(self.blob_at(before, "work-delta"), self.blob_at(self.tip(), "work-delta"))
            pr_result = claim_pr.write_pr_holding(self.b, 15170, "GOAT", "take", now=self.seconds(4))
            self.assertTrue(pr_result["ok"])
            self.assertEqual(self.blob_at(before, "work-delta"), self.blob_at(self.tip(), "work-delta"))
        finally:
            cs._read_holding = real
        self.assertEqual(self.blob_at(before, "work-delta"), self.blob_at(self.tip(), "work-delta"))

    def test_concurrent_distinct_keys_both_land_after_a_non_fast_forward_retry(self):
        seed = cs.holding_write(self.a, "seed", "SEAT-A", "take", now=self.t0)
        self.assertTrue(seed["ok"])
        stale_tip = seed["commit"]
        won = cs.holding_write(self.a, "work-zeta", "SEAT-A", "take", ttl_s=1800, now=self.seconds(1))
        self.assertTrue(won["ok"])
        zeta_blob = self.blob_at(self.tip(), "work-zeta")
        zeta_bytes = self.bytes_at(self.tip(), "work-zeta")
        real = cs._remote_tip
        calls = {"n": 0}

        def stale_then_real(git, branch, remote="origin"):
            calls["n"] += 1
            return stale_tip if calls["n"] == 1 else real(git, branch, remote)

        cs._remote_tip = stale_then_real
        try:
            other = cs.holding_write(self.b, "work-eta", "SEAT-B", "take", ttl_s=1800, now=self.seconds(2))
        finally:
            cs._remote_tip = real
        self.assertTrue(other["ok"], other)
        self.assertGreaterEqual(calls["n"], 2)
        final = self.tip()
        self.assertEqual(zeta_blob, self.blob_at(final, "work-zeta"))
        self.assertEqual(zeta_bytes, self.bytes_at(final, "work-zeta"))
        self.assertEqual("HELD", json.loads(self.bytes_at(final, "work-eta"))["state"])
        self.assertEqual("HELD", json.loads(self.bytes_at(final, "seed"))["state"])

    def test_exhausted_retries_return_a_deterministic_conflict_receipt(self):
        seed = cs.holding_write(self.a, "seed", "SEAT-A", "take", now=self.t0)
        self.assertTrue(seed["ok"])
        stale_tip = seed["commit"]
        cs.holding_write(self.a, "mover", "SEAT-A", "take", now=self.seconds(1))
        real = cs._remote_tip
        cs._remote_tip = lambda git, branch, remote="origin": stale_tip
        try:
            lost = cs.holding_write(self.b, "work-theta", "SEAT-B", "take", now=self.seconds(2), attempts=2)
        finally:
            cs._remote_tip = real
        self.assertFalse(lost["ok"])
        self.assertEqual("non-fast-forward", lost["conflict"])
        self.assertEqual(2, lost["attempts"])
        self.assertEqual(stale_tip, lost["tip"])

    def test_legacy_placeholder_record_is_vacant_and_no_holder_is_invented(self):
        seed = cs.holding_write(self.a, "seed", "SEAT-A", "take", now=self.t0)
        self.assertTrue(seed["ok"])
        tip = self.tip()
        holdings = cs._read_holdings(self.a, tip)
        holdings["holdings/work-legacy.json"] = {"unreadable": True}
        commit = cs._holdings_commit(self.a, tip, holdings, "legacy placeholder", self.t0)
        pushed = cs._push_ref(self.a, "origin", commit, cs.HOLDINGS_BRANCH)
        self.assertEqual(0, pushed.returncode, pushed.stderr)
        listing = cs.holdings_list(self.b, now=self.seconds(1))
        row = {r["key"]: r for r in listing["holdings"]}["work-legacy"]
        self.assertFalse(row["live"])
        self.assertIsNone(row["holder"])
        taken = cs.holding_write(self.b, "work-legacy", "SEAT-B", "take", ttl_s=1800, now=self.seconds(2))
        self.assertTrue(taken["ok"], taken)
        record = json.loads(self.bytes_at(self.tip(), "work-legacy"))
        self.assertEqual("SEAT-B", record["holder"])
        self.assertNotIn("previous_holder", record)
        self.assertNotIn("unreadable", record)
        self.assertEqual(cs.HOLDING_SCHEMA, record["schema"])
        self.assertEqual(self.blob_at(tip, "seed"), self.blob_at(self.tip(), "seed"))


if __name__ == "__main__":
    unittest.main()
