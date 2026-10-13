#!/usr/bin/env python3
"""UIOWA-029 -- tests for the prioritization method and horizon rules.

Run:
    python3 -m unittest -v test_method

The order requires worked examples covering quick wins, prerequisite work and
high-effort items, effort expressed as ranges, and organization into the
0-90 / 90-180 / 180+ horizons.
"""

import copy
import json
import os
import subprocess
import sys
import unittest

import method
from method import NEEDS_ESTIMATE, UNKNOWN

HERE = os.path.dirname(os.path.abspath(__file__))


def clean():
    return method.Backlog(method.load("backlog.json"))


def broken():
    return method.Backlog(method.load("backlog_violations.json"))


def item(backlog, rid):
    rows = [r for r in backlog.results if r["recommendation_id"] == rid]
    assert rows, rid
    return rows[0]


def codes(backlog):
    return sorted(set(v["code"] for v in backlog.violations))


class TestTheShippedBacklogIsClean(unittest.TestCase):
    def test_no_rule_violations(self):
        self.assertEqual(clean().violations, [])

    def test_the_named_deliverable_exists_and_is_current(self):
        path = os.path.join(HERE, "29-prioritization-method.md")
        self.assertTrue(os.path.exists(path), "the order names this file")
        with open(path, encoding="utf-8") as fh:
            committed = fh.read()
        self.assertEqual(committed, method.render(clean()),
                         "stale -- regenerate with: python3 method.py --render")


class TestTheThreeClassesTheOrderRequires(unittest.TestCase):
    def setUp(self):
        self.b = clean()

    def test_quick_wins_are_present_and_identified_by_stated_criteria(self):
        wins = [r["recommendation_id"] for r in self.b.quick_wins()]
        self.assertGreaterEqual(len(wins), 2)
        for r in self.b.quick_wins():
            self.assertEqual(r["prerequisites"], [], r["recommendation_id"])
            self.assertLessEqual(r["effort_days_high"],
                                 self.b.parameters["quick_win_max_effort_days"])
            self.assertTrue(any(v > 0 for v in r["effects_assessed"].values()))

    def test_prerequisite_work_is_present_and_is_what_others_depend_on(self):
        prereq = [r["recommendation_id"] for r in self.b.prerequisite_work()]
        self.assertIn("REC-SYN-ESS-SD-001", prereq)
        self.assertIn("REC-SYN-IAM-SEC-003", prereq)

    def test_high_effort_items_are_present_and_proposed_late(self):
        high = [r for r in self.b.results
                if r["effort_days_low"] != UNKNOWN
                and r["effort_days_low"] >= self.b.parameters["high_effort_min_effort_days"]]
        self.assertGreaterEqual(len(high), 2)
        for r in high:
            self.assertEqual(r["proposed_horizon"], "180+", r["recommendation_id"])

    def test_every_item_lands_in_a_horizon_or_in_needs_estimate(self):
        placed = sum(len(v) for v in self.b.by_horizon().values())
        self.assertEqual(placed, len(self.b.results))


