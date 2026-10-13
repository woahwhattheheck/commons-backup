#!/usr/bin/env python3
"""Hermetic: equipment get_role_card (HINGE)."""

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


class GetRoleEquipmentCardTests(unittest.TestCase):
    # hinge-r4-equipment-get-role-card-20260912-01

    def setUp(self) -> None:
        self.eq = GrokBotEquipment()
        self.diag = json.loads(DIAG.read_text(encoding="utf-8"))

    def test_tool_listed(self) -> None:
        names = {t["name"] for t in self.eq.tools()}
        self.assertIn("get_role_card", names)

    def test_get_role_card_from_roles(self) -> None:
        out = self.eq.call(
            "get_role_card",
            {
                "role_id": self.diag["role_id"],
                "roles": [self.diag],
            },
        )
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(out["role"]["role_id"], self.diag["role_id"])
        self.assertEqual(out["role"].get("schema"), "commons.transferable_role/v1")

    def test_get_role_card_from_role(self) -> None:
        out = self.eq.call(
            "get_role_card",
            {"role_id": self.diag["role_id"], "role": self.diag},
        )
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(out["role"]["role_id"], self.diag["role_id"])

    def test_missing_role_id(self) -> None:
        miss = self.eq.call("get_role_card", {"roles": [self.diag]})
        self.assertFalse(miss.get("ok"))
        self.assertEqual(miss.get("error"), "missing_argument")

    def test_unknown_role_id_refuses(self) -> None:
        out = self.eq.call(
            "get_role_card",
            {"role_id": "role.missing.example", "roles": [self.diag]},
        )
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "role_refused")


if __name__ == "__main__":
    unittest.main()
