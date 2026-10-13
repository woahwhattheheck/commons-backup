from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from .core import compile_cockpit, load_json_bytes

HERE = Path(__file__).resolve().parent
REPLAY = datetime(2026, 9, 14, 1, 30, 0, tzinfo=timezone.utc)
GOLDEN_RECEIPT = "a5bc6e56fae6c001f6af34b3a6276ed9b7f9eb67bc283b7bff91785926596e96"


class FixtureTests(unittest.TestCase):
    def test_synthetic_portfolio_golden(self):
        packet = load_json_bytes((HERE / "example_input.json").read_bytes())
        policy = load_json_bytes((HERE / "example_policy.json").read_bytes())
        compiled = compile_cockpit(packet, policy, as_of=REPLAY)
        self.assertEqual(GOLDEN_RECEIPT, compiled["receipt_sha256"])
        self.assertEqual(8, compiled["summary"]["opportunity_count"])
        self.assertEqual(10, compiled["summary"]["queue_row_count"])
        self.assertEqual("source:zeta", compiled["rows"][0]["row_id"])
        legal = next(r for r in compiled["rows"] if r["action_key"] == "LEGAL_ENTITY_CONFIRM")
        self.assertEqual(["alpha", "beta", "gamma"], legal["affected_opportunity_ids"])
        tax_rows = [r for r in compiled["rows"] if r["action_key"] == "TAX_VENDOR_FORM"]
        self.assertEqual(2, len(tax_rows))
        self.assertTrue(all("INCOMPATIBLE_ACTION_VARIANTS_EXIST" in r["reason_codes"] for r in tax_rows))


if __name__ == "__main__":
    unittest.main()