class TestUncertaintyIsExpressedNotHidden(unittest.TestCase):
    def setUp(self):
        self.b = clean()

    def test_unsized_work_cannot_be_proposed_for_the_first_horizon(self):
        row = item(self.b, "REC-SYN-ESS-AI-008")
        self.assertEqual(row["effort_days_low"], UNKNOWN)
        self.assertEqual(row["proposed_horizon"], NEEDS_ESTIMATE)
        self.assertNotEqual(row["proposed_horizon"], "0-90")

    def test_needs_estimate_is_reported_separately_from_the_horizons(self):
        by_h = self.b.by_horizon()
        self.assertIn("REC-SYN-ESS-AI-008", by_h[NEEDS_ESTIMATE])
        for h in method.HORIZONS:
            self.assertNotIn("REC-SYN-ESS-AI-008", by_h[h])

    def test_unsized_work_is_not_a_disagreement_when_it_is_also_unplaced(self):
        self.assertTrue(item(self.b, "REC-SYN-ESS-AI-008")["agrees"])

    def test_a_point_estimate_is_permitted_but_flagged(self):
        row = item(self.b, "REC-SYN-IAM-SEC-007")
        self.assertEqual(row["effort_days_low"], row["effort_days_high"])
        self.assertIn("POINT_ESTIMATE", row["flags"])

    def test_an_unassessed_effect_is_unknown_and_not_zero(self):
        row = item(self.b, "REC-SYN-ESS-SD-004")
        self.assertIn("delivery", row["effects_unknown"])
        self.assertNotIn("delivery", row["effects_assessed"])

    def test_an_assessed_zero_is_kept_as_a_result(self):
        row = item(self.b, "REC-SYN-ESS-SD-001")
        self.assertEqual(row["effects_assessed"]["security"], 0)
        self.assertNotIn("security", row["effects_unknown"])


class TestItProposesAndNeverOverwrites(unittest.TestCase):
    def setUp(self):
        self.b = clean()

    def test_a_disagreement_shows_both_readings(self):
        disagreements = {r["recommendation_id"]: r for r in self.b.disagreements()}
        self.assertIn("REC-SYN-IAM-SEC-003", disagreements)
        row = disagreements["REC-SYN-IAM-SEC-003"]
        self.assertEqual(row["declared_horizon"], "0-90")
        self.assertEqual(row["proposed_horizon"], "90-180")
        self.assertTrue(row["declared_horizon_reason"].strip())

    def test_the_declared_horizon_is_preserved_unchanged(self):
        for r in self.b.results:
            declared = [x for x in self.b.doc["recommendations"]
                        if x["recommendation_id"] == r["recommendation_id"]][0]
            expected = declared.get("declared_horizon") or UNKNOWN
            self.assertEqual(r["declared_horizon"], expected)

    def test_a_high_effort_item_pulled_early_with_a_reason_is_a_disagreement_not_a_violation(self):
        row = item(self.b, "REC-SYN-RIS-SD-006")
        self.assertEqual(row["declared_horizon"], "90-180")
        self.assertEqual(row["proposed_horizon"], "180+")
        self.assertFalse(row["agrees"])
        self.assertEqual([v for v in self.b.violations
                          if v["recommendation_id"] == "REC-SYN-RIS-SD-006"], [])

    def test_every_proposal_states_the_rule_it_came_from(self):
        for r in self.b.results:
            self.assertTrue(r["proposal_reasons"], r["recommendation_id"])
            joined = " ".join(r["proposal_reasons"])
            self.assertTrue(any(rule in joined for rule in method.RULES),
                            r["recommendation_id"])


class TestEveryRuleGoesRed(unittest.TestCase):
    """A rule that has never fired is not a rule."""

    def setUp(self):
        self.b = broken()

    def test_a_prerequisite_scheduled_after_its_dependent_is_caught(self):
        self.assertIn("PREREQUISITE_AFTER_DEPENDENT", codes(self.b))

    def test_a_dangling_prerequisite_is_caught(self):
        self.assertIn("DANGLING_PREREQUISITE", codes(self.b))

    def test_a_duplicate_id_is_caught(self):
        self.assertIn("DUPLICATE_RECOMMENDATION_ID", codes(self.b))

    def test_a_horizon_outside_the_vocabulary_is_caught(self):
        self.assertIn("UNKNOWN_HORIZON_VALUE", codes(self.b))

    def test_a_reversed_effort_range_is_caught(self):
        self.assertIn("EFFORT_RANGE_REVERSED", codes(self.b))

    def test_high_effort_pulled_early_with_no_reason_is_caught(self):
        self.assertIn("HIGH_EFFORT_MOVED_EARLIER_WITHOUT_REASON", codes(self.b))

    def test_unsized_work_declared_into_the_first_horizon_is_caught(self):
        self.assertIn("UNKNOWN_EFFORT_DECLARED_IN_FIRST_HORIZON", codes(self.b))

    def test_a_prerequisite_cycle_is_caught_and_the_path_is_named(self):
        self.assertIn("PREREQUISITE_CYCLE", codes(self.b))
        cyc = [v for v in self.b.violations if v["code"] == "PREREQUISITE_CYCLE"][0]
        self.assertIn("->", cyc["detail"])

    def test_all_eight_codes_are_exercised_by_the_fixture(self):
        self.assertEqual(len(codes(self.b)), 8)

    def test_an_empty_backlog_is_refused(self):
        with self.assertRaises(method.MethodError):
            method.Backlog({"backlog_id": "E", "recommendations": []})


