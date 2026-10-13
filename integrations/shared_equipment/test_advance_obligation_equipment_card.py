#!/usr/bin/env python3
"""Hermetic: equipment advance_obligation_card (TENON)."""

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


class AdvanceObligationEquipmentCardTests(unittest.TestCase):
    # tenon-r4-equipment-advance-obligation-card-20260906-01

    def setUp(self) -> None:
        self.eq = GrokBotEquipment()
        self.diag = json.loads(DIAG.read_text(encoding="utf-8"))

    def test_tool_listed(self) -> None:
        names = {t["name"] for t in self.eq.tools()}
        self.assertIn("advance_obligation_card", names)

    def test_advance_marks_done_and_preserves_siblings(self) -> None:
        before = json.dumps(self.diag, sort_keys=True)
        out = self.eq.call(
            "advance_obligation_card",
            {
                "role": self.diag,
                "obligation_id": "ob-intake",
                "status": "done",
                "next_action": "Intake recorded from equipment advance",
                "evidence_pointer": "p/tenon-r4-equipment-advance-obligation-card-20260906-01.md",
            },
        )
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(json.dumps(self.diag, sort_keys=True), before)
        role = out["role"]
        self.assertEqual(role["purpose"], self.diag["purpose"])
        by_id = {ob["id"]: ob for ob in role["obligations"]}
        self.assertEqual(by_id["ob-intake"]["status"], "done")
        self.assertEqual(
            by_id["ob-intake"]["next_action"],
            "Intake recorded from equipment advance",
        )
        self.assertEqual(
            by_id["ob-intake"]["evidence_pointer"],
            "p/tenon-r4-equipment-advance-obligation-card-20260906-01.md",
        )
        self.assertEqual(by_id["ob-diagnose"]["status"], "open")

    def test_crm_role_can_advance(self) -> None:
        # Advance is role-general (not diagnostic-gated).
        crm = json.loads(CRM.read_text(encoding="utf-8"))
        oid = crm["obligations"][0]["id"]
        out = self.eq.call(
            "advance_obligation_card",
            {
                "role": crm,
                "obligation_id": oid,
                "status": "done",
            },
        )
        self.assertTrue(out.get("ok"), out)
        by_id = {ob["id"]: ob for ob in out["role"]["obligations"]}
        self.assertEqual(by_id[oid]["status"], "done")

    def test_missing_fields_refuse(self) -> None:
        missing_id = self.eq.call(
            "advance_obligation_card",
            {"role": self.diag, "status": "done"},
        )
        self.assertFalse(missing_id.get("ok"))
        self.assertEqual(missing_id.get("error"), "missing_argument")
        no_update = self.eq.call(
            "advance_obligation_card",
            {"role": self.diag, "obligation_id": "ob-intake"},
        )
        self.assertFalse(no_update.get("ok"))
        self.assertEqual(no_update.get("error"), "role_refused")
        unknown = self.eq.call(
            "advance_obligation_card",
            {
                "role": self.diag,
                "obligation_id": "ob-missing",
                "status": "done",
            },
        )
        self.assertFalse(unknown.get("ok"))
        self.assertEqual(unknown.get("error"), "role_refused")


if __name__ == "__main__":
    unittest.main()
