# SPDX-License-Identifier: Apache-2.0
"""Recovery tests against the unchanged real Migration Desk core (synthetic data)."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

import workspace_backup as recovery
from intake import MigrationError, digest
from migrate import (apply_plan, connect, edit_record, export_workspace, make_plan,
                     read_state, rollback)

HERE = Path(__file__).resolve().parent
ERRORS = (MigrationError, OSError, ValueError, sqlite3.Error, zipfile.BadZipFile)


class WorkspaceRecovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.db, self.assets = self.root / "desk.sqlite3", self.root / "assets"
        self.archive, self.restored = self.root / "backup.zip", self.root / "restored"
        self.raw = b"SYNTHETIC original\x00\xff\r\n"
        mapping = {"namespace": "synthetic", "customers": {
            "file": "customers.csv", "fields": {"external_id": "id", "name": "name", "email": "email"}},
            "tasks": {"file": "tasks.csv", "fields": {
                "external_id": "id", "customer_external_id": "customer", "title": "title"}},
            "attachments": {"file": "attachments.csv", "fields": {
                "external_id": "id", "customer_external_id": "customer", "path": "path", "name": "name"}}}
        (self.source / "mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
        (self.source / "customers.csv").write_text("id,name,email\n001,Synthetic Client,client@example.invalid\n", encoding="utf-8")
        (self.source / "tasks.csv").write_text("id,customer,title\n001,001,Review sample\n", encoding="utf-8")
        (self.source / "attachments.csv").write_text("id,customer,path,name\n001,001,original.bin,Original.bin\n", encoding="utf-8")
        (self.source / "original.bin").write_bytes(self.raw)
        self.plan = make_plan(self.source, "mapping.json", self.db, "synthetic-import-1")
        apply_plan(self.plan, self.source, self.db, self.assets)

    def backup(self):
        return recovery.backup_workspace(self.db, self.assets, self.archive)

    def restore(self):
        recovery.restore_workspace(self.archive, self.restored)
        return self.restored / recovery.DATABASE, self.restored / "assets"

    def tables(self, database):
        db = sqlite3.connect(database)
        try:
            return {name: db.execute(f"SELECT * FROM {name} ORDER BY 1,2").fetchall()
                    for name in ("records", "runs", "changes")}
        finally:
            db.close()

    def changed_attachment(self):
        new = b"SYNTHETIC replaced\x00\xfe"
        (self.source / "original.bin").write_bytes(new)
        plan = make_plan(self.source, "mapping.json", self.db, "synthetic-import-2")
        apply_plan(plan, self.source, self.db, self.assets)
        return plan, new

    def rewrite(self, change):
        with zipfile.ZipFile(self.archive) as bundle:
            entries = {name: bundle.read(name) for name in bundle.namelist()}
        manifest = json.loads(entries[recovery.MANIFEST])
        change(entries, manifest)
        entries[recovery.MANIFEST] = json.dumps(manifest).encode()
        other = self.root / "changed.zip"
        with zipfile.ZipFile(other, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, raw in entries.items():
                bundle.writestr(name, raw)
        return other

    def test_roundtrip_exact_tables_and_original_bytes(self):
        original = self.tables(self.db)
        result = self.backup()
        self.assertEqual(result["counts"], {"records": 3, "runs": 1, "changes": 3, "attachments": 1})
        manifest = recovery.verify_archive(self.archive)
        database, assets = self.restore()
        self.assertEqual(self.tables(database), original)
        self.assertEqual(self.tables(self.db), original)
        self.assertEqual((assets / digest(self.raw)).read_bytes(), self.raw)
        self.assertEqual(manifest, json.loads((self.restored / recovery.MANIFEST).read_bytes()))
        self.assertFalse((self.restored / recovery.MARKER).exists())
        if os.name == "posix":
            self.assertEqual(self.archive.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.restored.stat().st_mode & 0o777, 0o700)

    def test_continue_edit_on_restored_workspace_only(self):
        before = read_state(self.db)
        self.backup()
        database, _ = self.restore()
        task = next(row for row in before.values() if row["kind"] == "tasks")
        updated = edit_record(database, task["id"], task["revision"], {"status": "done"})
        self.assertEqual(updated["data"]["status"], "done")
        self.assertEqual(read_state(self.db), before)
        with self.assertRaises(MigrationError):
            rollback(database, self.plan["operation"])
        self.assertEqual(read_state(database)[task["id"]], updated)

    def test_retry_and_rollback_journal_survive_recovery(self):
        self.backup()
        database, assets = self.restore()
        retry = apply_plan(self.plan, self.source, database, assets)
        self.assertTrue(retry["repeated"])
        self.assertEqual(len(self.tables(database)["runs"]), 1)
        self.assertEqual(rollback(database, self.plan["operation"])["restored_records"], 3)
        self.assertEqual(read_state(database), {})
        self.assertTrue(rollback(database, self.plan["operation"])["repeated"])
        self.assertEqual(len(read_state(self.db)), 3)

    def test_historical_attachment_restored_by_real_rollback_and_export(self):
        plan, new = self.changed_attachment()
        self.backup()
        database, assets = self.restore()
        self.assertEqual({p.name for p in assets.iterdir()}, {digest(self.raw), digest(new)})
        rollback(database, plan["operation"])
        output = self.root / "after-rollback-export"
        export_workspace(database, assets, output)
        self.assertEqual((output / "attachments" / digest(self.raw)).read_bytes(), self.raw)
        self.assertFalse((output / "attachments" / digest(new)).exists())
        rollback(database, self.plan["operation"])
        self.assertEqual(read_state(database), {})

    def test_already_rolled_back_history_and_assets_retained(self):
        rollback(self.db, self.plan["operation"])
        self.backup()
        database, assets = self.restore()
        self.assertEqual(read_state(database), {})
        self.assertTrue(rollback(database, self.plan["operation"])["repeated"])
        self.assertEqual((assets / digest(self.raw)).read_bytes(), self.raw)
        self.assertEqual(self.tables(database), self.tables(self.db))

    def test_committed_wal_included_pending_write_excluded(self):
        writer = sqlite3.connect(self.db, isolation_level=None)
        try:
            writer.execute("PRAGMA journal_mode=WAL")
            task = next(r for r in read_state(self.db).values() if r["kind"] == "tasks")
            edit_record(self.db, task["id"], task["revision"], {"status": "in_progress"})
            committed = read_state(self.db)
            self.assertTrue(Path(str(self.db) + "-wal").is_file())
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("UPDATE records SET revision=999 WHERE id=?", (task["id"],))
            self.backup()
            database, _ = self.restore()
            self.assertEqual(read_state(database), committed)
            self.assertEqual(writer.execute("SELECT revision FROM records WHERE id=?", (task["id"],)).fetchone()[0], 999)
        finally:
            writer.rollback()
            writer.close()

    def test_empty_canonical_workspace(self):
        empty = self.root / "empty.db"
        connect(empty).close()
        recovery.backup_workspace(empty, self.root / "absent-assets", self.archive)
        database, assets = self.restore()
        self.assertEqual(read_state(database), {})
        self.assertEqual(list(assets.iterdir()), [])

    def test_content_deduplication_and_unrelated_files_excluded(self):
        with (self.source / "attachments.csv").open("a", encoding="utf-8") as stream:
            stream.write("002,001,original.bin,Second-name.bin\n")
        plan = make_plan(self.source, "mapping.json", self.db, "same-content")
        apply_plan(plan, self.source, self.db, self.assets)
        (self.assets / "unrelated-private.txt").write_text("must not be copied")
        self.backup()
        manifest = recovery.verify_archive(self.archive)
        self.assertEqual(manifest["counts"]["records"], 4)
        self.assertEqual(manifest["counts"]["attachments"], 1)
        self.assertEqual(set(manifest["files"]), {recovery.DATABASE, "assets/" + digest(self.raw)})

    def test_missing_or_changed_current_asset_does_not_publish(self):
        asset = self.assets / digest(self.raw)
        for raw in (None, b"incorrect"):
            with self.subTest(raw=raw):
                asset.unlink(missing_ok=True)
                if raw is not None:
                    asset.write_bytes(raw)
                with self.assertRaises(ERRORS):
                    self.backup()
                self.assertFalse(self.archive.exists())
                self.assertEqual(list(self.root.glob(".migration-backup-*")), [])

    def test_missing_historical_asset_does_not_publish(self):
        self.changed_attachment()
        (self.assets / digest(self.raw)).unlink()
        with self.assertRaises(ERRORS):
            self.backup()
        self.assertFalse(self.archive.exists())
        self.assertEqual(len(read_state(self.db)), 3)

    def test_missing_and_unrelated_databases_rejected(self):
        missing = self.root / "missing.db"
        with self.assertRaises(ERRORS):
            recovery.backup_workspace(missing, self.assets, self.archive)
        self.assertFalse(missing.exists())
        unrelated = self.root / "unrelated.db"
        db = sqlite3.connect(unrelated)
        db.execute("CREATE TABLE unrelated(value TEXT)")
        db.close()
        with self.assertRaises(ERRORS):
            recovery.backup_workspace(unrelated, self.assets, self.archive)
        self.assertFalse(self.archive.exists())

    def test_existing_outputs_never_overwritten(self):
        self.archive.write_bytes(b"existing archive")
        with self.assertRaises(ERRORS):
            self.backup()
        self.assertEqual(self.archive.read_bytes(), b"existing archive")
        self.archive.unlink()
        self.backup()
        self.restored.mkdir()
        (self.restored / "original").write_bytes(b"keep")
        with self.assertRaises(ERRORS):
            self.restore()
        self.assertEqual((self.restored / "original").read_bytes(), b"keep")
        self.assertEqual(len(list(self.restored.iterdir())), 1)

    def test_concurrent_backup_publication_has_one_winner(self):
        def contender(_):
            try:
                self.backup()
                return True
            except ERRORS:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(contender, range(16))), 1)
        self.assertEqual(recovery.verify_archive(self.archive)["counts"]["records"], 3)

    def test_concurrent_restore_has_one_winner(self):
        self.backup()
        def contender(_):
            try:
                self.restore()
                return True
            except ERRORS:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(contender, range(16))), 1)
        self.assertEqual(self.tables(self.restored / recovery.DATABASE), self.tables(self.db))
        self.assertFalse((self.restored / recovery.MARKER).exists())

    def test_damaged_member_fails_before_destination_reservation(self):
        self.backup()
        damaged = self.rewrite(lambda entries, manifest: entries.__setitem__("assets/" + digest(self.raw), b"x" * len(self.raw)))
        with self.assertRaises(ERRORS):
            recovery.restore_workspace(damaged, self.restored)
        self.assertFalse(self.restored.exists())

    def test_missing_historical_member_rejected_even_with_consistent_manifest(self):
        self.changed_attachment()
        self.backup()
        def remove(entries, manifest):
            name = "assets/" + digest(self.raw)
            del entries[name]
            del manifest["files"][name]
            manifest["counts"]["attachments"] -= 1
        damaged = self.rewrite(remove)
        with self.assertRaisesRegex(MigrationError, "complete attachment history"):
            recovery.verify_archive(damaged)

    def test_duplicate_extra_and_path_members_rejected(self):
        self.backup()
        extra = self.rewrite(lambda entries, manifest: entries.__setitem__("../outside", b"no"))
        with self.assertRaises(ERRORS):
            recovery.restore_workspace(extra, self.restored)
        self.assertFalse((self.root / "outside").exists())
        def invalid(entries, manifest):
            entries["../outside"] = b"no"
            manifest["files"]["../outside"] = {"sha256": digest(b"no"), "bytes": 2}
        declared = self.rewrite(invalid)
        with self.assertRaisesRegex(MigrationError, "member name"):
            recovery.verify_archive(declared)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.archive, "a") as bundle:
                bundle.writestr(recovery.MANIFEST, b"{}")
        with self.assertRaisesRegex(MigrationError, "Duplicate"):
            recovery.verify_archive(self.archive)

    def test_bad_metadata_and_byte_limits_rejected(self):
        self.backup()
        mutations = [lambda e, m: m.__setitem__("format", "other"),
                     lambda e, m: m.__setitem__("files", []),
                     lambda e, m: m["files"][recovery.DATABASE].__setitem__("bytes", True),
                     lambda e, m: m["files"][recovery.DATABASE].__setitem__("sha256", "wrong"),
                     lambda e, m: m["counts"].__setitem__("runs", True)]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(ERRORS):
                    recovery.verify_archive(self.rewrite(mutation))
        with patch.object(recovery, "MAX_BYTES", 10):
            with self.assertRaises(MigrationError):
                recovery.verify_archive(self.archive)
            with self.assertRaises(MigrationError):
                recovery.backup_workspace(self.db, self.assets, self.root / "tiny.zip")
        self.assertFalse((self.root / "tiny.zip").exists())

    def test_failed_transfer_retains_incomplete_marker_and_source(self):
        self.backup()
        original = self.tables(self.db)
        with patch.object(recovery.shutil, "copyfileobj", side_effect=OSError("synthetic full disk")):
            with self.assertRaises(OSError):
                self.restore()
        self.assertTrue((self.restored / recovery.MARKER).is_file())
        self.assertEqual(self.tables(self.db), original)
        with self.assertRaises(ERRORS):
            self.restore()

    def test_symlink_asset_rejected_without_publishing(self):
        asset = self.assets / digest(self.raw)
        asset.unlink()
        try:
            asset.symlink_to(self.source / "original.bin")
        except OSError:
            self.skipTest("OS does not permit symlink creation")
        with self.assertRaises(ERRORS):
            self.backup()
        self.assertFalse(self.archive.exists())

    def test_actual_cli_backup_verify_restore_and_error(self):
        def run(*args):
            return subprocess.run([sys.executable, "-B", str(HERE / "workspace_backup.py"), *map(str, args)],
                                  text=True, capture_output=True, check=False, timeout=15)
        result = run("backup", "--database", self.db, "--assets", self.assets, "--output", self.archive)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        verified = run("verify", self.archive)
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        self.assertTrue(json.loads(verified.stdout)["verified"])
        result = run("restore", self.archive, self.restored)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.tables(self.restored / recovery.DATABASE), self.tables(self.db))
        rejected = run("restore", self.archive, self.restored)
        self.assertEqual(rejected.returncode, 2)
        self.assertFalse(json.loads(rejected.stdout)["completed"])
        self.assertEqual(rejected.stderr, "")


if __name__ == "__main__":
    unittest.main()
