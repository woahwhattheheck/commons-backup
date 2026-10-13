#!/usr/bin/env python3
"""UIOWA-107 -- tests for the deadline-continuity analysis.

Run:
    python3 -m unittest -v test_continuity

The order's completion condition is the spec: "Dependency and capacity
assumptions are explicit; results identify practical preparation choices and
the evidence needed to distinguish them."
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

import continuity
import intervals
from intervals import Assumption, AssumptionError, Interval

HERE = os.path.dirname(os.path.abspath(__file__))
SCENARIO = os.path.join(HERE, "fixtures", "ris_deadline_scenario.json")


def analysis():
    return continuity.Analysis(continuity.load(SCENARIO))


def result(a, option_id):
    rows = [r for r in a.results if r["option_id"] == option_id]
    assert rows, option_id
    return rows[0]


def pair(a, x, y):
    for c in a.comparisons():
        if c["pair"] == [x, y]:
            return c
    raise AssertionError("no pair %s/%s" % (x, y))


def minimal_scenario():
    return {
        "scenario_id": "TEST",
        "service": "RIS",
        "assumptions": [
            {"id": "A1", "statement": "work", "basis": "ESTIMATED", "unit": "hours",
             "low": 4, "high": 6},
            {"id": "A2", "statement": "capacity", "basis": "MEASURED", "unit": "hours",
             "low": 32, "high": 40, "source_ref": "synthetic://test/roster"},
        ],
        "options": [
            {"id": "O1", "label": "one",
             "exposure_terms": [{"assumption_ref": "A1"}],
             "capacity_terms": [{"assumption_ref": "A2"}]},
        ],
    }


class TestIntervalArithmetic(unittest.TestCase):
    def test_unbounded_plus_bounded_stays_unbounded(self):
        total = Interval(2, None) + Interval(3, 5)
        self.assertEqual(total.low, 5)
        self.assertIsNone(total.high)
        self.assertFalse(total.bounded)

    def test_an_unbounded_interval_is_below_nothing(self):
        """You cannot conclude a comparison you have not bounded."""
        self.assertFalse(Interval(0, None).strictly_below(Interval(100, 200)))

    def test_a_bounded_interval_can_still_be_below_an_unbounded_one(self):
        """This is what makes OPT-B's conclusion survive the unknown."""
        self.assertTrue(Interval(2, 2).strictly_below(Interval(20, None)))

    def test_overlap_is_the_default_when_in_doubt(self):
        self.assertTrue(Interval(0, None).overlaps(Interval(5, 10)))

    def test_a_reversed_or_negative_interval_is_rejected(self):
        with self.assertRaises(AssumptionError):
            Interval(10, 4)
        with self.assertRaises(AssumptionError):
            Interval(-1, 4)


class TestAssumptionsAreExplicit(unittest.TestCase):
    """"Dependency and capacity assumptions are explicit" -- enforced at the
    point the record is read."""

    def test_an_unknown_assumption_may_not_carry_numbers(self):
        """A value under an UNKNOWN label is an invented figure wearing a
        disclaimer. Rejected outright."""
        with self.assertRaises(AssumptionError) as ctx:
            Assumption({"id": "X", "statement": "s", "basis": "UNKNOWN",
                        "low": 5, "high": 9})
        self.assertIn("invented figure", str(ctx.exception))

    def test_measured_without_a_source_is_rejected(self):
        """MEASURED means somebody can point at the record."""
        with self.assertRaises(AssumptionError) as ctx:
            Assumption({"id": "X", "statement": "s", "basis": "MEASURED",
                        "low": 1, "high": 2})
        self.assertIn("source_ref", str(ctx.exception))

    def test_a_range_assumption_needs_both_bounds(self):
        with self.assertRaises(AssumptionError):
            Assumption({"id": "X", "statement": "s", "basis": "ESTIMATED", "low": 1, "high": None})

    def test_an_unrecognised_basis_is_rejected(self):
        with self.assertRaises(AssumptionError):
            Assumption({"id": "X", "statement": "s", "basis": "PROBABLY", "low": 1, "high": 2})

    def test_an_assumption_without_a_statement_is_rejected(self):
        with self.assertRaises(AssumptionError):
            Assumption({"id": "X", "basis": "ESTIMATED", "low": 1, "high": 2})

    def test_every_assumption_in_the_scenario_carries_a_basis(self):
        for a in analysis().as_dict()["assumptions"]:
            self.assertIn(a["basis"], intervals.BASES)
            self.assertTrue(a["basis_meaning"])


