#!/usr/bin/env python3
"""Hermetic: $199 diagnostic R4 fixture points at landed contract spines."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from roles import RoleStore

DIAGNOSTIC_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "synthetic_diagnostic_fulfillment_role.json"
)
DEALER_CONTRACT = "revenue/dealer_service_lead_rescue/contract.json"
DEALER_RECEIPT = "revenue/dealer_service_lead_rescue/receipt.md"
REFERRAL_CONTRACT = "revenue/referral_intake_completeness/contract.json"
REFERRAL_RECEIPT = "revenue/referral_intake_completeness/receipt.md"
REPAIR_CONTRACT = "revenue/repair_booking_preflight/contract.json"
PLANT_CONTRACT = "revenue/plant_downtime_handoff/contract.json"
PLANT_RECEIPT = "revenue/plant_downtime_handoff/receipt.md"


class DiagnosticContractSpinePointerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RoleStore(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_diagnostic_fixture_points_at_contract_spines(self) -> None:
        raw = json.loads(DIAGNOSTIC_FIXTURE.read_text(encoding="utf-8"))
        role = self.store.create(raw)
        pointers = {k["pointer"] for k in role["knowledge"]}
        self.assertIn(DEALER_CONTRACT, pointers)
        self.assertIn(DEALER_RECEIPT, pointers)
        self.assertIn(REFERRAL_CONTRACT, pointers)
        self.assertIn(REFERRAL_RECEIPT, pointers)
        self.assertIn(REPAIR_CONTRACT, pointers)
        self.assertIn(PLANT_CONTRACT, pointers)
        self.assertIn(PLANT_RECEIPT, pointers)
        # Live checkouts preserved; no Stripe invent.
        blob = json.dumps(role)
        self.assertIn("buy.stripe.com/3cIdR8gBf6379uF1Oy43S0b", blob)
        for forbidden in ("prod_", "price_", "plink_", "acct_"):
            self.assertNotIn(forbidden, blob)


if __name__ == "__main__":
    unittest.main()
