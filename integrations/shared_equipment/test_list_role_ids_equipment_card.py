#!/usr/bin/env python3
"""Hermetic: equipment list_role_ids_card (HINGE)."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from integrations.shared_equipment.peers import GrokBotEquipment

_FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "transferable_roles"
    / "fixtures"
)
DIAG = _FIXTURES / "synthetic_diagnostic_fulfillment_role.json"
CRM = _FIXTURES / "synthetic_crm_followup_role.json"


class ListRoleIdsEquipmentCardTests(unittest.TestCase):
    # hinge-r4-equipment-list-role-ids-card-20260912-01

    def setUp(self) -> None:
        self.eq = GrokBotEquipment()
        self.diag = json.loads(DIAG.read_text(encoding="utf-8"))
        self.crm = json.loads(CRM.read_text(encoding="utf-8"))

    def test_tool_listed(self) -> None:
        names = {t["name"] for t in self.eq.tools()}
        self.assertIn("list_role_ids_card", names)

    def test_list_role_ids_card_ok(self) -> None:
        out = self.eq.call(
            "list_role_ids_card",
            {"roles": [self.diag, self.crm]},
        )
        self.assertTrue(out.get("ok"), out)
        ids = out["role_ids"]
        self.assertIn(self.diag["role_id"], ids)
        self.assertIn(self.crm["role_id"], ids)
        self.assertEqual(len(ids), 2)

    def test_duplicate_role_id_refuses(self) -> None:
        a = deepcopy(self.diag)
        b = deepcopy(self.diag)
        out = self.eq.call("list_role_ids_card", {"roles": [a, b]})
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "role_refused")

    def test_missing_roles(self) -> None:
        miss = self.eq.call("list_role_ids_card", {})
        self.assertFalse(miss.get("ok"))
        self.assertEqual(miss.get("error"), "missing_argument")


if __name__ == "__main__":
    unittest.main()
