"""Focused source-contract tests for KAG-COMPOSE."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("compose", HERE / "compose.py")
assert SPEC and SPEC.loader
compose = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compose)


class CompositionTests(unittest.TestCase):
    def test_frozen_rowan_contract(self):
        self.assertEqual(hashlib.sha256(compose.ROWAN.read_bytes()).hexdigest(), compose.ROWAN_SHA256)

    def test_declared_variants_are_deterministic_and_parse(self):
        source = compose.ROWAN.read_text()
        for options in compose.DECLARED.values():
            one = compose.build(source, options)
            two = compose.build(source, options)
            self.assertEqual(one, two)
            ast.parse(one)
            self.assertIn("def choose_purchase", one)
            self.assertIn("while plans:", one)
            self.assertIn("DROP", one)

    def test_rejects_source_or_option_drift(self):
        source = compose.ROWAN.read_text()
        with self.assertRaises(ValueError):
            compose.build(source + "\n", {"pipeline": True})
        with self.assertRaises(ValueError):
            compose.build(source, {"town_expectation": 1.0})

    def test_generate_exact_declared_set(self):
        with tempfile.TemporaryDirectory() as directory:
            hashes = compose.generate(Path(directory))
            self.assertEqual(set(hashes), set(compose.DECLARED))
            for name, digest in hashes.items():
                self.assertEqual(hashlib.sha256((Path(directory) / f"{name}.py").read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
