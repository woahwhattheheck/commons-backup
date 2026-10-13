"""Real SQLite/file/CLI recovery tests; all workspace records are synthetic."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import warnings
import zipfile

import workspace_backup as backup


class WorkspaceBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "original.sqlite3"
        self.archive = self.root / "workspace.zip"
        with closing(sqlite3.connect(self.db)) as con:
            con.executescript('''
                PRAGMA foreign_keys=ON;
                PRAGMA user_version=7;
                PRAGMA application_id=20260908;
                CREATE TABLE candidates(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE bookings(id INTEGER PRIMARY KEY, candidate_id INTEGER
                  REFERENCES candidates(id), revision INTEGER NOT NULL, starts TEXT);
                CREATE TABLE history(id INTEGER PRIMARY KEY, booking_id INTEGER
                  REFERENCES bookings(id), revision INTEGER, body BLOB);
                CREATE TABLE operations(id TEXT PRIMARY KEY, response TEXT);
                CREATE INDEX candidate_name ON candidates(name);
                INSERT INTO candidates VALUES(1,'Synthetic candidate');
                INSERT INTO bookings VALUES(1,1,1,'2026-10-10T14:00:00+00:00');
                INSERT INTO history VALUES(1,1,1,X'0001ff');
                INSERT INTO operations VALUES('synthetic-operation','{"id":1,"revision":1}');
            ''')

    def create(self):
        return backup.create_backup(self.db, self.archive)

    def rewrite(self, transform):
        with zipfile.ZipFile(self.archive) as source:
            members = {name: source.read(name) for name in source.namelist()}
        transform(members)
        with zipfile.ZipFile(self.archive, 'w', zipfile.ZIP_DEFLATED) as target:
            for name, content in members.items():
                target.writestr(name, content)

    def test_snapshot_verify_restore_continue_edit(self):
        source_digest = backup._digest(self.db)
        result = self.create()
        manifest = backup.verify_backup(self.archive)
        self.assertEqual(result['archive_sha256'], backup._digest(self.archive))
        self.assertEqual(manifest['database']['table_rows']['bookings'], 1)
        self.assertEqual(manifest['database']['user_version'], 7)
        self.assertEqual(manifest['database']['application_id'], 20260908)
        restored = self.root / 'restored.sqlite3'
        backup.restore_backup(self.archive, restored)
        with closing(sqlite3.connect(restored)) as con:
            self.assertEqual(con.execute('SELECT body FROM history').fetchone()[0], b'\x00\x01\xff')
            self.assertEqual(con.execute('SELECT response FROM operations').fetchone()[0], '{"id":1,"revision":1}')
            con.execute('UPDATE bookings SET revision=2,starts=? WHERE id=1', ('2026-10-11T15:00:00+00:00',))
            con.commit()
        with closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(con.execute('SELECT revision FROM bookings').fetchone()[0], 1)
        self.assertEqual(source_digest, backup._digest(self.db))

    def test_live_wal_commits_included_without_checkpoint(self):
        with closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(con.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
            con.execute('PRAGMA wal_autocheckpoint=0')
            con.execute("INSERT INTO candidates VALUES(2,'Committed WAL record')")
            con.commit()
            self.assertGreater(Path(str(self.db)+'-wal').stat().st_size, 0)
            self.create()
            restored = self.root/'from-wal.db'
            backup.restore_backup(self.archive, restored)
            with closing(sqlite3.connect(restored)) as copy:
                self.assertEqual(copy.execute('SELECT count(*) FROM candidates').fetchone()[0], 2)
                self.assertEqual(copy.execute('PRAGMA journal_mode').fetchone()[0], 'delete')

    def test_uncommitted_write_excluded(self):
        with closing(sqlite3.connect(self.db)) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute("INSERT INTO candidates VALUES(2,'Uncommitted')")
            self.create()
            self.assertEqual(backup.verify_backup(self.archive)['database']['table_rows']['candidates'], 1)
            writer.rollback()

    def test_consistent_snapshot_during_writes(self):
        with closing(sqlite3.connect(self.db)) as con:
            con.execute('PRAGMA journal_mode=WAL')
            con.executescript('CREATE TABLE balance(a INTEGER,b INTEGER); INSERT INTO balance VALUES(0,0);')
        started, stop = threading.Event(), threading.Event()
        errors = []
        def writer():
            try:
                with closing(sqlite3.connect(self.db)) as con:
                    for n in range(1, 1001):
                        con.execute('UPDATE balance SET a=?,b=?', (n,n))
                        con.commit()
                        started.set()
                        if stop.is_set():
                            break
            except Exception as exc:
                errors.append(exc)
                started.set()
        thread = threading.Thread(target=writer)
        thread.start()
        try:
            self.assertTrue(started.wait(5))
            self.create()
        finally:
            stop.set(); thread.join(5)
        self.assertFalse(thread.is_alive()); self.assertEqual(errors, [])
        restored = self.root/'consistent.db'
        backup.restore_backup(self.archive, restored)
        with closing(sqlite3.connect(restored)) as con:
            a,b = con.execute('SELECT a,b FROM balance').fetchone()
            self.assertEqual(a,b); self.assertGreater(a,0)

    def test_existing_archive_retained(self):
        self.archive.write_bytes(b'existing')
        with self.assertRaises(backup.BackupError): self.create()
        self.assertEqual(self.archive.read_bytes(), b'existing')

    def test_existing_database_retained(self):
        self.create()
        original = self.db.read_bytes()
        with self.assertRaises(backup.BackupError): backup.restore_backup(self.archive,self.db)
        self.assertEqual(self.db.read_bytes(), original)

    def test_destination_sidecars_not_adopted(self):
        self.create()
        for suffix in ('-wal','-shm','-journal'):
            target = self.root / ('restore'+suffix+'.db')
            sidecar = Path(str(target)+suffix); sidecar.write_bytes(b'old')
            with self.assertRaises(backup.BackupError): backup.restore_backup(self.archive,target)
            self.assertFalse(target.exists()); self.assertEqual(sidecar.read_bytes(),b'old')

    def test_missing_source_not_created(self):
        missing = self.root/'missing.db'
        with self.assertRaises(backup.BackupError): backup.create_backup(missing,self.archive)
        self.assertFalse(missing.exists()); self.assertFalse(self.archive.exists())

    def test_invalid_database_not_published(self):
        self.db.write_bytes(b'not SQLite')
        with self.assertRaises(backup.BackupError): self.create()
        self.assertFalse(self.archive.exists())
        self.assertFalse(list(self.root.glob('.recruiting-backup-*')))

    def test_broken_foreign_key_not_published(self):
        with closing(sqlite3.connect(self.db)) as con:
            con.execute('INSERT INTO bookings VALUES(2,999,1,NULL)'); con.commit()
        with self.assertRaises(backup.BackupError): self.create()
        self.assertFalse(self.archive.exists())

    def test_snapshot_size_limit(self):
        with self.assertRaises(backup.BackupError): backup.create_backup(self.db,self.archive,max_bytes=512)
        self.assertFalse(self.archive.exists())

    def test_restore_size_limit(self):
        self.create()
        with self.assertRaises(backup.BackupError): backup.verify_backup(self.archive,max_bytes=512)

    def test_invalid_limits(self):
        for size in (0,-1,True,0.5):
            with self.assertRaises(backup.BackupError): backup.verify_backup(self.archive,max_bytes=size)
        for value in (0,-1,float('nan'),float('inf'),True):
            with self.assertRaises(backup.BackupError): backup.create_backup(self.db,self.archive,timeout=value)

    def test_corrupt_bytes_rejected_before_destination_creation(self):
        self.create()
        self.rewrite(lambda files: files.__setitem__(backup.DATABASE, b'x' * len(files[backup.DATABASE])))
        target = self.root/'never.db'
        with self.assertRaises(backup.BackupError): backup.restore_backup(self.archive,target)
        self.assertFalse(target.exists())

    def test_extra_archive_path_rejected_without_extraction(self):
        self.create()
        self.rewrite(lambda files: files.__setitem__('../unexpected.txt',b'unexpected'))
        with self.assertRaises(backup.BackupError): backup.verify_backup(self.archive)
        self.assertFalse((self.root.parent/'unexpected.txt').exists())

    def test_duplicate_archive_member_rejected(self):
        self.create()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(self.archive,'a') as target: target.writestr(backup.MANIFEST,'{}')
        with self.assertRaises(backup.BackupError): backup.verify_backup(self.archive)

    def test_manifest_duplicates_rejected(self):
        self.create()
        self.rewrite(lambda files: files.__setitem__(backup.MANIFEST,b'{"format":1,"format":2}'))
        with self.assertRaises(backup.BackupError): backup.verify_backup(self.archive)

    def test_manifest_metadata_binding(self):
        self.create()
        def change(files):
            manifest=json.loads(files[backup.MANIFEST]); manifest['database']['table_rows']['candidates']=999
            files[backup.MANIFEST]=json.dumps(manifest).encode()
        self.rewrite(change)
        with self.assertRaises(backup.BackupError): backup.verify_backup(self.archive)

    def test_invalid_zip_and_format(self):
        self.archive.write_bytes(b'not zip')
        with self.assertRaises(backup.BackupError): backup.verify_backup(self.archive)
        self.archive.unlink(); self.create()
        self.rewrite(lambda files: files.__setitem__(backup.MANIFEST,b'{"format":"future"}'))
        with self.assertRaises(backup.BackupError): backup.verify_backup(self.archive)

    def test_cli_backup_verify_restore_errors(self):
        script=Path(backup.__file__)
        def run(*args):
            return subprocess.run([sys.executable,'-B',str(script),*map(str,args)],capture_output=True,text=True,timeout=15)
        created=run('backup',self.db,self.archive); self.assertEqual(created.returncode,0,created.stderr)
        checked=run('verify',self.archive); self.assertEqual(checked.returncode,0,checked.stderr)
        restored=run('restore',self.archive,self.root/'cli.db'); self.assertEqual(restored.returncode,0,restored.stderr)
        duplicate=run('restore',self.archive,self.root/'cli.db'); self.assertEqual(duplicate.returncode,2)
        self.assertIn('already exists',json.loads(duplicate.stderr)['error'])
        self.assertNotIn('Synthetic candidate',created.stdout)

    def test_concurrent_restore_single_winner(self):
        self.create(); target=self.root/'one.db'
        def attempt(_):
            try: backup.restore_backup(self.archive,target); return 'ok'
            except backup.BackupError: return 'exists'
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes=list(pool.map(attempt,range(16)))
        self.assertEqual(outcomes.count('ok'),1)
        self.assertEqual(backup._digest(target),backup.verify_backup(self.archive)['database']['sha256'])

    @unittest.skipUnless(os.name=='posix','POSIX file permissions and symlinks')
    def test_private_permissions_and_symlink_no_overwrite(self):
        self.create(); target=self.root/'private.db'
        backup.restore_backup(self.archive,target)
        self.assertEqual(self.archive.stat().st_mode & 0o777,0o600)
        self.assertEqual(target.stat().st_mode & 0o777,0o600)
        link=self.root/'link.db'; link.symlink_to(self.root/'missing-link-target')
        with self.assertRaises(backup.BackupError): backup.restore_backup(self.archive,link)
        self.assertTrue(link.is_symlink())

    def test_no_record_content_in_manifest(self):
        self.create()
        with zipfile.ZipFile(self.archive) as archive:
            self.assertEqual(set(archive.namelist()),{backup.DATABASE,backup.MANIFEST})
            text=archive.read(backup.MANIFEST).decode()
            self.assertNotIn('Synthetic candidate',text)
            self.assertNotIn(str(self.root),text)
            self.assertIn('not encrypted',text)

    def test_two_restore_copies_are_independent(self):
        self.create(); first=self.root/'a.db'; second=self.root/'b.db'
        backup.restore_backup(self.archive,first); backup.restore_backup(self.archive,second)
        with closing(sqlite3.connect(first)) as con:
            con.execute("UPDATE candidates SET name='Independent copy'"); con.commit()
        with closing(sqlite3.connect(second)) as con:
            self.assertEqual(con.execute('SELECT name FROM candidates').fetchone()[0],'Synthetic candidate')


if __name__=='__main__': unittest.main()
