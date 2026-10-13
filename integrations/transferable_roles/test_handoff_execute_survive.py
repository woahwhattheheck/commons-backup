#!/usr/bin/env python3
"""Hermetic: role-gated executes survive transfer and export→import."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from handoff_execute import prove_successor_executes
from roles import RoleError, RoleStore
import cli as roles_cli

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CRM = FIXTURES / "synthetic_crm_followup_role.json"
DIAG = FIXTURES / "synthetic_diagnostic_fulfillment_role.json"
DIAG_CONTRACT = FIXTURES.parents[2] / "revenue/dealer_service_lead_rescue/contract.json"
DIAG_REFUND = json.loads(DIAG_CONTRACT.read_text(encoding="utf-8"))["commercial"]["refund"]


class HandoffExecuteSurviveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RoleStore(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_diagnostic_transfer_then_prove(self) -> None:
        role = self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))
        rid = role["role_id"]
        self.store.equip(rid, session_id="d-A", harness="hinge")
        self.store.transfer(
            rid,
            from_session_id="d-A",
            to_session_id="d-B",
            to_harness="rivet",
        )
        proof = prove_successor_executes(self.store, rid, diagnostic_slug="dealer")
        self.assertTrue(proof["ok"])
        self.assertIn("diagnostic-contract", proof["executes"])
        self.assertEqual(proof["executes"]["diagnostic-contract"]["slug"], "dealer")
        # rivet-r4-handoff-prove-diag-contract-diagnostic-usd-20260905-01
        self.assertEqual(
            proof["executes"]["diagnostic-contract"]["diagnostic_usd"], 199
        )
        # rivet-r4-handoff-prove-diag-receipt-fulfill-20260905-01
        self.assertIn("diagnostic-receipt", proof["executes"])
        self.assertEqual(proof["executes"]["diagnostic-receipt"]["slug"], "dealer")
        self.assertEqual(proof["executes"]["diagnostic-receipt"].get("cash_usd"), 0)
        self.assertIn("diagnostic-fulfill-deadline", proof["executes"])
        fulfill = proof["executes"]["diagnostic-fulfill-deadline"]
        self.assertEqual(fulfill["slug"], "dealer")
        self.assertTrue(fulfill.get("delivery_due_at"))
        # hinge-r4-handoff-prove-diag-sla-20260905-01
        self.assertIn("diagnostic-fulfill-sla", proof["executes"])
        sla = proof["executes"]["diagnostic-fulfill-sla"]
        self.assertEqual(sla["slug"], "dealer")
        self.assertEqual(sla["sla_status"], "OPEN")
        # rivet-r4-handoff-prove-diag-sla-diagnostic-usd-20260905-01
        self.assertEqual(sla["diagnostic_usd"], 199)
        self.assertEqual(sla["refund"], DIAG_REFUND)

        missed = prove_successor_executes(
            self.store,
            rid,
            diagnostic_slug="dealer",
            as_of="2026-09-10T10:00:00-04:00",
        )
        self.assertEqual(
            missed["executes"]["diagnostic-fulfill-sla"]["sla_status"], "MISSED"
        )
        self.assertEqual(
            missed["executes"]["diagnostic-fulfill-sla"]["diagnostic_usd"], 199
        )

        repair_proof = prove_successor_executes(
            self.store, rid, diagnostic_slug="repair"
        )
        self.assertTrue(repair_proof["ok"])
        self.assertIn("diagnostic-contract", repair_proof["executes"])
        # rivet-r4-handoff-prove-diag-contract-diagnostic-usd-20260905-01
        self.assertEqual(
            repair_proof["executes"]["diagnostic-contract"]["diagnostic_usd"], 199
        )
        self.assertNotIn("diagnostic-receipt", repair_proof["executes"])
        self.assertIn("diagnostic-fulfill-deadline", repair_proof["executes"])
        self.assertIn("diagnostic-fulfill-sla", repair_proof["executes"])

    def test_diagnostic_export_import_then_prove(self) -> None:
        # rivet-r4-handoff-prove-diag-export-import-20260905-01
        role = self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))
        rid = role["role_id"]
        self.store.equip(rid, session_id="d-exp-A", harness="hinge")
        package = self.store.export_package(rid)
        with tempfile.TemporaryDirectory() as fresh_dir:
            fresh = RoleStore(fresh_dir)
            imported = fresh.import_package(package)
            fresh.equip(
                imported["role_id"],
                session_id="d-exp-B",
                harness="rivet",
                seat="RIVET",
            )
            proof = prove_successor_executes(
                fresh, imported["role_id"], diagnostic_slug="dealer"
            )
            self.assertTrue(proof["ok"])
            self.assertEqual(proof["occupant_session"], "d-exp-B")
            self.assertIn("diagnostic-contract", proof["executes"])
            # rivet-r4-handoff-prove-diag-contract-diagnostic-usd-20260905-01
            self.assertEqual(
                proof["executes"]["diagnostic-contract"]["diagnostic_usd"], 199
            )
            self.assertIn("diagnostic-receipt", proof["executes"])
            self.assertIn("diagnostic-fulfill-deadline", proof["executes"])
            self.assertIn("diagnostic-fulfill-sla", proof["executes"])
            self.assertEqual(
                proof["executes"]["diagnostic-fulfill-sla"]["sla_status"], "OPEN"
            )
            # rivet-r4-handoff-prove-diag-sla-diagnostic-usd-20260905-01
            sla = proof["executes"]["diagnostic-fulfill-sla"]
            self.assertEqual(sla["diagnostic_usd"], 199)
            self.assertEqual(sla["refund"], DIAG_REFUND)

    def test_diagnostic_release_then_equip_prove(self) -> None:
        # rivet-r4-handoff-prove-release-equip-20260905-01
        role = self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))
        rid = role["role_id"]
        self.store.equip(rid, session_id="d-rel-A", harness="hinge")
        self.store.release(rid, from_session_id="d-rel-A")
        self.store.equip(rid, session_id="d-rel-B", harness="rivet")
        proof = prove_successor_executes(self.store, rid, diagnostic_slug="dealer")
        self.assertTrue(proof["ok"])
        self.assertEqual(proof["occupant_session"], "d-rel-B")
        self.assertIn("diagnostic-contract", proof["executes"])
        # rivet-r4-handoff-prove-diag-contract-diagnostic-usd-20260905-01
        self.assertEqual(
            proof["executes"]["diagnostic-contract"]["diagnostic_usd"], 199
        )
        self.assertIn("diagnostic-receipt", proof["executes"])
        self.assertIn("diagnostic-fulfill-deadline", proof["executes"])
        self.assertIn("diagnostic-fulfill-sla", proof["executes"])
        self.assertEqual(
            proof["executes"]["diagnostic-fulfill-sla"]["sla_status"], "OPEN"
        )
        # rivet-r4-handoff-prove-diag-sla-diagnostic-usd-20260905-01
        sla = proof["executes"]["diagnostic-fulfill-sla"]
        self.assertEqual(sla["diagnostic_usd"], 199)
        self.assertEqual(sla["refund"], DIAG_REFUND)

    def test_crm_refuses(self) -> None:
        role = self.store.create(json.loads(CRM.read_text(encoding="utf-8")))
        with self.assertRaises(RoleError):
            prove_successor_executes(self.store, role["role_id"])

    def test_cli_prove_handoff(self) -> None:
        store_dir = self._tmp.name
        with redirect_stdout(io.StringIO()):
            rc = roles_cli.main(
                ["--store", store_dir, "create", "--file", str(DIAG)]
            )
        self.assertEqual(rc, 0)
        rid = "role-synthetic-diagnostic-fulfillment-20260905"
        with redirect_stdout(io.StringIO()):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "equip",
                    rid,
                    "--session",
                    "cli-A",
                    "--harness",
                    "hinge",
                ]
            )
        self.assertEqual(rc, 0)
        cli = FIXTURES.parent / "cli.py"
        result = subprocess.run(
            [
                sys.executable,
                str(cli),
                "prove-handoff",
                rid,
                "--store",
                store_dir,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        proof = json.loads(result.stdout)
        self.assertTrue(proof["ok"])
        self.assertIn("diagnostic-contract", proof["executes"])
        self.assertIn("diagnostic-fulfill-sla", proof["executes"])
        self.assertEqual(proof["executes"]["diagnostic-fulfill-sla"]["diagnostic_usd"], 199)


if __name__ == "__main__":
    unittest.main()
