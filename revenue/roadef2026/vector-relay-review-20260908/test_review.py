"""Small tests of the reviewer only; no solver or official checker execution."""
import io
import json
import unittest
import zipfile
from decimal import Decimal
from review_artifact import compare_vectors, read_json, verify_manifest, digest

class ReviewTests(unittest.TestCase):
    def test_scientific_submicro_first_difference(self):
        x = compare_vectors([Decimal('1'), Decimal('2.1e-8')], [Decimal('1'), Decimal('2.0e-8')])
        self.assertEqual(x['winner'], 'new')
        self.assertEqual(x['first_difference']['rank'], 2)
    def test_lexicographic_not_pareto(self):
        x = compare_vectors([Decimal('0.5'), Decimal('0.2')], [Decimal('0.4'), Decimal('0.3')])
        self.assertEqual((x['winner'], x['worsened_ranks']), ('new', 1))
    def test_tie(self):
        self.assertIsNone(compare_vectors([Decimal('0.20')], [Decimal('0.2')])['first_difference'])
    def test_length_rejection(self):
        with self.assertRaises(ValueError):
            compare_vectors([Decimal('1')], [])
    def test_duplicate_json_key_rejection(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z: z.writestr('x', '{"x":1,"x":2}')
        with zipfile.ZipFile(data) as z, self.assertRaises(ValueError): read_json(z, 'x')
    def test_nonfinite_json_rejection(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z: z.writestr('x', '{"x":NaN}')
        with zipfile.ZipFile(data) as z, self.assertRaises(ValueError): read_json(z, 'x')
    def test_manifest_mismatch_rejection(self):
        data = io.BytesIO()
        manifest = {'files':[{'path':'x', 'bytes':3, 'sha256':digest(b'abc')}]}
        with zipfile.ZipFile(data, 'w') as z:
            z.writestr('x', b'abd')
            z.writestr('ARTIFACT-MANIFEST.json', json.dumps(manifest))
        with zipfile.ZipFile(data) as z, self.assertRaises(ValueError): verify_manifest(z)
    def test_manifest_extra_file_rejection(self):
        data = io.BytesIO()
        manifest = {'files':[{'path':'x', 'bytes':3, 'sha256':digest(b'abc')}]}
        with zipfile.ZipFile(data, 'w') as z:
            z.writestr('x', b'abc'); z.writestr('extra', b'')
            z.writestr('ARTIFACT-MANIFEST.json', json.dumps(manifest))
        with zipfile.ZipFile(data) as z, self.assertRaises(ValueError): verify_manifest(z)

if __name__ == '__main__': unittest.main(verbosity=2)
