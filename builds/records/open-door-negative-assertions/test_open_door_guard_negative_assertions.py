#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import unittest


def load_guard(path: Path):
    spec = importlib.util.spec_from_file_location('guard_under_test', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def diff(path: str, added: list[str]):
    lines = [
        f'diff --git a/{path} b/{path}',
        f'--- a/{path}',
        f'+++ b/{path}',
        f'@@ -0,0 +1,{len(added)} @@',
    ]
    lines.extend('+' + line for line in added)
    return '\n'.join(lines) + '\n'


class ScopeTests(unittest.TestCase):
    guard = None

    def rules(self, path: str, *added: str):
        return {item.rule for item in self.guard.scan_diff(diff(path, list(added)))}

    def test_semicolon_unittest_tail_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py', 'self.assertFalse(flag); SEAT_GATE = True'))

    def test_semicolon_assert_tail_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py', "assert not hasattr(module, 'gate'); REQUIRE_IDENTITY = True"))

    def test_boolean_expression_tail_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py', 'self.assertFalse(flag) or REQUIRE_IDENTITY()'))

    def test_assignment_expression_is_not_hidden(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py', 'self.assertFalse(SEAT_GATE := True)'))

    def test_assert_boolean_tail_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py',
            "assert not hasattr(module, 'gate') or REQUIRE_IDENTITY()",
        ))

    def test_assertion_argument_gate_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py', 'self.assertFalse(REQUIRE_IDENTITY())'))

    def test_assert_notin_gate_call_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py', 'assert REQUIRE_IDENTITY() not in source'))

    def test_assertion_message_gate_call_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py', 'self.assertFalse(flag, REQUIRE_IDENTITY())'))

    def test_assert_quoted_negative_or_gate_call_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py',
            'assert "permission denied" not in source.lower() or REQUIRE_IDENTITY()',
        ))

    def test_assert_quoted_negative_or_gate_without_method_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py',
            'assert "permission denied" not in source or REQUIRE_IDENTITY()',
        ))

    def test_incomplete_assertion_with_gate_tail_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py', 'self.assertFalse(flag) or REQUIRE_IDENTITY('))

    def test_chained_assertion_gate_call_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py', 'self.assertFalse(flag).REQUIRE_IDENTITY()'))

    def test_semicolon_window_schema_tail_is_scanned(self):
        found = self.rules(
            'test_policy.py', 'self.assertFalse(flag); schema = {"required": ["identity"]}')
        self.assertTrue({'admission-phrase', 'required-speaker-schema'} & found, found)

    def test_multiline_assertion_closing_tail_is_scanned(self):
        found = self.rules(
            'test_policy.py',
            'self.assertFalse(',
            '    "identity required",',
            '); SEAT_GATE = True',
        )
        self.assertIn('gate-identifier', found)

    def test_standalone_unittest_negative_quote_passes(self):
        self.assertEqual(self.rules(
            'test_policy.py', 'self.assertFalse("authentication required" in source.lower())'), set())

    def test_standalone_assert_negative_quote_passes(self):
        self.assertEqual(self.rules(
            'test_policy.py', 'assert "permission denied" not in source.lower()'), set())

    def test_standalone_hasattr_negative_passes(self):
        self.assertEqual(self.rules(
            'test_policy.py', 'assert not hasattr(module, "PROTECTED_FILES")'), set())

    def test_quoted_semicolon_does_not_create_tail(self):
        self.assertEqual(self.rules(
            'test_policy.py', 'self.assertFalse("x; SEAT_GATE = True" in source)'), set())

    def test_trailing_comment_does_not_create_tail(self):
        self.assertEqual(self.rules(
            'test_policy.py', 'self.assertFalse(flag)  # no identity gate'), set())

    def test_multiline_negative_quote_passes(self):
        self.assertEqual(self.rules(
            'test_policy.py',
            'self.assertFalse(',
            '    "identity required" in source.lower()',
            ')',
        ), set())

    def test_incomplete_changed_first_line_remains_exempt(self):
        self.assertEqual(self.rules(
            'test_policy.py', 'self.assertFalse("identity required" in source.lower(),'), set())

    def test_javascript_negative_assertion_unchanged(self):
        self.assertEqual(self.rules(
            'test_policy.js', 'assert.ok(!source.includes("permission denied"));'), set())

    def test_positive_unittest_assertion_still_fails(self):
        self.assertIn('explicit-denial', self.rules(
            'test_policy.py', 'self.assertTrue("authentication required" in source.lower())'))

    def test_ordinary_hard_identifier_still_fails(self):
        self.assertIn('gate-identifier', self.rules(
            'policy.py', 'SEAT_GATE = True'))

    def test_directive_prohibition_still_passes(self):
        self.assertEqual(self.rules(
            'AGENTS.md', '- authentication, identity, claim, seat, or memory gates'), set())

    def test_two_standalone_negative_assertions_same_hunk_pass(self):
        self.assertEqual(self.rules(
            'test_policy.py',
            'self.assertFalse("authentication required" in source.lower())',
            'assert not hasattr(module, "PROTECTED_FILES")',
        ), set())

    def test_separate_following_gate_is_scanned(self):
        found = self.rules(
            'test_policy.py',
            'self.assertFalse("authentication required" in source.lower())',
            'SEAT_GATE = True',
        )
        self.assertIn('gate-identifier', found)

    def test_fstring_negative_literal_passes(self):
        self.assertEqual(self.rules(
            'test_policy.py',
            'self.assertFalse(f"authentication required {value}" in source)',
        ), set())

    def test_raw_fstring_negative_literal_passes(self):
        self.assertEqual(self.rules(
            'test_policy.py',
            'self.assertFalse(fr"authentication required" in source)',
        ), set())

    def test_fstring_escaped_gate_text_passes(self):
        self.assertEqual(self.rules(
            'test_policy.py',
            'self.assertFalse(f"{{REQUIRE_IDENTITY()}}" in source)',
        ), set())

    def test_fstring_gate_expression_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py',
            'self.assertFalse(f"safe {REQUIRE_IDENTITY()}" in source)',
        ))

    def test_fstring_format_gate_expression_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py',
            'self.assertFalse(f"{REQUIRE_IDENTITY():permission denied}" in source)',
        ))

    def test_multiline_plain_assert_negative_quote_passes(self):
        self.assertEqual(self.rules(
            'test_policy.py',
            'assert (',
            '    "permission denied" not in source.lower()',
            ')',
        ), set())

    def test_multiline_plain_assert_positive_quote_is_scanned(self):
        self.assertIn('explicit-denial', self.rules(
            'test_policy.py',
            'assert (',
            '    "permission denied" in source.lower()',
            ')',
        ))

    def test_multiline_plain_assert_gate_tail_is_scanned(self):
        self.assertIn('gate-identifier', self.rules(
            'test_policy.py',
            'assert (',
            '    "permission denied" not in source.lower()',
            '    or REQUIRE_IDENTITY()',
            ')',
        ))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--guard', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    ScopeTests.guard = load_guard(args.guard.resolve())
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ScopeTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        'guard': str(args.guard.resolve()),
        'guard_sha256': hashlib.sha256(args.guard.read_bytes()).hexdigest(),
        'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'tests': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'successful': result.wasSuccessful(),
        'failure_names': [str(test) for test, _ in result.failures],
        'error_names': [str(test) for test, _ in result.errors],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
