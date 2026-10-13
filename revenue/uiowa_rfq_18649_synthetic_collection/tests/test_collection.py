import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validator", ROOT / "validate_collection.py")
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)

class CollectionTests(unittest.TestCase):
    def test_collection_validates(self):
        self.assertEqual(validator.validate(ROOT), [])

    def test_exact_twelve_cell_coverage(self):
        facts = json.loads((ROOT / "facts.json").read_text(encoding="utf-8"))["facts"]
        cells = {(f["service"], f["area"]) for f in facts}
        self.assertEqual(len(cells), 12)
        self.assertEqual(len(facts), 24)

    def test_unknown_is_present_and_not_rewritten_as_gap(self):
        facts = json.loads((ROOT / "facts.json").read_text(encoding="utf-8"))["facts"]
        states = {f["fact_id"]: f["status"] for f in facts}
        self.assertEqual(states["ESS-SEC-002"], "unknown")
        self.assertEqual(states["ESS-AI-002"], "unknown")
        self.assertEqual(states["IAM-AI-001"], "unknown")
        self.assertNotEqual(states["IAM-AI-001"], "gap")

    def test_each_service_has_all_four_areas(self):
        facts = json.loads((ROOT / "facts.json").read_text(encoding="utf-8"))["facts"]
        for service in validator.SERVICES:
            self.assertEqual({f["area"] for f in facts if f["service"] == service}, validator.AREAS)

    def test_manifest_references_every_fact(self):
        facts = json.loads((ROOT / "facts.json").read_text(encoding="utf-8"))["facts"]
        manifest = json.loads((ROOT / "evidence_manifest.json").read_text(encoding="utf-8"))
        referenced = {fid for d in manifest["documents"] for fid in d["fact_ids"]}
        self.assertEqual(referenced, {f["fact_id"] for f in facts})

if __name__ == "__main__":
    unittest.main()
