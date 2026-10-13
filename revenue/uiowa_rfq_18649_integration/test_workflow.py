from __future__ import annotations
import hashlib, json, tempfile, types, unittest
from pathlib import Path
from unittest import mock
import workflow

class Tests(unittest.TestCase):
    def test_dotted_preserves_nested_value(self):
        self.assertEqual(workflow._dotted({"a":{"b":3}}, "a.b"), 3)
        self.assertIsNone(workflow._dotted({"a":1}, "a.b"))
    def test_component_qualified_identity(self):
        a=workflow._record("alpha","R-1","ESS","x","a", "0"*64,{})
        b=workflow._record("beta","R-1","ESS","x","b", "1"*64,{})
        self.assertNotEqual(a["canonical_id"], b["canonical_id"])
    def test_invalid_group_fails(self):
        with self.assertRaises(workflow.IntegrationError): workflow._record("x","1","OTHER","x","p","0"*64,{})
    def test_interface_map_requires_no_synthesized_scores(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/"revenue/uiowa_rfq_18649_integration"; p.mkdir(parents=True)
            (p/"interface_map.json").write_text(json.dumps({"schema":"uiowa-098-interface-map-v1","boundaries":{"numeric_scores_synthesized":True}}))
            with self.assertRaises(workflow.IntegrationError): workflow._load_map(root)
    def test_presenter_receipt_counts_are_checked(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/"revenue/uiowa_rfq_18649_integration"; p.mkdir(parents=True)
            rows=[{"status":"X"} for _ in range(12)]
            (p/"presenter_run.json").write_text(json.dumps({"matrix":rows,"status_counts":{"X":11}}))
            with self.assertRaises(workflow.IntegrationError): workflow._presenter_receipt(root)
    def test_component_status_does_not_fabricate_missing(self):
        with tempfile.TemporaryDirectory() as td:
            status=workflow._component_status(Path(td))
            self.assertTrue(all(v=="NOT_YET_MERGED" for v in status.values()))
    def test_write_outputs_is_reviewable(self):
        packet={"run_sha256":"a","mapped_records":[],"workbench":{"cells":[],"receipt_sha256":"b"},
                "traceability_rehearsal":{"validator_stdout":"trace validation: PASS"},
                "presenter_run":{"receipt_sha256":"c"},"component_status":{"roadmap":"NOT_YET_MERGED"}}
        with tempfile.TemporaryDirectory() as td:
            workflow.write_outputs(packet, Path(td)); self.assertTrue((Path(td)/"integration-run.json").exists())
            self.assertIn("NOT_YET_MERGED", (Path(td)/"RUN_REPORT.md").read_text())
    def test_presenter_fixture_file_is_internally_consistent(self):
        data=json.loads((Path(__file__).parent/"presenter_run.json").read_text())
        self.assertEqual(len(data["matrix"]), 12)
        counts={}
        for row in data["matrix"]: counts[row["status"]]=counts.get(row["status"],0)+1
        self.assertEqual(counts, data["status_counts"])
        self.assertEqual(data["receipt_sha256"], "3b58382daa78e4c152ff87111e17322bc6f86fe0d92abc4cf69412ee8bb11530")

if __name__ == "__main__": unittest.main()
