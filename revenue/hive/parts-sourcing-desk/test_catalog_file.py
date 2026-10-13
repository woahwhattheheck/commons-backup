import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from catalog_file import CatalogFileError, main, map_fields, parse_bytes, read_catalog


class CatalogFileTests(unittest.TestCase):
    def test_csv_source_hash_and_location(self):
        raw = b'part,notes,price\r\nDEMO-7,"quoted, note",32.45\r\n'
        parsed = parse_bytes(raw, '/private/folder/catalog.csv')
        self.assertEqual(parsed.source['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(parsed.source['filename'], 'catalog.csv')
        self.assertEqual(parsed.source['size_bytes'], len(raw))
        self.assertEqual(parsed.records[0]['location'], {'line_start': 2, 'line_end': 2})
        self.assertEqual(parsed.records[0]['fields']['notes'], 'quoted, note')
        self.assertEqual(parsed.records[0]['fields']['price'], '32.45')

    def test_multiline_and_blank_physical_lines(self):
        parsed = parse_bytes(b'part,notes\nA,"line one\nline two"\n\nB,third\n', 'x.csv')
        self.assertEqual(parsed.records[0]['location'], {'line_start': 2, 'line_end': 3})
        self.assertEqual(parsed.records[1]['location'], {'line_start': 5, 'line_end': 5})
        self.assertEqual(parsed.records[0]['fields']['notes'], 'line one\nline two')

    def test_utf8_bom_and_unicode(self):
        raw = bytes([239,187,191]) + 'part,notes\nDEMO-7,café\n'.encode()
        parsed = parse_bytes(raw, 'x.csv')
        self.assertEqual(parsed.records[0]['fields']['notes'], 'café')
        self.assertEqual(parsed.source['sha256'], hashlib.sha256(raw).hexdigest())

    def test_duplicate_blank_or_whitespace_headers(self):
        for raw in (b'a,a\n1,2\n', b'a,\n1,2\n', b' a,b\n1,2\n'):
            with self.subTest(raw=raw), self.assertRaises(CatalogFileError):
                parse_bytes(raw, 'x.csv')

    def test_short_and_long_rows_have_line_errors(self):
        for raw in (b'a,b\n1\n', b'a,b\n1,2,3\n'):
            with self.subTest(raw=raw), self.assertRaisesRegex(CatalogFileError, 'lines 2-2'):
                parse_bytes(raw, 'x.csv')

    def test_unclosed_csv_quotes(self):
        with self.assertRaisesRegex(CatalogFileError, 'CSV near line'):
            parse_bytes(b'a,b\n1,"unterminated', 'x.csv')

    def test_no_empty_inputs(self):
        for raw, name in ((b'', 'x.csv'), (b'a,b\n', 'x.csv'), (b'[]', 'x.json')):
            with self.subTest(raw=raw), self.assertRaises(CatalogFileError):
                parse_bytes(raw, name)

    def test_invalid_encoding_nul_and_format(self):
        for raw, name in ((bytes([97,255]), 'x.csv'), (bytes([97,0]), 'x.csv'), (b'a\nb', 'x.xlsx')):
            with self.subTest(name=name), self.assertRaises(CatalogFileError):
                parse_bytes(raw, name)

    def test_byte_and_row_limits(self):
        with patch('catalog_file.MAX_BYTES', 3), self.assertRaises(CatalogFileError):
            parse_bytes(b'a\nb\nc\n', 'x.csv')
        with patch('catalog_file.MAX_ROWS', 1):
            for raw, name in ((b'a\nb\nc\n', 'x.csv'), (b'[{"a":1},{"a":2}]', 'x.json')):
                with self.subTest(name=name), self.assertRaises(CatalogFileError):
                    parse_bytes(raw, name)

    def test_json_decimal_and_leading_zero_part(self):
        parsed = parse_bytes(b'[{"part":"0007","price":12.30,"aliases":["A","B"]}]', 'x.json')
        self.assertEqual(parsed.records[0]['fields'], {'part': '0007', 'price': '12.30', 'aliases': ['A', 'B']})
        self.assertEqual(parsed.records[0]['location'], {'json_pointer': '/0'})

    def test_json_rows_container_pointer(self):
        parsed = parse_bytes(b'{"rows":[{"part":"A"}]}', 'x.json')
        self.assertEqual(parsed.records[0]['location']['json_pointer'], '/rows/0')

    def test_json_duplicate_keys_and_nonfinite(self):
        for raw in (b'[{"a":1,"a":2}]', b'[{"a":NaN}]', b'[{"a":Infinity}]', b'[{"a":-Infinity}]'):
            with self.subTest(raw=raw), self.assertRaises(CatalogFileError):
                parse_bytes(raw, 'x.json')

    def test_json_wrong_shapes_and_extra_data(self):
        for raw in (b'[1]', b'[{}]', b'null', b'"text"', b'{"rows":{}}', b'{"rows":[{"a":1}],"other":2}'):
            with self.subTest(raw=raw), self.assertRaises(CatalogFileError):
                parse_bytes(raw, 'x.json')

    def test_json_syntax_location(self):
        with self.assertRaisesRegex(CatalogFileError, 'line 2, column'):
            parse_bytes(b'[\n{"part":}]', 'x.json')

    def test_mapping_preserves_fields_and_provenance(self):
        parsed = parse_bytes(b'SKU,amount,note\n007,12.30,observed\n', 'x.csv')
        row = map_fields(parsed, {'SKU': 'part', 'amount': 'unit_price'})[0]
        self.assertEqual(row['fields'], {'part': '007', 'unit_price': '12.30', 'note': 'observed'})
        self.assertEqual(row['provenance']['record'], 1)
        self.assertEqual(row['provenance']['line_start'], 2)
        self.assertEqual(row['provenance']['sha256'], parsed.source['sha256'])

    def test_mapping_collision_never_drops_data(self):
        parsed = parse_bytes(b'a,b\n1,2\n', 'x.csv')
        for mapping in ({'a': 'b'}, {'a': 'x', 'b': 'x'}):
            with self.subTest(mapping=mapping), self.assertRaisesRegex(CatalogFileError, 'collides'):
                map_fields(parsed, mapping)

    def test_mapping_typo_visible(self):
        parsed = parse_bytes(b'part\nA\n', 'x.csv')
        with self.assertRaisesRegex(CatalogFileError, 'not found'):
            map_fields(parsed, {'sku': 'part'})
        for mapping in ({'part': ''}, {'part': 1}, ['part'], []):
            with self.subTest(mapping=mapping), self.assertRaises(CatalogFileError):
                map_fields(parsed, mapping)

    def test_defaults_preserve_existing_values(self):
        parsed = parse_bytes(b'part,supplier\n007,\n008,Existing\n', 'x.csv')
        rows = map_fields(parsed, defaults={'supplier': 'Supplied default', 'currency': 'USD'})
        self.assertEqual(rows[0]['fields']['supplier'], 'Supplied default')
        self.assertEqual(rows[1]['fields']['supplier'], 'Existing')
        self.assertEqual(rows[1]['fields']['currency'], 'USD')
        self.assertEqual(parsed.records[0]['fields']['supplier'], '')

    def test_single_snapshot_preview_and_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'source.csv'
            path.write_bytes(b'part\nA\n')
            out = Path(tmp) / 'preview.json'
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('no repeated reads')):
                parsed = read_catalog(path)
                self.assertEqual(main([str(path), '--output', str(out)]), 0)
            doc = json.loads(out.read_text())
            self.assertFalse(doc['applied'])
            self.assertEqual(doc['supplier_contact'], 'not_performed')
            self.assertEqual(doc['source'], parsed.source)
            with self.assertRaises(SystemExit) as exc:
                main([str(path), '--output', str(out)])
            self.assertEqual(exc.exception.code, 2)
            self.assertEqual(json.loads(out.read_text()), doc)


if __name__ == '__main__':
    unittest.main()
