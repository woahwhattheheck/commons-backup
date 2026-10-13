#!/usr/bin/env python3
"""Hermetic: equipment bind/unbind access_route cards (TENON)."""

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
ROUTE = "grokbot_control_g2"


class BindUnbindRouteEquipmentCardTests(unittest.TestCase):
    # tenon-r4-equipment-bind-unbind-route-cards-20260906-01

    def setUp(self) -> None:
        self.eq = GrokBotEquipment()
        self.diag = json.loads(DIAG.read_text(encoding="utf-8"))

    def test_tools_listed(self) -> None:
        names = {t["name"] for t in self.eq.tools()}
        self.assertIn("bind_access_route_card", names)
        self.assertIn("unbind_access_route_card", names)

    def test_bind_stamps_recover_fields(self) -> None:
        out = self.eq.call(
            "bind_access_route_card",
            {
                "role": self.diag,
                "route_name": ROUTE,
                "session_id": "sess-bind-1",
                "last_run_id": "run-99",
            },
        )
        self.assertTrue(out.get("ok"), out)
        role = out["role"]
        route = next(r for r in role["access_routes"] if r["name"] == ROUTE)
        self.assertEqual(route["session_id"], "sess-bind-1")
        self.assertEqual(route["last_run_id"], "run-99")
        self.assertEqual(route.get("pool_id"), "grokbot")
        self.assertEqual(role["purpose"], self.diag["purpose"])

    def test_unbind_clears_default_fields(self) -> None:
        bound = deepcopy(self.diag)
        for route in bound["access_routes"]:
            if route["name"] == ROUTE:
                route["session_id"] = "sess-bound"
                route["last_run_id"] = "run-bound"
        out = self.eq.call(
            "unbind_access_route_card",
            {"role": bound, "route_name": ROUTE},
        )
        self.assertTrue(out.get("ok"), out)
        role = out["role"]
        route = next(r for r in role["access_routes"] if r["name"] == ROUTE)
        self.assertNotIn("session_id", route)
        self.assertNotIn("last_run_id", route)
        self.assertEqual(route.get("pool_id"), "grokbot")

    def test_bind_missing_stamp_refuses(self) -> None:
        out = self.eq.call(
            "bind_access_route_card",
            {"role": self.diag, "route_name": ROUTE},
        )
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "role_refused")

    def test_missing_args(self) -> None:
        miss = self.eq.call(
            "bind_access_route_card",
            {"role": self.diag, "session_id": "x"},
        )
        self.assertFalse(miss.get("ok"))
        self.assertEqual(miss.get("error"), "missing_argument")


if __name__ == "__main__":
    unittest.main()
