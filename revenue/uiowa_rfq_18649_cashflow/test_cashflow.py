"""UIOWA-009 tests. Run normal and with python -O."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from decimal import Decimal

try:
    from .canonical import BASE_TOTAL, COMMERCIAL_BLOB, COMMERCIAL_PATH, OPTIONAL_READOUT, ROLES
    from .cli import main as cli_main
    from .engine import prime_university_register, project_all, project_scenario
    from .formulas import assert_parity, weekly_formula_sheet
    from .workbook import CashflowError, load_workbook, validate_workbook
except ImportError:
    from canonical import BASE_TOTAL, COMMERCIAL_BLOB, COMMERCIAL_PATH, OPTIONAL_READOUT, ROLES
    from cli import main as cli_main
    from engine import prime_university_register, project_all, project_scenario
    from formulas import assert_parity, weekly_formula_sheet
    from workbook import CashflowError, load_workbook, validate_workbook

HERE = os.path.dirname(os.path.abspath(__file__))
WB = os.path.join(HERE, "fixtures", "workbook.json")


def _load():
    return load_workbook(WB)


class ReconciliationTests(unittest.TestCase):
    def test_base_receipts_reconcile(self):
        for name, p in project_all(_load()).items():
            self.assertEqual(p["totals"]["base_receipts_usd"], BASE_TOTAL, name)
            self.assertEqual(p["totals"]["optional_receipts_usd"], Decimal("0.00"), name)
            self.assertFalse(p["optional_in_base"])

    def test_optional_excluded_until_enabled(self):
        wb = _load()
        self.assertFalse(wb["assumptions"]["optional_readout_enabled"])
        self.assertEqual(OPTIONAL_READOUT, Decimal("4000.00"))
        enabled = copy.deepcopy(wb)
        enabled["assumptions"]["optional_readout_enabled"] = True
        p = project_scenario(enabled, "prompt")
        self.assertEqual(p["totals"]["base_receipts_usd"], BASE_TOTAL)
        self.assertEqual(p["totals"]["optional_receipts_usd"], OPTIONAL_READOUT)

    def test_events_invoices_cash_are_distinct(self):
        p = project_scenario(_load(), "prompt")
        kick = next(m for m in p["milestones"] if m["id"] == "kickoff")
        self.assertEqual(kick["event_week"], 0)
        self.assertEqual(kick["invoice_week"], 0)
        self.assertEqual(kick["cash_week"], 1)
        self.assertNotEqual(kick["event_week"], kick["cash_week"])
        self.assertEqual(p["weekly"][0]["events"][0].split(":")[1], "written_authorization")
        self.assertEqual(p["weekly"][0]["invoice_ids"], ["kickoff"])
        self.assertEqual(p["weekly"][0]["cash_ids"], [])
        self.assertEqual(p["weekly"][1]["cash_ids"], ["kickoff"])

    def test_three_scenarios_differ(self):
        ps = project_all(_load())
        prompt_cash = [m["cash_week"] for m in ps["prompt"]["milestones"]]
        delayed_cash = [m["cash_week"] for m in ps["delayed_collection"]["milestones"]]
        extended_final = next(m for m in ps["extended_final_review"]["milestones"] if m["id"] == "final")
        prompt_final = next(m for m in ps["prompt"]["milestones"] if m["id"] == "final")
        self.assertNotEqual(prompt_cash, delayed_cash)
        self.assertGreater(extended_final["event_week"], prompt_final["event_week"])
        self.assertGreater(
            ps["delayed_collection"]["funding"]["peak_funding_before_opening_liquidity"],
            ps["prompt"]["funding"]["peak_funding_before_opening_liquidity"],
        )

    def test_trough_and_funding(self):
        p = project_scenario(_load(), "prompt")
        peak = p["funding"]["peak_funding_before_opening_liquidity"]
        need = p["funding"]["incremental_need_after_opening_liquidity"]
        self.assertGreater(peak, Decimal("0.00"))
        self.assertLess(need, peak)
        self.assertEqual(need, Decimal("0.00"))
        self.assertGreater(p["trough"]["pre_receipt_cash"], Decimal("0.00"))

    def test_imputed_effort_is_noncash(self):
        p = project_scenario(_load(), "prompt")
        self.assertGreater(p["totals"]["imputed_effort_noncash_usd"], Decimal("0.00"))
        # Imputed effort must not be subtracted from closing cash.
        costs = p["totals"]["cash_cost_usd"]
        receipts = p["totals"]["base_receipts_usd"]
        opening = p["opening_liquidity_usd"]
        expected = (opening + receipts - costs).quantize(Decimal("0.01"))
        self.assertEqual(p["totals"]["closing_cash_usd"], expected)

    def test_prime_register_does_not_fund_tjlabs(self):
        wb = _load()
        reg = prime_university_register(wb)
        self.assertFalse(reg["funds_tjlabs_cash_model"])
        self.assertIsNone(reg["rows"][0]["amount_usd"])
        p = project_scenario(wb, "prompt")
        for week in p["weekly"]:
            self.assertNotIn("PU-PLAN-01", week["cash_ids"])
            self.assertNotIn("PU-PLAN-01", week["invoice_ids"])

    def test_formula_parity(self):
        for p in project_all(_load()).values():
            self.assertTrue(assert_parity(p))
            sheet = weekly_formula_sheet(p)
            self.assertEqual(sheet["rows"][0]["D_pre_receipt_formula"], "opening-B0")


class BoundaryTests(unittest.TestCase):
    def test_out_of_horizon_refused(self):
        wb = _load()
        wb["assumptions"]["horizon_weeks"] = 8
        with self.assertRaises(CashflowError) as ctx:
            project_scenario(wb, "delayed_collection")
        self.assertIn("out-of-horizon", str(ctx.exception))

    def test_rewritten_milestone_refused(self):
        wb = _load()
        wb["assumptions"]["base_milestones"][0]["amount"] = "10000.00"
        with self.assertRaises(CashflowError):
            validate_workbook(wb)

    def test_bool_horizon_refused(self):
        wb = _load()
        wb["assumptions"]["horizon_weeks"] = True
        with self.assertRaises(CashflowError):
            validate_workbook(wb)

    def test_roles_not_collapsed(self):
        self.assertEqual(ROLES["principal"], "prime")
        self.assertEqual(ROLES["specialist"], "subcontract")

    def test_commercial_blob_pin(self):
        self.assertEqual(COMMERCIAL_BLOB, "b6e9ca58984c15d96b497f3bb51000992fdb9b5f")
        sibling = os.path.abspath(
            os.path.join(HERE, os.pardir, "uiowa_rfq_18649_workshare", "COMMERCIAL.md")
        )
        if os.path.isfile(sibling):
            with open(sibling, "rb") as fh:
                data = fh.read()
            blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
            self.assertEqual(blob, COMMERCIAL_BLOB)
        self.assertEqual(COMMERCIAL_PATH, "revenue/uiowa_rfq_18649_workshare/COMMERCIAL.md")

    def test_required_checks_are_not_assert(self):
        for name in ("engine.py", "workbook.py", "formulas.py", "cli.py", "render.py"):
            with open(os.path.join(HERE, name), encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotRegex(src, r"(?m)^\s*assert ", msg=name)

    def test_cli_exit_zero(self):
        dest = os.path.join(tempfile.mkdtemp(prefix="uiowa009-"), "out")
        self.assertEqual(cli_main(["--workbook", WB, "--out", dest]), 0)
        self.assertTrue(os.path.isfile(os.path.join(dest, "dashboard.md")))
        self.assertTrue(os.path.isfile(os.path.join(dest, "pack.json")))
        self.assertTrue(os.path.isfile(os.path.join(dest, "prompt", "weekly.csv")))
        with open(os.path.join(dest, "pack.json"), encoding="utf-8") as fh:
            pack = json.load(fh)
        self.assertFalse(pack["prime_university_register"]["funds_tjlabs_cash_model"])
        self.assertEqual(pack["projections"]["prompt"]["totals"]["base_receipts_usd"], "24000.00")

    def test_cli_overwrite_exit_two(self):
        dest = os.path.join(tempfile.mkdtemp(prefix="uiowa009-"), "out")
        self.assertEqual(cli_main(["--workbook", WB, "--out", dest]), 0)
        self.assertEqual(cli_main(["--workbook", WB, "--out", dest]), 2)


if __name__ == "__main__":
    unittest.main()
