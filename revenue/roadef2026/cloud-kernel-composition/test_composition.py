# SPDX-License-Identifier: MIT
"""Offline composition boundary tests; native joined evidence is separate."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from compose_kernels import compose, digest

BASE = b''.join(f'line_{i}: original\n'.encode() for i in range(40))


class CompositionTests(unittest.TestCase):
    def test_identity(self):
        value, report = compose(BASE, {})
        self.assertEqual(value, BASE)
        self.assertEqual(len(report['merge_orders']), 1)

    def test_three_disjoint_donors_all_orders(self):
        donors = {str(i): BASE.replace(f'line_{i}: original'.encode(), f'line_{i}: changed'.encode())
                  for i in (4, 18, 32)}
        value, report = compose(BASE, donors)
        self.assertEqual(len(report['merge_orders']), 6)
        self.assertEqual(value.count(b'changed'), 3)
        self.assertEqual({r['sha256'] for r in report['merge_orders']}, {digest(value)})

    def test_identical_deltas_deduplicate(self):
        donor = BASE.replace(b'line_18: original', b'line_18: changed')
        value, report = compose(BASE, {'a': donor, 'b': donor})
        self.assertEqual(value, donor)
        self.assertEqual(len(report['merge_orders']), 2)

    def test_conflict_is_not_output(self):
        with self.assertRaisesRegex(ValueError, 'conflict/error'):
            compose(BASE, {'a': BASE.replace(b'line_18: original', b'line_18: first'),
                           'b': BASE.replace(b'line_18: original', b'line_18: second')})

    def test_sources_are_unchanged(self):
        donors = {'a': BASE.replace(b'line_18: original', b'line_18: changed')}
        before = dict(donors)
        compose(BASE, donors)
        self.assertEqual(donors, before)

    def test_invalid_text_preserved_as_failure(self):
        with self.assertRaises(UnicodeDecodeError):
            compose(BASE, {'a': b'\xff'})

    def test_permutation_bound(self):
        with self.assertRaisesRegex(ValueError, 'four donors'):
            compose(BASE, {str(i): BASE for i in range(5)})

    def test_existing_output_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); source = root/'base.cpp'; source.write_bytes(BASE)
            out = root/'out'; out.mkdir(); sentinel = out/'main.cpp'; sentinel.write_bytes(b'retained')
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('compose_kernels.py')),
                                     '--baseline', str(source), '--out', str(out)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_bytes(), b'retained')

    def test_cli_exact_source_and_report(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); source = root/'base.cpp'; source.write_bytes(BASE)
            donor = root/'donor.cpp'; donor.write_bytes(BASE.replace(b'line_18: original', b'line_18: changed'))
            out = root/'out'
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('compose_kernels.py')),
                                     '--baseline', str(source), '--donor', 'one='+str(donor),
                                     '--out', str(out)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((out/'main.cpp').read_bytes(), donor.read_bytes())
            self.assertEqual(json.loads((out/'COMPOSITION.json').read_text())['merged_sha256'], digest(donor.read_bytes()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
