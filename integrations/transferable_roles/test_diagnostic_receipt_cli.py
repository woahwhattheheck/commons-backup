#!/usr/bin/env python3
"""Hermetic: diagnostic role loads landed receipt.json by slug via CLI glue."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from diagnostic_receipt import (
    SLUG_TO_RECEIPT,
    load_receipt_from_role,
    require_diagnostic_receipt_tool,
)
from roles import RoleError, RoleStore

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DIAG = FIXTURES / "synthetic_diagnostic_fulfillment_role.json"
CRM = FIXTURES / "synthetic_crm_followup_role.json"


class DiagnosticReceiptCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RoleStore(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_diagnostic_role_loads_each_slug(self) -> None:
        role = self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))
        tool = require_diagnostic_receipt_tool(role)
        self.assertEqual(tool["name"], "diagnostic_receipt")
        for slug, pointer in SLUG_TO_RECEIPT.items():
            card = load_receipt_from_role(role, slug=slug)
            self.assertEqual(card["slug"], slug)
            self.assertEqual(card["pointer"], pointer)
            self.assertTrue(card.get("receipt_id"))
            self.assertTrue(card.get("status"))
            self.assertEqual(card.get("cash_usd"), 0)
            self.assertIs(card.get("payment_verified"), False)

    def test_documented_cli_loads_all_receipts_without_equipping(self) -> None:
        role = self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))
        self.assertIsNone(role["occupant"])
        cli = FIXTURES.parent / "cli.py"
        before = {p.name: p.read_bytes() for p in Path(self._tmp.name).glob("*.json")}
        for slug in SLUG_TO_RECEIPT:
            with self.subTest(slug=slug):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(cli),
                        "diagnostic-receipt",
                        role["role_id"],
                        "--slug",
                        slug,
                        "--store",
                        self._tmp.name,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                card = json.loads(result.stdout)
                self.assertEqual(card["slug"], slug)
                self.assertEqual(card["cash_usd"], 0)
                self.assertIs(card["payment_verified"], False)
                self.assertTrue(card["status"])
                self.assertTrue(card["receipt_id"])
        after = {p.name: p.read_bytes() for p in Path(self._tmp.name).glob("*.json")}
        self.assertEqual(after, before)

    def test_crm_refuses(self) -> None:
        crm = self.store.create(json.loads(CRM.read_text(encoding="utf-8")))
        with self.assertRaises(RoleError):
            require_diagnostic_receipt_tool(crm)
        with self.assertRaises(RoleError):
            load_receipt_from_role(crm, slug="dealer")

    def test_repair_and_unknown_slug_refuse(self) -> None:
        role = self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))
        with self.assertRaises(RoleError):
            load_receipt_from_role(role, slug="repair")
        with self.assertRaises(RoleError):
            load_receipt_from_role(role, slug="not-a-slug")


if __name__ == "__main__":
    unittest.main()
