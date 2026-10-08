#!/usr/bin/env python3
"""Focused regression for exhausted GitHub primary quota admission."""
import sqlite3
import unittest

from admission import SCHEMA, acquire, observe, status


class PrimaryQuotaRecovery(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.executescript(SCHEMA)
        self.now = 1_791_430_000

    def tearDown(self):
        self.db.close()

    def observe_primary(self, event, **kwargs):
        return observe(self.db, "woahwhattheheck", "rest", "pulls", event,
                       self.now, 403, "API rate limit exceeded for user ID",
                       **kwargs)

    def admit(self, operation, when):
        return acquire(self.db, "woahwhattheheck", "rest", "pulls",
                       operation, when)

    def test_no_reset_never_reopens_on_estimated_backoff(self):
        result = self.observe_primary("missing")
        self.assertEqual(result["classification"], "PRIMARY_LIMIT")
        self.assertIsNone(result["until_epoch"])
        self.assertEqual(self.admit("a", self.now + 86_400)["reason"], "gate_blocked")
        self.assertIsNone(status(self.db, now=self.now + 86_400)["active_gates"][0]["until_epoch"])

    def test_stale_reset_and_retry_after_still_need_verified_recovery(self):
        result = self.observe_primary("stale", reset_epoch=self.now - 1, retry_after=900)
        self.assertIsNone(result["until_epoch"])
        self.assertFalse(self.admit("b", self.now + 1_000_000)["admitted"])

    def test_known_future_reset_allows_fresh_operation_after_deadline(self):
        result = self.observe_primary("future", reset_epoch=self.now + 720, retry_after=900)
        self.assertEqual(result["until_epoch"], self.now + 900)
        self.assertFalse(self.admit("c", self.now + 899)["admitted"])
        self.assertTrue(self.admit("d", self.now + 900)["admitted"])

    def test_later_observation_cannot_shorten_indefinite_gate(self):
        self.observe_primary("unknown")
        result = self.observe_primary("later", reset_epoch=self.now + 720)
        self.assertIsNone(result["until_epoch"])
        result = observe(self.db, "woahwhattheheck", "rest", "pulls", "secondary",
                         self.now + 10, 429, "secondary rate limit")
        self.assertIsNone(result["until_epoch"])
        self.assertEqual(status(self.db, now=self.now + 86_400)["active_gates"][0]["kind"], "PRIMARY_LIMIT")
        self.assertFalse(self.admit("e", self.now + 86_400)["admitted"])

    def test_secondary_limit_remains_timed(self):
        result = observe(self.db, "woahwhattheheck", "rest", "pulls", "secondary",
                         self.now, 429, "secondary rate limit")
        self.assertEqual(result["until_epoch"], self.now + 300)
        self.assertFalse(self.admit("f", self.now + 299)["admitted"])
        self.assertTrue(self.admit("g", self.now + 300)["admitted"])


if __name__ == "__main__":
    unittest.main()
