"""Focused capability initialization, verification, rotation and migration tests."""
from __future__ import annotations

import concurrent.futures
import sqlite3
import tempfile
import unittest
from pathlib import Path

from operator_auth import OperatorAuth, OperatorSetupRequired
from toolkit import Store


class OperatorAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "workspace.sqlite3"
        self.store = Store(self.path, lambda: 1000)

    def test_uninitialized_workspace_refuses_operator_auth_without_data_loss(self):
        with self.assertRaises(OperatorSetupRequired):
            OperatorAuth(self.path)
        self.assertEqual(self.store.dashboard()["counts"], {"members": 0, "requests": 0})
        with sqlite3.connect(self.path) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("creator_security", tables)
        self.assertIn("resources", tables)

    def test_initialize_stores_only_digest_and_verifies_exact_key(self):
        key = OperatorAuth.initialize(self.path)
        auth = OperatorAuth(self.path)
        self.assertTrue(auth.verify(key))
        for candidate in (None, "", "wrong", "x" * 257, "\ud800"):
            with self.subTest(candidate=repr(candidate)):
                self.assertFalse(auth.verify(candidate))
        with sqlite3.connect(self.path) as db:
            digest = db.execute("SELECT value FROM creator_security WHERE name='operator_sha256'").fetchone()[0]
            dump = "\n".join(db.iterdump())
        self.assertEqual(len(digest), 64)
        self.assertNotEqual(digest, key)
        self.assertNotIn(key, dump)
        self.assertTrue(auth.verify_header("Bearer " + key))
        self.assertFalse(auth.verify_header(key))
        self.assertFalse(auth.verify_header("Basic " + key))

    def test_second_initialization_refuses_to_replace_live_key(self):
        key = OperatorAuth.initialize(self.path)
        with self.assertRaises(RuntimeError):
            OperatorAuth.initialize(self.path)
        self.assertTrue(OperatorAuth(self.path).verify(key))

    def test_rotation_invalidates_old_key_and_survives_reopen(self):
        old = OperatorAuth.initialize(self.path)
        auth = OperatorAuth(self.path)
        new = auth.rotate()
        self.assertNotEqual(old, new)
        self.assertFalse(auth.verify(old))
        self.assertTrue(auth.verify(new))
        reopened = OperatorAuth(self.path)
        self.assertTrue(reopened.verify(new))
        self.assertFalse(reopened.verify(old))

    def test_parallel_initializers_produce_exactly_one_live_key(self):
        fresh = Path(self.temp.name) / "parallel.sqlite3"
        Store(fresh, lambda: 1000)
        def attempt(_):
            try:
                return ("ok", OperatorAuth.initialize(fresh))
            except RuntimeError:
                return ("exists", None)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        winners = [key for state, key in results if state == "ok"]
        self.assertEqual(len(winners), 1)
        self.assertEqual(sum(state == "exists" for state, _ in results), 7)
        self.assertTrue(OperatorAuth(fresh).verify(winners[0]))
        with sqlite3.connect(fresh) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM creator_security WHERE name='operator_sha256'").fetchone()[0], 1)

    def test_initialization_does_not_change_existing_workspace_records(self):
        resource = self.store.mutate("resource.create", "r1", {
            "title": "Existing resource", "kind": "link", "target": "https://example.invalid/resource"
        })
        delivery = self.store.mutate("request", "q1", {
            "resource_id": resource["id"], "email": "existing@example.invalid", "opt_in": False
        })
        before = self.store.member(delivery["member_id"])
        key = OperatorAuth.initialize(self.path)
        self.assertTrue(OperatorAuth(self.path).verify(key))
        reopened = Store(self.path, lambda: 1000)
        self.assertEqual(reopened.member(delivery["member_id"]), before)
        self.assertEqual(reopened.delivery(delivery["request_id"])["target"], "https://example.invalid/resource")


if __name__ == "__main__":
    unittest.main(verbosity=2)
