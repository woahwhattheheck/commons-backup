"""Focused regressions and an actual SQLite consumer transaction."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from attachment_intake import AttachmentError, prepare_attachments, read_attachment


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'docs').mkdir()
        self.payload = b'Customer export\x00\xff\xfe\r\nOriginal bytes.\n'
        (self.root / 'docs' / 'brief.bin').write_bytes(self.payload)
        self.row = {'id': 'a-001', 'contact_id': 'c-001', 'filename': 'Brief.bin', 'path': 'docs/brief.bin'}

    def tearDown(self):
        self.temp.cleanup()

    def test_binary_bytes_name_size_and_digest(self):
        result = read_attachment(self.root, 'docs/brief.bin')
        self.assertEqual(result, {'data': self.payload, 'size': len(self.payload),
                                 'source_path': 'docs/brief.bin',
                                 'sha256': hashlib.sha256(self.payload).hexdigest()})

    def test_empty_file_allowed(self):
        (self.root / 'empty').write_bytes(b'')
        self.assertEqual(read_attachment(self.root, 'empty')['size'], 0)

    def test_missing_file(self):
        with self.assertRaises(AttachmentError):
            read_attachment(self.root, 'missing')

    def test_path_forms(self):
        for name in ('../brief', '/tmp/brief', './docs/brief.bin', 'docs//brief.bin',
                     'docs/../brief', 'C:/brief', 'docs\\brief', 'docs/brief\x00', ''):
            with self.subTest(path=name), self.assertRaises(AttachmentError):
                read_attachment(self.root, name)

    def test_symlink_final(self):
        (self.root / 'link').symlink_to(self.root / 'docs' / 'brief.bin')
        with self.assertRaises(AttachmentError):
            read_attachment(self.root, 'link')

    def test_symlink_directory(self):
        (self.root / 'alias').symlink_to(self.root / 'docs', target_is_directory=True)
        with self.assertRaises(AttachmentError):
            read_attachment(self.root, 'alias/brief.bin')

    def test_symlink_root(self):
        with tempfile.TemporaryDirectory() as other:
            link = Path(other) / 'alias'
            link.symlink_to(self.root, target_is_directory=True)
            with self.assertRaises(AttachmentError):
                read_attachment(link, 'docs/brief.bin')

    def test_directory_is_not_an_attachment(self):
        with self.assertRaises(AttachmentError):
            read_attachment(self.root, 'docs')

    def test_fifo_is_rejected_without_waiting_for_a_writer(self):
        os.mkfifo(self.root / 'pipe')
        with self.assertRaises(AttachmentError):
            read_attachment(self.root, 'pipe')

    def test_exact_file_limit_and_oversized(self):
        self.assertEqual(read_attachment(self.root, 'docs/brief.bin', max_bytes=len(self.payload))['data'], self.payload)
        with self.assertRaises(AttachmentError):
            read_attachment(self.root, 'docs/brief.bin', max_bytes=len(self.payload)-1)

    def test_numeric_limits_are_strict(self):
        for limit in (0, -1, True, 1.2, '20'):
            with self.subTest(limit=limit), self.assertRaises(AttachmentError):
                read_attachment(self.root, 'docs/brief.bin', max_bytes=limit)
        for field in ('max_total_bytes', 'max_rows'):
            with self.subTest(field=field), self.assertRaises(AttachmentError):
                prepare_attachments(self.root, [], [], **{field: False})

    def test_file_replaced_during_read(self):
        real_read = os.read
        fired = False
        def replace(fd, size):
            nonlocal fired
            data = real_read(fd, size)
            if not fired:
                fired = True
                replacement = self.root / 'replacement'
                replacement.write_bytes(self.payload)
                replacement.replace(self.root / 'docs' / 'brief.bin')
            return data
        with patch('attachment_intake.os.read', replace), self.assertRaises(AttachmentError):
            read_attachment(self.root, 'docs/brief.bin')

    def test_file_grows_during_read(self):
        real_read = os.read
        fired = False
        def grow(fd, size):
            nonlocal fired
            data = real_read(fd, size)
            if not fired:
                fired = True
                with (self.root / 'docs' / 'brief.bin').open('ab') as stream:
                    stream.write(b'more')
            return data
        with patch('attachment_intake.os.read', grow), self.assertRaises(AttachmentError):
            read_attachment(self.root, 'docs/brief.bin')

    def test_same_size_rewrite_during_read(self):
        real_read = os.read
        fired = False
        def rewrite(fd, size):
            nonlocal fired
            data = real_read(fd, size)
            if not fired:
                fired = True
                target = self.root / 'docs' / 'brief.bin'
                old = target.stat()
                target.write_bytes(b'x' * len(self.payload))
                os.utime(target, ns=(old.st_atime_ns, old.st_mtime_ns + 1_000_000))
            return data
        with patch('attachment_intake.os.read', rewrite), self.assertRaises(AttachmentError):
            read_attachment(self.root, 'docs/brief.bin')

    def test_duplicate_id_same_bytes_and_metadata_coalesces(self):
        rows = prepare_attachments(self.root, [self.row, self.row.copy()], ['c-001'])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], 'a-001')
        self.assertEqual(rows[0]['contact_id'], 'c-001')
        self.assertEqual(rows[0]['filename'], 'Brief.bin')

    def test_differing_duplicate_metadata_conflicts(self):
        changed = dict(self.row, filename='New name')
        with self.assertRaises(AttachmentError):
            prepare_attachments(self.root, [self.row, changed], ['c-001'])

    def test_duplicate_id_with_different_bytes_conflicts(self):
        (self.root / 'different').write_bytes(b'different bytes')
        changed = dict(self.row, path='different')
        with self.assertRaises(AttachmentError):
            prepare_attachments(self.root, [self.row, changed], ['c-001'])

    def test_relationship_must_resolve_before_file_read(self):
        with patch('attachment_intake.read_attachment') as read:
            with self.assertRaises(AttachmentError):
                prepare_attachments(self.root, [self.row], ['c-002'])
            read.assert_not_called()

    def test_identifier_strings_preserved_and_not_trimmed(self):
        for field in ('id', 'contact_id'):
            with self.subTest(field=field), self.assertRaises(AttachmentError):
                prepare_attachments(self.root, [dict(self.row, **{field: ' c-001 '})], ['c-001'])
        for contacts in ('c-001', [' c-001 '], [123], [{}]):
            with self.subTest(contacts=contacts), self.assertRaises(AttachmentError):
                prepare_attachments(self.root, [self.row], contacts)

    def test_missing_fields_and_wrong_row_type(self):
        for field in self.row:
            row = self.row.copy()
            del row[field]
            with self.subTest(field=field), self.assertRaises(AttachmentError):
                prepare_attachments(self.root, [row], ['c-001'])
        with self.assertRaises(AttachmentError):
            prepare_attachments(self.root, [None], ['c-001'])

    def test_total_read_budget_includes_duplicates(self):
        with self.assertRaises(AttachmentError):
            prepare_attachments(self.root, [self.row, self.row], ['c-001'], max_total_bytes=len(self.payload))
        self.assertEqual(len(prepare_attachments(self.root, [self.row], ['c-001'], max_total_bytes=len(self.payload))), 1)

    def test_zero_length_after_exact_budget(self):
        (self.root / 'empty').write_bytes(b'')
        empty = dict(self.row, id='empty', path='empty')
        result = prepare_attachments(self.root, [self.row, empty], ['c-001'], max_total_bytes=len(self.payload))
        self.assertEqual(len(result), 2)

    def test_row_count_bounds_even_empty_files(self):
        (self.root / 'empty').write_bytes(b'')
        row = dict(self.row, path='empty')
        with self.assertRaises(AttachmentError):
            prepare_attachments(self.root, [row, row], ['c-001'], max_rows=1)

    def test_descriptors_closed_after_success_and_error(self):
        proc = Path('/proc/self/fd')
        if not proc.exists():
            self.skipTest('descriptor count requires procfs')
        before = len(list(proc.iterdir()))
        for _ in range(8):
            read_attachment(self.root, 'docs/brief.bin')
            with self.assertRaises(AttachmentError):
                read_attachment(self.root, 'docs/missing')
        self.assertEqual(len(list(proc.iterdir())), before)

    def test_real_sqlite_transfer_reopen_and_relationship(self):
        rows = prepare_attachments(self.root, [self.row, self.row], ['c-001'])
        destination = self.root / 'destination.sqlite'
        with sqlite3.connect(destination) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.executescript('CREATE TABLE contacts(id TEXT PRIMARY KEY,name TEXT);'
                             'CREATE TABLE tasks(id TEXT PRIMARY KEY,contact_id TEXT REFERENCES contacts(id),status TEXT);'
                             'CREATE TABLE attachments(id TEXT PRIMARY KEY,contact_id TEXT REFERENCES contacts(id),data BLOB,sha256 TEXT);')
            db.execute('INSERT INTO contacts VALUES(?,?)', ('c-001', 'Example customer'))
            db.execute('INSERT INTO tasks VALUES(?,?,?)', ('t-001', 'c-001', 'open'))
            for row in rows:
                db.execute('INSERT INTO attachments VALUES(?,?,?,?)',
                           (row['id'], row['contact_id'], row['data'], row['sha256']))
        with sqlite3.connect(destination) as db:
            got = db.execute('SELECT a.data,a.sha256,c.name,t.status FROM attachments a '
                             'JOIN contacts c ON c.id=a.contact_id JOIN tasks t ON t.contact_id=c.id').fetchone()
            self.assertEqual(got, (self.payload, hashlib.sha256(self.payload).hexdigest(), 'Example customer', 'open'))
            db.execute('UPDATE tasks SET status=? WHERE id=?', ('done', 't-001'))
        with sqlite3.connect(destination) as db:
            self.assertEqual(db.execute('SELECT status FROM tasks').fetchone()[0], 'done')

    def test_real_sqlite_failed_cutover_has_no_partial_rows(self):
        rows = prepare_attachments(self.root, [self.row], ['c-001'])
        with sqlite3.connect(':memory:') as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.executescript('CREATE TABLE contacts(id TEXT PRIMARY KEY);'
                             'CREATE TABLE attachments(id TEXT PRIMARY KEY,contact_id TEXT REFERENCES contacts(id),data BLOB);')
            try:
                with db:
                    db.execute('INSERT INTO contacts VALUES(?)', ('c-001',))
                    row = rows[0]
                    db.execute('INSERT INTO attachments VALUES(?,?,?)', (row['id'], row['contact_id'], row['data']))
                    db.execute('INSERT INTO attachments VALUES(?,?,?)', ('bad', 'missing-contact', b'x'))
            except sqlite3.IntegrityError:
                pass
            else:
                self.fail('foreign-key cutover should have rolled back')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM contacts').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM attachments').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
