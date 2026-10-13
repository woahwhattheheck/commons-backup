import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from check_mechanism_claims import RegistryError, git_blob, load_json_bytes, verify

PREFIX = "revenue/kaggriculture/cloud-execution-lab/"


def claim(cid="a.claim", *, status="CONFIRMED", path=PREFIX + "reference/engine/kaggriculture.py", blob=None, anchor="ANCHOR"):
    row = {
        "id": cid,
        "status": status,
        "proposition": f"Proposition {cid}",
        "scope": "narrow source fact",
        "disposition": "consume this result before rebuilding the same mechanism",
        "next_gate": "new source or evidence must supersede the pinned proof",
        "tags": ["engine", "mechanism"],
        "evidence": [{"path": path, "git_blob": blob or "0" * 40, "anchors": [anchor]}],
    }
    if status == "FALSIFIED":
        row["do_not_repeat_without_new_evidence"] = True
    return row


def registry(claims):
    return {"schema": "titan-v4-mechanism-claims/v1", "canonical_branch": "main", "claims": claims}


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / PREFIX / "reference/engine/kaggriculture.py"
        self.path.parent.mkdir(parents=True)
        self.path.write_text("ANCHOR\nsecond anchor\n", encoding="utf-8")
        self.blob = git_blob(self.path.read_bytes())

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_registry(self):
        doc = registry([claim(blob=self.blob)])
        out = verify(doc, self.root)
        self.assertTrue(out["valid"])
        self.assertEqual(1, out["claim_count"])
        self.assertEqual(1, out["status_counts"]["CONFIRMED"])

    def test_falsified_requires_repeat_guard(self):
        row = claim(status="FALSIFIED", blob=self.blob)
        del row["do_not_repeat_without_new_evidence"]
        with self.assertRaises(RegistryError):
            verify(registry([row]), self.root)

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(RegistryError):
            verify(registry([claim("a", blob=self.blob), claim("a", blob=self.blob)]), self.root)

    def test_duplicate_normalized_proposition_rejected(self):
        a = claim("a", blob=self.blob)
        b = claim("b", blob=self.blob)
        b["proposition"] = "  PROPOSITION   A "
        with self.assertRaises(RegistryError):
            verify(registry([a, b]), self.root)

    def test_claims_must_be_sorted(self):
        with self.assertRaises(RegistryError):
            verify(registry([claim("b", blob=self.blob), claim("a", blob=self.blob)]), self.root)

    def test_blob_drift_rejected(self):
        with self.assertRaises(RegistryError):
            verify(registry([claim(blob="f" * 40)]), self.root)

    def test_missing_anchor_rejected(self):
        with self.assertRaises(RegistryError):
            verify(registry([claim(blob=self.blob, anchor="NOPE")]), self.root)

    def test_bad_paths_rejected(self):
        for bad in ("../x", "/x", "revenue\\x", PREFIX + "../escape"):
            with self.subTest(bad=bad), self.assertRaises(RegistryError):
                verify(registry([claim(path=bad, blob=self.blob)]), self.root)

    def test_symlink_rejected(self):
        target = self.root / "target.txt"
        target.write_text("ANCHOR\n")
        link = self.root / PREFIX / "reference/engine/link.py"
        link.symlink_to(target)
        with self.assertRaises(RegistryError):
            verify(registry([claim(path=PREFIX + "reference/engine/link.py", blob=git_blob(target.read_bytes()))]), self.root)

    def test_duplicate_json_keys_rejected(self):
        raw = b'{"schema":"x","schema":"y"}'
        with self.assertRaises(RegistryError):
            load_json_bytes(raw)

    def test_tags_and_anchors_must_be_sorted_unique(self):
        row = claim(blob=self.blob)
        row["tags"] = ["z", "a"]
        with self.assertRaises(RegistryError):
            verify(registry([row]), self.root)
        row = claim(blob=self.blob)
        row["evidence"][0]["anchors"] = ["second anchor", "ANCHOR"]
        with self.assertRaises(RegistryError):
            verify(registry([row]), self.root)

    def test_bad_status_rejected(self):
        row = claim(blob=self.blob)
        row["status"] = "MAYBE"
        with self.assertRaises(RegistryError):
            verify(registry([row]), self.root)


if __name__ == "__main__":
    unittest.main()
