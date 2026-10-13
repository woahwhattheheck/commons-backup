from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from .cli import _load_json, compile_command
from .engine import CloseBoardError, INPUT_SCHEMA, ZERO_SHA256, canonical_bounty_key, compile_board, mint_receipt, validate_input, verify_bundle
from .test_support import *  # test fixture helpers

class CliTests(unittest.TestCase):
    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            p.write_text('{"a":1,"a":2}')
            with self.assertRaises(CloseBoardError):
                _load_json(p)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            p.write_text('{"a":NaN}')
            with self.assertRaises(CloseBoardError):
                _load_json(p)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW not available")
    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "target.json"; target.write_text('{}')
            link = Path(td) / "link.json"; link.symlink_to(target)
            with self.assertRaises(OSError):
                _load_json(link)

    def test_compile_is_create_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            inp = td / "input.json"
            inp.write_text(json.dumps(make_doc([make_bounty([])]), sort_keys=True))
            out = td / "out"
            first = compile_command(inp, out)
            self.assertEqual(first["status"], "OWNER_REVIEW_ONLY")
            with self.assertRaises(FileExistsError):
                compile_command(inp, out)

    def test_markdown_uses_integer_minor_rendering(self):
        doc = make_doc([make_bounty([])])
        out, md, receipt = compile_board(doc, AS_OF)
        self.assertIn("USD 90.00", md)
        verify_bundle(doc, out, md, receipt)
