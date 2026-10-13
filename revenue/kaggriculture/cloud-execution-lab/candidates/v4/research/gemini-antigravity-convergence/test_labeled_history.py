#!/usr/bin/env python3
import copy
from pathlib import Path
import tempfile
import unittest

import check_labeled_history as L
import check_ledger as C

HERE = Path(__file__).resolve().parent
HISTORY = HERE / "HISTORICAL-LABELED.json"


def materialize(root: Path, doc):
    for entry in doc["entries"]:
        for rel in entry["canonical_evidence"]:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("evidence\n", encoding="utf-8")


class LabeledHistoryTests(unittest.TestCase):
    def setUp(self):
        self.doc = C.load_strict_json(HISTORY)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        materialize(self.root, self.doc)

    def tearDown(self):
        self.tmp.cleanup()

    def assertRejected(self, doc, text=None):
        with self.assertRaises(C.ConvergenceError) as ctx:
            L.validate_document(doc, self.root)
        if text:
            self.assertIn(text, str(ctx.exception))

    def test_complete_history_accepts(self):
        result = L.validate_document(copy.deepcopy(self.doc), self.root)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["entry_count"], 12)
        self.assertEqual(result["blocked_count"], 6)
        self.assertEqual(result["corrected_count"], 6)
        self.assertEqual(result["provenance_locked_count"], 12)

    def test_missing_or_duplicate_id_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc["entries"].pop()
        doc["entry_count"] -= 1
        self.assertRejected(doc, "coverage mismatch")
        doc = copy.deepcopy(self.doc)
        doc["entries"][1]["id"] = doc["entries"][0]["id"]
        self.assertRejected(doc, "source-lineage provenance drift")

    def test_entries_must_stay_sorted(self):
        doc = copy.deepcopy(self.doc)
        doc["entries"][0], doc["entries"][1] = doc["entries"][1], doc["entries"][0]
        self.assertRejected(doc, "sorted by id")

    def test_blocked_family_cannot_be_promoted_by_json_edit(self):
        doc = copy.deepcopy(self.doc)
        entry = next(e for e in doc["entries"] if e["id"] == "gemini.meridian-adaptive-recourse")
        entry["disposition"] = "CORRECTED_DESCENDANT"
        entry["activation"] = "RESEARCH_ONLY"
        self.assertRejected(doc, "must remain FIELD_BLOCKED/BLOCKED")

    def test_blocked_family_requires_durable_fence(self):
        doc = copy.deepcopy(self.doc)
        entry = next(e for e in doc["entries"] if e["id"] == "gemini.pro-capital")
        entry.pop("do_not_repeat_without_new_evidence")
        self.assertRejected(doc, "durably fenced")

    def test_source_lineage_provenance_is_locked_per_id(self):
        for source in self.doc["entries"]:
            with self.subTest(entry_id=source["id"]):
                doc = copy.deepcopy(self.doc)
                entry = next(e for e in doc["entries"] if e["id"] == source["id"])
                entry["source_lineage"] += " tampered"
                self.assertRejected(doc, "source-lineage provenance drift")

    def test_pr_provenance_is_locked_per_id(self):
        for source in self.doc["entries"]:
            with self.subTest(entry_id=source["id"]):
                doc = copy.deepcopy(self.doc)
                entry = next(e for e in doc["entries"] if e["id"] == source["id"])
                entry["provenance_pull_numbers"] = [
                    value + 100000 for value in entry["provenance_pull_numbers"]
                ]
                self.assertRejected(doc, "PR provenance drift")

    def test_stale_g01_donor_certificate_is_rejected(self):
        doc = copy.deepcopy(self.doc)
        entry = next(e for e in doc["entries"] if e["id"] == "gemini.legacy-g01-e11")
        rel = C.V4_PREFIX + "research/market-baseline/gemini_market_certificate.py"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stale\n", encoding="utf-8")
        entry["canonical_evidence"] = [rel]
        self.assertRejected(doc, "stale donor-only evidence")

    def test_missing_current_evidence_rejected(self):
        doc = copy.deepcopy(self.doc)
        rel = doc["entries"][0]["canonical_evidence"][0]
        (self.root / rel).unlink()
        self.assertRejected(doc, "missing canonical evidence")

    def test_evidence_outside_v4_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc["entries"][0]["canonical_evidence"] = ["revenue/kaggriculture/cloud-market-game-theory/adaptive/README.md"]
        self.assertRejected(doc, "outside canonical V4")

    def test_runtime_activation_implication_cannot_flip(self):
        doc = copy.deepcopy(self.doc)
        doc["runtime_activation_implied"] = True
        self.assertRejected(doc, "must remain false")

    def test_pr_provenance_type_poison_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc["entries"][0]["provenance_pull_numbers"] = [True]
        self.assertRejected(doc, "invalid PR provenance")

    def test_pr_provenance_must_be_sorted_unique(self):
        doc = copy.deepcopy(self.doc)
        doc["entries"][0]["provenance_pull_numbers"] = [12998, 12551, 12551]
        self.assertRejected(doc, "sorted and unique")


if __name__ == "__main__":
    unittest.main()
