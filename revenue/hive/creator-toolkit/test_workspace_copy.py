"""Real snapshot/restore, WAL, concurrent-write, CLI and HTTP regressions."""
import base64
import concurrent.futures
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import make_server
from operator_auth import OperatorAuth
from toolkit import Store
from workspace_copy import CopyError, REQUIRED, copy_workspace, snapshot_bytes

BINARY = bytes(range(256)) + b'\x00\xff original resource\r\n'


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'original.sqlite3'
        self.store = Store(self.source, lambda: 1000)
        self.resource = self.store.mutate('resource.create', 'resource', {
            'title': 'Fictional file', 'kind': 'file', 'filename': 'original.bin',
            'data_base64': base64.b64encode(BINARY).decode(),
            'sequence': [{'delay_minutes': 0, 'subject': 'Optional', 'body': 'Fictional draft.'}],
        })
        self.request = self.store.mutate('request', 'request', {
            'resource_id': self.resource['id'], 'email': 'reader@example.invalid', 'opt_in': True,
        })
        member = self.store.member(self.request['member_id'])
        self.store.mutate('preferences', 'stop', {
            'member_id': member['id'], 'expected_revision': member['revision'], 'opted_in': False,
        })
        self.store.mutate('inquiry', 'inquiry', {'member_id': member['id'], 'body': 'A fictional question.'})
        self.destination = self.root / 'restored.sqlite3'

    def rows(self, path):
        with closing(sqlite3.connect(path)) as db:
            return {table: db.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
                    for table in REQUIRED}

    def test_full_restore_preserves_all_tables_bytes_and_cancelled_state(self):
        original_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        original = self.rows(self.source)
        receipt = copy_workspace(self.source, self.destination)
        self.assertEqual(self.rows(self.destination), original)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), original_hash)
        self.assertEqual(receipt['sha256'], hashlib.sha256(self.destination.read_bytes()).hexdigest())
        self.assertEqual(receipt['bytes'], self.destination.stat().st_size)
        reopened = Store(self.destination)
        self.assertEqual(reopened.delivery(self.request['request_id'])['data'], BINARY)
        self.assertFalse(reopened.member(self.request['member_id'])['opted_in'])
        self.assertEqual(reopened.dashboard()['outbox'][0]['state'], 'cancelled')
        repeat = reopened.mutate('request', 'another-operation', {
            'resource_id': self.resource['id'], 'email': 'reader@example.invalid', 'opt_in': True,
        })
        self.assertEqual(repeat['request_id'], self.request['request_id'])
        self.assertFalse(reopened.member(self.request['member_id'])['opted_in'])
        self.assertEqual(reopened.dashboard()['counts']['requests'], 1)

    def test_copy_is_independent_of_later_source_mutations(self):
        copy_workspace(self.source, self.destination)
        self.store.mutate('inquiry', 'later', {'member_id': self.request['member_id'], 'body': 'Later question.'})
        self.assertEqual(len(Store(self.destination).dashboard()['inquiries']), 1)
        self.assertEqual(len(self.store.dashboard()['inquiries']), 2)

    def test_committed_wal_rows_are_included(self):
        with closing(sqlite3.connect(self.source)) as db:
            self.assertEqual(db.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
            db.execute('PRAGMA wal_autocheckpoint=0')
            db.execute("UPDATE resources SET title='Committed in WAL' WHERE id=?", (self.resource['id'],))
            db.commit()
            self.assertGreater(Path(str(self.source) + '-wal').stat().st_size, 0)
            copy_workspace(self.source, self.destination)
            self.assertEqual(Store(self.destination).catalog()[0]['title'], 'Committed in WAL')

    def test_concurrent_requests_produce_a_consistent_complete_snapshot(self):
        started = threading.Event()
        def writer():
            for number in range(20):
                self.store.mutate('request', f'parallel-{number}', {
                    'resource_id': self.resource['id'], 'email': f'parallel{number}@example.invalid', 'opt_in': True,
                })
                started.set()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            job = pool.submit(writer)
            self.assertTrue(started.wait(3))
            receipt = copy_workspace(self.source, self.destination)
            job.result(timeout=10)
        self.assertGreaterEqual(receipt['counts']['requests'], 2)
        self.assertLessEqual(receipt['counts']['requests'], 21)
        self.assertEqual(receipt['counts']['requests'], receipt['counts']['outbox'])
        with closing(sqlite3.connect(self.destination)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.store.dashboard()['counts']['requests'], 21)

    def test_existing_destination_is_not_overwritten(self):
        self.destination.write_bytes(b'keep the existing file')
        with self.assertRaisesRegex(CopyError, 'already exists'):
            copy_workspace(self.source, self.destination)
        self.assertEqual(self.destination.read_bytes(), b'keep the existing file')

    def test_source_cannot_be_its_destination(self):
        original = self.source.read_bytes()
        with self.assertRaises(CopyError):
            copy_workspace(self.source, self.source)
        self.assertEqual(self.source.read_bytes(), original)

    def test_destination_symlink_and_its_target_remain_unchanged(self):
        target = self.root / 'target'
        target.write_bytes(b'retained')
        self.destination.symlink_to(target)
        with self.assertRaises(CopyError):
            copy_workspace(self.source, self.destination)
        self.assertTrue(self.destination.is_symlink())
        self.assertEqual(target.read_bytes(), b'retained')

    def test_destination_created_during_copy_wins(self):
        link = os.link
        def race(source, destination):
            Path(destination).write_bytes(b'concurrent owner')
            return link(source, destination)
        with patch('workspace_copy.os.link', side_effect=race):
            with self.assertRaisesRegex(CopyError, 'already exists'):
                copy_workspace(self.source, self.destination)
        self.assertEqual(self.destination.read_bytes(), b'concurrent owner')
        self.assertEqual(list(self.root.glob('.creator-copy-*')), [])

    def test_missing_source_does_not_create_a_database(self):
        source = self.root / 'absent'
        with self.assertRaisesRegex(CopyError, 'existing workspace'):
            copy_workspace(source, self.destination)
        self.assertFalse(source.exists())
        self.assertFalse(self.destination.exists())

    def test_non_sqlite_source_leaves_no_partial_output(self):
        source = self.root / 'not-a-database'
        source.write_bytes(b'not sqlite')
        with self.assertRaises(CopyError):
            copy_workspace(source, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob('.creator-copy-*')), [])

    def test_other_database_is_not_mislabeled_a_workspace(self):
        source = self.root / 'other.sqlite3'
        with closing(sqlite3.connect(source)) as db:
            db.execute('CREATE TABLE notes(id TEXT)')
            db.commit()
        with self.assertRaisesRegex(CopyError, 'Not a Creator Desk'):
            copy_workspace(source, self.destination)
        self.assertFalse(self.destination.exists())

    def test_resource_digest_mismatch_is_retained_only_in_source(self):
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("UPDATE resources SET data=X'00'")
            db.commit()
        with self.assertRaisesRegex(CopyError, 'SHA-256'):
            copy_workspace(self.source, self.destination)
        self.assertFalse(self.destination.exists())
        with closing(sqlite3.connect(self.source)) as db:
            self.assertEqual(db.execute('SELECT data FROM resources').fetchone()[0], b'\0')

    def test_broken_relationship_prevents_publishing_copy(self):
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("UPDATE requests SET member_id='missing'")
            db.commit()
        with self.assertRaisesRegex(CopyError, 'relationship'):
            copy_workspace(self.source, self.destination)
        self.assertFalse(self.destination.exists())

    def test_size_limit_has_no_partial_destination(self):
        with self.assertRaisesRegex(CopyError, 'size limit'):
            copy_workspace(self.source, self.destination, max_bytes=1)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob('.creator-copy-*')), [])

    def test_invalid_options_fail_before_copy(self):
        for maximum in (True, 0, -1, 1.5):
            with self.subTest(maximum=maximum), self.assertRaises(CopyError):
                copy_workspace(self.source, self.destination, max_bytes=maximum)
        for timeout in (True, 0, -1, float('nan'), float('inf')):
            with self.subTest(timeout=timeout), self.assertRaises(CopyError):
                copy_workspace(self.source, self.destination, timeout_seconds=timeout)
        self.assertFalse(self.destination.exists())

    def test_download_receipt_has_no_member_data_or_temporary_path(self):
        data, receipt = snapshot_bytes(self.source)
        self.assertEqual(hashlib.sha256(data).hexdigest(), receipt['sha256'])
        self.assertNotIn('destination', receipt)
        self.assertNotIn('reader@example.invalid', json.dumps(receipt))
        self.assertEqual(receipt['counts']['members'], 1)

    def test_real_cli_restore_and_existing_path_error(self):
        command = [sys.executable, str(Path(__file__).with_name('workspace_copy.py')), str(self.source), str(self.destination)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['counts']['requests'], 1)
        before = self.destination.read_bytes()
        duplicate = subprocess.run(command, text=True, capture_output=True, timeout=10)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn('already exists', duplicate.stderr)
        self.assertEqual(self.destination.read_bytes(), before)

    def test_live_http_backup_restores_usable_workspace(self):
        operator_key = OperatorAuth.initialize(self.source)
        server = make_server(self.store, port=0)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        try:
            backup_url = f'http://127.0.0.1:{server.server_port}/workspace.sqlite3'
            with self.assertRaises(HTTPError) as denied:
                urlopen(backup_url, timeout=10)
            self.assertEqual(denied.exception.code, 403)
            request = Request(backup_url, headers={'Authorization': f'Bearer {operator_key}'})
            with urlopen(request, timeout=10) as response:
                data, headers = response.read(), response.headers
            self.assertEqual(headers['X-Content-SHA256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertIn('attachment', headers['Content-Disposition'])
            self.destination.write_bytes(data)
            reopened = Store(self.destination)
            self.assertEqual(reopened.delivery(self.request['request_id'])['data'], BINARY)
            self.assertFalse(reopened.member(self.request['member_id'])['opted_in'])
            self.assertTrue(OperatorAuth(self.destination).verify(operator_key))
            with urlopen(f'http://127.0.0.1:{server.server_port}/') as response:
                self.assertIn(b'href="/workspace.sqlite3"', response.read())
            with closing(sqlite3.connect(self.source)) as db:
                db.execute("UPDATE resources SET sha256='invalid'")
                db.commit()
            request = Request(backup_url, headers={'Authorization': f'Bearer {operator_key}'})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=10)
            self.assertEqual(caught.exception.code, 409)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


if __name__ == '__main__':
    unittest.main(verbosity=2)