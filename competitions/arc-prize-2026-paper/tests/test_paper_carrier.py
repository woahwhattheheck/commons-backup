from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(HERE))

import microdynamics
import paper_carrier as pc


class PaperCarrierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        microdynamics.write_outputs(HERE)
        cls.paper = (HERE / "paper.md").read_text(encoding="utf-8")
        cls.results = pc.load_json_strict(HERE / "experiment_results.json")
        cls.example = pc.load_json_strict(HERE / "evidence.example.json")

    def good_evidence(self):
        evidence = json.loads(json.dumps(self.example))
        evidence.update({
            "kaggle_track": "ARC-AGI-3",
            "kaggle_submission_id": "real-provider-id-1234",
            "public_notebook_url": "https://www.kaggle.com/code/example/real-notebook",
            "leaderboard_score": 0.125,
            "cover_asset_sha256": "a" * 64,
        })
        evidence["provider_deadline"] = {
            "reconciled": True,
            "source_urls": list(pc.OFFICIAL_DEADLINE_SOURCES.values()),
            "effective_deadline_utc": pc.CONSERVATIVE_DEADLINE_UTC,
            "verified_at_utc": "2026-09-14T03:45:00Z",
        }
        return evidence

    def compile(self, evidence=None, paper=None, results=None):
        return pc.compile_readiness(
            self.good_evidence() if evidence is None else evidence,
            paper_text=self.paper if paper is None else paper,
            experiment_results=self.results if results is None else results,
            now_utc="2026-09-14T04:00:00Z",
        )

    def test_paper_is_under_limit_and_structured(self):
        validation = pc.validate_paper_text(self.paper)
        self.assertTrue(validation["word_limit_ok"], validation)
        self.assertTrue(validation["structure_ok"], validation)
        self.assertLessEqual(validation["word_count_conservative"], 1500)

    def test_example_is_hold(self):
        receipt = pc.compile_readiness(
            self.example,
            paper_text=self.paper,
            experiment_results=self.results,
            now_utc="2026-09-14T04:00:00Z",
        )
        self.assertEqual(receipt["disposition"], "HOLD")
        self.assertFalse(receipt["authority"]["external_mutation_authorized"])

    def test_exact_evidence_can_reach_owner_review_only(self):
        receipt = self.compile()
        self.assertEqual(receipt["disposition"], "READY_FOR_OWNER_KAGGLE_SUBMISSION_REVIEW")
        self.assertFalse(receipt["authority"]["kaggle_submission_performed"])
        self.assertFalse(receipt["authority"]["award_attested"])
        self.assertFalse(receipt["authority"]["payment_attested"])

    def test_word_limit_fails_closed(self):
        paper = self.paper + "\n" + (" filler" * 1600)
        receipt = self.compile(paper=paper)
        self.assertIn("PAPER_WORD_LIMIT_EXCEEDED", receipt["reasons"])

    def test_upstream_pin_drift_fails(self):
        evidence = self.good_evidence()
        evidence["upstream"]["ARC-AGI-3-SAGE"] = "0" * 40
        self.assertIn("UPSTREAM_PIN_MISMATCH:ARC-AGI-3-SAGE", self.compile(evidence=evidence)["reasons"])

    def test_local_result_cannot_claim_kaggle_accuracy(self):
        results = json.loads(json.dumps(self.results))
        results["claims_kaggle_accuracy"] = True
        self.assertIn("EXPERIMENT_KAGGLE_ACCURACY_OVERREACH", self.compile(results=results)["reasons"])

    def test_required_ablations_are_enforced(self):
        results = json.loads(json.dumps(self.results))
        results["variants"] = [r for r in results["variants"] if r["name"] != "no_skill_reuse"]
        self.assertIn("EXPERIMENT_REQUIRED_ABLATIONS_MISSING", self.compile(results=results)["reasons"])

    def test_missing_notebook_holds(self):
        evidence = self.good_evidence()
        evidence["public_notebook_url"] = None
        self.assertIn("PUBLIC_NOTEBOOK_URL_MISSING", self.compile(evidence=evidence)["reasons"])

    def test_missing_cover_holds(self):
        evidence = self.good_evidence()
        evidence["cover_asset_sha256"] = None
        self.assertIn("COVER_MEDIA_EVIDENCE_MISSING", self.compile(evidence=evidence)["reasons"])

    def test_deadline_disagreement_must_be_reconciled(self):
        evidence = self.good_evidence()
        evidence["provider_deadline"]["reconciled"] = False
        self.assertIn("PROVIDER_DEADLINE_UNRECONCILED", self.compile(evidence=evidence)["reasons"])

    def test_later_than_conservative_deadline_rejected(self):
        evidence = self.good_evidence()
        evidence["provider_deadline"]["effective_deadline_utc"] = "2026-11-09T23:59:00Z"
        self.assertIn("PROVIDER_DEADLINE_WEAKER_THAN_CONSERVATIVE_FENCE", self.compile(evidence=evidence)["reasons"])

    def test_future_verification_time_rejected(self):
        evidence = self.good_evidence()
        evidence["provider_deadline"]["verified_at_utc"] = "2027-01-01T00:00:00Z"
        self.assertIn("PROVIDER_DEADLINE_VERIFICATION_TIME_INVALID", self.compile(evidence=evidence)["reasons"])

    def test_forbidden_award_self_assertion_rejected(self):
        evidence = self.good_evidence()
        evidence["winner"] = True
        self.assertTrue(any(r.startswith("FORBIDDEN_RESULT_AUTHORITY") for r in self.compile(evidence=evidence)["reasons"]))

    def test_receipt_is_deterministic(self):
        self.assertEqual(self.compile()["receipt_sha256"], self.compile()["receipt_sha256"])

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaises(ValueError):
                pc.load_json_strict(path)

    def test_microdynamics_result_schema(self):
        reasons = pc.validate_experiment_results(self.results)
        self.assertEqual(reasons, [])
        names = {r["name"] for r in self.results["variants"]}
        self.assertEqual(names, set(microdynamics.VARIANTS))

    def test_full_mechanism_reduces_action_cost_vs_each_ablation(self):
        rows = {r["name"]: r for r in self.results["variants"]}
        for name in ("no_skill_reuse", "no_model_update", "no_information_gain"):
            with self.subTest(name=name):
                self.assertLess(rows["full"]["mean_actions"], rows[name]["mean_actions"])


if __name__ == "__main__":
    unittest.main()
