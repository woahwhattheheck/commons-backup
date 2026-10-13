#!/usr/bin/env python3
"""Focused predecessor battery for the canonical revenue Unicode DLP boundary."""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("revenue_recovery_unicode_guard", ROOT / "host/revenue_recovery.py")
rr = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(rr)


class RevenueRecoveryUnicodeDlpTests(unittest.TestCase):
    def test_nfkc_compatibility_contacts_and_credentials_are_sensitive(self):
        cases = (
            "contact jane＠example.test for the harness",  # U+FF20 -> @
            "contact ｊａｎｅ＠ｅｘａｍｐｌｅ．ｔｅｓｔ for the harness",
            "api＿key＝owner-secret-value",                # fullwidth underscore/equal
            "account：1234567890",                         # fullwidth colon
            "token＝sk_live_1234567890abcdef",
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertTrue(rr.contains_sensitive_value(value))

    def test_unicode_format_controls_fail_closed_even_when_the_visible_text_is_benign(self):
        cases = (
            "jane@\u200bexample.test",  # ZERO WIDTH SPACE, Cf
            "api_\u2060key=secret",     # WORD JOINER, Cf
            "public\u200cobjective",    # ZERO WIDTH NON-JOINER, Cf
            "https://example.com/\u2060contact",
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertTrue(rr.contains_sensitive_value(value))

    def test_percent_and_double_percent_layers_reach_nfkc_and_cf_guards(self):
        cases = (
            "contact%20jane%EF%BC%A0example.test",
            "contact%2520jane%25EF%25BC%25A0example.test",
            "api%EF%BC%BFkey%EF%BC%9Downer-secret-value",
            "api%25EF%25BC%25BFkey%25EF%25BC%259Downer-secret-value",
            "jane@%E2%80%8Bexample.test",
            "jane@%25E2%2580%258Bexample.test",
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertTrue(rr.contains_sensitive_value(value))

    def test_public_https_and_benign_compatibility_text_remain_non_sensitive(self):
        safe = (
            "PUBLIC_CONTACT_URL: https://example.com/contact",
            "https://example.com/contact?source=public%20campaign",
            "PUBLIC_OBJECTIVE: reproducibility",
            "ｐｕｂｌｉｃ objective reproducibility",
            "note=hello%20world",
        )
        for value in safe:
            with self.subTest(value=value):
                self.assertFalse(rr.contains_sensitive_value(value))

    def test_guard_is_identical_under_python_optimized_mode(self):
        if not __debug__:
            return
        completed = subprocess.run(
            [sys.executable, "-O", str(Path(__file__).resolve())],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertIn("OK", completed.stdout)


if __name__ == "__main__":
    unittest.main()
