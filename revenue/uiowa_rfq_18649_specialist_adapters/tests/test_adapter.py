import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parents[1]

def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

adapter = load_module("uiowa102_adapter", HERE / "adapter.py")
common = load_module(
    "uiowa023_validator",
    ROOT / "revenue" / "uiowa_rfq_18649_workshare" / "methodology" / "validate_23_evidence_register.py",
)

class AdapterTests(unittest.TestCase):
    def test_real_component_row_counts(self):
        self.assertEqual(len(adapter.build("delivery", ROOT)), 8)
        self.assertEqual(len(adapter.build("security", ROOT)), 5)
        self.assertEqual(len(adapter.build("ai", ROOT)), 6)

    def test_each_output_passes_common_register_validator(self):
        for component in ("delivery", "security", "ai", "all"):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as td:
                path = Path(td) / "register.csv"
                adapter.write_csv(adapter.build(component, ROOT), path)
                self.assertEqual(common.validate(path), [])

    def test_extensions_preserve_native_record_and_identity(self):
        for component in ("delivery", "security", "ai"):
            for row in adapter.build(component, ROOT):
                ext = json.loads(row["extensions_json"])
                self.assertEqual(ext["source_component"], row["source_component"])
                self.assertEqual(ext["native_id"], row["native_id"])
                self.assertTrue(ext["synthetic"])
                self.assertEqual(ext["source_sha256"], row["source_sha256"])
                self.assertIsInstance(ext["native_record"], dict)
                self.assertIn(row["native_id"], row["source_ref"])

    def test_unknown_ai_facts_remain_not_evidenced(self):
        rows = {row["native_id"]: row for row in adapter.build("ai", ROOT)}
        self.assertEqual(rows["ESS-AI-002"]["evidence_state"], "NO_EVIDENCE_OBSERVED")
        self.assertEqual(rows["ESS-AI-002"]["confidence"], "NOT_EVIDENCED")
        self.assertEqual(rows["IAM-AI-001"]["evidence_state"], "NO_EVIDENCE_OBSERVED")
        self.assertEqual(json.loads(rows["IAM-AI-001"]["extensions_json"])["native_record"]["status"], "unknown")

    def test_security_boundary_is_not_flattened(self):
        rows = {row["native_id"]: row for row in adapter.build("security", ROOT)}
        self.assertEqual(rows["ESS-MON-001"]["evidence_state"], "SUPPORTING")
        self.assertIn("monitoring-only", rows["ESS-MON-001"]["claim"])
        self.assertEqual(rows["ESS-SEC-003"]["evidence_state"], "NO_EVIDENCE_OBSERVED")
        self.assertEqual(rows["RIS-UNK-004"]["confidence"], "NOT_EVIDENCED")
        self.assertEqual(json.loads(rows["IAM-SEC-005"]["extensions_json"])["native_record"]["action"]["status"], "in_progress")

    def test_delivery_native_semantics_survive(self):
        rows = {row["native_id"]: row for row in adapter.build("delivery", ROOT)}
        self.assertEqual(rows["DEP-002"]["group"], "ESS")
        self.assertIn("intervention_required=true", rows["DEP-002"]["claim"])
        ext = json.loads(rows["DEP-003"]["extensions_json"])
        self.assertEqual(ext["native_record"]["unplanned_rework"], "true")
        self.assertEqual(ext["native_record"]["notes"], "Unplanned deployment for user-facing production defect")

    def test_combined_identifiers_are_unique(self):
        rows = adapter.build("all", ROOT)
        evidence = [r["evidence_id"] for r in rows]
        observations = [r["observation_id"] for r in rows]
        self.assertEqual(len(evidence), len(set(evidence)))
        self.assertEqual(len(observations), len(set(observations)))

    def test_checked_in_examples_are_exact_adapter_outputs(self):
        examples = HERE / "examples"
        for component in ("delivery", "security", "ai", "all"):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as td:
                out = Path(td)
                rows = adapter.build(component, ROOT)
                adapter.write_csv(rows, out / f"{component}_to_register.csv")
                adapter.write_json(rows, out / f"{component}_to_register.json")
                self.assertEqual(
                    (out / f"{component}_to_register.csv").read_bytes(),
                    (examples / f"{component}_to_register.csv").read_bytes(),
                )
                self.assertEqual(
                    (out / f"{component}_to_register.json").read_bytes(),
                    (examples / f"{component}_to_register.json").read_bytes(),
                )

if __name__ == "__main__":
    unittest.main()
