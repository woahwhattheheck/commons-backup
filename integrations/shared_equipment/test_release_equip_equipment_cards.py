#!/usr/bin/env python3
"""Hermetic: equipment equip_role_card + release_occupant_card (TENON)."""

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


class ReleaseEquipEquipmentCardTests(unittest.TestCase):
    # tenon-r4-equipment-release-equip-cards-20260906-01

    def setUp(self) -> None:
        self.eq = GrokBotEquipment()
        self.diag = json.loads(DIAG.read_text(encoding="utf-8"))

    def test_tools_listed(self) -> None:
        names = {t["name"] for t in self.eq.tools()}
        self.assertIn("equip_role_card", names)
        self.assertIn("release_occupant_card", names)

    def test_equip_then_release(self) -> None:
        before = json.dumps(self.diag, sort_keys=True)
        equipped = self.eq.call(
            "equip_role_card",
            {
                "role": self.diag,
                "session_id": "sess-tenon-A",
                "harness": "cursor-tenon",
                "seat": "TENON",
            },
        )
        self.assertTrue(equipped.get("ok"), equipped)
        self.assertEqual(json.dumps(self.diag, sort_keys=True), before)
        role = equipped["role"]
        self.assertEqual(role["occupant"]["session_id"], "sess-tenon-A")
        self.assertEqual(role["occupant"]["seat"], "TENON")
        self.assertEqual(role["purpose"], self.diag["purpose"])

        released = self.eq.call(
            "release_occupant_card",
            {"role": role, "from_session_id": "sess-tenon-A"},
        )
        self.assertTrue(released.get("ok"), released)
        out = released["role"]
        self.assertIsNone(out.get("occupant"))
        self.assertEqual(out["purpose"], self.diag["purpose"])
        self.assertEqual(
            out["last_released"]["session_id"], "sess-tenon-A"
        )

    def test_equip_occupied_refuses(self) -> None:
        raw = deepcopy(self.diag)
        raw["occupant"] = {
            "session_id": "already",
            "harness": "hinge",
            "equipped_at": "2026-09-05T00:00:00Z",
        }
        out = self.eq.call(
            "equip_role_card",
            {
                "role": raw,
                "session_id": "sess-B",
                "harness": "tenon",
            },
        )
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "role_refused")

    def test_release_empty_refuses(self) -> None:
        out = self.eq.call(
            "release_occupant_card",
            {"role": self.diag},
        )
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "role_refused")

    def test_missing_args(self) -> None:
        miss = self.eq.call(
            "equip_role_card",
            {"role": self.diag, "session_id": "x"},
        )
        self.assertFalse(miss.get("ok"))
        self.assertEqual(miss.get("error"), "missing_argument")


if __name__ == "__main__":
    unittest.main()
