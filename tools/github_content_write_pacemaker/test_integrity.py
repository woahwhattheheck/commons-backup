from __future__ import annotations
import datetime as dt
import json
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from tools.github_content_write_pacemaker import store_base as store_base_module
from tools.github_content_write_pacemaker.github_write_pacemaker import (
    PacemakerError, PacemakerStore, StoreInvariantError,
    canonical_json, normalize_intent,
)

UTC = dt.timezone.utc


class Clock:
    def __init__(self):
        self.value = dt.datetime(2026, 9, 14, 7, 0, tzinfo=UTC)
    def __call__(self):
        return self.value


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "state.db"
        self.store = PacemakerStore(self.db, clock=Clock())

    def intent(self, key="one", body=None):
        return {"schema": "commons-github-content-write-intent/v2",
                "mutationKey": key, "method": "POST",
                "apiPath": "/provider/path", "description": "test mutation",
                "body": {"value": 1} if body is None else body}

    def _victim(self, root: Path) -> Path:
        path = root / "victim.db"
        db = sqlite3.connect(path)
        try:
            db.execute("CREATE TABLE sentinel(value TEXT NOT NULL)")
            db.execute("INSERT INTO sentinel(value) VALUES('keep')")
            db.commit()
        finally:
            db.close()
        os.chmod(path, 0o644)
        return path

    def _victim_snapshot(self, path: Path):
        return path.read_bytes(), stat.S_IMODE(os.stat(path).st_mode)

    def _assert_victim_unchanged(self, path: Path, snapshot) -> None:
        self.assertEqual(self._victim_snapshot(path), snapshot)
        db = sqlite3.connect(path)
        try:
            self.assertEqual(
                db.execute("SELECT value FROM sentinel").fetchone()[0], "keep"
            )
            self.assertIsNone(
                db.execute(
                    "SELECT name FROM sqlite_master WHERE name='meta'"
                ).fetchone()
            )
        finally:
            db.close()

    def test_json_and_receipt_privacy(self):
        integer = normalize_intent(self.intent(body={"value": 1}))
        boolean = normalize_intent(self.intent("bool", body={"value": True}))
        self.assertNotEqual(integer.semantic_sha256, boolean.semantic_sha256)
        with self.assertRaises(PacemakerError):
            canonical_json({"value": float("nan")})
        receipt, _ = self.store.enqueue(
            self.intent("privacy-case", body={"private": "secret-value"}))
        rendered = json.dumps(receipt, sort_keys=True)
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("test mutation", rendered)

    def test_verify_and_tamper(self):
        self.store.enqueue(self.intent())
        report = self.store.verify()
        self.assertEqual(report["integrity"], "VALID")
        self.assertFalse(report["authority"]["directNetworkClientPresent"])
        self.assertEqual(os.stat(self.db).st_mode & 0o777, 0o600)
        db = sqlite3.connect(self.db)
        db.execute("UPDATE mutations SET body_json=?", (b'{"value":2}',))
        db.commit()
        db.close()
        with self.assertRaises(StoreInvariantError):
            self.store.verify()

    @unittest.skipIf(os.name == "nt", "POSIX symlink custody hostile")
    def test_foreign_symlink_is_rejected_without_mutating_victim(self):
        root = Path(self.tmp.name) / "symlink"
        root.mkdir(mode=0o700)
        victim = self._victim(root)
        snapshot = self._victim_snapshot(victim)
        requested = root / "state.db"
        requested.symlink_to(victim)
        with self.assertRaises(PacemakerError):
            PacemakerStore(requested, clock=Clock())
        self._assert_victim_unchanged(victim, snapshot)

    @unittest.skipIf(os.name == "nt", "POSIX hardlink custody hostile")
    def test_foreign_hardlink_is_rejected_without_mutating_victim(self):
        root = Path(self.tmp.name) / "hardlink"
        root.mkdir(mode=0o700)
        victim = self._victim(root)
        requested = root / "state.db"
        os.link(victim, requested)
        snapshot = self._victim_snapshot(victim)
        with self.assertRaises(PacemakerError):
            PacemakerStore(requested, clock=Clock())
        self._assert_victim_unchanged(victim, snapshot)

    @unittest.skipIf(os.name == "nt", "POSIX parent custody hostile")
    def test_final_parent_symlink_is_rejected(self):
        real_parent = Path(self.tmp.name) / "real-parent"
        real_parent.mkdir(mode=0o700)
        alias = Path(self.tmp.name) / "alias-parent"
        alias.symlink_to(real_parent, target_is_directory=True)
        with self.assertRaises(PacemakerError):
            PacemakerStore(alias / "state.db", clock=Clock())
        self.assertFalse((real_parent / "state.db").exists())

    @unittest.skipIf(os.name == "nt", "POSIX parent permissions hostile")
    def test_group_writable_parent_is_rejected(self):
        parent = Path(self.tmp.name) / "unsafe-parent"
        parent.mkdir(mode=0o700)
        os.chmod(parent, 0o770)
        with self.assertRaises(PacemakerError):
            PacemakerStore(parent / "state.db", clock=Clock())
        self.assertFalse((parent / "state.db").exists())

    @unittest.skipIf(os.name == "nt", "POSIX pathname rebind hostile")
    def test_path_rebind_during_sqlite_open_preserves_foreign_victim(self):
        root = Path(self.tmp.name) / "rebind"
        root.mkdir(mode=0o700)
        requested = root / "state.db"
        initial = PacemakerStore(requested, clock=Clock())
        initial.close()
        victim = self._victim(root)
        snapshot = self._victim_snapshot(victim)
        moved = root / "state-old.db"
        real_assert = store_base_module.StoreBase._assert_db_identity
        calls = 0

        def racing_assert(store):
            nonlocal calls
            calls += 1
            if calls == 1:
                real_assert(store)
                os.replace(requested, moved)
                requested.symlink_to(victim)
                return
            return real_assert(store)

        with mock.patch.object(
            store_base_module.StoreBase,
            "_assert_db_identity",
            new=racing_assert,
        ):
            with self.assertRaises(StoreInvariantError):
                PacemakerStore(requested, clock=Clock())
        self._assert_victim_unchanged(victim, snapshot)

    @unittest.skipIf(os.name == "nt", "POSIX swap-open-restore hostile")
    def test_swap_open_restore_cannot_redirect_sqlite_generation(self):
        root = Path(self.tmp.name) / "swap-open-restore"
        root.mkdir(mode=0o700)
        requested = root / "state.db"
        initial = PacemakerStore(requested, clock=Clock())
        initial.close()
        victim = self._victim(root)
        snapshot = self._victim_snapshot(victim)
        moved = root / "state-old.db"
        real_assert = store_base_module.StoreBase._assert_db_identity
        calls = 0

        def racing_assert(store):
            nonlocal calls
            calls += 1
            if calls == 1:
                real_assert(store)
                os.replace(requested, moved)
                requested.symlink_to(victim)
                return
            if calls == 2:
                requested.unlink()
                os.replace(moved, requested)
            return real_assert(store)

        with mock.patch.object(
            store_base_module.StoreBase,
            "_assert_db_identity",
            new=racing_assert,
        ):
            repaired = PacemakerStore(requested, clock=Clock())
            self.assertEqual(repaired.verify()["integrity"], "VALID")
            repaired.close()

        self.assertGreaterEqual(calls, 2)
        self._assert_victim_unchanged(victim, snapshot)

    @unittest.skipIf(os.name == "nt", "POSIX post-import connector hostile")
    def test_post_import_connect_substitution_cannot_redirect_sqlite_generation(self):
        root = Path(self.tmp.name) / "connect-substitution"
        root.mkdir(mode=0o700)
        requested = root / "state.db"
        initial = PacemakerStore(requested, clock=Clock())
        initial.close()
        victim = self._victim(root)
        snapshot = self._victim_snapshot(victim)
        real_connect = sqlite3.connect

        def foreign_connect(*args, **kwargs):
            return real_connect(victim)

        with mock.patch.object(
            store_base_module.sqlite3, "connect", side_effect=foreign_connect
        ), mock.patch.object(
            store_base_module,
            "_SQLITE_CONNECT",
            side_effect=foreign_connect,
            create=True,
        ):
            repaired = PacemakerStore(requested, clock=Clock())
            self.assertEqual(repaired.verify()["integrity"], "VALID")
            repaired.close()

        self._assert_victim_unchanged(victim, snapshot)


if __name__ == "__main__":
    unittest.main()
