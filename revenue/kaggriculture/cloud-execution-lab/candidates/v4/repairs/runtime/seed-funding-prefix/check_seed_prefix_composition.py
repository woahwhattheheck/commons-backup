# SPDX-License-Identifier: Apache-2.0
"""Independent byte-preserving composition controls for the ONE seed repair.

No gameplay module is executed. Set TITAN_CURRENT_RUNTIME to exact b952 source,
or run from the canonical package where the production root is five levels up.
The authoritative peer transformer is imported from this SAME directory.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
RUNTIME = Path(os.environ['TITAN_CURRENT_RUNTIME']) if 'TITAN_CURRENT_RUNTIME' in os.environ else HERE.parents[4] / 'titan_runtime.py'
REPAIR_BLOB = 'a5c2c131fd83d83d6be822556abce5723b464a50'
RUNTIME_BLOB = 'b952c9c228ecbde592bf3d2df01638677abb0d24'
BEFORE_SHA256 = 'b3bf094820b77a7b871b017c78fdfa18ef3663c94970c96c2eb572e5c693ff01'
AFTER_SHA256 = '2aef22adfe3dd46782b71f9c6fefb4f4c38b2d8a8671766ea8e395b1adebeab6'


def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def section(data: bytes) -> tuple[bytes, bytes, bytes]:
    """Independent AST/byte-line reader, not the repair's own locator."""
    tree = ast.parse(data.decode('utf-8'))
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'TitanAgent']
    if len(classes) != 1:
        raise ValueError('expected one direct TitanAgent')
    methods = [node for node in classes[0].body if isinstance(node, ast.FunctionDef) and node.name == '_seed_selected']
    if len(methods) != 1:
        raise ValueError('expected one direct synchronous seed consumer')
    node = methods[0]
    lines = data.splitlines(keepends=True)
    return b''.join(lines[:node.lineno-1]), b''.join(lines[node.lineno-1:node.end_lineno]), b''.join(lines[node.end_lineno:])


class SeedCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = RUNTIME.read_bytes()
        actual = blob(cls.source)
        if actual != RUNTIME_BLOB:
            raise ValueError(f'current runtime pin: expected {RUNTIME_BLOB}, got {actual}')
        cls.before_prefix, cls.before, cls.before_suffix = section(cls.source)
        if hashlib.sha256(cls.before).hexdigest() != BEFORE_SHA256:
            raise ValueError('current seed method pin mismatch')
        path = HERE / 'repair_seed_funding_prefix.py'
        if blob(path.read_bytes()) != REPAIR_BLOB:
            raise ValueError('authoritative repair source pin changed; revalidate explicitly')
        spec = importlib.util.spec_from_file_location('_authoritative_seed_prefix', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        cls.repair = staticmethod(module.repair)
        cls.post = cls.repair(cls.source)
        cls.after = section(cls.post)[1]
        if hashlib.sha256(cls.after).hexdigest() != AFTER_SHA256:
            raise ValueError('authoritative postimage changed; revalidate instead of silently repinning')

    def check_preservation(self, data: bytes) -> bytes:
        prefix, method, suffix = section(data)
        self.assertEqual(method, self.before)
        result = self.repair(data)
        self.assertIsInstance(result, bytes)
        self.assertEqual(result, prefix + self.after + suffix)
        compile(result, '<composed-source>', 'exec')
        return result

    def test_exact_current_runtime_repair_preserves_every_other_byte(self):
        self.check_preservation(self.source)
        self.assertEqual(blob(self.source), RUNTIME_BLOB)

    def test_idempotence_is_byte_identity(self):
        self.assertEqual(self.repair(self.post), self.post)

    def test_peer_edits_before_and_after_method_64_vectors(self):
        for leading in range(8):
            for trailing in range(8):
                with self.subTest(leading=leading, trailing=trailing):
                    prefix = ('# peer receipt: delta \u0394\n' * leading).encode('utf-8')
                    suffix = ('\n# preserve sibling evidence \u03bb\n' * trailing).encode('utf-8')
                    data = prefix + self.source + suffix
                    result = self.check_preservation(data)
                    self.assertEqual(self.repair(result), result)

    def test_new_sibling_methods_are_not_rewound(self):
        sibling = b'    def _v4_other_lane(self, obs):\n        return (obs, "peer-exact")\n\n'
        data = self.source.replace(b'class TitanAgent:\n', b'class TitanAgent:\n' + sibling, 1)
        result = self.check_preservation(data)
        self.assertIn(sibling, result)

    def test_existing_other_method_edit_is_preserved(self):
        anchor = b'    def _operating_stock_selected(self, obs, cfg, selected):\n'
        self.assertEqual(self.source.count(anchor), 1)
        peer = anchor + b'        # independent operating-stock owner receipt; keep this exact\n'
        result = self.check_preservation(self.source.replace(anchor, peer, 1))
        self.assertIn(peer, result)

    def test_unrelated_change_commutes_with_seed_repair(self):
        old = b"    consumer: str = 'frozen'"
        new = old + b'  # harmless independent peer comment'
        self.assertEqual(self.source.count(old), 1)
        left = self.repair(self.source.replace(old, new, 1))
        right = self.repair(self.source).replace(old, new, 1)
        self.assertEqual(left, right)

    def test_source_lookalikes_inside_strings_and_comments_are_preserved(self):
        decoy = b'\nSEED_RECEIPT_TEXT = "def _seed_selected(self, obs, cfg, selected):"\n# class TitanAgent:\n'
        self.check_preservation(decoy + self.source + decoy.replace(b'SEED_RECEIPT_TEXT', b'OTHER_TEXT'))

    def test_nested_unrelated_seed_method_is_not_a_second_target(self):
        decoy = b'\nclass Unrelated:\n    def _seed_selected(self, obs, cfg, selected):\n        return selected\n'
        self.check_preservation(self.source + decoy)

    def test_changed_seed_body_is_rejected(self):
        changes = [
            self.before.replace(b'return proposed', b'return selected'),
            self.before.replace(b'if not self.features.seed', b'if self.features.seed'),
            self.before.replace(b'        from scheduler', b'        # changed method\n        from scheduler'),
            self.before.replace(b"'BUY_SEED'", b"'BUY_ANIMAL'"),
        ]
        for method in changes:
            with self.subTest(method=hashlib.sha256(method).hexdigest()), self.assertRaises(ValueError):
                self.repair(self.before_prefix + method + self.before_suffix)

    def test_duplicate_direct_classes_or_methods_are_rejected(self):
        variants = [
            self.source + b'\nclass TitanAgent:\n    pass\n',
            self.before_prefix + self.before + self.before + self.before_suffix,
            self.source.replace(b'class TitanAgent:\n', b'class NotTitanAgent:\n', 1),
        ]
        for data in variants:
            with self.subTest(data=blob(data)), self.assertRaises(ValueError):
                self.repair(data)

    def test_decorated_or_async_method_cannot_be_replaced_as_plain_method(self):
        variants = [b'    @staticmethod\n' + self.before,
                    self.before.replace(b'    def _seed_selected', b'    async def _seed_selected', 1)]
        for method in variants:
            with self.subTest(method=blob(method)), self.assertRaises(ValueError):
                self.repair(self.before_prefix + method + self.before_suffix)

    def test_postimage_drift_is_not_mistaken_for_idempotence(self):
        changed = self.after.replace(b'return proposed', b'return selected')
        self.assertNotEqual(changed, self.after)
        with self.assertRaises(ValueError):
            self.repair(self.before_prefix + changed + self.before_suffix)

    def test_invalid_utf8_and_syntax_are_rejected(self):
        for data in (b'\xff' + self.source, b'class TitanAgent(:\n', b''):
            with self.subTest(data=data[:30]), self.assertRaises((ValueError, SyntaxError)):
                self.repair(data)


if __name__ == '__main__':
    unittest.main(verbosity=2)