class TestUnknownNeverBecomesANumber(unittest.TestCase):
    def setUp(self):
        self.a = analysis()

    def test_unknown_propagates_as_unbounded_not_as_a_default(self):
        asm = self.a.assumptions["ASM-002"]
        self.assertFalse(asm.resolved)
        self.assertIsNone(asm.low)
        self.assertIsNone(asm.high)
        self.assertEqual(asm.interval(), Interval(0, None))

    def test_no_midpoint_or_zero_substitution_reaches_the_output(self):
        row = [a for a in self.a.as_dict()["assumptions"] if a["id"] == "ASM-002"][0]
        self.assertIsNone(row["low"])
        self.assertIsNone(row["high"])
        self.assertFalse(row["resolved"])

    def test_the_unresolved_assumption_is_listed_where_a_reader_will_see_it(self):
        self.assertEqual(self.a.unresolved_assumptions(), ["ASM-002"])
        self.assertIn("ASM-002", continuity.render_markdown(self.a))


class TestVerdicts(unittest.TestCase):
    def setUp(self):
        self.a = analysis()

    def test_an_option_clear_of_capacity_in_its_worst_case_fits(self):
        row = result(self.a, "OPT-B")
        self.assertEqual(row["verdict"], "FITS")

    def test_an_option_resting_on_an_unbounded_input_is_not_determined(self):
        for oid in ("OPT-A", "OPT-C", "OPT-D"):
            row = result(self.a, oid)
            self.assertEqual(row["verdict"], "NOT_DETERMINED", oid)
            self.assertIn("ASM-002", row["unbounded_inputs"], oid)

    def test_an_option_above_capacity_in_its_best_case_is_at_risk(self):
        scenario = minimal_scenario()
        scenario["assumptions"][0].update({"low": 100, "high": 120})
        a = continuity.Analysis(scenario)
        self.assertEqual(result(a, "O1")["verdict"], "AT_RISK")

    def test_the_verdict_vocabulary_is_exactly_three_states(self):
        self.assertEqual(sorted(continuity.VERDICTS),
                         sorted(("FITS", "AT_RISK", "NOT_DETERMINED")))
        for row in self.a.results:
            self.assertIn(row["verdict"], continuity.VERDICTS)


