#!/usr/bin/env python3
"""Hermetic: $199 diagnostic R4 fixture points at reply→cash + tip-shelf."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from roles import RoleStore

DIAGNOSTIC_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "synthetic_diagnostic_fulfillment_role.json"
)
REPLY_README = "revenue/reply_to_revenue/README.md"
REPLY_FUNNEL = "revenue/reply_to_revenue/funnel.json"
COMMERCE_PAGE = "commerce.html"
HANDOFF_FUTURE_FORD = (
    "revenue/reply_to_revenue/handoffs/future-ford-concord-devin-parker.json"
)
HANDOFF_MAC_HAIK = (
    "revenue/reply_to_revenue/handoffs/mac-haik-chevrolet-mike-sutton.json"
)
HANDOFF_LEXINGTON = (
    "revenue/reply_to_revenue/handoffs/lexington-recycle-center-julie-hatter.json"
)
HANDOFF_COMMUNITYCARE = (
    "revenue/reply_to_revenue/handoffs/communitycare-katherine-reyes.json"
)


class DiagnosticReplyCashPointerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RoleStore(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_diagnostic_fixture_points_at_reply_cash_and_tip_shelf(self) -> None:
        raw = json.loads(DIAGNOSTIC_FIXTURE.read_text(encoding="utf-8"))
        role = self.store.create(raw)
        pointers = {k["pointer"] for k in role["knowledge"]}
        self.assertIn(REPLY_README, pointers)
        self.assertIn(REPLY_FUNNEL, pointers)
        self.assertIn(COMMERCE_PAGE, pointers)
        self.assertIn(HANDOFF_FUTURE_FORD, pointers)
        self.assertIn(HANDOFF_MAC_HAIK, pointers)
        self.assertIn(HANDOFF_LEXINGTON, pointers)
        self.assertIn(HANDOFF_COMMUNITYCARE, pointers)
        # Live checkouts stay; no remint of handoff bodies.
        blob = json.dumps(role)
        self.assertIn("buy.stripe.com/3cIdR8gBf6379uF1Oy43S0b", blob)


if __name__ == "__main__":
    unittest.main()
