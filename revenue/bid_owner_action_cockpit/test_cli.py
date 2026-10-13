from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from .cli import _read_regular, _write_exclusive
from .core import ValidationError


class CliIoTests(unittest.TestCase):
    def test_write_exclusive_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "out.json"
            _write_exclusive(p, b"first")
            with self.assertRaises(ValidationError):
                _write_exclusive(p, b"second")
            self.assertEqual(b"first", p.read_bytes())

    def test_write_exclusive_refuses_symlink_target(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "target"
            target.write_bytes(b"keep")
            link = Path(td) / "link"
            os.symlink(target, link)
            with self.assertRaises(ValidationError):
                _write_exclusive(link, b"replace")
            self.assertEqual(b"keep", target.read_bytes())

    def test_read_regular_refuses_symlink(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "target"
            target.write_bytes(b"{}")
            link = Path(td) / "link"
            os.symlink(target, link)
            with self.assertRaises(ValidationError):
                _read_regular(link)

    def test_read_regular_refuses_directory(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValidationError):
                _read_regular(td)

    def test_read_regular_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "in.json"
            p.write_bytes(b'{"ok":true}')
            self.assertEqual(b'{"ok":true}', _read_regular(p))


if __name__ == "__main__":
    unittest.main()
