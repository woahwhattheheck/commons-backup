#!/usr/bin/env python3
"""Source-transform contracts; test fixture text is not a solver benchmark."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from apply_prefix import EDITS, ORIGINAL, REPLACEMENT, apply


def source():
    return '\n// peer header\n' + '\n// peer region\n'.join(before for before, _ in EDITS) + '\n// peer footer\n'


class ApplyTests(unittest.TestCase):
    def test_three_edits(self):
        text = source()
        actual = apply(text)
        for old, new in EDITS:
            self.assertNotIn(old, actual)
            self.assertEqual(actual.count(new), 1)
        for old, new in reversed(EDITS):
            actual = actual.replace(new, old)
        self.assertEqual(actual, text)

    def test_idempotent(self):
        actual = apply(source())
        self.assertEqual(apply(actual), actual)

    def test_unrelated_regions_are_preserved(self):
        text = source().replace('// peer region', '// another peer\nint extra = 71;')
        result = apply(text)
        self.assertEqual(result.count('int extra = 71;'), 2)
        self.assertTrue(result.endswith('// peer footer\n'))
        self.assertTrue(result.startswith('\n// peer header\n'))

    def test_independent_changes_commute(self):
        edit = lambda text: text.replace('// peer header', '// cache change\n// peer header')
        self.assertEqual(apply(edit(source())), edit(apply(source())))

    def test_each_missing_region_rejected(self):
        for old, _ in EDITS:
            with self.subTest(region=old[:45]):
                with self.assertRaises(ValueError):
                    apply(source().replace(old, ''))

    def test_each_duplicated_region_rejected(self):
        for old, _ in EDITS:
            with self.subTest(region=old[:45]):
                with self.assertRaises(ValueError):
                    apply(source() + old)

    def test_each_partial_state_rejected(self):
        for mask in range(1, 7):
            text = source()
            for bit, (old, new) in enumerate(EDITS):
                if mask & (1 << bit):
                    text = text.replace(old, new)
            with self.subTest(mask=mask):
                with self.assertRaises(ValueError):
                    apply(text)

    def test_unknown_method_change_rejected(self):
        with self.assertRaises(ValueError):
            apply(source().replace('demands[d].volume[t] <= 0', 'demands[d].volume[t] < 0'))

    def test_call_limits_match_existing_consumers(self):
        result = apply(source())
        self.assertIn('contributors(t, edge, d, 4);', result)
        self.assertIn('contributors(t, e, -1, 32);', result)
        self.assertIn('std::numeric_limits<std::size_t>::max()', result)
        self.assertIn('a.second < b.second', result)

    def test_cli_writes_new_output_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            src, dst = root / 'main.cpp', root / 'new.cpp'
            src.write_text(source())
            command = [sys.executable, str(Path(__file__).with_name('apply_prefix.py')), str(src), str(dst)]
            result = subprocess.run(command, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)['changed'])
            self.assertEqual(src.read_text(), source())
            self.assertEqual(dst.read_text(), apply(source()))
            result = subprocess.run(command, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(dst.read_text(), apply(source()))

    def test_native_preparation_rejects_already_changed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            src, dst = root / 'main.cpp', root / 'generated'
            src.write_text(apply(source()))
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('prepare_native.py')),
                                     str(src), str(dst)], capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(dst.exists())


if __name__ == '__main__':
    unittest.main()
