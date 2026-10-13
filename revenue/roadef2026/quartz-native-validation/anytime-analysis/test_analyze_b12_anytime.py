"""Narrow reader boundary tests; the full original B12 archive is exercised separately."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import analyze_b12_anytime as reader


class EvidenceReaderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'evidence.zip'

    def make_archive(self, entries, data=b'original\n'):
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('payload', data)
            archive.writestr('manifest.json', json.dumps({'files': entries}))
        return reader.sha(self.path.read_bytes())

    def row(self, data=b'original\n'):
        return {'path': 'payload', 'bytes': len(data), 'sha256': reader.sha(data)}

    def test_exact_payload_is_read_without_execution(self):
        expected = self.make_archive([self.row()])
        archive, receipt = reader.verify_archive(self.path, expected, 'manifest.json')
        with archive:
            self.assertEqual(archive.read('payload'), b'original\n')
        self.assertEqual(receipt['verified_payload_count'], 1)

    def test_changed_outer_archive_is_rejected(self):
        self.make_archive([self.row()])
        with self.assertRaisesRegex(ValueError, 'Archive digest mismatch'):
            reader.verify_archive(self.path, '0' * 64, 'manifest.json')

    def test_changed_payload_digest_is_rejected(self):
        row = self.row(); row['sha256'] = '0' * 64
        expected = self.make_archive([row])
        with self.assertRaisesRegex(ValueError, 'Manifest mismatch'):
            reader.verify_archive(self.path, expected, 'manifest.json')

    def test_changed_payload_size_is_rejected(self):
        row = self.row(); row['bytes'] += 1
        expected = self.make_archive([row])
        with self.assertRaisesRegex(ValueError, 'Manifest mismatch'):
            reader.verify_archive(self.path, expected, 'manifest.json')

    def test_missing_payload_is_rejected(self):
        row = self.row(); row['path'] = 'absent'
        expected = self.make_archive([row])
        with self.assertRaises(KeyError):
            reader.verify_archive(self.path, expected, 'manifest.json')

    def test_duplicate_manifest_identity_is_rejected(self):
        expected = self.make_archive([self.row(), self.row()])
        with self.assertRaisesRegex(ValueError, 'Duplicate manifest entry'):
            reader.verify_archive(self.path, expected, 'manifest.json')

    def test_complete_lane_log_is_retained(self):
        log = b'Completed 336 improving moves / 30116707 attempts; MLU 0.629742; elapsed 287.179s\n'
        result = reader.log_summary(log)
        self.assertEqual((result['accepted_moves'], result['attempts']), (336, 30116707))
        self.assertEqual(result['logged_elapsed_seconds'], 287.179)
        self.assertEqual(result['log_sha256'], hashlib.sha256(log).hexdigest())

    def test_incomplete_lane_log_is_not_a_completion(self):
        with self.assertRaisesRegex(ValueError, 'Missing completed lane record'):
            reader.log_summary(b'Loaded 1263 nodes; preparing routes\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
