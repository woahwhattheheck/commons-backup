#!/usr/bin/env python3
import copy
from pathlib import Path
import tempfile
import unittest

import check_full_coverage as F
import check_ledger as C

HERE = Path(__file__).resolve().parent
MASTER = HERE / "GEMINI-ANTIGRAVITY.json"
HISTORY = HERE / "HISTORICAL-DIRECT.json"


def materialize_evidence(root: Path, *documents):
    for document in documents:
        entries = document.get("entries", document.get("historical_entries", []))
        for entry in entries:
            for rel in entry["canonical_evidence"]:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("evidence\n", encoding="utf-8")


class FullDirectAuthorCoverageTests(unittest.TestCase):
    def setUp(self):
        self.master = C.load_strict_json(MASTER)
        self.history = C.load_strict_json(HISTORY)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        materialize_evidence(self.root, self.master, self.history)

    def tearDown(self):
        self.tmp.cleanup()

    def assertRejected(self, history, pattern=None):
        with self.assertRaises(C.ConvergenceError) as ctx:
            F.validate_history(history, self.root)
        if pattern is not None:
            self.assertIn(pattern, str(ctx.exception))

    def test_complete_44_message_25_proposition_audit_accepts(self):
        C.validate_document(copy.deepcopy(self.master), self.root)
        result = F.validate_history(copy.deepcopy(self.history), self.root)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["direct_author_messages"], 44)
        self.assertEqual(result["master_propositions"], 21)
        self.assertEqual(result["historical_propositions"], 4)
        self.assertEqual(result["combined_distinct_propositions"], 25)

    def test_missing_message_rejected(self):
        history = copy.deepcopy(self.history)
        history["message_map"].pop()
        self.assertRejected(history, "exactly 44")

    def test_duplicate_or_out_of_order_ordinal_rejected(self):
        history = copy.deepcopy(self.history)
        history["message_map"][1]["ordinal"] = 1
        self.assertRejected(history, "exactly 1..44")

    def test_page_counts_and_message_count_are_frozen(self):
        history = copy.deepcopy(self.history)
        history["scan"]["page_counts"] = [20, 24]
        self.assertRejected(history, "page counts drift")
        history = copy.deepcopy(self.history)
        history["scan"]["author_message_count"] = 43
        self.assertRejected(history, "message count drift")

    def test_query_identity_is_frozen(self):
        history = copy.deepcopy(self.history)
        history["scan"]["query"] = "Antigravity"
        self.assertRejected(history, "query drift")
        history = copy.deepcopy(self.history)
        history["scan"]["gemini_author_id"] = "OTHER"
        self.assertRejected(history, "author id")

    def test_unknown_message_proposition_rejected(self):
        history = copy.deepcopy(self.history)
        history["message_map"][0]["proposition_ids"] = ["gemini.unknown"]
        self.assertRejected(history, "unknown propositions")

    def test_coordination_row_cannot_smuggle_proposition(self):
        history = copy.deepcopy(self.history)
        row = next(row for row in history["message_map"] if row["classification"] == "coordination")
        row["proposition_ids"] = ["gemini.goose-printer"]
        self.assertRejected(history, "coordination row cannot carry propositions")

    def test_proposition_or_refinement_row_must_map_something(self):
        history = copy.deepcopy(self.history)
        row = next(row for row in history["message_map"] if row["classification"] == "refinement")
        row["proposition_ids"] = []
        self.assertRejected(history, "refinement row must map a proposition")

    def test_missing_or_duplicate_historical_entry_rejected(self):
        history = copy.deepcopy(self.history)
        history["historical_entries"].pop()
        self.assertRejected(history, "cardinality drift")
        history = copy.deepcopy(self.history)
        history["historical_entries"][1]["id"] = history["historical_entries"][0]["id"]
        self.assertRejected(history, "duplicate historical entry id")

    def test_field_blocked_historical_entry_requires_durable_fence(self):
        history = copy.deepcopy(self.history)
        entry = next(e for e in history["historical_entries"] if e["disposition"] == "FIELD_BLOCKED")
        entry.pop("do_not_repeat_without_new_evidence")
        self.assertRejected(history, "durably fenced")

    def test_missing_historical_evidence_rejected(self):
        history = copy.deepcopy(self.history)
        rel = history["historical_entries"][0]["canonical_evidence"][0]
        (self.root / rel).unlink()
        self.assertRejected(history, "missing canonical evidence")

    def test_every_distinct_proposition_must_be_anchored_by_message_map(self):
        history = copy.deepcopy(self.history)
        target = "gemini.analyzer-margin-clipping"
        for row in history["message_map"]:
            row["proposition_ids"] = [item for item in row["proposition_ids"] if item != target]
        self.assertRejected(history, "proposition coverage mismatch")

    def test_historical_entries_must_stay_sorted(self):
        history = copy.deepcopy(self.history)
        history["historical_entries"][0], history["historical_entries"][1] = (
            history["historical_entries"][1],
            history["historical_entries"][0],
        )
        self.assertRejected(history, "sorted by id")


if __name__ == "__main__":
    unittest.main()
