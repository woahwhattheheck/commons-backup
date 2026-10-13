#!/usr/bin/env python3
"""Hermetic: equipment transfer_role_card (TENON)."""

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


class TransferRoleEquipmentCardTests(unittest.TestCase):
    # tenon-r4-equipment-transfer-role-card-20260906-01

    def setUp(self) -> None:
        self.eq = GrokBotEquipment()
        self.diag = json.loads(DIAG.read_text(encoding="utf-8"))

    def test_tool_listed(self) -> None:
        names = {t["name"] for t in self.eq.tools()}
        self.assertIn("transfer_role_card", names)

    def test_transfer_moves_occupant(self) -> None:
        occupied = deepcopy(self.diag)
        occupied["occupant"] = {
            "session_id": "sess-A",
            "harness": "hinge",
            "seat": "HINGE",
            "equipped_at": "2026-09-05T12:00:00Z",
        }
        out = self.eq.call(
            "transfer_role_card",
            {
                "role": occupied,
                "from_session_id": "sess-A",
                "to_session_id": "sess-B",
                "to_harness": "cursor-tenon",
                "seat": "TENON",
            },
        )
        self.assertTrue(out.get("ok"), out)
        role = out["role"]
        self.assertEqual(role["occupant"]["session_id"], "sess-B")
        self.assertEqual(role["occupant"]["harness"], "cursor-tenon")
        self.assertEqual(role["occupant"]["seat"], "TENON")
        self.assertEqual(role["occupant"]["prior_session_id"], "sess-A")
        self.assertEqual(role["purpose"], self.diag["purpose"])
        self.assertGreaterEqual(int(role.get("transfer_count") or 0), 1)

    def test_transfer_without_occupant_refuses(self) -> None:
        out = self.eq.call(
            "transfer_role_card",
            {
                "role": self.diag,
                "to_session_id": "sess-B",
                "to_harness": "tenon",
            },
        )
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "role_refused")

    def test_missing_args(self) -> None:
        occupied = deepcopy(self.diag)
        occupied["occupant"] = {
            "session_id": "sess-A",
            "harness": "hinge",
            "equipped_at": "2026-09-05T12:00:00Z",
        }
        miss = self.eq.call(
            "transfer_role_card",
            {"role": occupied, "to_session_id": "sess-B"},
        )
        self.assertFalse(miss.get("ok"))
        self.assertEqual(miss.get("error"), "missing_argument")


if __name__ == "__main__":
    unittest.main()
