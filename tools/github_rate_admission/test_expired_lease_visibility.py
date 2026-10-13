#!/usr/bin/env python3
"""Focused regression for idle visibility of expired, unresolved writes."""
import sqlite3
import unittest

from admission import SCHEMA, acquire, settle, status


class ExpiredLeaseVisibility(unittest.TestCase):
    def test_status_shows_expired_as_unknown_without_replaying_or_mutating(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        try:
            db.executescript(SCHEMA)
            now = 1_791_430_000
            self.assertTrue(acquire(db, "woahwhattheheck", "rest", "pulls:create",
                                    "delivery-1", now, lease_seconds=10)["admitted"])
            live = status(db, "woahwhattheheck", "rest", now=now + 9)
            self.assertEqual(live["open_leases"][0]["state"], "reserved")

            expired = status(db, "woahwhattheheck", "rest", now=now + 10)
            self.assertEqual(expired["open_count"], 1)
            self.assertEqual(expired["open_leases"][0]["operation_id"], "delivery-1")
            self.assertEqual(expired["open_leases"][0]["state"], "unknown")
            self.assertEqual(expired["open_leases"][0]["outcome"], "unknown")
            self.assertEqual(db.execute(
                "SELECT state,outcome FROM leases WHERE operation_id='delivery-1'"
            ).fetchone(), ("reserved", None))

            denied = acquire(db, "woahwhattheheck", "rest", "pulls:create",
                             "delivery-2", now + 11)
            self.assertFalse(denied["admitted"])
            self.assertEqual(denied["reason"], "unreconciled_effect")
            self.assertTrue(settle(db, "delivery-1", "no-effect")["updated"])
            self.assertEqual(status(db, now=now + 12)["open_count"], 0)
            self.assertTrue(acquire(db, "woahwhattheheck", "rest", "pulls:create",
                                    "delivery-3", now + 12)["admitted"])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
