"""UIOWA-002 tests. Run normal and with python -O."""

from __future__ import annotations

import copy
import hashlib
import os
import tempfile
import unittest
from decimal import Decimal

try:
    from .canonical import COMMERCIAL_BLOB, INTERVIEW_SESSIONS, ROLES, SPECIALIST_HOURS_IN_BASE
    from .cli import main as cli_main
    from .engine import schedule
    from .render import eval_formula_sheet, formula_sheet
    from .workbook import StaffingError, load_workbook, validate_workbook
except ImportError:
    from canonical import COMMERCIAL_BLOB, INTERVIEW_SESSIONS, ROLES, SPECIALIST_HOURS_IN_BASE
    from cli import main as cli_main
    from engine import schedule
    from render import eval_formula_sheet, formula_sheet
    from workbook import StaffingError, load_workbook, validate_workbook

HERE = os.path.dirname(os.path.abspath(__file__))
WB8 = os.path.join(HERE, "fixtures", "workbook_8w.json")
WB6 = os.path.join(HERE, "fixtures", "workbook_6w.json")


class ModelTests(unittest.TestCase):
    def test_eight_week_reconciles(self):
        r = schedule(load_workbook(WB8))
        self.assertEqual(r["horizon_weeks"], 8)
        self.assertEqual(r["specialist"]["productive_hours"], SPECIALIST_HOURS_IN_BASE)
        self.assertEqual(sum(r["specialist"]["weekly_total"], Decimal("0.00")), SPECIALIST_HOURS_IN_BASE)
        self.assertEqual(r["interview_sessions"], 12)
        self.assertEqual(r["participant_count"], 21)
        self.assertTrue(r["participant_count_is_not_session_count"])
        self.assertFalse(r["specialist"]["onsite_is_additive"])
        self.assertEqual(r["specialist"]["onsite_subset_hours"], Decimal("0.00"))
        self.assertEqual(r["specialist_location"], "remote")
        self.assertEqual(r["travel"], "excluded_from_base")

    def test_six_week_reconciles(self):
        r = schedule(load_workbook(WB6))
        self.assertEqual(r["horizon_weeks"], 6)
        self.assertEqual(r["specialist"]["productive_hours"], SPECIALIST_HOURS_IN_BASE)
        self.assertEqual(r["participant_count"], 18)
        self.assertEqual(r["interview_sessions"], 12)

    def test_headcount_does_not_change_sessions(self):
        wb = load_workbook(WB8)
        sessions = []
        for n in (18, 21, 24):
            wb["assumptions"]["participant_count"] = n
            r = schedule(wb)
            sessions.append(r["interview_sessions"])
            self.assertEqual(r["participant_count"], n)
        self.assertEqual(sessions, [12, 12, 12])

    def test_onsite_is_subset_not_added(self):
        r = schedule(load_workbook(WB8))
        productive = r["prime"]["productive_hours"]
        interviews = r["prime"]["task_hours"]["interviews"]
        review = r["prime"]["task_hours"]["review"]
        self.assertEqual(productive, interviews + review)
        self.assertLessEqual(r["prime"]["onsite_subset_hours"], interviews)
        self.assertEqual(sum(r["prime"]["weekly_total"], Decimal("0.00")), productive)

    def test_delay_propagates(self):
        wb = load_workbook(WB8)
        base = schedule(wb)
        wb["assumptions"]["evidence_access_delay_weeks"] = 2
        delayed = schedule(wb)
        self.assertGreaterEqual(delayed["specialist"]["rows"]["evidence_processing"]["earliest_week"], 2)
        self.assertGreaterEqual(
            delayed["specialist"]["rows"]["synthesis"]["earliest_week"],
            delayed["specialist"]["rows"]["evidence_processing"]["earliest_week"],
        )
        self.assertGreaterEqual(
            delayed["specialist"]["rows"]["synthesis"]["earliest_week"],
            base["specialist"]["rows"]["synthesis"]["earliest_week"],
        )

    def test_formula_parity(self):
        r = schedule(load_workbook(WB8))
        rows = formula_sheet(r)
        got = eval_formula_sheet(rows)
        for row, value in zip(rows, got):
            self.assertEqual(value, row["engine_total"])

    def test_roles_not_collapsed(self):
        self.assertEqual(ROLES["principal"], "prime")
        self.assertEqual(ROLES["specialist"], "subcontract")


class BoundaryTests(unittest.TestCase):
    def test_zero_capacity_refused(self):
        wb = load_workbook(WB8)
        wb["assumptions"]["specialist_capacity_hours_per_week"] = "0.00"
        with self.assertRaises(StaffingError):
            validate_workbook(wb)

    def test_overflow_not_silently_dropped(self):
        wb = load_workbook(WB8)
        wb["assumptions"]["specialist_capacity_hours_per_week"] = "5.00"
        with self.assertRaises(StaffingError) as ctx:
            schedule(wb)
        self.assertIn("overflow", str(ctx.exception))

    def test_hours_must_reconcile_to_160(self):
        wb = load_workbook(WB8)
        wb["assumptions"]["specialist_task_hours"]["preparation"] = "17.00"
        with self.assertRaises(StaffingError):
            validate_workbook(wb)

    def test_specialist_onsite_must_stay_zero(self):
        wb = load_workbook(WB8)
        wb["assumptions"]["specialist_onsite_subset_hours"] = "8.00"
        with self.assertRaises(StaffingError):
            validate_workbook(wb)

    def test_required_checks_are_not_assert(self):
        for name in ("engine.py", "workbook.py", "cli.py", "render.py"):
            with open(os.path.join(HERE, name), encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotRegex(src, r"(?m)^\s*assert ", msg=name)

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

    def test_cli_exit_zero(self):
        dest = os.path.join(tempfile.mkdtemp(prefix="uiowa002-"), "out")
        self.assertEqual(cli_main(["--workbook", WB8, "--out", dest]), 0)
        self.assertTrue(os.path.isfile(os.path.join(dest, "calendar.md")))

    def test_cli_overwrite_exit_two(self):
        dest = os.path.join(tempfile.mkdtemp(prefix="uiowa002-"), "out")
        self.assertEqual(cli_main(["--workbook", WB8, "--out", dest]), 0)
        self.assertEqual(cli_main(["--workbook", WB8, "--out", dest]), 2)

    def test_cli_overflow_exit_two(self):
        wb = load_workbook(WB8)
        wb["assumptions"]["specialist_capacity_hours_per_week"] = "5.00"
        path = os.path.join(tempfile.mkdtemp(prefix="uiowa002-"), "bad.json")
        import json

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(wb, fh)
        self.assertEqual(cli_main(["--workbook", path]), 2)


if __name__ == "__main__":
    unittest.main()