class TestItDoesNotForkTheScoringModel(unittest.TestCase):
    def test_this_lane_contains_no_scoring_weights(self):
        """Weighting belongs to UIOWA-084. Two models that disagree is worse
        than one model somebody has to look up."""
        with open(os.path.join(HERE, "method.py"), encoding="utf-8") as fh:
            source = fh.read().lower()
        for banned in ("weight", "profiles", "tie_epsilon", "sweep"):
            self.assertNotIn('"%s"' % banned, source)
        self.assertNotIn("def score", source)

    def test_the_method_document_points_at_the_scoring_model_it_binds_to(self):
        text = method.render(clean())
        self.assertIn("uiowa_rfq_18649_prioritization", text)
        self.assertIn("UIOWA-084", text)
        self.assertIn("no scoring model", text.lower())

    def test_complexity_and_effort_are_kept_as_different_quantities(self):
        text = method.render(clean())
        self.assertIn("must not be conflated", text)
        b = clean()
        row = item(b, "REC-SYN-IAM-DEP-009")
        self.assertEqual(row["complexity"], 4)
        self.assertEqual(row["effort_days_low"], 30)

    def test_the_payload_records_where_the_scoring_model_lives(self):
        meta = clean().as_dict()["meta"]
        self.assertIn("UIOWA-084", meta["scoring_model"])
        self.assertIn("not implemented here", meta["scoring_model"])


class TestParametersAreVisible(unittest.TestCase):
    def test_the_thresholds_are_stated_in_the_document(self):
        text = method.render(clean())
        self.assertIn("quick_win_max_effort_days", text)
        self.assertIn("high_effort_min_effort_days", text)
        self.assertIn("not findings", text.lower() if "not findings" in text.lower() else
                      "parameters of this method, not findings")

    def test_changing_a_threshold_moves_items(self):
        doc = copy.deepcopy(method.load("backlog.json"))
        doc["parameters"]["quick_win_max_effort_days"] = 1
        tightened = method.Backlog(doc)
        self.assertLess(len(tightened.quick_wins()), len(clean().quick_wins()))

    def test_no_maturity_or_score_reaches_the_output(self):
        payload = json.dumps(clean().as_dict()).lower()
        for banned in ("maturity", "percentile", "grade", "ranking", "score"):
            self.assertNotIn(banned, payload, "found %r in the output" % banned)


class TestCli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, os.path.join(HERE, "method.py")] + list(args),
                              cwd=HERE, capture_output=True, text=True)

    def test_check_exits_zero_on_the_clean_backlog(self):
        proc = self.run_cli("--check")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("violations=0", proc.stderr)
        self.assertIn("disagreements=2", proc.stderr)

    def test_render_reports_the_worked_classes(self):
        proc = self.run_cli("--render")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("quick_wins=", proc.stderr)
        self.assertIn("prerequisite_work=", proc.stderr)

    def test_the_document_is_labelled_fictional_and_not_a_commitment(self):
        text = method.render(clean())
        self.assertIn("fictional", text.lower())
        self.assertIn("not a commitment to any date", text)
        self.assertIn("Still UNKNOWN", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