class TestSeparabilityAndEvidence(unittest.TestCase):
    """"results identify practical preparation choices and the evidence
    needed to distinguish them"."""

    def setUp(self):
        self.a = analysis()

    def test_a_conclusion_that_survives_the_unknown_is_still_reported(self):
        """Deferring is lower in-window exposure than every proceed option,
        and that holds no matter what the identity freeze turns out to be.
        Refusing to say so would be over-caution, not honesty."""
        for x, y in (("OPT-A", "OPT-B"), ("OPT-B", "OPT-C"), ("OPT-B", "OPT-D")):
            c = pair(self.a, x, y)
            self.assertEqual(c["status"], "SEPARATED", c["pair"])
            self.assertEqual(c["lower_in_window_exposure"], "OPT-B", c["pair"])

    def test_overlapping_options_are_not_ranked(self):
        for x, y in (("OPT-A", "OPT-C"), ("OPT-A", "OPT-D"), ("OPT-C", "OPT-D")):
            c = pair(self.a, x, y)
            self.assertEqual(c["status"], "NOT_SEPARABLE", c["pair"])
            self.assertIsNone(c["lower_in_window_exposure"], c["pair"])

    def test_an_unbounded_shared_input_is_named_as_the_blocker(self):
        c = pair(self.a, "OPT-A", "OPT-C")
        self.assertEqual(c["bound_required"], ["ASM-002"])
        asks = " ".join(r["ask"] for r in c["evidence_requests"])
        self.assertIn("Obtain any upper bound", asks)
        self.assertIn("change-freeze", asks)

    def test_a_pair_differing_only_in_capacity_names_that_input(self):
        """OPT-A and OPT-D have identical exposure. Comparing exposure alone
        would report 'not separable' and say nothing useful; the real
        difference is an ASSUMED capacity input nobody has confirmed."""
        c = pair(self.a, "OPT-A", "OPT-D")
        refs = [r["assumption_ref"] for r in c["evidence_requests"]]
        self.assertIn("ASM-006", refs)
        why = " ".join(r["why"] for r in c["evidence_requests"] if r["assumption_ref"] == "ASM-006")
        self.assertIn("identical in-window exposure", why)

    def test_every_unseparated_pair_emits_at_least_one_evidence_request(self):
        for c in self.a.comparisons():
            if c["status"] == "NOT_SEPARABLE":
                self.assertTrue(c["evidence_requests"], c["pair"])
                for r in c["evidence_requests"]:
                    self.assertTrue(r["ask"].strip())
                    self.assertTrue(r["why"].strip())

    def test_when_nothing_separates_a_pair_the_tool_says_so(self):
        """Rather than manufacturing a preference from the numbers."""
        scenario = minimal_scenario()
        scenario["options"].append({
            "id": "O2", "label": "two",
            "exposure_terms": [{"assumption_ref": "A1"}],
            "capacity_terms": [{"assumption_ref": "A2"}],
        })
        a = continuity.Analysis(scenario)
        c = pair(a, "O1", "O2")
        self.assertEqual(c["status"], "NOT_SEPARABLE")
        asks = " ".join(r["ask"] for r in c["evidence_requests"])
        self.assertIn("No single assumption separates", asks)


class TestItNeverRecommends(unittest.TestCase):
    def test_no_recommendation_field_exists_anywhere_in_the_output(self):
        payload = json.dumps(analysis().as_dict()).lower()
        for banned in ("recommend", "best option", "winner", "preferred option",
                       "maturity", "score", "percentile"):
            self.assertNotIn(banned, payload, "found %r in the analysis output" % banned)

    def test_comparisons_reference_options_only_never_teams_or_people(self):
        a = analysis()
        option_ids = set(o.id for o in a.options)
        for c in a.comparisons():
            for member in c["pair"]:
                self.assertIn(member, option_ids)

    def test_a_separated_pair_is_labelled_as_exposure_not_as_advice(self):
        text = continuity.render_markdown(analysis())
        self.assertIn("it is not a recommendation", text)
        self.assertIn("Not modelled", text)


class TestHostileAndMissingInput(unittest.TestCase):
    def test_a_term_referencing_an_unknown_assumption_is_an_error(self):
        scenario = minimal_scenario()
        scenario["options"][0]["exposure_terms"] = [{"assumption_ref": "NOPE"}]
        with self.assertRaises(continuity.ScenarioError):
            continuity.Analysis(scenario)

    def test_a_duplicate_assumption_id_is_an_error(self):
        scenario = minimal_scenario()
        scenario["assumptions"].append(copy.deepcopy(scenario["assumptions"][0]))
        with self.assertRaises(continuity.ScenarioError):
            continuity.Analysis(scenario)

    def test_a_duplicate_option_id_is_an_error(self):
        scenario = minimal_scenario()
        scenario["options"].append(copy.deepcopy(scenario["options"][0]))
        with self.assertRaises(continuity.ScenarioError):
            continuity.Analysis(scenario)

    def test_a_scenario_with_no_options_is_an_error_not_an_empty_report(self):
        scenario = minimal_scenario()
        scenario["options"] = []
        with self.assertRaises(continuity.ScenarioError):
            continuity.Analysis(scenario)

    def test_an_option_with_no_exposure_terms_models_nothing_and_is_refused(self):
        scenario = minimal_scenario()
        scenario["options"][0]["exposure_terms"] = []
        with self.assertRaises(continuity.ScenarioError):
            continuity.Analysis(scenario)

    def test_an_option_must_say_which_capacity_it_draws_on(self):
        scenario = minimal_scenario()
        scenario["options"][0]["capacity_terms"] = []
        with self.assertRaises(continuity.ScenarioError):
            continuity.Analysis(scenario)

    def test_the_analysis_is_deterministic(self):
        one = json.dumps(analysis().as_dict(), sort_keys=True)
        two = json.dumps(analysis().as_dict(), sort_keys=True)
        self.assertEqual(one, two)


