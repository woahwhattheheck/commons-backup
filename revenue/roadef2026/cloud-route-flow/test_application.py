#!/usr/bin/env python3
"""Source-only contract checks for the routeFlow application utility."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import apply_route_flow as a


class ApplicationTests(unittest.TestCase):
    def test_exact_one_method(self):
        self.assertEqual(a.apply_bytes(b'before\n' + a.ORIGINAL + b'after\n'),
                         b'before\n' + a.CANDIDATE + b'after\n')

    def test_disjoint_peer_changes_survive(self):
        src = b'// peer distance/cache changes\n' + a.ORIGINAL + b'\n// peer comparator changes\n'
        out = a.apply_bytes(src)
        self.assertEqual(out.replace(a.CANDIDATE, a.ORIGINAL), src)

    def test_unknown_and_duplicate_methods_rejected(self):
        for src in (b'empty', a.ORIGINAL + a.ORIGINAL, a.CANDIDATE,
                    a.ORIGINAL.replace(b'flow.clear()', b'flow.resize(0)')):
            with self.subTest(src=hashlib.sha256(src).hexdigest()):
                with self.assertRaises(ValueError):
                    a.apply_bytes(src)

    def test_output_is_new_and_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'new.cpp'
            a.write_new(out, a.CANDIDATE)
            self.assertEqual(out.read_bytes(), a.CANDIDATE)
            self.assertEqual(list(Path(directory).iterdir()), [out])

    def test_existing_output_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'source.cpp'
            out.write_bytes(a.ORIGINAL)
            with self.assertRaises(FileExistsError):
                a.write_new(out, a.CANDIDATE)
            self.assertEqual(out.read_bytes(), a.ORIGINAL)
            self.assertEqual(list(Path(directory).iterdir()), [out])

    def test_aliases_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source.cpp'; source.write_bytes(a.ORIGINAL)
            for name, link in (('symbolic', lambda p: p.symlink_to(source)),
                               ('hard', lambda p: p.hardlink_to(source))):
                out = root / name; link(out)
                with self.assertRaises(FileExistsError):
                    a.write_new(out, a.CANDIDATE)
                self.assertEqual(source.read_bytes(), a.ORIGINAL)

    def test_fsync_failure_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(a.os, 'fsync', side_effect=OSError('injected')):
                with self.assertRaises(OSError):
                    a.write_new(root / 'output.cpp', a.CANDIDATE)
            self.assertEqual(list(root.iterdir()), [])

    def test_cli_preserves_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source.cpp'; out = root / 'candidate.cpp'
            source.write_bytes(a.ORIGINAL)
            run = subprocess.run([sys.executable, a.__file__, str(source), str(out)], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(source.read_bytes(), a.ORIGINAL)
            self.assertEqual(out.read_bytes(), a.CANDIDATE)


if __name__ == '__main__':
    unittest.main(verbosity=2)
