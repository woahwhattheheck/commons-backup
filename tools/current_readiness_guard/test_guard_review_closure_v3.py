from __future__ import annotations

import unittest

from .guard import analyze_source


class ReviewClosureV3Tests(unittest.TestCase):
    def rules(self, source: str) -> list[str]:
        return [finding.rule for finding in analyze_source(source, path="revenue/x.py")]

    def test_overlay_literal_ready_collapses_to_one_crg003(self):
        source = '''
def evaluate(packet):
    return "PRIME_READY"
'''
        self.assertEqual(self.rules(source), ["CRG003"])

    def test_if_without_else_fallthrough_keeps_false_branch_authority(self):
        source = '''
def evaluate(packet, authority_root):
    if not authority_root:
        return "HOLD"
    state = "PRIME_" + "READY"
    return state
'''
        self.assertNotIn("CRG003", self.rules(source))

    def test_reaching_overwrite_kills_composed_positive(self):
        source = '''
def evaluate(packet):
    state = "PRIME_" + "READY"
    state = "HOLD"
    return state
'''
        self.assertNotIn("CRG003", self.rules(source))

    def test_branch_assignment_authority_survives_composed_overlay(self):
        source = '''
def evaluate(packet, authority_root):
    if authority_root:
        state = "PRIME_" + "READY"
    else:
        state = "HOLD"
    return state
'''
        self.assertNotIn("CRG003", self.rules(source))

    def test_local_composed_readiness_strings_fail_closed(self):
        samples = (
            '''
def evaluate(packet):
    state = "PRIME_" + "READY"
    return state
''',
            '''
def evaluate(packet):
    prefix = "PRIME_"
    state = f"{prefix}READY"
    return state
''',
        )
        for source in samples:
            with self.subTest(source=source):
                self.assertIn("CRG003", self.rules(source))

    def test_public_method_boolean_and_computed_string_surfaces_fail_closed(self):
        samples = (
            '''
class Gate:
    def verify_current(self, packet):
        return True
''',
            '''
class Gate:
    def is_ready(self, packet):
        return packet["state"] == "READY"
''',
            '''
class Gate:
    def evaluate(self, packet):
        return "PRIME_" + "READY"
''',
        )
        for source in samples:
            with self.subTest(source=source):
                self.assertIn("CRG003", self.rules(source))

        controlled = '''
class Gate:
    def is_ready(self, packet, authority_root):
        return bool(authority_root)
'''
        self.assertNotIn("CRG003", self.rules(controlled))

    def test_local_validator_alias_must_consume_authority(self):
        ignored = '''
def validate_authority(packet, authority_root):
    return packet["verified"]

def evaluate(packet, authority_root):
    verify = validate_authority
    if verify(packet, authority_root):
        return "PRIME_READY"
    return "HOLD"
'''
        consumed = '''
def validate_authority(packet, authority_root):
    return bool(authority_root)

def evaluate(packet, authority_root):
    verify = validate_authority
    if verify(packet, authority_root):
        return "PRIME_READY"
    return "HOLD"
'''
        self.assertIn("CRG003", self.rules(ignored))
        self.assertNotIn("CRG003", self.rules(consumed))

    def test_module_validator_alias_must_consume_authority(self):
        ignored = '''
def validate_authority(packet, authority_root):
    return packet["verified"]

verify = validate_authority

def evaluate(packet, authority_root):
    if verify(packet, authority_root):
        return "PRIME_READY"
    return "HOLD"
'''
        self.assertIn("CRG003", self.rules(ignored))

    def test_method_validator_alias_must_consume_authority(self):
        ignored = '''
class Gate:
    def validate_authority(self, packet, authority_root):
        return packet["verified"]

    def evaluate(self, packet, authority_root):
        verify = self.validate_authority
        if verify(packet, authority_root):
            return "PRIME_READY"
        return "HOLD"
'''
        consumed = '''
class Gate:
    def validate_authority(self, packet, authority_root):
        return bool(authority_root)

    def evaluate(self, packet, authority_root):
        verify = self.validate_authority
        if verify(packet, authority_root):
            return "PRIME_READY"
        return "HOLD"
'''
        self.assertIn("CRG003", self.rules(ignored))
        self.assertNotIn("CRG003", self.rules(consumed))

    def test_class_level_validator_alias_must_consume_authority(self):
        ignored = '''
class Gate:
    def validate_authority(self, packet, authority_root):
        return packet["verified"]

    verify = validate_authority

    def evaluate(self, packet, authority_root):
        if self.verify(packet, authority_root):
            return "PRIME_READY"
        return "HOLD"
'''
        consumed = '''
class Gate:
    def validate_authority(self, packet, authority_root):
        return bool(authority_root)

    verify = validate_authority

    def evaluate(self, packet, authority_root):
        if self.verify(packet, authority_root):
            return "PRIME_READY"
        return "HOLD"
'''
        self.assertIn("CRG003", self.rules(ignored))
        self.assertNotIn("CRG003", self.rules(consumed))

    def test_dynamic_rebinding_aliases_fail_closed(self):
        local_dynamic = '''
def validate_authority(packet, authority_root):
    return bool(authority_root)

def evaluate(packet, authority_root):
    verify = validate_authority
    if packet["use_custom"]:
        verify = packet["validator"]
    if verify(packet, authority_root):
        return "PRIME_READY"
    return "HOLD"
'''
        module_dynamic = '''
def validate_authority(packet, authority_root):
    return bool(authority_root)

verify = validate_authority
verify = incoming["validator"]

def evaluate(packet, authority_root):
    if verify(packet, authority_root):
        return "PRIME_READY"
    return "HOLD"
'''
        class_dynamic = '''
class Gate:
    def validate_authority(self, packet, authority_root):
        return bool(authority_root)

    verify = validate_authority
    verify = incoming["validator"]

    def evaluate(self, packet, authority_root):
        if self.verify(packet, authority_root):
            return "PRIME_READY"
        return "HOLD"
'''
        for source in (local_dynamic, module_dynamic, class_dynamic):
            with self.subTest(source=source):
                self.assertIn("CRG003", self.rules(source))


if __name__ == "__main__":
    unittest.main()
