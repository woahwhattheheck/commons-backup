"""Exercise real Fleetline SQLite backups, reopen, WAL and file preservation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

from backup import BackupError, backup_workspace
from fleet import CHECKS, Store

START = '2026-09-10T09:00:00-05:00'
END = '2026-09-11T09:00:00-05:00'


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.sqlite'
        self.target = self.root / 'backup.sqlite'
        self.store = Store(self.source)
        self.store.command(dict(action='save_asset', id='asset-01', name='Example lift',
                                unit='day', rate='75.25', minimum_units=1, notes='Synthetic'),
                           'asset-create')
        self.booking = self.store.command(
            dict(action='save_reservation', id='booking-01', asset_id='asset-01',
                 kind='booking', start=START, end=END, customer='Example customer',
                 contact='example@example.invalid', notes='Synthetic fixture only'),
            'book-create')['record']
        self.store.command(dict(action='checklist', id=self.booking['id'],
                                expected_revision=self.booking['revision'],
                                stage='handover',
                                checks={key: True for key in CHECKS['handover']},
                                complete=True, notes='Example condition'),
                           'handover-1')

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_counts_hash_and_idempotent_reopen(self):
        before = self.source.read_bytes()
        receipt = backup_workspace(self.source, self.target)
        self.assertEqual(receipt['format'], 'fleetline-sqlite-backup-v1')
        self.assertEqual(receipt['counts'],
                         {'assets': 1, 'reservations': 1, 'operations': 3, 'audit': 3})
        self.assertEqual(receipt['sha256'], hashlib.sha256(self.target.read_bytes()).hexdigest())
        self.assertEqual(receipt['bytes'], self.target.stat().st_size)
        self.assertEqual(receipt['sqlite_quick_check'], 'ok')
        self.assertEqual(receipt['foreign_key_check'], 'ok')
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        copy = Store(self.target)
        self.assertEqual(copy.state()['reservations'][0]['status'], 'out')
        retry = copy.command(dict(action='save_asset', id='asset-01', name='Example lift',
                                  unit='day', rate='75.25', minimum_units=1, notes='Synthetic'),
                             'asset-create')
        self.assertEqual(retry['record']['id'], 'asset-01')
        self.assertEqual(self.source.read_bytes(), before)

    def test_reopened_backup_can_continue_without_changing_original(self):
        backup_workspace(self.source, self.target)
        restored = Store(self.target)
        restored.command(dict(action='save_asset', id='asset-02', name='Second lift',
                              unit='hour', rate='10.00', minimum_units=1, notes=''),
                         'asset-2')
        self.assertEqual(len(restored.state()['assets']), 2)
        self.assertEqual(len(Store(self.source).state()['assets']), 1)

    def test_existing_destination_and_source_preserved(self):
        self.target.write_bytes(b'keep previous backup')
        source_bytes = self.source.read_bytes()
        with self.assertRaises(FileExistsError):
            backup_workspace(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), b'keep previous backup')
        self.assertEqual(self.source.read_bytes(), source_bytes)
        with self.assertRaises(BackupError):
            backup_workspace(self.source, self.source)
        self.assertEqual(self.source.read_bytes(), source_bytes)

    def test_missing_and_wrong_source_never_create_backup(self):
        missing = self.root / 'absent.sqlite'
        with self.assertRaises(FileNotFoundError):
            backup_workspace(missing, self.target)
        self.assertFalse(missing.exists())
        self.assertFalse(self.target.exists())
        other = self.root / 'unrelated.sqlite'
        with closing(sqlite3.connect(other)) as conn:
            conn.execute('CREATE TABLE unrelated (value TEXT)')
        with self.assertRaises(BackupError):
            backup_workspace(other, self.target)
        self.assertFalse(self.target.exists())

    def test_invalid_database_preserves_source(self):
        invalid = self.root / 'invalid.sqlite'
        invalid.write_bytes(b'not a SQLite database')
        with self.assertRaises(sqlite3.DatabaseError):
            backup_workspace(invalid, self.target)
        self.assertFalse(self.target.exists())
        self.assertEqual(invalid.read_bytes(), b'not a SQLite database')

    def test_timeout_removes_only_the_incomplete_copy(self):
        with self.assertRaises(BackupError) as caught:
            backup_workspace(self.source, self.target, max_seconds=1e-9)
        self.assertIn('time budget', str(caught.exception))
        self.assertFalse(self.target.exists())
        self.assertTrue(self.source.is_file())
        with self.assertRaises(BackupError):
            backup_workspace(self.source, self.root / 'zero.sqlite', max_seconds=0)

    def test_wal_committed_pages_are_included(self):
        with closing(sqlite3.connect(self.source)) as conn:
            self.assertEqual(conn.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
            conn.execute('PRAGMA wal_autocheckpoint=0')
            conn.execute("INSERT INTO assets VALUES('asset-wal','WAL committed','','day',100,1,1)")
            conn.commit()
        receipt = backup_workspace(self.source, self.target)
        self.assertEqual(receipt['counts']['assets'], 2)
        ids = {asset['id'] for asset in Store(self.target).state()['assets']}
        self.assertEqual(ids, {'asset-01', 'asset-wal'})

    def test_live_wal_writer_and_backup_are_consistent(self):
        with closing(sqlite3.connect(self.source)) as conn:
            self.assertEqual(conn.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
        barrier = threading.Barrier(2)

        def writer():
            barrier.wait()
            current = self.store.state()['reservations'][0]
            self.store.command(dict(action='checklist', id=current['id'],
                                    expected_revision=current['revision'],
                                    stage='return',
                                    checks={key: True for key in CHECKS['return']},
                                    complete=True, notes='Returned'),
                               'return-1')

        def backup():
            barrier.wait()
            return backup_workspace(self.source, self.target)

        with ThreadPoolExecutor(max_workers=2) as pool:
            write_future = pool.submit(writer)
            backup_future = pool.submit(backup)
            receipt = backup_future.result(timeout=15)
            write_future.result(timeout=15)
        copied = Store(self.target)
        status = copied.state()['reservations'][0]['status']
        self.assertIn(status, ('out', 'returned'))
        self.assertEqual(receipt['counts']['reservations'], 1)
        self.assertEqual(Store(self.source).state()['reservations'][0]['status'], 'returned')

    def test_real_cli_and_failure_exit(self):
        script = str(Path(__file__).with_name('backup.py'))
        command = [sys.executable, script, '--source', str(self.source),
                   '--destination', str(self.target)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['counts']['assets'], 1)
        self.assertEqual(Store(self.target).state()['reservations'][0]['status'], 'out')
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Backup not created:', result.stderr)
        self.assertEqual(Store(self.target).state()['reservations'][0]['status'], 'out')


if __name__ == '__main__':
    unittest.main()
