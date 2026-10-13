import unittest

from tools.runtime_provenance.runtime_registry import verify_registry
from tools.runtime_provenance._test_fixtures import NOW, EVIDENCE_AT, PROBE_AT, GEN, proven_record, registry


class EvidenceBindingTests(unittest.TestCase):
    def assessment(self, record):
        return verify_registry(registry(record), now=NOW)["records"][0]

    def test_fresh_top_level_evidence_time_cannot_mask_different_typed_row(self):
        rec = proven_record()
        rec["evidence"][0]["observed_at"] = "2026-09-15T07:20:00Z"
        result = self.assessment(rec)
        self.assertFalse(result["deployment_proven"])
        self.assertIn("EVIDENCE_TIME_UNBOUND", result["reasons"])

    def test_fresh_top_level_probe_time_cannot_mask_different_typed_row(self):
        rec = proven_record()
        rec["evidence"][1]["observed_at"] = "2026-09-15T07:40:00Z"
        result = self.assessment(rec)
        self.assertFalse(result["deployment_proven"])
        self.assertIn("PROBE_TIME_UNBOUND", result["reasons"])

    def test_previous_generation_history_does_not_poison_current_generation(self):
        rec = proven_record()
        rec["evidence"].extend([
            {
                "kind": "DEPLOYMENT_RECEIPT",
                "ref": "provider:deploy/previous",
                "observed_at": "2026-09-14T06:00:00Z",
                "generation": "deploy:previous",
            },
            {
                "kind": "BLACK_BOX_PROBE",
                "ref": "probe:previous/1",
                "observed_at": "2026-09-14T06:10:00Z",
                "generation": "deploy:previous",
            },
        ])
        result = self.assessment(rec)
        self.assertTrue(result["deployment_proven"])
        self.assertEqual(result["reasons"], [])


if __name__ == "__main__":
    unittest.main()
