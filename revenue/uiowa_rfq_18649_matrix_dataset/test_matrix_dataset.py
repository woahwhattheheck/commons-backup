#!/usr/bin/env python3
"""Tests for the editable twelve-cell assessment dataset (UIOWA-035).

Run:  python3 -m unittest -v test_matrix_dataset.py

`UnassessedIsNotALowScoreTests` is the class the order turns on. Everything else
could pass and the tool would still be wrong if a blank rank came back as a zero.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import matrix_dataset as md  # noqa: E402
import make_dataset as mk  # noqa: E402


class TwelveCellsTests(unittest.TestCase):
    def setUp(self):
        self.m = mk.build()

    def test_an_empty_matrix_already_holds_twelve_cells(self):
        e = md.Matrix.empty()
        self.assertEqual(12, len(e.cells))
        self.assertEqual([], [c for c in e.ordered() if c.assessment_status != md.UNASSESSED])

    def test_all_twelve_cells_are_populated(self):
        self.assertEqual(12, len(self.m.cells))
        for g in md.GROUPS:
            for a in md.AREAS:
                with self.subTest(cell=f"{g}/{a}"):
                    self.assertIn((g, a), self.m.cells)

    def test_the_populated_dataset_validates(self):
        issues = self.m.validate()
        self.assertEqual([], issues, "\n".join(issues))

    def test_a_missing_cell_is_an_error_not_an_omission(self):
        del self.m.cells[("RIS", "security")]
        issues = self.m.validate()
        self.assertTrue(any("is missing" in i for i in issues))

    def test_the_dataset_carries_all_three_non_rank_reasons(self):
        statuses = {c.assessment_status for c in self.m.ordered()}
        for s in md.NON_RANK_STATUSES:
            with self.subTest(status=s):
                self.assertIn(s, statuses)

    def test_counts_add_up_to_twelve(self):
        self.assertEqual(12, sum(self.m.counts().values()))


class UnassessedIsNotALowScoreTests(unittest.TestCase):
    """The order's completion condition, asserted from every angle."""

    def setUp(self):
        self.m = mk.build()
        self.td = tempfile.mkdtemp()

    def test_non_rank_cells_carry_no_rank_and_no_label(self):
        for c in self.m.ordered():
            if c.assessment_status in md.NON_RANK_STATUSES:
                with self.subTest(cell=f"{c.group}/{c.area}"):
                    self.assertIsNone(c.maturity_rank)
                    self.assertEqual("", c.maturity_label)
                    self.assertFalse(c.is_ranked())

    def test_a_blank_rank_reopens_as_none_not_zero(self):
        """The exact failure the order names: CSV writes '', something reads 0."""
        path = md.save_csv(self.m, os.path.join(self.td, "m.csv"))
        with open(path, newline="", encoding="utf-8") as f:
            rows = {(r["group"], r["area"]): r for r in csv.DictReader(f)}
        self.assertEqual("", rows[("RIS", "ai_readiness")]["maturity_rank"])
        back = md.load_csv(path)
        cell = back.get("RIS", "ai_readiness")
        self.assertIsNone(cell.maturity_rank)
        self.assertNotEqual(0, cell.maturity_rank)
        self.assertEqual(md.UNASSESSED, cell.assessment_status)

    def test_a_blank_rank_reopens_as_none_through_json_too(self):
        path = md.save_json(self.m, os.path.join(self.td, "m.json"))
        back = md.load_json(path)
        self.assertIsNone(back.get("RIS", "ai_readiness").maturity_rank)
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        cell = next(c for c in payload["cells"]
                    if c["group"] == "RIS" and c["area"] == "ai_readiness")
        self.assertIsNone(cell["maturity_rank"], "JSON must carry null, not 0")

    def test_an_unranked_cell_never_appears_in_a_ranking(self):
        ranked = self.m.ranked_cells()
        self.assertEqual(9, len(ranked))
        for c in ranked:
            self.assertIsNotNone(c.maturity_rank)
        keys = {c.key for c in ranked}
        self.assertNotIn(("RIS", "ai_readiness"), keys)
        self.assertNotIn(("IAM", "ai_readiness"), keys)
        self.assertNotIn(("RIS", "deployment"), keys)

    def test_sorting_by_rank_cannot_put_an_unassessed_cell_at_the_bottom(self):
        """Sorting the ranked set is safe; sorting all twelve by rank would need
        a None-to-number coercion, which is the bug."""
        ordered = sorted(self.m.ranked_cells(), key=lambda c: c.maturity_rank)
        self.assertEqual(1, ordered[0].maturity_rank)
        self.assertEqual(("ESS", "ai_readiness"), ordered[0].key,
                         "the lowest ranked cell must be a real level-1 finding")
        self.assertTrue(all(c.assessment_status == md.ASSESSED for c in ordered))

    def test_a_level_one_finding_and_an_unassessed_cell_are_distinguishable(self):
        absent = self.m.get("ESS", "ai_readiness")
        unassessed = self.m.get("RIS", "ai_readiness")
        self.assertEqual(md.ASSESSED, absent.assessment_status)
        self.assertEqual(1, absent.maturity_rank)
        self.assertEqual(md.UNASSESSED, unassessed.assessment_status)
        self.assertIsNone(unassessed.maturity_rank)
        grid = md.render_grid(self.m)
        self.assertIn("1 Absent", grid)
        self.assertIn("- not assessed", grid)

    def test_the_three_non_rank_reasons_render_differently_from_each_other(self):
        grid = md.render_grid(self.m)
        for text in ("- not assessed", "- not applicable", "- insufficient evidence"):
            with self.subTest(text=text):
                self.assertIn(text, grid)

    def test_setting_a_rank_on_a_non_assessed_cell_is_refused(self):
        for status in md.NON_RANK_STATUSES:
            with self.subTest(status=status):
                m = mk.build()
                with self.assertRaises(md.DatasetError):
                    md.edit_cell(m, "RIS", "ai_readiness",
                                 assessment_status=status, maturity_rank=1,
                                 maturity_label="Absent")

    def test_demoting_a_cell_to_unassessed_drops_its_rank(self):
        """A stale rank left behind is exactly what an exporter would pick up."""
        m = mk.build()
        self.assertEqual(5, m.get("IAM", "security").maturity_rank)
        md.edit_cell(m, "IAM", "security", assessment_status=md.UNASSESSED,
                     follow_up_question="Re-open with the identity group.")
        c = m.get("IAM", "security")
        self.assertIsNone(c.maturity_rank)
        self.assertEqual("", c.maturity_label)
        self.assertEqual([], c.validate())

    def test_a_non_numeric_rank_is_refused_rather_than_coerced(self):
        with self.assertRaises(md.DatasetError) as ctx:
            md.Cell.from_row({"group": "ESS", "area": "security",
                              "assessment_status": md.ASSESSED, "maturity_rank": "n/a"})
        self.assertIn("not coerced to 0", str(ctx.exception))

    def test_a_rank_outside_one_to_five_is_an_error(self):
        c = md.Cell.from_row({"group": "ESS", "area": "security",
                              "assessment_status": md.ASSESSED, "maturity_rank": "0",
                              "evidence_refs": "EV-1", "rationale": "x"})
        self.assertTrue(any("not 1-5" in i for i in c.validate()))

    def test_an_unassessed_cell_must_carry_its_resolving_question(self):
        c = md.Cell(group="ESS", area="security", assessment_status=md.UNASSESSED)
        self.assertTrue(any("would resolve it" in i for i in c.validate()))


