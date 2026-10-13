#!/usr/bin/env python3
"""Hermetic: equipment inspect_role_card (TENON)."""

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


class InspectRoleEquipmentCardTests(unittest.TestCase):
    # tenon-r4-equipment-inspect-role-card-20260906-01

    def setUp(self) -> None:
        self.eq = GrokBotEquipment()
        self.diag = json.loads(DIAG.read_text(encoding="utf-8"))

    def test_tool_listed(self) -> None:
        names = {t["name"] for t in self.eq.tools()}
        self.assertIn("inspect_role_card", names)

    def test_inspect_normalizes_and_scrubs(self) -> None:
        dirty = deepcopy(self.diag)
        dirty["api_key"] = "should-never-persist"
        dirty["secret"] = "nope"
        out = self.eq.call("inspect_role_card", {"role": dirty})
        self.assertTrue(out.get("ok"), out)
        role = out["role"]
        self.assertEqual(role["role_id"], self.diag["role_id"])
        self.assertEqual(role["purpose"], self.diag["purpose"])
        self.assertEqual(role.get("schema"), "commons.transferable_role/v1")
        self.assertNotIn("api_key", role)
        self.assertNotIn("secret", role)

    def test_missing_role(self) -> None:
        miss = self.eq.call("inspect_role_card", {})
        self.assertFalse(miss.get("ok"))
        self.assertEqual(miss.get("error"), "missing_argument")


if __name__ == "__main__":
    unittest.main()
