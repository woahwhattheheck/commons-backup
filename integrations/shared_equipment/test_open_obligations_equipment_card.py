#!/usr/bin/env python3
"""Hermetic: equipment open_obligations_card (TENON full queue)."""

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


class OpenObligationsEquipmentCardTests(unittest.TestCase):
    # tenon-r4-equipment-open-obligations-card-20260906-01

    def setUp(self) -> None:
        self.eq = GrokBotEquipment()
        self.diag = json.loads(DIAG.read_text(encoding="utf-8"))
        self.crm = json.loads(CRM.read_text(encoding="utf-8"))

    def test_tool_listed(self) -> None:
        names = {t["name"] for t in self.eq.tools()}
        self.assertIn("open_obligations_card", names)
        self.assertIn("open_obligations_cash_card", names)

    def test_full_queue_includes_crm(self) -> None:
        roles = [self.crm, self.diag]
        out = self.eq.call("open_obligations_card", {"roles": roles})
        self.assertTrue(out.get("ok"), out)
        self.assertIs(out.get("cash_only"), False)
        rows = out["open_obligations"]
        expected = {
            (role["role_id"], ob["id"])
            for role in roles
            for ob in role["obligations"]
            if ob["status"] == "open"
        }
        self.assertEqual(
            {(row["role_id"], row["obligation_id"]) for row in rows}, expected
        )
        crm_rows = [r for r in rows if r["role_id"] == self.crm["role_id"]]
        self.assertTrue(crm_rows)
        for row in crm_rows:
            self.assertNotEqual(row.get("payment_capability"), True)

    def test_cash_only_opt_in_matches_wedge_card(self) -> None:
        roles = [self.crm, self.diag]
        full_cash = self.eq.call(
            "open_obligations_card",
            {"roles": roles, "cash_only": True},
        )
        wedge = self.eq.call("open_obligations_cash_card", {"roles": roles})
        self.assertTrue(full_cash.get("ok"), full_cash)
        self.assertTrue(wedge.get("ok"), wedge)
        self.assertIs(full_cash.get("cash_only"), True)
        self.assertEqual(
            {
                (r["role_id"], r["obligation_id"])
                for r in full_cash["open_obligations"]
            },
            {
                (r["role_id"], r["obligation_id"])
                for r in wedge["open_obligations"]
            },
        )

    def test_empty_roles_refuse(self) -> None:
        out = self.eq.call("open_obligations_card", {"roles": []})
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "missing_argument")


if __name__ == "__main__":
    unittest.main()