class EvidenceLinkTests(unittest.TestCase):
    def setUp(self):
        self.m = mk.build()
        self.td = tempfile.mkdtemp()

    def test_every_assessed_cell_carries_at_least_one_evidence_link(self):
        for c in self.m.ordered():
            if c.assessment_status == md.ASSESSED:
                with self.subTest(cell=f"{c.group}/{c.area}"):
                    self.assertTrue(c.evidence_refs)

    def test_an_assessed_cell_with_no_evidence_is_an_error(self):
        c = md.Cell(group="ESS", area="security", assessment_status=md.ASSESSED,
                    maturity_rank=3, maturity_label="Practised", rationale="x")
        self.assertTrue(any("no evidence link" in i for i in c.validate()))

    def test_multiple_evidence_links_survive_the_csv_round_trip(self):
        cell = self.m.get("IAM", "security")
        self.assertEqual(2, len(cell.evidence_refs))
        path = md.save_csv(self.m, os.path.join(self.td, "m.csv"))
        back = md.load_csv(path)
        self.assertEqual(cell.evidence_refs, back.get("IAM", "security").evidence_refs)

    def test_multi_value_strengths_and_gaps_survive_csv(self):
        before = self.m.get("ESS", "development")
        back = md.load_csv(md.save_csv(self.m, os.path.join(self.td, "m.csv")))
        after = back.get("ESS", "development")
        self.assertEqual(before.strengths, after.strengths)
        self.assertEqual(before.gaps, after.gaps)
        self.assertEqual(before.next_steps, after.next_steps)
        self.assertGreater(len(after.strengths), 1)

    def test_an_assessed_cell_with_no_rationale_is_an_error(self):
        c = md.Cell(group="ESS", area="security", assessment_status=md.ASSESSED,
                    maturity_rank=3, maturity_label="Practised",
                    evidence_refs=["EV-1"])
        self.assertTrue(any("no rationale" in i for i in c.validate()))


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self.m = mk.build()
        self.td = tempfile.mkdtemp()

    def test_csv_round_trip_has_no_differences(self):
        back = md.load_csv(md.save_csv(self.m, os.path.join(self.td, "m.csv")))
        self.assertEqual([], md.round_trip_report(self.m, back))

    def test_json_round_trip_has_no_differences(self):
        back = md.load_json(md.save_json(self.m, os.path.join(self.td, "m.json")))
        self.assertEqual([], md.round_trip_report(self.m, back))

    def test_csv_to_json_to_csv_has_no_differences(self):
        c1 = md.load_csv(md.save_csv(self.m, os.path.join(self.td, "a.csv")))
        j = md.load_json(md.save_json(c1, os.path.join(self.td, "b.json")))
        c2 = md.load_csv(md.save_csv(j, os.path.join(self.td, "c.csv")))
        self.assertEqual([], md.round_trip_report(self.m, c2))

    def test_the_reopened_dataset_still_validates(self):
        back = md.load_csv(md.save_csv(self.m, os.path.join(self.td, "m.csv")))
        self.assertEqual([], back.validate())

    def test_round_trip_report_detects_a_lost_evidence_link(self):
        """The comparison must be able to fail."""
        back = md.load_csv(md.save_csv(self.m, os.path.join(self.td, "m.csv")))
        back.get("IAM", "security").evidence_refs = []
        issues = md.round_trip_report(self.m, back)
        self.assertTrue(any("evidence_refs" in i for i in issues))

    def test_round_trip_report_detects_an_unassessed_cell_gaining_a_rank(self):
        back = md.load_csv(md.save_csv(self.m, os.path.join(self.td, "m.csv")))
        back.get("RIS", "ai_readiness").maturity_rank = 1
        issues = md.round_trip_report(self.m, back)
        self.assertTrue(any("maturity_rank None -> 1" in i for i in issues), issues)

    def test_unicode_and_separators_survive(self):
        m = mk.build()
        md.edit_cell(m, "ESS", "security", rationale="Ünicode — dash, and a, comma")
        back = md.load_csv(md.save_csv(m, os.path.join(self.td, "u.csv")))
        self.assertEqual("Ünicode — dash, and a, comma",
                         back.get("ESS", "security").rationale)

    def test_json_export_declares_the_non_rank_rule(self):
        payload = md.to_json(self.m)
        self.assertIn("null", payload["schema"]["note"])
        self.assertEqual(list(md.NON_RANK_STATUSES), payload["schema"]["non_rank_statuses"])
        self.assertIn("NOT A UNIVERSITY FINDING", payload["status"])


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.m = mk.build()

    def test_free_text_search_finds_a_cell_by_its_gap(self):
        hits = md.search(self.m, "privileged-access review")
        self.assertTrue(hits)
        self.assertIn(("RIS", "security"), {c.key for c in hits})

    def test_search_finds_a_cell_by_evidence_reference(self):
        hits = md.search(self.m, "EV-SYN-IAM-SEC-INV-005")
        self.assertEqual([("IAM", "security")], [c.key for c in hits])

    def test_search_by_status_returns_only_that_status(self):
        for s in md.ASSESSMENT_STATUSES:
            with self.subTest(status=s):
                for c in md.search(self.m, status=s):
                    self.assertEqual(s, c.assessment_status)

    def test_search_by_group_and_area(self):
        hits = md.search(self.m, group="IAM", area="security")
        self.assertEqual([("IAM", "security")], [c.key for c in hits])

    def test_ranked_only_excludes_every_non_rank_cell(self):
        for c in md.search(self.m, ranked_only=True):
            self.assertTrue(c.is_ranked())
        self.assertEqual(9, len(md.search(self.m, ranked_only=True)))

    def test_search_with_no_filters_returns_all_twelve(self):
        self.assertEqual(12, len(md.search(self.m)))

    def test_search_is_case_insensitive(self):
        self.assertTrue(md.search(self.m, "CONNECTOR"))
        self.assertTrue(md.search(self.m, "connector"))


