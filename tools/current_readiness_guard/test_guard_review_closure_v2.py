from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from . import guard as guard_module
from .guard import analyze_source, scan_paths


class ReviewClosureV2Tests(unittest.TestCase):
    def rules(self, source: str) -> list[str]:
        return [finding.rule for finding in analyze_source(source, path="revenue/x.py")]

    def test_bare_boolean_current_surfaces_fail_closed(self):
        samples = (
            'def verify_current(packet):\n return True\n',
            'def is_ready(packet):\n return packet["state"] == "READY"\n',
            'def evaluate(packet):\n return bool(packet["verified"])\n',
        )
        for source in samples:
            with self.subTest(source=source):
                self.assertIn("CRG003", self.rules(source))

        controlled = 'def ready(packet, authority_root):\n return bool(authority_root)\n'
        self.assertNotIn("CRG003", self.rules(controlled))

    def test_computed_readiness_strings_fail_closed(self):
        samples = (
            'def evaluate(packet):\n return "PRIME_" + "READY"\n',
            'def evaluate(packet):\n return f"PRIME_READY"\n',
            'READY_STATE = "PRIME_" + "READY"\ndef evaluate(packet):\n return READY_STATE\n',
        )
        for source in samples:
            with self.subTest(source=source):
                self.assertIn("CRG003", self.rules(source))

    def test_same_module_validator_must_consume_authority(self):
        ignored = '''
def validate_authority(packet, authority_root):
    return packet["verified"]

def evaluate(packet, authority_root):
    if validate_authority(packet, authority_root):
        return "PRIME_READY"
    return "HOLD"
'''
        consumed = '''
def validate_authority(packet, authority_root):
    return bool(authority_root)

def evaluate(packet, authority_root):
    if validate_authority(packet, authority_root):
        return "PRIME_READY"
    return "HOLD"
'''
        self.assertIn("CRG003", self.rules(ignored))
        self.assertNotIn("CRG003", self.rules(consumed))

    def test_same_module_process_clock_argument_must_be_consumed(self):
        ignored = '''
from datetime import datetime, timezone

def compile_state(packet, as_of=None):
    return packet["state"]

def verify_report(packet, report):
    retained = compile_state(packet, as_of=report["evaluated_at"])
    current = datetime.now(timezone.utc)
    fresh = compile_state(packet, as_of=current)
    return retained == report and fresh == report
'''
        consumed = '''
from datetime import datetime, timezone
DEADLINE = object()

def compile_state(packet, as_of=None):
    if as_of > DEADLINE:
        return "HOLD"
    return packet["state"]

def verify_report(packet, report):
    retained = compile_state(packet, as_of=report["evaluated_at"])
    current = datetime.now(timezone.utc)
    fresh = compile_state(packet, as_of=current)
    return retained == report and fresh == report
'''
        self.assertIn("CRG004", self.rules(ignored))
        self.assertNotIn("CRG004", self.rules(consumed))

    @unittest.skipUnless(hasattr(os, "rename"), "rename unavailable")
    def test_visible_ancestor_replacement_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            revenue = root / "revenue"
            revenue.mkdir()
            (revenue / "gate.py").write_text(
                'def evaluate(packet):\n return "HOLD"\n', encoding="utf-8"
            )
            original_read = guard_module.os.read
            swapped = False

            def swap_then_read(fd: int, size: int) -> bytes:
                nonlocal swapped
                if not swapped:
                    swapped = True
                    revenue.rename(root / "revenue.old")
                    replacement = root / "revenue"
                    replacement.mkdir()
                    (replacement / "gate.py").write_text(
                        'def evaluate(packet):\n return "PRIME_READY"\n', encoding="utf-8"
                    )
                return original_read(fd, size)

            with mock.patch.object(guard_module.os, "read", side_effect=swap_then_read):
                findings = scan_paths(["revenue/gate.py"], root=root)

            self.assertEqual([finding.rule for finding in findings], ["CRG000"])


if __name__ == "__main__":
    unittest.main()
