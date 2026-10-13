#!/usr/bin/env python3
"""Hermetic: diagnostic role loads landed contract.json by slug via CLI glue."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from diagnostic_contract import (
    SLUG_TO_CONTRACT,
    load_contract_from_role,
    require_diagnostic_contract_tool,
)
from roles import RoleError, RoleStore

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DIAG = FIXTURES / "synthetic_diagnostic_fulfillment_role.json"
CRM = FIXTURES / "synthetic_crm_followup_role.json"


class DiagnosticContractCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RoleStore(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_diagnostic_role_loads_each_slug(self) -> None:
        role = self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))
        tool = require_diagnostic_contract_tool(role)
        self.assertEqual(tool["name"], "diagnostic_contract")
        for slug, pointer in SLUG_TO_CONTRACT.items():
            card = load_contract_from_role(role, slug=slug)
            self.assertEqual(card["slug"], slug)
            self.assertEqual(card["pointer"], pointer)
            self.assertTrue(card["id"])
            self.assertEqual(card["diagnostic_usd"], 199)
            self.assertIn("one business day", str(card.get("diagnostic_window") or ""))

    def test_repair_card_preserves_its_distinct_source_schema(self) -> None:
        role = self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))
        card = load_contract_from_role(role, slug="repair")
        source = json.loads(
            (FIXTURES.parents[2] / SLUG_TO_CONTRACT["repair"]).read_text(encoding="utf-8")
        )
        self.assertEqual(card["refund"], source["offer"]["refund"])
        self.assertEqual(card["acceptance"], source["acceptance"])
        self.assertEqual(card["acceptance_count"], len(source["acceptance"]))
        self.assertEqual(card["scope"], source["scope"])
        self.assertEqual(card["accepted_terminal_states"], source["accepted_terminal_states"])

    def test_documented_cli_loads_all_contracts_without_equipping(self) -> None:
        role = self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))
        self.assertIsNone(role["occupant"])
        cli = FIXTURES.parent / "cli.py"
        before = {p.name: p.read_bytes() for p in Path(self._tmp.name).glob("*.json")}
        for slug in SLUG_TO_CONTRACT:
            with self.subTest(slug=slug):
                result = subprocess.run(
                    [sys.executable, str(cli), "diagnostic-contract", role["role_id"],
                     "--slug", slug, "--store", self._tmp.name],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                card = json.loads(result.stdout)
                self.assertEqual(card["diagnostic_usd"], 199)
                self.assertIn("one business day", card["diagnostic_window"])
                self.assertTrue(card["refund"])
                self.assertGreater(card["acceptance_count"], 0)
        after = {p.name: p.read_bytes() for p in Path(self._tmp.name).glob("*.json")}
        self.assertEqual(after, before)

    def test_crm_refuses(self) -> None:
        crm = self.store.create(json.loads(CRM.read_text(encoding="utf-8")))
        with self.assertRaises(RoleError):
            require_diagnostic_contract_tool(crm)
        with self.assertRaises(RoleError):
            load_contract_from_role(crm, slug="dealer")

    def test_unknown_slug_refuses(self) -> None:
        role = self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))
        with self.assertRaises(RoleError):
            load_contract_from_role(role, slug="not-a-slug")


if __name__ == "__main__":
    unittest.main()
