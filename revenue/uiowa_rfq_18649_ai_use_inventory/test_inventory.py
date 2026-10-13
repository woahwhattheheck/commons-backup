#!/usr/bin/env python3
"""UIOWA-071 -- tests for the AI-use inventory.

Run:
    python3 -m unittest -v test_inventory

These assert the behaviour the work order's completion condition depends on:
active use, informal experiments and planned use stay separated; an
unsupported adoption claim is left unfilled rather than counted as use; and
a missing answer stays UNKNOWN instead of becoming a zero.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

if __package__:
    from . import interview_guide, inventory, schema
    from .schema import UNKNOWN
else:  # Retain the original lane-local unittest command.
    import interview_guide
    import inventory
    import schema
    from schema import UNKNOWN

HERE = os.path.dirname(os.path.abspath(__file__))
CLEAN = os.path.join(HERE, "fixtures", "synthetic_ai_use.json")
HOSTILE = os.path.join(HERE, "fixtures", "synthetic_ai_use_hostile.json")


def build(path):
    records, label = inventory.load(path)
    return inventory.build(records, source_label=label)


def entry(inv, entry_id):
    rows = [e for e in inv.entries if e["entry_id"] == entry_id]
    assert rows, "no entry %s" % entry_id
    return rows[0]


class TestSeparatesTheThreeKindsOfUse(unittest.TestCase):
    """The order's first completion condition: active use, informal
    experiments and planned use must come out separated."""

    def setUp(self):
        self.inv = build(CLEAN)

    def test_active_use_requires_a_concrete_example(self):
        row = entry(self.inv, "AIU-SYN-001")
        self.assertEqual(row["classification"], "ACTIVE_USE")
        self.assertTrue(row["evidence_refs"])
        self.assertEqual(row["benefits_unsupported"], 0)

    def test_declared_active_without_a_cadence_is_demoted_to_experiment(self):
        row = entry(self.inv, "AIU-SYN-002")
        self.assertEqual(row["declared_status"], "ACTIVE")
        self.assertEqual(row["classification"], "INFORMAL_EXPERIMENT")
        self.assertTrue(row["demoted"], "a demotion must be flagged, not silent")
        self.assertIn("AD_HOC", " ".join(row["classification_reasons"]))

    def test_declared_active_but_not_integrated_is_demoted(self):
        row = entry(self.inv, "AIU-SYN-008")
        self.assertEqual(row["classification"], "INFORMAL_EXPERIMENT")
        self.assertEqual(row["integrations_state"], "NONE_REPORTED")
        self.assertIn("not integrated", " ".join(row["classification_reasons"]))

    def test_planned_use_stays_planned(self):
        row = entry(self.inv, "AIU-SYN-005")
        self.assertEqual(row["classification"], "PLANNED_USE")
        self.assertEqual(row["outputs"], [])

    def test_the_classifier_demotes_but_never_promotes(self):
        """A record declared PLANNED that turns up carrying an output is not
        silently reclassified as active. Both readings survive and a human
        reconciles them -- the same treatment conflicting sources get in
        23-evidence-confidence.md."""
        row = entry(self.inv, "AIU-SYN-006")
        self.assertEqual(row["declared_status"], "PLANNED")
        self.assertEqual(row["classification"], "PLANNED_USE")
        self.assertTrue(row["outputs"])
        self.assertIn(
            "STATUS_EVIDENCE_MISMATCH", [g["gap"] for g in row["gaps"]]
        )

    def test_missing_declared_status_is_unknown_not_a_guess(self):
        row = entry(self.inv, "AIU-SYN-009")
        self.assertEqual(row["classification"], UNKNOWN)
        self.assertIn("cannot separate", " ".join(row["classification_reasons"]))

    def test_the_five_buckets_account_for_every_record(self):
        counts = self.inv.counts()
        self.assertEqual(sum(counts.values()), self.inv.meta["record_count"])
        self.assertEqual(sorted(counts), sorted(schema.CLASSIFICATIONS))


class TestUnsupportedClaimsAreLeftUnfilled(unittest.TestCase):
    """The order's second completion condition: unsupported adoption claims
    are left unfilled. This is the test that matters most -- it is the
    difference between an inventory and an adoption number."""

    def setUp(self):
        self.inv = build(CLEAN)

    def test_a_confident_claim_with_nothing_behind_it_is_not_active_use(self):
        row = entry(self.inv, "AIU-SYN-003")
        self.assertEqual(row["declared_status"], "ACTIVE")
        self.assertEqual(row["classification"], "UNSUPPORTED_CLAIM")
        self.assertEqual(row["evidence_refs"], [])
        self.assertEqual(row["outputs"], [])
        self.assertEqual(row["benefits_with_example"], 0)

    def test_an_unsupported_claim_is_counted_in_the_open(self):
        """It is neither folded into active use nor dropped. Both moves
        would change the headline adoption figure while removing the
        evidence that it was ever in question."""
        counts = self.inv.counts()
        self.assertEqual(counts["UNSUPPORTED_CLAIM"], 1)
        ids = [e["entry_id"] for e in self.inv.entries]
        self.assertIn("AIU-SYN-003", ids)

    def test_a_benefit_without_an_example_is_counted_separately(self):
        row = entry(self.inv, "AIU-SYN-003")
        self.assertEqual(row["benefits_unsupported"], 1)
        self.assertIn("UNSUPPORTED_BENEFIT", [g["gap"] for g in row["gaps"]])

    def test_benefits_observed_for_a_use_that_has_not_started_are_flagged(self):
        row = entry(self.inv, "AIU-SYN-006")
        self.assertIn("projections", " ".join(row["classification_reasons"]))

    def test_every_gap_carries_the_question_that_closes_it(self):
        for gap in self.inv.gaps():
            self.assertTrue(gap["follow_up"].strip(), gap["gap"])
            self.assertIn(gap["gap"], inventory.GAP_FOLLOW_UPS)


class TestAbsentInputStaysUnknown(unittest.TestCase):
    """A blank answer is UNKNOWN. It is never a zero, never a 'no', never a
    pass, and never a maturity score."""

    def setUp(self):
        self.inv = build(CLEAN)

    def test_blank_frequency_is_unknown_not_never(self):
        row = entry(self.inv, "AIU-SYN-010")
        self.assertEqual(row["frequency"], UNKNOWN)
        self.assertNotEqual(row["frequency"], "NOT_YET")
        self.assertIn("UNKNOWN_FREQUENCY", [g["gap"] for g in row["gaps"]])

    def test_blank_headcount_is_unknown_not_zero(self):
        row = entry(self.inv, "AIU-SYN-010")
        self.assertEqual(row["user_count"], UNKNOWN)
        self.assertNotEqual(row["user_count"], 0)

    def test_blank_integrations_is_unknown_but_an_empty_list_is_an_answer(self):
        self.assertEqual(entry(self.inv, "AIU-SYN-010")["integrations_state"], UNKNOWN)
        self.assertEqual(entry(self.inv, "AIU-SYN-004")["integrations_state"], "NONE_REPORTED")

    def test_an_uncaptured_cell_is_not_a_finding_of_no_ai_use(self):
        cells = dict(((c["group"], c["function"]), c) for c in self.inv.coverage())
        self.assertEqual(cells[("RIS", "testing")]["state"], "NO_ENTRY_CAPTURED")
        self.assertEqual(cells[("RIS", "testing")]["entries"], 0)
        self.assertEqual(cells[("ESS", "testing")]["state"], "INFORMAL_ONLY")

    def test_no_maturity_or_percentile_field_exists_anywhere(self):
        """No score to misread. The absence is asserted so nobody adds one
        later without a test failing."""
        payload = json.dumps(self.inv.as_dict()).lower()
        for banned in ("maturity", "percentile", "benchmark", "certif", "score"):
            self.assertNotIn(banned, payload, "found %r in the inventory output" % banned)


class TestCapabilityNotIndividuals(unittest.TestCase):
    def test_a_record_carrying_an_individual_identifier_is_quarantined(self):
        inv = build(HOSTILE)
        row = entry(inv, "AIU-HOS-002")
        codes = [i["code"] for i in inv.issues if i["entry_id"] == "AIU-HOS-002"]
        self.assertIn("INDIVIDUAL_IDENTIFIER_PRESENT", codes)
        self.assertTrue(row["quarantined"])
        self.assertEqual(
            row["classification"], UNKNOWN,
            "flagging the row while still counting it means the identifier was accepted anyway",
        )

    def test_the_identifier_value_never_reaches_the_output(self):
        inv = build(HOSTILE)
        payload = json.dumps(inv.as_dict())
        self.assertNotIn("E-44821", payload)
        self.assertNotIn("employee_id", json.dumps(entry(inv, "AIU-HOS-002")))

    def test_the_schema_has_no_field_for_a_person(self):
        self.assertFalse(set(schema.BANNED_IDENTITY_KEYS) & set(schema.OPTIONAL_FIELDS))
        self.assertFalse(set(schema.BANNED_IDENTITY_KEYS) & set(schema.REQUIRED_FIELDS))


class TestHostileAndMissingData(unittest.TestCase):
    """Damaged input must be reported, not absorbed and not fatal."""

    def setUp(self):
        self.inv = build(HOSTILE)

    def test_the_bare_adoption_claim_does_not_become_use(self):
        row = entry(self.inv, "AIU-HOS-001")
        self.assertEqual(row["classification"], "UNSUPPORTED_CLAIM")

    def test_a_duplicate_entry_id_is_named_and_both_rows_survive(self):
        codes = [i["code"] for i in self.inv.issues]
        self.assertIn("DUPLICATE_ENTRY_ID", codes)
        dupes = [e for e in self.inv.entries if e["entry_id"] == "AIU-HOS-001"]
        self.assertEqual(len(dupes), 2)

    def test_an_out_of_vocabulary_function_is_reported_not_placed(self):
        codes = [(i["entry_id"], i["field"]) for i in self.inv.issues
                 if i["code"] == "UNKNOWN_VOCABULARY_VALUE"]
        self.assertIn(("AIU-HOS-004", "function"), codes)
        unmapped_ids = [u["entry_id"] for u in self.inv.unmapped()]
        self.assertIn("AIU-HOS-004", unmapped_ids)
        self.assertEqual(entry(self.inv, "AIU-HOS-004")["function_as_given"], "procurement")

    def test_an_out_of_vocabulary_frequency_normalises_to_unknown_not_a_guess(self):
        row = entry(self.inv, "AIU-HOS-005")
        self.assertEqual(row["frequency"], UNKNOWN)

    def test_malformed_benefits_are_named_and_not_counted(self):
        row = entry(self.inv, "AIU-HOS-006")
        codes = [i["code"] for i in self.inv.issues if i["entry_id"] == "AIU-HOS-006"]
        self.assertIn("MALFORMED_BENEFIT", codes)
        self.assertEqual(row["benefits_with_example"], 0)
        self.assertEqual(row["benefits_unsupported"], 0)

    def test_a_row_that_is_not_an_object_keeps_its_position(self):
        ids = [e["entry_id"] for e in self.inv.entries]
        self.assertIn("RECORD_007", ids)
        self.assertEqual(entry(self.inv, "RECORD_007")["classification"], UNKNOWN)

    def test_every_record_is_accounted_for_in_the_report(self):
        """Record conservation. The coverage grid plus the unmapped table
        must cover the collection exactly -- a malformed row cannot quietly
        leave the report."""
        placed = sum(c["entries"] for c in self.inv.coverage())
        self.assertEqual(placed + len(self.inv.unmapped()), self.inv.meta["record_count"])

    def test_an_empty_collection_does_not_crash_or_invent_zeros(self):
        inv = inventory.build([], source_label="empty")
        self.assertEqual(sum(inv.counts().values()), 0)
        states = set(c["state"] for c in inv.coverage())
        self.assertEqual(states, {"NO_ENTRY_CAPTURED"})

    def test_malformed_json_gives_a_sentence_not_a_traceback(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{ this is not json")
            path = fh.name
        try:
            with self.assertRaises(ValueError) as ctx:
                inventory.load(path)
            self.assertIn("not valid JSON", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_a_missing_file_gives_a_sentence_not_a_traceback(self):
        with self.assertRaises(ValueError) as ctx:
            inventory.load(os.path.join(HERE, "no-such-collection.json"))
        self.assertIn("cannot read", str(ctx.exception))


class TestInterviewInstrument(unittest.TestCase):
    """The order: "interview questions seek concrete examples and leave
    unsupported University adoption claims unfilled"."""

    def test_no_question_asks_for_an_unverifiable_self_rating(self):
        for q in interview_guide.all_questions():
            self.assertIn(q["seeks"], interview_guide.ALLOWED_SEEKS, q["id"])
            self.assertNotIn(q["seeks"], interview_guide.BANNED_SEEKS, q["id"])

    def test_every_question_can_be_answered_unknown(self):
        for q in interview_guide.all_questions():
            self.assertTrue(q["accepts_unknown"], q["id"])
        self.assertIn("UNKNOWN", interview_guide.RECORDING_RULE)

    def test_every_field_the_order_names_has_a_question(self):
        """The order enumerates task, users, inputs, outputs, integrations,
        frequency, observed benefits and known limitations. If a field loses
        its question the instrument has quietly stopped capturing it."""
        covered = set(q["field"] for q in interview_guide.BASE_QUESTIONS)
        for field in ("task", "users", "inputs", "outputs", "integrations",
                      "frequency", "observed_benefits", "known_limitations"):
            self.assertIn(field, covered, "no question captures %r" % field)

    def test_every_gap_kind_has_at_least_one_probe(self):
        for kind in inventory.GAP_FOLLOW_UPS:
            self.assertIn(kind, interview_guide.PROBE_QUESTIONS, kind)
            self.assertTrue(interview_guide.PROBE_QUESTIONS[kind], kind)

    def test_a_thin_record_produces_the_probes_that_would_fill_it(self):
        inv = build(CLEAN)
        probes = interview_guide.probes_for(entry(inv, "AIU-SYN-003"))
        ids = [p["id"] for p in probes]
        self.assertIn("P-EX-01", ids)
        self.assertIn("P-BEN-01", ids)

    def test_a_well_evidenced_record_is_not_over_probed(self):
        """A probe generator that fires on everything gets ignored. The
        strong record should draw few or no example probes."""
        inv = build(CLEAN)
        probes = interview_guide.probes_for(entry(inv, "AIU-SYN-001"))
        self.assertNotIn("P-EX-01", [p["id"] for p in probes])

    def test_probe_generation_is_deterministic(self):
        inv = build(CLEAN)
        row = entry(inv, "AIU-SYN-003")
        self.assertEqual(
            [p["id"] for p in interview_guide.probes_for(row)],
            [p["id"] for p in interview_guide.probes_for(row)],
        )


