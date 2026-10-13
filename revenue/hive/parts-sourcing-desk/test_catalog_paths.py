"""Cross-platform source labels remain basename metadata with exact byte hashes."""
import hashlib
import json
import unittest

from catalog_file import parse_bytes
from catalog_intake import PROVENANCE_LABEL, prepare_import
from test_catalog_intake import row


class CatalogPathTests(unittest.TestCase):
    def test_windows_drive_and_unc_csv_names(self):
        raw = b'part\n0007\n'
        for name in (r'C:\vendor\catalog.csv', r'\\fileserver\share\catalog.csv'):
            with self.subTest(name=name):
                parsed = parse_bytes(raw, name)
                self.assertEqual(parsed.source['filename'], 'catalog.csv')
                self.assertEqual(parsed.source['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(parsed.records[0]['fields']['part'], '0007')

    def test_posix_mixed_and_relative_names(self):
        raw = b'part\n0007\n'
        for name in ('/cloud/vendor/catalog.csv', r'C:\vendor/subdir/catalog.csv', 'catalog.csv'):
            with self.subTest(name=name):
                self.assertEqual(parse_bytes(raw, name).source['filename'], 'catalog.csv')

    def test_windows_json_extension_and_pointer(self):
        raw = b'[{"part":"0007","price":32.45}]'
        parsed = parse_bytes(raw, r'D:\exports\supplier.JSON')
        self.assertEqual(parsed.source['format'], 'json')
        self.assertEqual(parsed.source['filename'], 'supplier.JSON')
        self.assertEqual(parsed.records[0]['location']['json_pointer'], '/0')
        self.assertEqual(parsed.records[0]['fields']['price'], '32.45')

    def test_canonical_note_and_retry_identity_do_not_retain_directory_labels(self):
        raw = json.dumps([row()]).encode()
        first = prepare_import(parse_bytes(raw, r'C:\vendor\supplier.json'))
        second = prepare_import(parse_bytes(raw, '/cloud/vendor/supplier.json'))
        self.assertEqual(first['payload'], second['payload'])
        note = first['payload']['items'][0]['source_note']
        evidence = json.loads(note.split(PROVENANCE_LABEL, 1)[1])
        self.assertEqual(evidence['filename'], 'supplier.json')
        self.assertNotIn('vendor', note)
        self.assertEqual(evidence['sha256'], hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    unittest.main()
