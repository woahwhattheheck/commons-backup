"""UIOWA-133 tests. Run normal and with python -O."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

try:
    from .calculator import ScopeError, load_worksheet, quote
    from .catalog import BASELINE
    from .cli import main as cli_main
except ImportError:
    from calculator import ScopeError, load_worksheet, quote
    from catalog import BASELINE
    from cli import main as cli_main

HERE = os.path.dirname(os.path.abspath(__file__))
SCEN = os.path.join(HERE, "scenarios")


def _load(name):
    return load_worksheet(os.path.join(SCEN, name))


class ScenarioTests(unittest.TestCase):
    def test_additional_group(self):
        r = quote(_load("01_additional_group.json"))
        self.assertEqual(r["totals"]["incremental_hours"], 32)
        self.assertEqual(r["totals"]["incremental_usd"], 2400)
        self.assertEqual(r["totals"]["quoted_total_usd"], 26400)
        self.assertEqual(r["totals"]["status"], "PROPOSED_NOT_ACCEPTED")
        self.assertEqual(r["baseline"]["workshare_base_usd"], 24000)

    def test_extra_interview_qty_two(self):
        r = quote(_load("02_extra_interview.json"))
        self.assertEqual(r["totals"]["incremental_hours"], 24)
        self.assertEqual(r["totals"]["incremental_usd"], 1800)

    def test_new_domain(self):
        r = quote(_load("03_new_domain.json"))
        self.assertEqual(r["totals"]["incremental_usd"], 1800)
        self.assertEqual(r["totals"]["quoted_total_usd"], 25800)

    def test_additional_readout_uses_option(self):
        r = quote(_load("04_additional_readout.json"))
        self.assertEqual(r["totals"]["incremental_usd"], 4000)
        self.assertEqual(r["totals"]["optional_readout_usd"], 4000)

    def test_in_scope_correction_is_zero(self):
        r = quote(_load("05_mixed_with_correction.json"))
        corr = next(x for x in r["lines"] if x["id"] == "L3")
        self.assertEqual(corr["usd"], 0)
        self.assertEqual(corr["hours"], 0)
        self.assertEqual(corr["status"], "IN_SCOPE_NO_INCREMENT")
        # group + interview only
        self.assertEqual(r["totals"]["incremental_usd"], 2400 + 900)
        self.assertEqual(r["totals"]["incremental_hours"], 32 + 12)

    def test_onsite_is_hold_not_invented(self):
        r = quote(_load("06_onsite_hold.json"))
        self.assertIsNone(r["totals"]["incremental_usd"])
        self.assertIsNone(r["totals"]["quoted_total_usd"])
        self.assertEqual(r["totals"]["status"], "HOLD_MISSING_INPUTS")
        self.assertFalse(r["authority"]["travel"])
        self.assertFalse(r["authority"]["invoice"])
        codes = [i["code"] for i in r["issues"]]
        self.assertIn("ONSITE_TRAVEL_HOLD", codes)


class BoundaryTests(unittest.TestCase):
    def test_missing_quantity_refused(self):
        with self.assertRaises(ScopeError):
            quote(
                {
                    "schema": "uiowa-133-scope-change/1",
                    "lines": [{"id": "X", "type": "additional_group", "class": "added_scope"}],
                }
            )

    def test_unknown_type_refused(self):
        with self.assertRaises(ScopeError):
            quote(
                {
                    "schema": "uiowa-133-scope-change/1",
                    "lines": [
                        {
                            "id": "X",
                            "type": "magic_extra",
                            "class": "added_scope",
                            "quantity": 1,
                        }
                    ],
                }
            )

    def test_bool_quantity_refused(self):
        with self.assertRaises(ScopeError):
            quote(
                {
                    "schema": "uiowa-133-scope-change/1",
                    "lines": [
                        {
                            "id": "X",
                            "type": "additional_group",
                            "class": "added_scope",
                            "quantity": True,
                        }
                    ],
                }
            )

    def test_baseline_mismatch_is_error(self):
        r = quote(
            {
                "schema": "uiowa-133-scope-change/1",
                "baseline_workshare_usd": 25000,
                "lines": [],
            }
        )
        codes = [i["code"] for i in r["issues"]]
        self.assertIn("BASELINE_MISMATCH", codes)

    def test_roles_not_collapsed(self):
        self.assertEqual(BASELINE["roles"]["principal"], "prime")
        self.assertEqual(BASELINE["roles"]["specialist"], "subcontract")

    def test_required_checks_are_not_assert(self):
        with open(os.path.join(HERE, "calculator.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotRegex(src, r"(?m)^\s*assert ")

    def test_cli_group_exit_zero(self):
        out = tempfile.mkdtemp(prefix="uiowa133-")
        dest = os.path.join(out, "q")
        code = cli_main(
            ["--worksheet", os.path.join(SCEN, "01_additional_group.json"), "--out", dest]
        )
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(os.path.join(dest, "quote.md")))

    def test_cli_onsite_exit_one(self):
        out = os.path.join(tempfile.mkdtemp(prefix="uiowa133-"), "q")
        code = cli_main(
            ["--worksheet", os.path.join(SCEN, "06_onsite_hold.json"), "--out", out]
        )
        self.assertEqual(code, 1)

    def test_cli_overwrite_exit_two(self):
        dest = os.path.join(tempfile.mkdtemp(prefix="uiowa133-"), "q")
        cli_main(
            ["--worksheet", os.path.join(SCEN, "01_additional_group.json"), "--out", dest]
        )
        code = cli_main(
            ["--worksheet", os.path.join(SCEN, "01_additional_group.json"), "--out", dest]
        )
        self.assertEqual(code, 2)

    def test_blank_worksheet_is_baseline_only(self):
        blank = load_worksheet(os.path.join(HERE, "fixtures", "worksheet.json"))
        r = quote(blank)
        self.assertEqual(r["totals"]["incremental_usd"], 0)
        self.assertEqual(r["totals"]["quoted_total_usd"], 24000)


if __name__ == "__main__":
    unittest.main()