class AliasTests(unittest.TestCase):
    def test_the_workbench_spelling_loads(self):
        self.assertEqual("development", md.canon_area("software_development"))

    def test_the_short_codes_load(self):
        self.assertEqual("development", md.canon_area("SD"))
        self.assertEqual("security", md.canon_area("SEC"))
        self.assertEqual("deployment", md.canon_area("DEP"))
        self.assertEqual("ai_readiness", md.canon_area("AI"))

    def test_the_021_vocabulary_is_canonical(self):
        for a in md.AREAS:
            self.assertEqual(a, md.canon_area(a))

    def test_an_unknown_area_is_refused_with_the_accepted_list(self):
        with self.assertRaises(md.DatasetError) as ctx:
            md.canon_area("networking")
        self.assertIn("software_development", str(ctx.exception))

    def test_groups_are_case_insensitive(self):
        self.assertEqual("ESS", md.canon_group("ess"))
        with self.assertRaises(md.DatasetError):
            md.canon_group("ITS")

    def test_a_csv_written_with_workbench_spellings_loads(self):
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=md.CELL_FIELDS)
        w.writeheader()
        w.writerow({**{f: "" for f in md.CELL_FIELDS},
                    "group": "ESS", "area": "software_development",
                    "assessment_status": md.UNASSESSED,
                    "follow_up_question": "scheduled"})
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                         encoding="utf-8") as f:
            f.write(buf.getvalue())
            path = f.name
        m = md.load_csv(path)
        self.assertIn(("ESS", "development"), m.cells)


