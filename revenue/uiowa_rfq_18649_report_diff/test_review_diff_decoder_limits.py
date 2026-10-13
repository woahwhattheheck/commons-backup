#!/usr/bin/env python3
"""Decoder-limit regression tests; real parser, compiler, and CLI, no mocks.

Additional coverage by ZZ-RELAY / GPT-6 Astra Pro for QUARTZ's PR #16191.
The regression applies to Python versions with integer-string conversion limits.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import review_diff as diff
from synthetic_demo import example_reports


@unittest.skipUnless(hasattr(sys, "get_int_max_str_digits"),
                     "interpreter has no integer-string conversion limit")
class DecoderLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        previous_limit = sys.get_int_max_str_digits()
        sys.set_int_max_str_digits(4300)
        self.addCleanup(sys.set_int_max_str_digits, previous_limit)
        self.bad = self.root / "oversized-integer.json"
        self.bad.write_text('{"value":' + '1' * 5000 + '}', encoding="utf-8")
        self.before, self.after = example_reports()
        for name, value in (("before.json", self.before), ("after.json", self.after)):
            diff.write_new(self.root / name, diff.canonical_json_bytes(value))

    def run_cli(self, *args: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *(["-O"] if sys.flags.optimize else []),
             "-X", "int_max_str_digits=4300", str(Path(diff.__file__).resolve()),
             *map(str, args)],
            capture_output=True, text=True, timeout=15,
        )

    def test_library_maps_decoder_value_error_to_contract_error(self) -> None:
        self.assertLess(self.bad.stat().st_size, diff.MAX_INPUT_BYTES)
        with self.assertRaisesRegex(diff.ContractError, "JSON decoder rejected a value"):
            diff.load_json(self.bad)

    def test_compare_rejects_integer_limit_in_either_input_cleanly(self) -> None:
        good_before, good_after = self.root / "before.json", self.root / "after.json"
        original_bytes = (good_before.read_bytes(), good_after.read_bytes(), self.bad.read_bytes())
        for before, after in ((self.bad, good_after), (good_before, self.bad)):
            with self.subTest(invalid_before=before == self.bad):
                output = self.root / "must-not-exist.json"
                result = self.run_cli("compare", before, after, output)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("ERROR: ContractError:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(output.exists())
        self.assertEqual(original_bytes,
                         (good_before.read_bytes(), good_after.read_bytes(), self.bad.read_bytes()))

    def test_verify_rejects_integer_limit_delta_cleanly(self) -> None:
        result = self.run_cli("verify", self.root / "before.json", self.root / "after.json", self.bad)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("ERROR: ContractError:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("INTEGRITY_ONLY", result.stdout)

    def test_existing_strict_json_diagnostics_are_preserved(self) -> None:
        for raw, message in (('{"x":1,"x":2}', "duplicate JSON key"),
                             ('{"x":NaN}', "non-finite JSON token"),
                             ('{"x":Infinity}', "non-finite JSON token"),
                             ('{"x":', "invalid JSON")):
            with self.subTest(raw=raw):
                self.bad.write_text(raw, encoding="utf-8")
                with self.assertRaisesRegex(diff.ContractError, message):
                    diff.load_json(self.bad)

    def test_invalid_utf8_keeps_its_existing_error_type(self) -> None:
        self.bad.write_bytes(b"\xff\xfe")
        with self.assertRaises(UnicodeDecodeError):
            diff.load_json(self.bad)


if __name__ == "__main__":
    unittest.main()
