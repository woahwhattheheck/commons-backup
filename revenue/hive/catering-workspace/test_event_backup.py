"""Exercise real event-store backups, reopen, live writers and file preservation."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

from event_backup import backup_events
from event_store import Store


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.sqlite3'
        self.target = self.root / 'backup.sqlite3'
        self.store = Store(self.source)
        self.first = self.store.save({'headcount': '40', 'quote': '785.10'}, title='Synthetic lunch', operation_id='create')
        self.second = self.store.save({'headcount': '60', 'quote': '1096.40'}, self.first['id'], 1, title='Larger lunch', operation_id='edit')

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_history_and_idempotency_reopen(self):
        before = self.source.read_bytes()
        receipt = backup_events(self.source, self.target)
        self.assertEqual(receipt['counts'], {'events': 1, 'revisions': 2, 'operations': 2})
        self.assertEqual(receipt['sha256'], hashlib.sha256(self.target.read_bytes()).hexdigest())
        self.assertEqual(receipt['bytes'], self.target.stat().st_size)
        copy = Store(self.target)
        self.assertEqual(copy.get(self.first['id'], 1), self.first)
        self.assertEqual(copy.get(self.first['id']), self.second)
        retry = copy.save({'headcount': '40', 'quote': '785.10'}, title='Synthetic lunch', operation_id='create')
        self.assertEqual(retry, self.first)
        self.assertEqual(copy.get(self.first['id']), self.second)
        self.assertEqual(self.source.read_bytes(), before)

    def test_reopened_backup_can_continue_without_changing_original(self):
        backup_events(self.source, self.target)
        restored = Store(self.target)
        next_record = restored.save({'headcount': '70'}, self.first['id'], 2)
        self.assertEqual(next_record['revision'], 3)
        self.assertEqual(self.store.get(self.first['id']), self.second)
        self.assertEqual(len(self.store.history(self.first['id'])), 2)

    def test_existing_destination_and_source_preserved(self):
        self.target.write_bytes(b'keep previous backup')
        source_bytes = self.source.read_bytes()
        with self.assertRaises(FileExistsError):
            backup_events(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), b'keep previous backup')
        self.assertEqual(self.source.read_bytes(), source_bytes)
        with self.assertRaises(ValueError):
            backup_events(self.source, self.source)
        self.assertEqual(self.source.read_bytes(), source_bytes)

    def test_missing_and_wrong_source_never_create_backup(self):
        missing = self.root / 'absent.sqlite3'
        with self.assertRaises(FileNotFoundError):
            backup_events(missing, self.target)
        self.assertFalse(missing.exists())
        self.assertFalse(self.target.exists())
        other = self.root / 'unrelated.sqlite3'
        conn = sqlite3.connect(other)
        conn.execute('CREATE TABLE unrelated (value TEXT)')
        conn.close()
        with self.assertRaises(ValueError):
            backup_events(other, self.target)
        self.assertFalse(self.target.exists())

    def test_invalid_database_preserves_source(self):
        invalid = self.root / 'invalid.sqlite3'
        invalid.write_bytes(b'not a SQLite database')
        with self.assertRaises(sqlite3.DatabaseError):
            backup_events(invalid, self.target)
        self.assertFalse(self.target.exists())
        self.assertEqual(invalid.read_bytes(), b'not a SQLite database')

    def test_wal_writer_and_backup_are_consistent(self):
        conn = sqlite3.connect(self.source)
        self.assertEqual(conn.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
        conn.close()
        barrier = threading.Barrier(2)
        def writer():
            barrier.wait()
            for n in range(3, 13):
                self.store.save({'revision_value': n}, self.first['id'], n - 1, operation_id=f'edit-{n}')
        def backup():
            barrier.wait()
            return backup_events(self.source, self.target)
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_write = pool.submit(writer)
            f_backup = pool.submit(backup)
            receipt = f_backup.result(timeout=15)
            f_write.result(timeout=15)
        copied = Store(self.target)
        final = copied.get(self.first['id'])
        revision = final['revision']
        self.assertGreaterEqual(revision, 2)
        self.assertLessEqual(revision, 12)
        self.assertEqual(len(copied.history(self.first['id'])), revision)
        self.assertEqual(receipt['counts']['revisions'], revision)
        self.assertEqual(receipt['counts']['operations'], revision)
        self.assertEqual(self.store.get(self.first['id'])['revision'], 12)

    def test_real_cli_and_failure_exit(self):
        script = str(Path(__file__).with_name('event_backup.py'))
        command = [sys.executable, script, '--source', str(self.source), '--destination', str(self.target)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['counts']['events'], 1)
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Backup not created:', result.stderr)
        self.assertEqual(Store(self.target).get(self.first['id']), self.second)


if __name__ == '__main__':
    unittest.main()