class TestOutputsAndJoinKeys(unittest.TestCase):
    def test_the_cli_writes_all_four_files_and_reports_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, os.path.join(HERE, "inventory.py"),
                 "--input", CLEAN, "--outdir", tmp],
                cwd=HERE, capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for name in ("ai_use_inventory.csv", "ai_use_gaps.csv",
                         "ai_use_inventory.json", "ai_use_inventory.md"):
                self.assertTrue(os.path.exists(os.path.join(tmp, name)), name)
            self.assertIn("unsupported=1", proc.stderr)

    def test_the_cli_reports_a_bad_input_without_a_traceback(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "inventory.py"),
             "--input", os.path.join(HERE, "nope.json")],
            cwd=HERE, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("error:", proc.stderr)

    def test_join_keys_match_the_shapes_already_in_use_in_this_solicitation(self):
        inv = build(CLEAN)
        row = entry(inv, "AIU-SYN-001")
        self.assertTrue(row["proposed_evidence_id"].startswith("EV-SYN-ESS-AI-INV-"))
        self.assertEqual(row["area"], "AI")
        self.assertIn(row["group"], schema.GROUPS)
        for ref in row["evidence_refs"]:
            self.assertTrue(ref.startswith("synthetic://"),
                            "a fictional locator must be unmistakably fictional")

    def test_the_report_labels_itself_synthetic(self):
        inv = build(CLEAN)
        text = inventory.render_markdown(inv)
        self.assertIn("fictional", text.lower())
        self.assertIn("No University input has been collected", text)
        self.assertIn("Still UNKNOWN", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCommittedSampleIsNotStale(unittest.TestCase):
    """The committed sample_output/ must match what the code produces now.

    A checked-in artifact that has drifted from the code that made it is the
    same defect this engagement keeps finding in documentation: it reads as
    current and is not. The render is deterministic (sorted keys, no
    timestamps), so this comparison is exact rather than approximate.
    """

    def test_sample_markdown_matches_a_fresh_render(self):
        inv = build(CLEAN)
        path = os.path.join(HERE, "sample_output", "ai_use_inventory.md")
        with open(path, encoding="utf-8") as fh:
            committed = fh.read()
        self.assertEqual(
            committed, inventory.render_markdown(inv),
            "sample_output/ is stale -- regenerate with: "
            "python3 inventory.py --input fixtures/synthetic_ai_use.json --outdir sample_output",
        )

    def test_sample_json_matches_a_fresh_build(self):
        inv = build(CLEAN)
        path = os.path.join(HERE, "sample_output", "ai_use_inventory.json")
        with open(path, encoding="utf-8") as fh:
            committed = json.load(fh)
        self.assertEqual(committed, json.loads(json.dumps(inv.as_dict(), sort_keys=True)))
