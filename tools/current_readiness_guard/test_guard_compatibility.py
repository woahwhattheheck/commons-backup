from __future__ import annotations

import unittest

from .guard import analyze_source


class OriginalCompatibilityTests(unittest.TestCase):
    def rules(self, source: str):
        return [finding.rule for finding in analyze_source(source, path="revenue/x.py")]

    def test_private_time_projection_alone_is_not_public_surface(self):
        source = """
DEADLINE = object()
def _project(packet):
    current = packet["as_of"]
    if current > DEADLINE:
        return "HOLD"
    return "PRIME_READY"
"""
        self.assertNotIn("CRG001", self.rules(source))

    def test_public_verifier_time_override_is_flagged(self):
        source = """
def verify_current(report, verifier_now):
    if verifier_now:
        return "VALID"
    return "HOLD"
"""
        self.assertIn("CRG002", self.rules(source))

    def test_extra_caller_knob_does_not_evade_authority_rule(self):
        source = """
def evaluate(packet, mode):
    if packet.get("verified") and mode == "prime":
        return "PRIME_READY"
    return "HOLD"
"""
        self.assertIn("CRG003", self.rules(source))

    def test_subscript_assignment_does_not_taint_unrelated_lookup(self):
        source = """
DEADLINE = object()
def evaluate(packet, authority_root):
    ctx = {}
    ctx["now"] = packet["as_of"]
    if ctx.get("unrelated") > DEADLINE:
        return "HOLD"
    if authority_root:
        return "PRIME_READY"
    return "HOLD"
"""
        self.assertNotIn("CRG001", self.rules(source))


if __name__ == "__main__":
    unittest.main()
