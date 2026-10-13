from __future__ import annotations

import unittest
from pathlib import Path

from revenue.agent_capability_constraint_registry.core import RegistryError, compile_registry, load_json_bytes

HERE = Path(__file__).resolve().parent


def fixture() -> dict:
    return load_json_bytes((HERE / "fixture_12_agents.json").read_bytes(), "fixture")


class FreshnessTests(unittest.TestCase):
    def test_stale_capability_evidence_rejected(self):
        source = fixture()
        source["evidence_max_age_seconds"] = 60
        with self.assertRaisesRegex(RegistryError, "stale evidence"):
            compile_registry(source)

    def test_future_capability_evidence_rejected(self):
        source = fixture()
        source["records"][0]["measured_capabilities"][0]["measured_at"] = "2026-09-13T13:36:00Z"
        with self.assertRaisesRegex(RegistryError, "future"):
            compile_registry(source)

    def test_stale_constraint_evidence_rejected(self):
        source = fixture()
        source["records"][1]["declared_constraints"][0]["source_ts"] = "2026-09-13T10:00:00Z"
        with self.assertRaisesRegex(RegistryError, "stale evidence"):
            compile_registry(source)

    def test_bool_as_freshness_window_rejected(self):
        source = fixture()
        source["evidence_max_age_seconds"] = True
        with self.assertRaises(RegistryError):
            compile_registry(source)


if __name__ == "__main__":
    unittest.main()
