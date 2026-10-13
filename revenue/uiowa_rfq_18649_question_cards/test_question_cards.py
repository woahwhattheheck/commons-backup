#!/usr/bin/env python3
"""Regression tests for the UIOWA-114 question-card generator.

Run:  python3 -m unittest -v   (from this directory)

The hostile register (``data/observations_hostile.json``) holds one record per
rule, each violating exactly that rule, so a rule that stops working fails a
named test rather than quietly passing everything through.
"""

import copy
import json
import os
import tempfile
import unittest

import question_cards as qc

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def codes(diagnostics, observation_id=None):
    return {d["code"] for d in diagnostics
            if observation_id is None or d["observation_id"] == observation_id}


class RealRegister(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = qc.load_bundle(DATA)
        cls.cards, cls.diagnostics, cls.coverage = qc.build_cards(cls.bundle)

    def test_every_unresolved_observation_becomes_a_card(self):
        self.assertEqual(self.coverage["observations_total"], 10)
        self.assertEqual(self.coverage["cards_built"], 10)
        self.assertEqual([d for d in self.diagnostics if d["severity"] == qc.SEVERITY_ERROR], [])

    def test_nothing_is_dropped_between_register_and_cards(self):
        """The failure this order exists to prevent: an unresolved observation
        that quietly never becomes a question."""
        for register in ("observations.json", "observations_hostile.json"):
            bundle = qc.load_bundle(DATA, register)
            _, _, coverage = qc.build_cards(bundle)
            self.assertEqual(coverage["accounted_for"], coverage["observations_total"],
                             f"{register}: {coverage}")

    def test_every_card_can_change_at_least_two_findings(self):
        """THE rule. A question whose answers all land on the same finding is
        the interview guide restated, and costs a practitioner an hour."""
        for card in self.cards:
            outcomes = {o["resulting_finding"] for o in card["outcome_map"]}
            self.assertGreaterEqual(len(card["outcome_map"]), 2, card["card_id"])
            self.assertGreaterEqual(len(outcomes), 2, card["card_id"])

    def test_every_card_names_a_concrete_artifact(self):
        vague = [qc.fold(p) for p in self.bundle["templates"]["vague_request_phrases"]]
        for card in self.cards:
            self.assertTrue(card["example_request"], card["card_id"])
            for phrase in vague:
                self.assertNotIn(phrase, qc.fold(card["example_request"]), card["card_id"])

    def test_leading_lint_does_not_flag_any_legitimate_question(self):
        """A guard that flags correct prose gets switched off, and then it guards
        nothing. This asserts the lint stays narrow enough to survive."""
        leading = [qc.fold(p) for p in self.bundle["templates"]["leading_phrases"]]
        for card in self.cards:
            for phrase in leading:
                self.assertNotIn(phrase, qc.fold(card["question"]), card["card_id"])

    def test_absent_evidence_cards_carry_the_absence_caveat(self):
        absent = [c for c in self.cards if c["uncertainty_type"] == "ABSENT_EVIDENCE"]
        self.assertTrue(absent)
        for card in absent:
            self.assertTrue(card["absence_caveat"])
            self.assertIn("not evidence", qc.fold(card["absence_caveat"]))

    def test_no_unfilled_placeholder_ever_reaches_a_card(self):
        """Shipping '{reading_b}' to a practitioner is worse than shipping no card."""
        for card in self.cards:
            for field in ("question", "context", "uncertainty_statement"):
                self.assertNotIn("{", card[field], f"{card['card_id']}.{field}")

    def test_every_card_traces_to_a_real_source_locator(self):
        known = {s["source_id"] for s in self.bundle["sources"]["sources"]}
        for card in self.cards:
            self.assertTrue(card["source_ids"], card["card_id"])
            self.assertEqual(len(card["source_ids"]), len(card["source_locators"]))
            for sid in card["source_ids"]:
                self.assertIn(sid, known)

    def test_every_card_reaches_a_scheduled_interview_session(self):
        sessions = {s["session_id"] for s in self.bundle["interviews"]["sessions"]}
        for card in self.cards:
            self.assertIn(card["session_id"], sessions, card["card_id"])

    def test_all_six_uncertainty_shapes_are_exercised(self):
        self.assertEqual({c["uncertainty_type"] for c in self.cards},
                         set(self.bundle["templates"]["templates"]))

    def test_question_text_lives_in_the_templates_not_the_code(self):
        """Editing templates.json must change the cards. If it doesn't, the
        question text is really hard-coded and the 'editable' claim is false."""
        edited = copy.deepcopy(self.bundle)
        edited["templates"]["templates"]["SINGLE_SOURCE"]["question"] = \
            "REPHRASED: is there a system record for {claim}?"
        cards, _, _ = qc.build_cards(edited)
        rephrased = [c for c in cards if c["uncertainty_type"] == "SINGLE_SOURCE"]
        self.assertTrue(rephrased)
        for card in rephrased:
            self.assertTrue(card["question"].startswith("REPHRASED:"))

    def test_build_is_deterministic(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            qc.build(DATA, a)
            qc.build(DATA, b)
            for name in ("cards.json", "cards.csv", "question_cards.md"):
                with open(os.path.join(a, name), "rb") as fh:
                    first = fh.read()
                with open(os.path.join(b, name), "rb") as fh:
                    second = fh.read()
                self.assertEqual(first, second, name)


class HostileRegister(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = qc.load_bundle(DATA, "observations_hostile.json")
        cls.cards, cls.diagnostics, cls.coverage = qc.build_cards(cls.bundle)

    def test_missing_template_field_is_named_not_guessed(self):
        self.assertIn("TEMPLATE_FIELD_MISSING", codes(self.diagnostics, "OBS-H1-MISSING-FIELD"))
        named = [d for d in self.diagnostics if d["observation_id"] == "OBS-H1-MISSING-FIELD"]
        self.assertEqual(named[0]["field"], "reading_b")

    def test_two_answers_one_outcome_is_rejected(self):
        self.assertIn("USELESS_QUESTION", codes(self.diagnostics, "OBS-H2-SAME-OUTCOME"))

    def test_single_answer_is_rejected(self):
        self.assertIn("USELESS_QUESTION", codes(self.diagnostics, "OBS-H10-ONE-ANSWER"))

    def test_vague_artifact_request_is_rejected(self):
        self.assertIn("VAGUE_EXAMPLE_REQUEST", codes(self.diagnostics, "OBS-H3-VAGUE-REQUEST"))

    def test_dangling_source_reference_is_rejected(self):
        self.assertIn("UNKNOWN_SOURCE_REF", codes(self.diagnostics, "OBS-H4-DANGLING-SOURCE"))
        message = [d["message"] for d in self.diagnostics
                   if d["observation_id"] == "OBS-H4-DANGLING-SOURCE"][0]
        self.assertIn("SRC-DOES-NOT-EXIST", message)

    def test_leading_question_is_rejected(self):
        self.assertIn("LEADING_QUESTION", codes(self.diagnostics, "OBS-H5-LEADING"))

    def test_absent_evidence_without_caveat_is_rejected(self):
        self.assertIn("MISSING_ABSENCE_CAVEAT", codes(self.diagnostics, "OBS-H6-NO-CAVEAT"))

    def test_silent_suppression_is_rejected_but_reasoned_suppression_is_recorded(self):
        self.assertIn("NO_CARD_WITHOUT_REASON", codes(self.diagnostics, "OBS-H7-SUPPRESSED"))
        recorded = {s["observation_id"] for s in self.coverage["suppressed_with_reason"]}
        self.assertIn("OBS-H11-SUPPRESSED-OK", recorded)
        self.assertNotIn("OBS-H7-SUPPRESSED", recorded)

    def test_unknown_uncertainty_type_is_rejected_with_the_known_list(self):
        self.assertIn("UNKNOWN_UNCERTAINTY_TYPE", codes(self.diagnostics, "OBS-H8-UNKNOWN-TYPE"))
        message = [d["message"] for d in self.diagnostics
                   if d["observation_id"] == "OBS-H8-UNKNOWN-TYPE"][0]
        self.assertIn("CONFLICT", message)

    def test_unscheduled_role_warns_but_the_card_still_renders(self):
        """The question is still the right question; the reviewer just has nobody
        booked to ask it. Dropping the card would hide the real gap."""
        self.assertIn("NO_SESSION_FOR_ROLE", codes(self.diagnostics, "OBS-H9-NO-SESSION"))
        rendered = [c for c in self.cards if c["observation_id"] == "OBS-H9-NO-SESSION"]
        self.assertEqual(len(rendered), 1)
        self.assertEqual(rendered[0]["session_id"], "UNSCHEDULED")

    def test_only_the_unscheduled_card_survives_the_hostile_register(self):
        self.assertEqual([c["observation_id"] for c in self.cards], ["OBS-H9-NO-SESSION"])


class Rendering(unittest.TestCase):
    def test_csv_cell_is_spreadsheet_safe_and_keeps_three_empty_states(self):
        self.assertEqual(qc.csv_cell("=SUM(A1:A9)"), "'=SUM(A1:A9)")
        self.assertEqual(qc.csv_cell("@cmd"), "'@cmd")
        self.assertEqual(qc.csv_cell("'quoted"), "''quoted")
        self.assertEqual(qc.csv_cell("\\N"), "\\\\N")
        self.assertEqual(qc.csv_cell(None), qc.NULL_TOKEN)
        self.assertEqual(qc.csv_cell(""), "")
        self.assertEqual(qc.csv_cell("NA"), "NA")
        self.assertEqual(len({qc.csv_cell(None), qc.csv_cell(""), qc.csv_cell("NA")}), 3)

    def test_markdown_cell_cannot_break_the_table(self):
        cell = qc.md_cell("a | b\r\nsecond line")
        self.assertNotIn("\n", cell)
        self.assertNotIn("\r", cell)
        self.assertIn("\\|", cell)

    def test_generated_csv_reads_back_with_one_row_per_card(self):
        import csv as _csv
        with tempfile.TemporaryDirectory() as tmp:
            cards, _, _ = qc.build(DATA, tmp)
            with open(os.path.join(tmp, "cards.csv"), encoding="utf-8", newline="") as fh:
                rows = list(_csv.reader(fh))
        self.assertEqual(rows[0], qc.CARD_COLUMNS)
        self.assertEqual(len(rows) - 1, len(cards))
        for line in rows[1:]:
            for cell in line:
                self.assertFalse(cell.startswith(("=", "+", "@")), cell[:40])

    def test_markdown_shows_coverage_and_the_fiction_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            qc.build(DATA, tmp)
            with open(os.path.join(tmp, "question_cards.md"), encoding="utf-8") as fh:
                text = fh.read()
        self.assertIn("FICTION", text)
        self.assertIn("Accounted for: **10 of 10**", text)
        self.assertIn("not evidence that the review did not happen", text)
        self.assertIn("Where each answer leads", text)


class Search(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cards, _, _ = qc.build_cards(qc.load_bundle(DATA))
        cls.index = qc.CardIndex(cards)

    def test_field_filter_and_short_alias_agree(self):
        long_form = self.index.search("uncertainty_type:ABSENT_EVIDENCE")
        short_form = self.index.search("type:ABSENT_EVIDENCE")
        self.assertEqual([c["card_id"] for c in long_form],
                         [c["card_id"] for c in short_form])
        self.assertEqual(len(long_form), 2)

    def test_terms_are_ANDed_with_filters(self):
        hits = self.index.search("type:ABSENT_EVIDENCE inventory")
        self.assertEqual([c["card_id"] for c in hits], ["QC-RIS-AI-08"])

    def test_reviewer_can_go_from_an_observation_id_straight_to_its_card(self):
        """The completion condition, as a query: one unresolved observation in,
        one follow-up out -- no interview guide in between."""
        hits = self.index.search("OBS-ESS-SEC-07")
        self.assertEqual([c["card_id"] for c in hits], ["QC-ESS-SEC-07"])

    def test_role_filter_collects_one_sitting(self):
        hits = self.index.search("role:iam_administrator")
        self.assertEqual(len(hits), 3)
        self.assertEqual({c["session_id"] for c in hits}, {"S4"})

    def test_unknown_filter_field_explains_itself(self):
        with self.assertRaises(ValueError) as ctx:
            self.index.search("colour:blue")
        self.assertIn("uncertainty_type", str(ctx.exception))
        self.assertIn("short forms", str(ctx.exception))

    def test_query_with_no_match_returns_nothing_rather_than_everything(self):
        self.assertEqual(self.index.search("zzzznotaword"), [])


class CommandLine(unittest.TestCase):
    def test_check_exits_nonzero_on_the_hostile_register(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = qc.main(["check", "--data", DATA,
                          "--observations", "observations_hostile.json", "--out", tmp])
        self.assertEqual(rc, 1)

    def test_check_exits_zero_on_the_real_register(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = qc.main(["check", "--data", DATA, "--out", tmp])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
