#!/usr/bin/env python3
"""Hermetic: open-obligations marks payment_capability on cash roles only."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from roles import RoleStore
import cli as roles_cli

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CRM = FIXTURES / "synthetic_crm_followup_role.json"
DIAG = FIXTURES / "synthetic_diagnostic_fulfillment_role.json"


class OpenObligationsCashMarkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RoleStore(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_mixed_store_marks_paid_roles_only(self) -> None:
        crm = self.store.create(json.loads(CRM.read_text(encoding="utf-8")))
        diagnostic = self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))

        crm_names = {r["name"] for r in crm["access_routes"]}
        self.assertNotIn("payment_capability", crm_names)
        self.assertIn(
            "payment_capability",
            {r["name"] for r in diagnostic["access_routes"]},
        )

        rows = self.store.list_open_obligations()
        by_role: dict[str, list[dict]] = {}
        for row in rows:
            by_role.setdefault(row["role_id"], []).append(row)

        for row in by_role[crm["role_id"]]:
            self.assertNotIn("payment_capability", row)
            self.assertNotIn("amount_usd", row)
            self.assertNotIn("refund", row)
        for row in by_role[diagnostic["role_id"]]:
            self.assertIs(row.get("payment_capability"), True)
            self.assertEqual(row.get("amount_usd"), 199)
            self.assertTrue(str(row.get("refund") or "").strip())

    def test_cli_open_obligations_preserves_cash_marker(self) -> None:
        store_dir = self._tmp.name
        with redirect_stdout(io.StringIO()):
            self.assertEqual(
                roles_cli.main(
                    ["--store", store_dir, "create", "--file", str(CRM)]
                ),
                0,
            )
            self.assertEqual(
                roles_cli.main(
                    ["--store", store_dir, "create", "--file", str(DIAG)]
                ),
                0,
            )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = roles_cli.main(["--store", store_dir, "open-obligations"])
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        rows = out["open_obligations"]
        crm_rows = [r for r in rows if r["role_id"].startswith("role-synthetic-crm")]
        diagnostic_rows = [
            r for r in rows if "diagnostic" in r["role_id"]
        ]
        self.assertTrue(crm_rows)
        self.assertTrue(diagnostic_rows)
        for row in crm_rows:
            self.assertNotIn("payment_capability", row)
            self.assertNotIn("amount_usd", row)
            self.assertNotIn("refund", row)
        for row in diagnostic_rows:
            self.assertIs(row.get("payment_capability"), True)
            self.assertEqual(row.get("amount_usd"), 199)
            self.assertTrue(str(row.get("refund") or "").strip())

    def test_cash_only_filters_to_paid_roles(self) -> None:
        self.store.create(json.loads(CRM.read_text(encoding="utf-8")))
        self.store.create(json.loads(DIAG.read_text(encoding="utf-8")))

        before = {p.name: p.read_bytes() for p in Path(self._tmp.name).glob("*.json")}
        all_rows = self.store.list_open_obligations()
        cash_rows = self.store.list_open_obligations(cash_only=True)
        self.assertTrue(all_rows)
        self.assertTrue(cash_rows)
        self.assertLess(len(cash_rows), len(all_rows))
        self.assertEqual(self.store.list_open_obligations(cash_only=False), all_rows)
        self.assertEqual(
            cash_rows, [row for row in all_rows if row.get("payment_capability") is True]
        )
        for row in cash_rows:
            self.assertIs(row.get("payment_capability"), True)
            self.assertFalse(row["role_id"].startswith("role-synthetic-crm"))
            if "diagnostic" in row["role_id"]:
                self.assertEqual(row.get("amount_usd"), 199)
                self.assertTrue(str(row.get("refund") or "").strip())

        store_dir = self._tmp.name
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = roles_cli.main(
                ["--store", store_dir, "open-obligations", "--cash-only"]
            )
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        cli_rows = out["open_obligations"]
        self.assertEqual(cli_rows, cash_rows)
        for row in cli_rows:
            self.assertIs(row.get("payment_capability"), True)
            if "diagnostic" in row["role_id"]:
                self.assertEqual(row.get("amount_usd"), 199)
                self.assertTrue(str(row.get("refund") or "").strip())
        after = {p.name: p.read_bytes() for p in Path(self._tmp.name).glob("*.json")}
        self.assertEqual(after, before)


    def test_cash_only_without_marked_roles_is_empty(self) -> None:
        crm = json.loads(CRM.read_text(encoding="utf-8"))
        crm["label"] = "Paid work label is not a payment capability marker"
        self.store.create(crm)
        self.assertTrue(self.store.list_open_obligations())
        self.assertEqual(self.store.list_open_obligations(cash_only=True), [])

        output = io.StringIO()
        with redirect_stdout(output):
            result = roles_cli.main(["--store", self._tmp.name, "open-obligations", "--cash-only"])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())["open_obligations"], [])

if __name__ == "__main__":
    unittest.main()
