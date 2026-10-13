"""Focused contracts for FLORA KAG-PRODUCTION."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("kag_production_build", HERE / "build.py")
assert SPEC and SPEC.loader
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)

CANDIDATE_SPEC = importlib.util.spec_from_file_location("kag_production_candidate", HERE / "candidate.py")
assert CANDIDATE_SPEC and CANDIDATE_SPEC.loader
candidate = importlib.util.module_from_spec(CANDIDATE_SPEC)
CANDIDATE_SPEC.loader.exec_module(candidate)


class ProductionTests(unittest.TestCase):
    def test_exact_parent_contract(self):
        self.assertEqual(hashlib.sha256(build.PARENT.read_bytes()).hexdigest(), build.PARENT_SHA256)

    def test_deterministic_standalone_generation(self):
        source = build.PARENT.read_text()
        one, two = build.build(source), build.build(source)
        self.assertEqual(one, two)
        tree = ast.parse(one)
        callables = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
        self.assertEqual(callables[-1], "agent")
        self.assertNotIn("_base_agent", callables)
        self.assertIn("FERTILIZE", one)
        self.assertIn("BUY_LAND", one)
        self.assertIn('"STRAWBERRY"', one)

    def test_rejects_parent_drift(self):
        with self.assertRaises(ValueError):
            build.build(build.PARENT.read_text() + "\n")

    def test_generated_candidate_is_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate.py"
            digest = build.generate(output)
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), digest)

    def test_rowan_next_refresh_fertilizer_contract(self):
        strawberry = {"kind": "PLANT", "crop": "STRAWBERRY", "planted_day": 0,
                      "fertilized_until_day": 8}
        self.assertEqual(candidate._fertilizer_window(strawberry, 8, 8 * 24, 24, 720), (1, 9))
        strawberry["fertilized_until_day"] = 9
        self.assertIsNone(candidate._fertilizer_window(strawberry, 9, 9 * 24, 24, 720))
        late = {"kind": "PLANT", "crop": "STRAWBERRY", "planted_day": 20,
                "fertilized_until_day": -1}
        self.assertEqual(candidate.production_events(late, 20 * 24, 24, 720), [])

    def test_sequential_product_fill_preserves_budget(self):
        market = {"inventory": {"WHEAT": 10000}, "prices": {"WHEAT": 25}}
        qty, cost = candidate._product_fill("WHEAT", 20, 100, 30, market)
        self.assertGreater(qty, 0)
        self.assertLessEqual(cost, 70)
        self.assertGreater(candidate.price("WHEAT", -qty, market), 0)

    def test_dynamic_crop_cap_uses_observable_worker_capacity(self):
        plants = [(i, 0, {"kind": "PLANT", "crop": "STRAWBERRY"}) for i in range(6)]
        animals = [(i, 1, {"animal": "GOOSE"}) for i in range(6)]
        low = candidate._dynamic_crop_cap(animals, plants, 0, [(0, 0)] * 4, 24, candidate.POLICY)
        high = candidate._dynamic_crop_cap(animals, plants, 0, [(0, 0)] * 10, 24, candidate.POLICY)
        self.assertGreater(high, low)
        self.assertLessEqual(high, candidate.POLICY["crop_cap"])
        self.assertGreaterEqual(low, len(plants))


if __name__ == "__main__":
    unittest.main()
