import hashlib
import json
import unittest
from pathlib import Path

import adapter

ROOT = Path(__file__).resolve().parent


class BarnyardAdapterTest(unittest.TestCase):
    def test_preserved_source_hash(self):
        self.assertEqual(
            hashlib.sha256((ROOT / "upstream" / "main.py").read_bytes()).hexdigest(),
            adapter.EXPECTED_SHA256,
        )

    def test_real_initial_observation_is_callable(self):
        obs = json.loads((ROOT / "fixtures" / "initial-observation.json").read_text())
        action = adapter.make_agent()(obs, {"ignored": True})
        self.assertIsInstance(action, dict)
        self.assertEqual(set(action), {"farmer", "hands", "market"})
        self.assertIsInstance(action["farmer"], list)
        self.assertIsInstance(action["hands"], list)
        self.assertIsInstance(action["market"], list)

    def test_fresh_instances_are_deterministic_at_step_zero(self):
        obs = json.loads((ROOT / "fixtures" / "initial-observation.json").read_text())
        self.assertEqual(adapter.make_agent()(obs), adapter.make_agent()(obs))


if __name__ == "__main__":
    unittest.main()
