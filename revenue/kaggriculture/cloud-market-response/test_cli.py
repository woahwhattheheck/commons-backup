# SPDX-License-Identifier: MIT
"""Exercise the actual CLI parser without starting a game or needing engine files."""
import argparse
import ast
import contextlib
import io
from pathlib import Path
import unittest

class CliTests(unittest.TestCase):
    def parse(self, extra):
        source=Path(__file__).with_name('measure.py')
        entry=ast.parse(source.read_text()).body[-1]
        assert isinstance(entry,ast.If)
        # Execute the parser construction exactly as shipped; omit parse/run.
        setup=ast.Module(body=entry.body[:-2],type_ignores=[])
        namespace={'argparse':argparse,'Path':Path}
        exec(compile(setup,str(source),'exec'),namespace)
        return namespace['parser'].parse_args(['--seed','9840001','--arm','response',
            '--opponent','arlene','--engine-dir','.','--output','.']+extra)
    def test_omitted_seat_defaults_zero(self):
        self.assertEqual(self.parse([]).seat,0)
    def test_explicit_seat_one_preserved(self):
        self.assertEqual(self.parse(['--seat','1']).seat,1)
    def test_invalid_seat_still_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:self.parse(['--seat','2'])
        self.assertEqual(raised.exception.code,2)

if __name__=='__main__':unittest.main()
