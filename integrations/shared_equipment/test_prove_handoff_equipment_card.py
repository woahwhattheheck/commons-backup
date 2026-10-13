#!/usr/bin/env python3
"""Hermetic: equipment prove_handoff_card (HINGE)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from integrations.shared_equipment.peers import GrokBotEquipment

_FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "transferable_roles"
    / "fixtures"
)
DIAG = _FIXTURES / "synthetic_diagnostic_fulfillment_role.json"
CRM = _FIXTURES / "synthetic_crm_followup_role.json"

_EVIDENCE = "2026-09-04T15:00:00-04:00"
_AS_OF_OPEN = "2026-09-04T16:00:00-04:00"
_AS_OF_MISSED = "2026-09-08T10:00:00-04:00"


class ProveHandoffEquipmentCardTests(unittest.TestCase):
    # hinge-r4-equipment-prove-handoff-card-20260906-01

    def setUp(self) -> None:
        self.eq = GrokBotEquipment()
        self.diag = json.loads(DIAG.read_text(encoding="utf-8"))

    def test_tool_listed(self) -> None:
        names = {t["name"] for t in self.eq.tools()}
        self.assertIn("prove_handoff_card", names)

    def test_prove_handoff_card_diagnostic(self) -> None:
        before = json.dumps(self.diag, sort_keys=True)
        out = self.eq.call(
            "prove_handoff_card",
            {
                "role": self.diag,
                "slug": "dealer",
                "usable_evidence_at": _EVIDENCE,
                "as_of": _AS_OF_OPEN,
            },
        )
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(json.dumps(self.diag, sort_keys=True), before)
        proof = out["proof"]
        self.assertTrue(proof.get("ok"))
        self.assertIn("diagnostic-contract", proof["executes"])
        self.assertIn("diagnostic-fulfill-sla", proof["executes"])
        sla = proof["executes"]["diagnostic-fulfill-sla"]
        self.assertEqual(sla.get("sla_status"), "OPEN")
        self.assertEqual(sla.get("diagnostic_usd"), 199)
        self.assertEqual(sla.get("slug"), "dealer")

        missed = self.eq.call(
            "prove_handoff_card",
            {
                "role": self.diag,
                "slug": "dealer",
                "usable_evidence_at": _EVIDENCE,
                "as_of": _AS_OF_MISSED,
            },
        )
        self.assertTrue(missed.get("ok"), missed)
        self.assertEqual(
            missed["proof"]["executes"]["diagnostic-fulfill-sla"]["sla_status"],
            "MISSED",
        )

    def test_crm_role_refuses(self) -> None:
        crm = json.loads(CRM.read_text(encoding="utf-8"))
        out = self.eq.call("prove_handoff_card", {"role": crm})
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "role_refused")

    def test_missing_role_refuses(self) -> None:
        out = self.eq.call("prove_handoff_card", {})
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "missing_argument")


if __name__ == "__main__":
    unittest.main()
