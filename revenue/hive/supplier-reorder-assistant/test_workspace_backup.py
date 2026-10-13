"""Exercise real online SQLite snapshots, restores and retained receiving state."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile

import desk
import workspace_backup as backup
from test_desk import make_request, receiving


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / 'active.sqlite3'
        self.archive = self.root / 'copy.zip'
        self.restored = self.root / 'restored.sqlite3'
        self.store = desk.Store(self.database)
        self.original = self.store.create(make_request())
        self.current = self.store.receive(self.original['id'], receiving())

    def create_archive(self):
        return backup.snapshot(self.database, self.archive)

    def rewrite_archive(self, mutate):
        self.create_archive()
        with zipfile.ZipFile(self.archive) as source:
            parts = {name: source.read(name) for name in source.namelist()}
        mutate(parts)
        changed = self.root / 'changed.zip'
        with zipfile.ZipFile(changed, 'w') as target:
            for name, data in parts.items():
                target.writestr(name, data)
        return changed

    def test_complete_history_and_retry_state_round_trip(self):
        result = self.create_archive()
        restored = backup.restore(self.archive, self.restored)
        self.assertEqual(result['database_sha256'], restored['database_sha256'])
        self.assertEqual(result['tables'], {'runs': 1, 'revisions': 2, 'operations': 2})
        store = desk.Store(self.restored)
        self.assertEqual(store.get(self.original['id']), self.current)
        self.assertEqual(store.get(self.original['id'], 1), self.original)
        self.assertEqual(store.create(make_request()), self.original)
        self.assertEqual(store.receive(self.original['id'], receiving()), self.current)
        self.assertEqual(store.get(self.original['id'])['revision'], 2)
        self.assertEqual(self.store.get(self.original['id']), self.current)

    def test_restore_can_receive_more_without_duplicate_stock(self):
        self.create_archive()
        backup.restore(self.archive, self.restored)
        store = desk.Store(self.restored)
        doc = store.receive(self.original['id'], receiving('second', 2, 'R2', 5))
        self.assertIn('Filter cartridge,11,3,1,each', doc['updated_stock'])
        with self.assertRaises(desk.DeskError):
            store.receive(doc['id'], receiving('over', 3, 'R3', 1))

    def test_wal_database_is_snapshotted_with_uncheckpointed_work(self):
        with closing(sqlite3.connect(self.database)) as holder:
            self.assertEqual(holder.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
            holder.execute('BEGIN')
            holder.execute('SELECT count(*) FROM runs').fetchone()
            self.store.create(make_request('wal-plan'))
            self.assertTrue(Path(str(self.database) + '-wal').exists())
            self.create_archive()
        backup.restore(self.archive, self.restored)
        self.assertEqual(len(desk.Store(self.restored).list()), 2)

    def test_online_snapshot_while_real_writer_commits(self):
        started, stop = threading.Event(), threading.Event()
        errors, writes = [], []
        def writer():
            try:
                for i in range(100):
                    if stop.is_set():
                        break
                    self.store.create(make_request(f'live-{i}'))
                    writes.append(i)
                    started.set()
                    time.sleep(0.002)
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=writer)
        thread.start()
        try:
            self.assertTrue(started.wait(5))
            self.assertTrue(thread.is_alive())
            result = self.create_archive()
        finally:
            stop.set()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        self.assertTrue(writes)
        backup.restore(self.archive, self.restored)
        counts = backup.inspect_database(self.restored)
        self.assertEqual(counts, result['tables'])
        self.assertEqual(counts['revisions'], counts['runs'] + 1)
        self.assertEqual(counts['operations'], counts['runs'] + 1)

    def test_existing_archive_is_preserved(self):
        self.archive.write_bytes(b'keep archive')
        with self.assertRaises(backup.BackupError):
            self.create_archive()
        self.assertEqual(self.archive.read_bytes(), b'keep archive')

    def test_existing_database_is_preserved(self):
        self.create_archive()
        self.restored.write_bytes(b'keep database')
        with self.assertRaises(backup.BackupError):
            backup.restore(self.archive, self.restored)
        self.assertEqual(self.restored.read_bytes(), b'keep database')

    def test_publish_race_does_not_replace_target(self):
        first, second = self.root / 'first', self.root / 'second'
        first.write_bytes(b'new'); second.write_bytes(b'existing')
        with self.assertRaises(backup.BackupError):
            backup.publish_new(first, second)
        self.assertEqual(second.read_bytes(), b'existing')
        self.assertEqual(first.read_bytes(), b'new')

    def test_altered_database_digest_is_not_restored(self):
        changed = self.rewrite_archive(lambda parts: parts.__setitem__('workspace.sqlite3', b'x' + parts['workspace.sqlite3'][1:]))
        with self.assertRaisesRegex(backup.BackupError, 'digest'):
            backup.restore(changed, self.restored)
        self.assertFalse(self.restored.exists())

    def test_wrong_table_count_is_not_restored(self):
        def mutate(parts):
            manifest = json.loads(parts['manifest.json'])
            manifest['tables']['runs'] += 1
            parts['manifest.json'] = json.dumps(manifest).encode()
        changed = self.rewrite_archive(mutate)
        with self.assertRaisesRegex(backup.BackupError, 'table counts'):
            backup.restore(changed, self.restored)
        self.assertFalse(self.restored.exists())

    def test_unexpected_member_is_not_extracted(self):
        changed = self.rewrite_archive(lambda parts: parts.__setitem__('../extra', b'ignored'))
        with self.assertRaisesRegex(backup.BackupError, 'exactly'):
            backup.restore(changed, self.restored)
        self.assertFalse((self.root.parent / 'extra').exists())
        self.assertFalse(self.restored.exists())

    def test_invalid_manifest_and_types_are_rejected(self):
        for value in [b'{', b'[]', b'{}', b'null']:
            with self.subTest(value=value):
                fake = self.root / 'invalid.zip'
                with zipfile.ZipFile(fake, 'w') as target:
                    target.writestr('manifest.json', value)
                    target.writestr('workspace.sqlite3', b'not a database')
                with self.assertRaises(backup.BackupError):
                    backup.restore(fake, self.restored)
                self.assertFalse(self.restored.exists())

    def test_snapshot_and_restore_size_limits(self):
        with self.assertRaisesRegex(backup.BackupError, 'size limit'):
            backup.snapshot(self.database, self.archive, max_bytes=1)
        self.assertFalse(self.archive.exists())
        self.create_archive()
        with self.assertRaisesRegex(backup.BackupError, 'size limit'):
            backup.restore(self.archive, self.restored, max_bytes=1)
        self.assertFalse(self.restored.exists())

    def test_missing_source_does_not_create_empty_database(self):
        missing = self.root / 'missing.sqlite3'
        with self.assertRaises(backup.BackupError):
            backup.snapshot(missing, self.archive)
        self.assertFalse(missing.exists())
        self.assertFalse(self.archive.exists())

    def test_other_database_is_not_a_workspace(self):
        other = self.root / 'other.sqlite3'
        with closing(sqlite3.connect(other)) as db:
            db.execute('CREATE TABLE unrelated(x)')
        with self.assertRaisesRegex(backup.BackupError, 'workspace columns'):
            backup.snapshot(other, self.archive)
        self.assertFalse(self.archive.exists())

    def test_boolean_manifest_count_is_invalid(self):
        def mutate(parts):
            manifest = json.loads(parts['manifest.json'])
            manifest['tables']['runs'] = True
            parts['manifest.json'] = json.dumps(manifest).encode()
        changed = self.rewrite_archive(mutate)
        with self.assertRaisesRegex(backup.BackupError, 'integers'):
            backup.restore(changed, self.restored)
        self.assertFalse(self.restored.exists())

    def test_restore_result_names_actual_destination(self):
        def mutate(parts):
            manifest = json.loads(parts['manifest.json'])
            manifest.update(database='different-name.sqlite3', verified=False)
            parts['manifest.json'] = json.dumps(manifest).encode()
        changed = self.rewrite_archive(mutate)
        result = backup.restore(changed, self.restored)
        self.assertEqual(result['database'], str(self.restored))
        self.assertTrue(result['verified'])

    def test_corrupt_database_leaves_no_archive(self):
        corrupt = self.root / 'corrupt.sqlite3'
        corrupt.write_bytes(b'not sqlite')
        with self.assertRaises(sqlite3.DatabaseError):
            backup.snapshot(corrupt, self.archive)
        self.assertFalse(self.archive.exists())

    def test_invalid_archive_cli_reports_error_without_database(self):
        bad = self.root / 'bad.zip'
        bad.write_bytes(b'not a zip')
        run = subprocess.run([sys.executable, str(Path(backup.__file__)), 'restore', '--archive', str(bad), '--db', str(self.restored)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertFalse(self.restored.exists())

    def test_uri_characters_in_source_filename(self):
        unusual = self.root / 'workspace #1?.sqlite3'
        with closing(backup.readonly(self.database)) as source, closing(sqlite3.connect(unusual)) as target:
            source.backup(target)
        backup.snapshot(unusual, self.archive)
        backup.restore(self.archive, self.restored)
        self.assertEqual(desk.Store(self.restored).get(self.original['id']), self.current)

    def test_real_cli_snapshot_restore_and_error(self):
        script = str(Path(backup.__file__))
        run = subprocess.run([sys.executable, script, 'snapshot', '--db', str(self.database), '--out', str(self.archive)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(run.stdout)['tables']['runs'], 1)
        run = subprocess.run([sys.executable, script, 'restore', '--archive', str(self.archive), '--db', str(self.restored)], capture_output=True, text=True, check=True)
        self.assertTrue(json.loads(run.stdout)['verified'])
        run = subprocess.run([sys.executable, script, 'restore', '--archive', str(self.archive), '--db', str(self.restored)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn('already exists', run.stderr)


if __name__ == '__main__':
    unittest.main()
