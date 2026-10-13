#!/usr/bin/env python3
"""Regression tests for the UIOWA-034 interview-notes adapter.

Run:  python3 -m unittest -v   (from this directory)
"""

import copy
import json
import os
import tempfile
import unittest

import interview_adapter as ia

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SESSION = os.path.join(DATA, "session.json")
HOSTILE = os.path.join(DATA, "session_hostile.json")
NAMED = os.path.join(DATA, "session_named.json")
REGISTER = os.path.join(DATA, "source_register.json")


def by_note(records, note_id):
    return next(r for r in records if r["record_id"].endswith("-" + note_id))


def codes(diagnostics, note_id=None):
    return {d["code"] for d in diagnostics
            if note_id is None or d["note_id"] == note_id}


class RealSession(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = ia.load_json(SESSION)
        cls.register = ia.load_json(REGISTER)
        cls.records, cls.diagnostics, cls.coverage = ia.adapt(cls.session, cls.register)

    def test_only_corroborated_records_may_support_a_finding(self):
        """The completion condition, as an assertion: a participant's statement
        never becomes a verified observation on its own."""
        for record in self.records:
            self.assertEqual(record["supports_finding"],
                             record["status"] == ia.CORROBORATED, record["record_id"])
        supporting = [r for r in self.records if r["supports_finding"]]
        self.assertTrue(supporting)
        for record in supporting:
            self.assertTrue(record["corroborating_artifact"])
            self.assertTrue(record["artifact_locator"])

    def test_all_four_statuses_occur(self):
        self.assertEqual({r["status"] for r in self.records},
                         {ia.STATED, ia.ILLUSTRATED, ia.CORROBORATED, ia.DISPUTED})

    def test_a_disagreement_keeps_both_sides_and_promotes_neither(self):
        """A disagreement is the most informative thing an interview produces and
        the easiest to lose: resolve it and you have invented a finding, drop it
        and you have hidden one."""
        one, two = by_note(self.records, "N1"), by_note(self.records, "N2")
        self.assertEqual(one["status"], ia.DISPUTED)
        self.assertEqual(two["status"], ia.DISPUTED)
        self.assertFalse(one["supports_finding"])
        self.assertFalse(two["supports_finding"])
        self.assertIn("N2", one["disputed_with"])
        self.assertIn("N1", two["disputed_with"])

    def test_a_corroborated_statement_that_is_contradicted_is_not_promoted(self):
        """N1 carries an artifact AND is contradicted by N2. The artifact is a
        pointer for a human, not a verdict the adapter may reach."""
        one = by_note(self.records, "N1")
        self.assertEqual(one["status"], ia.DISPUTED)
        self.assertFalse(one["supports_finding"])
        self.assertIn("SRC-ESS-REL-LOG", one["basis"])
        self.assertIn("does not decide", one["basis"])

    def test_disagreement_is_marked_on_the_side_that_did_not_record_it(self):
        """N8 does not know it is contradicted. Unmarked, it would export as
        settled evidence."""
        self.assertIsNone(self.session["notes"][7].get("disagrees_with")
                          if self.session["notes"][7]["note_id"] == "N8" else "x")
        eight = by_note(self.records, "N8")
        self.assertEqual(eight["status"], ia.DISPUTED)
        self.assertIn("DISAGREEMENT_MADE_MUTUAL", codes(self.diagnostics, "N8"))

    def test_a_habit_is_not_a_concrete_example(self):
        five = by_note(self.records, "N5")
        self.assertEqual(five["status"], ia.STATED)
        self.assertIn("VAGUE_EXAMPLE", codes(self.diagnostics, "N5"))

    def test_a_specific_example_reaches_illustrated_but_no_further(self):
        eleven = by_note(self.records, "N11")
        self.assertEqual(eleven["status"], ia.ILLUSTRATED)
        self.assertFalse(eleven["supports_finding"])

    def test_every_record_carries_a_role_and_no_individual(self):
        for record in self.records:
            self.assertTrue(record["role"])
            for key in ia.FORBIDDEN_KEYS:
                self.assertNotIn(key, record)

    def test_basis_is_recorded_for_every_record(self):
        for record in self.records:
            self.assertTrue(record["basis"], record["record_id"])

    def test_no_errors_on_the_real_session(self):
        self.assertEqual([d for d in self.diagnostics if d["severity"] == ia.ERROR], [])


class HostileSession(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.diagnostics, cls.coverage = ia.adapt(
            ia.load_json(HOSTILE), ia.load_json(REGISTER))

    def test_unresolvable_artifact_downgrades_instead_of_corroborating(self):
        self.assertIn("ARTIFACT_NOT_IN_REGISTER", codes(self.diagnostics, "H1"))
        one = by_note(self.records, "H1")
        self.assertNotEqual(one["status"], ia.CORROBORATED)
        self.assertFalse(one["supports_finding"])
        self.assertIsNone(one["corroborating_artifact"])

    def test_an_interview_cannot_corroborate_interview_testimony(self):
        self.assertIn("SELF_CORROBORATION", codes(self.diagnostics, "H2"))
        two = by_note(self.records, "H2")
        self.assertFalse(two["supports_finding"])

    def test_disagreement_pointing_at_a_missing_note_is_an_error(self):
        self.assertIn("DISAGREEMENT_TARGET_MISSING", codes(self.diagnostics, "H3"))

    def test_unknown_participant_and_question_are_named(self):
        self.assertIn("UNKNOWN_PARTICIPANT", codes(self.diagnostics, "H4"))
        self.assertIn("UNKNOWN_QUESTION", codes(self.diagnostics, "H5"))
        self.assertNotIn("H4", [r["record_id"].split("-")[-1] for r in self.records])

    def test_one_sided_disagreement_marks_both_even_when_one_has_an_artifact(self):
        seven, eight = by_note(self.records, "H7"), by_note(self.records, "H8")
        self.assertEqual(seven["status"], ia.DISPUTED)
        self.assertEqual(eight["status"], ia.DISPUTED)
        self.assertFalse(eight["supports_finding"])
        self.assertIn("SRC-ESS-TEST-RUN", eight["basis"])

    def test_nothing_supports_a_finding_in_the_hostile_session(self):
        self.assertEqual([r for r in self.records if r["supports_finding"]], [])

    def test_a_question_nobody_answered_is_not_covered_not_a_gap(self):
        q3 = next(c for c in self.coverage if c["question_id"] == "Q3")
        self.assertEqual(q3["answered_by"], [])
        self.assertEqual(sorted(q3["not_covered_by"]), ["P1", "P2"])
        message = [d["message"] for d in self.diagnostics
                   if d["code"] == "NOT_COVERED" and d["note_id"] == "Q3"][0]
        self.assertIn("not a finding about the practice", message)


class PersonalIdentifiers(unittest.TestCase):
    def test_a_session_carrying_a_name_is_refused_not_stripped(self):
        with self.assertRaises(ia.LoadError) as ctx:
            ia.load_json(NAMED)
        self.assertIn("ROLES, not individuals", str(ctx.exception))

    def test_a_forbidden_key_is_caught_at_any_depth(self):
        session = ia.load_json(SESSION)
        deep = copy.deepcopy(session)
        deep["notes"][0]["email"] = "someone@example.invalid"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "deep.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(deep, fh)
            with self.assertRaises(ia.LoadError):
                ia.load_json(path)

    def test_cli_refuses_rather_than_importing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                ia.main(["import", "--session", NAMED, "--register", REGISTER,
                         "--out", tmp]), 2)
            self.assertFalse(os.path.exists(os.path.join(tmp, "evidence_records.json")))


class Output(unittest.TestCase):
    def test_csv_is_spreadsheet_safe_and_keeps_null_distinct(self):
        self.assertEqual(ia.csv_cell("=SUM(A1)"), "'=SUM(A1)")
        self.assertEqual(ia.csv_cell(None), "\\N")
        self.assertEqual(ia.csv_cell(""), "")
        self.assertEqual(ia.csv_cell(True), "true")
        self.assertEqual(ia.csv_cell(False), "false")
        self.assertEqual(len({ia.csv_cell(None), ia.csv_cell(""), ia.csv_cell("NA")}), 3)

    def test_generated_csv_has_one_row_per_record_and_no_formula_cell(self):
        import csv as _csv
        with tempfile.TemporaryDirectory() as tmp:
            records, _, _ = ia.build(SESSION, REGISTER, tmp)
            with open(os.path.join(tmp, "evidence_records.csv"),
                      encoding="utf-8", newline="") as fh:
                rows = list(_csv.reader(fh))
        self.assertEqual(rows[0], ia.RECORD_COLUMNS)
        self.assertEqual(len(rows) - 1, len(records))
        for row in rows[1:]:
            for cell in row:
                self.assertFalse(cell.startswith(("=", "+", "@")), cell[:40])

    def test_report_states_the_rule_and_names_the_uncovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            ia.build(HOSTILE, REGISTER, tmp)
            with open(os.path.join(tmp, "session_report.md"), encoding="utf-8") as fh:
                text = fh.read()
        self.assertIn("FICTION", text)
        self.assertIn("is testimony", text)
        self.assertIn("not evidence of a gap in it", text)
        self.assertIn("both notes retained", text.lower())

    def test_build_is_deterministic(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            ia.build(SESSION, REGISTER, a)
            ia.build(SESSION, REGISTER, b)
            for name in ("evidence_records.json", "evidence_records.csv",
                         "session_report.md"):
                with open(os.path.join(a, name), "rb") as fh:
                    first = fh.read()
                with open(os.path.join(b, name), "rb") as fh:
                    second = fh.read()
                self.assertEqual(first, second, name)

    def test_check_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(ia.main(["check", "--session", SESSION,
                                      "--register", REGISTER, "--out", tmp]), 0)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(ia.main(["check", "--session", HOSTILE,
                                      "--register", REGISTER, "--out", tmp]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
