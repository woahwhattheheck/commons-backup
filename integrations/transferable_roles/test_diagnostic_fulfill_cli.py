#!/usr/bin/env python3
"""Hermetic: $199 diagnostic R4 CLI executes SLA deadline via landed calendar."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from diagnostic_contract import require_diagnostic_contract_tool
from diagnostic_fulfill import run_deadline
from roles import RoleError, RoleStore

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DIAG = FIXTURES / "synthetic_diagnostic_fulfillment_role.json"
CRM = FIXTURES / "synthetic_crm_followup_role.json"


class DiagnosticFulfillCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RoleStore(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_deadline_executes_for_each_slug(self) -> None:
        role = self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))
        tool = require_diagnostic_contract_tool(role)
        self.assertEqual(tool["name"], "diagnostic_contract")
        stamp = "2026-09-04T15:00:00-04:00"
        for slug in ("dealer", "referral", "repair", "plant"):
            out = run_deadline(role, slug=slug, usable_evidence_at=stamp)
            self.assertEqual(out["slug"], slug)
            self.assertEqual(out["usable_evidence_at"], stamp)
            # Friday 15:00 ET → Monday same wall clock.
            self.assertEqual(out["delivery_due_at"], "2026-09-07T15:00:00-04:00")
            self.assertIn("one business day", str(out["diagnostic_window"]).lower())
            self.assertEqual(out["diagnostic_usd"], 199)

    def test_crm_refuses(self) -> None:
        crm = self.store.create(json.loads(CRM.read_text(encoding="utf-8")))
        with self.assertRaises(RoleError):
            run_deadline(
                crm, slug="dealer", usable_evidence_at="2026-09-04T15:00:00-04:00"
            )

    def test_documented_command_runs_without_equipping(self) -> None:
        role = self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))
        self.assertIsNone(role["occupant"])
        before = {p.name: p.read_bytes() for p in Path(self._tmp.name).glob("*.json")}
        result = subprocess.run(
            [
                sys.executable,
                str(FIXTURES.parent / "cli.py"),
                "diagnostic-fulfill-deadline",
                role["role_id"],
                "--slug",
                "dealer",
                "--usable-evidence-at",
                "2026-09-04T15:00:00-04:00",
                "--store",
                self._tmp.name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out["delivery_due_at"], "2026-09-07T15:00:00-04:00")
        after = {p.name: p.read_bytes() for p in Path(self._tmp.name).glob("*.json")}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