class TestCli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, os.path.join(HERE, "continuity.py")] + list(args),
            cwd=HERE, capture_output=True, text=True,
        )

    def test_it_writes_four_files_and_reports_the_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli("--input", SCENARIO, "--outdir", tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for name in ("continuity_options.csv", "evidence_requests.csv",
                         "continuity_analysis.json", "continuity_report.md"):
                self.assertTrue(os.path.exists(os.path.join(tmp, name)), name)
            self.assertIn("undetermined=3", proc.stderr)
            self.assertIn("unresolved_assumptions=1", proc.stderr)

    def test_malformed_json_exits_two_without_a_traceback(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{ nope")
            path = fh.name
        try:
            proc = self.run_cli("--input", path)
            self.assertEqual(proc.returncode, 2)
            self.assertNotIn("Traceback", proc.stderr)
        finally:
            os.unlink(path)

    def test_a_bad_scenario_exits_two_without_a_traceback(self):
        bad = minimal_scenario()
        bad["assumptions"][0]["basis"] = "PROBABLY"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(bad, fh)
            path = fh.name
        try:
            proc = self.run_cli("--input", path)
            self.assertEqual(proc.returncode, 2)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertIn("basis must be one of", proc.stderr)
        finally:
            os.unlink(path)


class TestFictionIsLabelled(unittest.TestCase):
    def test_the_report_labels_itself_fictional_and_not_a_commitment(self):
        text = continuity.render_markdown(analysis())
        self.assertIn("fictional", text.lower())
        self.assertIn("not a commitment to any date", text)
        self.assertIn("Still UNKNOWN", text)

    def test_the_payload_carries_the_prohibited_interpretations(self):
        meta = analysis().as_dict()["meta"]
        self.assertTrue(meta["synthetic"])
        self.assertEqual(meta["authority"], "FICTIONAL_REHEARSAL_ONLY")
        self.assertIn("a commitment, appointment, or scheduled date",
                      meta["prohibited_interpretation"])

    def test_the_deadline_is_relative_to_kickoff_not_a_calendar_date(self):
        deadline = analysis().as_dict()["deadline"]
        self.assertIn("kickoff", deadline["date_basis"])


class TestCommittedSampleIsNotStale(unittest.TestCase):
    def test_sample_markdown_matches_a_fresh_render(self):
        path = os.path.join(HERE, "sample_output", "continuity_report.md")
        with open(path, encoding="utf-8") as fh:
            committed = fh.read()
        self.assertEqual(
            committed, continuity.render_markdown(analysis()),
            "sample_output/ is stale -- regenerate with: "
            "python3 continuity.py --input fixtures/ris_deadline_scenario.json --outdir sample_output",
        )

    def test_sample_json_matches_a_fresh_analysis(self):
        path = os.path.join(HERE, "sample_output", "continuity_analysis.json")
        with open(path, encoding="utf-8") as fh:
            committed = json.load(fh)
        self.assertEqual(committed, json.loads(json.dumps(analysis().as_dict(), sort_keys=True)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
