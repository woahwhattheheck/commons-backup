#!/usr/bin/env python3
import copy
from pathlib import Path
import tempfile
import unittest

import check_ledger as C

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "GEMINI-ANTIGRAVITY.json"


def load_doc():
    return C.load_strict_json(LEDGER)


def melon_entry(doc):
    return next(e for e in doc["entries"] if e["id"] == C.MELON_ID)


def materialize_evidence(root: Path, doc):
    for entry in doc["entries"]:
        for rel in entry["canonical_evidence"]:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("evidence\n", encoding="utf-8")


class GeminiConvergenceTests(unittest.TestCase):
    def setUp(self):
        self.doc = load_doc()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        materialize_evidence(self.root, self.doc)

    def tearDown(self):
        self.tmp.cleanup()

    def assertRejected(self, doc, pattern=None):
        with self.assertRaises(C.ConvergenceError) as ctx:
            C.validate_document(doc, self.root)
        if pattern is not None:
            self.assertIn(pattern, str(ctx.exception))

    def test_complete_ledger_accepts(self):
        result = C.validate_document(copy.deepcopy(self.doc), self.root)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["entry_count"], 21)
        self.assertEqual(sum(result["dispositions"].values()), 21)

    def test_missing_required_id_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc["entries"] = doc["entries"][1:]
        doc["entry_count"] -= 1
        self.assertRejected(doc, "coverage mismatch")

    def test_duplicate_id_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc["entries"][1]["id"] = doc["entries"][0]["id"]
        self.assertRejected(doc, "duplicate entry id")

    def test_entries_must_stay_sorted(self):
        doc = copy.deepcopy(self.doc)
        doc["entries"][0], doc["entries"][1] = doc["entries"][1], doc["entries"][0]
        self.assertRejected(doc, "sorted by id")

    def test_evidence_outside_v4_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc["entries"][0]["canonical_evidence"][0] = "README.md"
        self.assertRejected(doc, "outside canonical V4")

    def test_literal_legacy_evidence_rejected(self):
        doc = copy.deepcopy(self.doc)
        rel = C.V4_PREFIX + "legacy/stale.md"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stale\n", encoding="utf-8")
        doc["entries"][0]["canonical_evidence"][0] = rel
        self.assertRejected(doc, "noncanonical ancestry")

    def test_symlink_ancestor_alias_rejected(self):
        doc = copy.deepcopy(self.doc)
        legacy = self.root / C.V4_PREFIX / "research" / "legacy"
        legacy.mkdir(parents=True, exist_ok=True)
        (legacy / "stale.md").write_text("stale\n", encoding="utf-8")
        alias = self.root / C.V4_PREFIX / "research" / "current-alias"
        try:
            alias.symlink_to("legacy", target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        rel = C.V4_PREFIX + "research/current-alias/stale.md"
        doc["entries"][0]["canonical_evidence"][0] = rel
        self.assertRejected(doc, "symlink path component")

    def test_leaf_symlink_rejected(self):
        doc = copy.deepcopy(self.doc)
        rel = doc["entries"][0]["canonical_evidence"][0]
        path = self.root / rel
        backing = path.with_name(path.name + ".real")
        path.replace(backing)
        try:
            path.symlink_to(backing.name)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        self.assertRejected(doc, "symlink path component")

    def test_missing_evidence_rejected(self):
        doc = copy.deepcopy(self.doc)
        rel = doc["entries"][0]["canonical_evidence"][0]
        (self.root / rel).unlink()
        self.assertRejected(doc, "missing canonical evidence")

    def test_directory_is_not_evidence(self):
        doc = copy.deepcopy(self.doc)
        rel = doc["entries"][0]["canonical_evidence"][0]
        path = self.root / rel
        path.unlink()
        path.mkdir()
        self.assertRejected(doc, "not a regular file")

    def test_falsified_claim_must_be_fenced(self):
        doc = copy.deepcopy(self.doc)
        entry = next(e for e in doc["entries"] if e["disposition"] == "FALSIFIED")
        entry.pop("do_not_repeat_without_new_evidence")
        self.assertRejected(doc, "durably fenced")

    def test_field_blocked_claim_must_remain_blocked(self):
        doc = copy.deepcopy(self.doc)
        entry = next(e for e in doc["entries"] if e["disposition"] == "FIELD_BLOCKED")
        entry["activation"] = "DEFAULT_OFF"
        self.assertRejected(doc, "must use BLOCKED activation")

    def test_melon_corrected_descendant_contract_is_pinned(self):
        doc = copy.deepcopy(self.doc)
        entry = melon_entry(doc)
        entry["disposition"] = "FIELD_BLOCKED"
        entry["activation"] = "BLOCKED"
        entry["do_not_repeat_without_new_evidence"] = True
        self.assertRejected(doc, "corrected default-off")

        doc = copy.deepcopy(self.doc)
        melon_entry(doc)["canonical_evidence"].remove(
            C.V4_PREFIX
            + "repairs/gameplay/antigravity-melon-cap/INTEGRATION-SPEC.md"
        )
        self.assertRejected(doc, "source/test/manifest/spec")

        doc = copy.deepcopy(self.doc)
        melon_entry(doc)["provenance_pull_numbers"].remove(C.MELON_REPAIR_PR)
        self.assertRejected(doc, "through PR 13118")

        doc = copy.deepcopy(self.doc)
        melon_entry(doc)["next_gate"] = "Source debt remains blocked."
        self.assertRejected(doc, "current-native composition economics")

        doc = copy.deepcopy(self.doc)
        melon_entry(doc)["do_not_repeat_without_new_evidence"] = True
        self.assertRejected(doc, "stale FIELD_BLOCKED fence")

    def test_pr_provenance_must_be_sorted_unique_plain_ints(self):
        doc = copy.deepcopy(self.doc)
        doc["entries"][0]["provenance_pull_numbers"] = [12837, 12819, 12819]
        self.assertRejected(doc, "sorted and unique")
        doc = copy.deepcopy(self.doc)
        doc["entries"][0]["provenance_pull_numbers"] = [True]
        self.assertRejected(doc, "invalid PR provenance")

    def test_nonfinite_json_rejected(self):
        path = self.root / "bad.json"
        path.write_text('{"x": NaN}', encoding="utf-8")
        with self.assertRaises(C.ConvergenceError):
            C.load_strict_json(path)

    def test_duplicate_root_json_key_rejected(self):
        path = self.root / "dup.json"
        path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
        with self.assertRaisesRegex(C.ConvergenceError, "duplicate JSON key: schema"):
            C.load_strict_json(path)

    def test_duplicate_nested_json_key_rejected(self):
        path = self.root / "dup-nested.json"
        path.write_text('{"x":{"id":"first","id":"second"}}', encoding="utf-8")
        with self.assertRaisesRegex(C.ConvergenceError, "duplicate JSON key: id"):
            C.load_strict_json(path)

    def test_source_buckets_are_exact_and_unique(self):
        doc = copy.deepcopy(self.doc)
        doc["source_stream"]["included_buckets"] = ["master_manifest"]
        self.assertRejected(doc, "included_buckets")
        doc = copy.deepcopy(self.doc)
        doc["source_stream"]["included_buckets"].append("master_manifest")
        self.assertRejected(doc, "included_buckets")


if __name__ == "__main__":
    unittest.main()