class EditTests(unittest.TestCase):
    def setUp(self):
        self.m = mk.build()

    def test_editing_a_cell_updates_it(self):
        md.edit_cell(self.m, "ESS", "security", gaps=["a new gap"])
        self.assertEqual(["a new gap"], self.m.get("ESS", "security").gaps)

    def test_the_label_is_derived_from_the_rank_not_trusted(self):
        md.edit_cell(self.m, "ESS", "security", maturity_rank=3,
                     maturity_label="Whatever The Editor Typed")
        self.assertEqual("Practised", self.m.get("ESS", "security").maturity_label)

    def test_an_unknown_field_is_refused(self):
        with self.assertRaises(md.DatasetError):
            md.edit_cell(self.m, "ESS", "security", overall_score=7)

    def test_an_edit_that_would_break_validity_is_refused_and_not_applied(self):
        """A rejected edit must leave the dataset exactly as it was. The first
        version of edit_cell mutated the live cell and then raised, so the matrix
        kept the value it had just refused."""
        before = self.m.get("IAM", "security").evidence_refs[:]
        self.assertTrue(before)
        with self.assertRaises(md.DatasetError):
            md.edit_cell(self.m, "IAM", "security", evidence_refs=[])
        self.assertEqual(before, self.m.get("IAM", "security").evidence_refs)
        self.assertEqual([], self.m.validate())

    def test_a_refused_status_edit_leaves_the_rank_untouched(self):
        before = self.m.get("IAM", "security").maturity_rank
        with self.assertRaises(md.DatasetError):
            md.edit_cell(self.m, "IAM", "security",
                         assessment_status=md.UNASSESSED, maturity_rank=1)
        self.assertEqual(before, self.m.get("IAM", "security").maturity_rank)
        self.assertEqual(md.ASSESSED, self.m.get("IAM", "security").assessment_status)

    def test_editing_an_unknown_cell_raises(self):
        with self.assertRaises(md.DatasetError):
            md.edit_cell(self.m, "ITS", "security", gaps=["x"])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.path = md.save_json(mk.build(), os.path.join(self.td, "m.json"))

    def test_grid_and_validate_exit_zero(self):
        self.assertEqual(0, md.main(["--dataset", self.path, "--grid"]))
        self.assertEqual(0, md.main(["--dataset", self.path, "--validate"]))

    def test_round_trip_exits_zero(self):
        self.assertEqual(0, md.main(["--dataset", self.path, "--round-trip"]))

    def test_search_runs(self):
        self.assertEqual(0, md.main(["--dataset", self.path, "--search", "connector"]))

    def test_exports_write_files(self):
        c = os.path.join(self.td, "out.csv")
        j = os.path.join(self.td, "out.json")
        md.main(["--dataset", self.path, "--export-csv", c, "--export-json", j])
        self.assertTrue(os.path.exists(c))
        self.assertTrue(os.path.exists(j))


if __name__ == "__main__":
    unittest.main(verbosity=2)
