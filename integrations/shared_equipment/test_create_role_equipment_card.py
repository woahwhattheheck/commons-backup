#!/usr/bin/env python3
"""Hermetic: equipment create_role_card (HINGE)."""

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


class CreateRoleEquipmentCardTests(unittest.TestCase):
    # hinge-r4-equipment-create-role-card-20260912-01

    def setUp(self) -> None:
        self.eq = GrokBotEquipment()
        self.diag = json.loads(DIAG.read_text(encoding="utf-8"))

    def test_tool_listed(self) -> None:
        names = {t["name"] for t in self.eq.tools()}
        self.assertIn("create_role_card", names)

    def test_create_role_card_ok(self) -> None:
        before = json.dumps(self.diag, sort_keys=True)
        out = self.eq.call("create_role_card", {"role": self.diag})
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(json.dumps(self.diag, sort_keys=True), before)
        role = out["role"]
        self.assertEqual(role["role_id"], self.diag["role_id"])
        self.assertEqual(role.get("schema"), "commons.transferable_role/v1")

    def test_create_role_card_role_id_override(self) -> None:
        raw = deepcopy(self.diag)
        out = self.eq.call(
            "create_role_card",
            {"role": raw, "role_id": "role.create-override.test"},
        )
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(out["role"]["role_id"], "role.create-override.test")

    def test_missing_role(self) -> None:
        miss = self.eq.call("create_role_card", {})
        self.assertFalse(miss.get("ok"))
        self.assertEqual(miss.get("error"), "missing_argument")


if __name__ == "__main__":
    unittest.main()
