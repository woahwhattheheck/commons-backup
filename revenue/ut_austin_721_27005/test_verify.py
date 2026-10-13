from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ut_verify", HERE / "verify.py")
assert SPEC and SPEC.loader
ut_verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ut_verify)

def load(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))

class PursuitVerifierTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load("source_manifest.json")
        self.qual = load("qualification.json")

    def test_current_carrier_is_teaming_ready_not_prime_ready(self):
        result = ut_verify.verify(self.manifest, self.qual)
        self.assertEqual(result["posture"], "TEAMING_READY")
        self.assertFalse(result["prime_ready"])
        self.assertFalse(result["submission_authorized"])
        self.assertIn("comparable_project_experience", result["prime_missing_gates"])
        self.assertIn("authorized_pricing", result["prime_missing_gates"])

    def test_missing_official_source_fails_closed(self):
        bad = copy.deepcopy(self.manifest)
        bad["sources"] = [s for s in bad["sources"] if s["id"] != "bonfire"]
        with self.assertRaises(ut_verify.VerificationError):
            ut_verify.verify(bad, self.qual)

    def test_deadline_rewrite_fails_closed(self):
        bad = copy.deepcopy(self.manifest)
        bad["opportunity"]["submission_deadline"] = "2026-09-29T14:30:00-05:00"
        with self.assertRaises(ut_verify.VerificationError):
            ut_verify.verify(bad, self.qual)

    def test_action_authority_cannot_be_silently_enabled(self):
        bad = copy.deepcopy(self.qual)
        bad["action_authority"]["buyer_contact"] = True
        with self.assertRaises(ut_verify.VerificationError):
            ut_verify.verify(self.manifest, bad)

    def test_verified_evidence_requires_reference(self):
        bad = copy.deepcopy(self.qual)
        bad["evidence"]["curated_ux_portfolio"] = {"status": "VERIFIED", "refs": []}
        with self.assertRaises(ut_verify.VerificationError):
            ut_verify.verify(self.manifest, bad)

    def test_false_prime_assertion_is_rejected(self):
        bad = copy.deepcopy(self.qual)
        bad["asserted_posture"] = "PRIME_READY"
        with self.assertRaises(ut_verify.VerificationError):
            ut_verify.verify(self.manifest, bad)

if __name__ == "__main__":
    unittest.main()
