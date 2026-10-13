"""Queue stability when a saved analyst handoff is imported under another label.

Synthetic unit data only. Parent integrity is explicitly stubbed here; this suite
is not a substitute for UIOWA_REQUIRE_PARENT=1 integration validation.
"""
from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

import handoff_review as hr
from test_handoff_review import integrity_fixture, report_fixture


class DuplicateContentQueueTests(unittest.TestCase):
    def setUp(self):
        self.report = report_fixture()
        verifier = patch.object(hr, "_parent_integrity", side_effect=integrity_fixture)
        verifier.start()
        self.addCleanup(verifier.stop)

    def populated(self, disposition="NEEDS_EVIDENCE"):
        handoff = hr._blank_handoff(self.report)
        for row in handoff["cell_notes"]:
            row.update(disposition=disposition,
                       analyst_note="FICTIONAL: supporting record still requested.")
        return handoff

    def compare(self, handoffs):
        return hr.reconcile(self.report, handoffs)

    def test_two_or_twenty_copies_cannot_clear_pending_queue(self):
        handoff = self.populated()
        original = self.compare([("original", handoff)])
        self.assertEqual(len(original["review_queue"]), 12)
        for copies in (2, 3, 20):
            with self.subTest(copies=copies):
                repeated = self.compare([(f"copy-{i}", copy.deepcopy(handoff))
                                         for i in range(copies)])
                self.assertEqual(repeated["distinct_handoff_content_count"], 1)
                self.assertEqual(repeated["review_queue"], original["review_queue"])
                self.assertEqual(repeated["reason_counts"], original["reason_counts"])

    def test_every_active_disposition_and_cell_survives_duplicate_import(self):
        # 12 cells x 3 non-default dispositions x 3 import multiplicities = 108.
        checked = 0
        for index in range(len(hr.CELLS)):
            for disposition in sorted(hr.DISPOSITIONS - {"UNREVIEWED"}):
                handoff = hr._blank_handoff(self.report)
                handoff["cell_notes"][index].update(
                    disposition=disposition, analyst_note="FICTIONAL: one saved note.")
                original = self.compare([("original", handoff)])
                for copies in (2, 3, 20):
                    with self.subTest(index=index, disposition=disposition, copies=copies):
                        repeated = self.compare([(f"copy-{i}", copy.deepcopy(handoff))
                                                 for i in range(copies)])
                        self.assertEqual(repeated["review_queue"], original["review_queue"])
                        checked += 1
        self.assertEqual(checked, 108)

    def test_reordered_cells_and_object_keys_are_still_one_handoff(self):
        handoff = self.populated("DISCUSS_WITH_PRIME")
        reordered = json.loads(json.dumps(handoff, sort_keys=True))
        reordered["cell_notes"].reverse()
        single = self.compare([("first", handoff)])
        duplicate = self.compare([("first", handoff), ("reordered", reordered)])
        self.assertEqual(duplicate["distinct_handoff_content_count"], 1)
        self.assertEqual(duplicate["identical_content_groups"], [["first", "reordered"]])
        self.assertEqual(duplicate["review_queue"], single["review_queue"])

    def test_all_unreviewed_is_unchanged(self):
        handoff = hr._blank_handoff(self.report)
        single = self.compare([("one", handoff)])
        repeated = self.compare([("one", handoff), ("two", copy.deepcopy(handoff))])
        self.assertEqual(single["review_queue"], repeated["review_queue"])
        self.assertEqual(repeated["reason_counts"], {"ALL_UNREVIEWED": 12})

    def test_duplicate_added_to_two_distinct_handoffs_changes_no_queue(self):
        first = self.populated()
        second = copy.deepcopy(first)
        second["cell_notes"][0].update(disposition="DISCUSS_WITH_PRIME",
                                       analyst_note="FICTIONAL: distinct context.")
        baseline = self.compare([("first", first), ("second", second)])
        repeated = self.compare([("first", first), ("second", second),
                                 ("first-copy", copy.deepcopy(first))])
        self.assertEqual(repeated["distinct_handoff_content_count"], 2)
        self.assertEqual(repeated["review_queue"], baseline["review_queue"])
        self.assertEqual(repeated["reason_counts"], baseline["reason_counts"])
        self.assertIn("DISPOSITION_DISAGREEMENT", repeated["reason_counts"])

    def test_identical_imports_keep_every_note_label_and_source(self):
        handoff = self.populated()
        handoff["cell_notes"][0]["analyst_note"] = "FICTIONAL: résumé\nquoted \"text\" 🙂"
        before = copy.deepcopy((self.report, handoff))
        repeated = self.compare([("left", handoff), ("right", copy.deepcopy(handoff))])
        self.assertEqual((self.report, handoff), before)
        self.assertEqual(repeated["input_count"], 2)
        self.assertEqual(repeated["identical_content_groups"], [["left", "right"]])
        for cell, original in zip(repeated["assessment_cells"], self.report["assessment_matrix"]):
            self.assertEqual([entry["label"] for entry in cell["entries"]], ["left", "right"])
            self.assertEqual(cell["source_ids"], original["source_ids"])
            self.assertEqual(cell["source_record_sha256s"], original["source_record_sha256s"])
        for entry in repeated["assessment_cells"][0]["entries"]:
            self.assertEqual(entry["analyst_note"], handoff["cell_notes"][0]["analyst_note"])

    def test_reconciliation_receipt_still_covers_the_preserved_queue(self):
        handoff = self.populated()
        result = self.compare([("a", handoff), ("b", copy.deepcopy(handoff))])
        self.assertEqual(len(result["review_queue"]), 12)
        receipt = result.pop("reconciliation_sha256")
        self.assertEqual(receipt, hr.digest(result))
        result["review_queue"].pop()
        self.assertNotEqual(receipt, hr.digest(result))

    def test_duplicate_labels_do_not_gain_any_authority(self):
        handoff = self.populated()
        result = self.compare([("a", handoff), ("b", copy.deepcopy(handoff))])
        self.assertIs(result["reviewer_identity_verified"], False)
        self.assertIs(result["source_authenticity_verified"], False)
        self.assertTrue(all(value is False for value in result["authority"].values()))
        self.assertEqual(result["status"], hr.DRAFT)

    def test_matching_cell_in_genuinely_distinct_exports_still_matches(self):
        first = self.populated("TECHNICAL_DRAFT_NOTE")
        second = copy.deepcopy(first)
        second["cell_notes"][1]["analyst_note"] = "FICTIONAL: extra context on another cell."
        result = self.compare([("a", first), ("b", second)])
        self.assertEqual(result["distinct_handoff_content_count"], 2)
        self.assertEqual(result["assessment_cells"][0]["review_reason_codes"], ["MATCHING_DRAFT_ENTRIES"])
        self.assertEqual(len(result["review_queue"]), 1)

    def test_markdown_retains_single_content_queue_explanation(self):
        handoff = self.populated()
        result = self.compare([("a", handoff), ("b", copy.deepcopy(handoff))])
        text = hr.render_markdown(result)
        self.assertIn("Input labels: 2; distinct handoff contents: 1.", text)
        self.assertIn("SINGLE_DRAFT_ENTRY", text)
        self.assertIn("Identical content is not independent corroboration", text)


if __name__ == "__main__":
    unittest.main()
