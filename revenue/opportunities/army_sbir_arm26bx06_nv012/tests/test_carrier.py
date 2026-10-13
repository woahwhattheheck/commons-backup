from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import decision_program as dp
import qualification_gate as qg


def load(name):
    return json.loads((ROOT / name).read_text())


class DecisionProgramTests(unittest.TestCase):
    def test_point_demo_ready_for_human_not_final(self):
        result = dp.evaluate(load("examples/point_trade.json"))
        self.assertEqual(result["readiness"], "READY_FOR_HUMAN_REVIEW")
        self.assertIsNotNone(result["machine_preference"])
        self.assertTrue(result["human_decision_required"])
        self.assertIsNone(result["final_decision"])
        self.assertEqual(result["what_flips_decision"]["kind"], "RUNNER_UP_SCORE_SWING")

    def test_canonical_digest_is_key_order_independent(self):
        p = load("examples/point_trade.json")
        scrambled = {k: p[k] for k in reversed(list(p))}
        self.assertEqual(dp.digest(p), dp.digest(scrambled))

    def test_float_is_rejected(self):
        p = load("examples/point_trade.json")
        p["objectives"][0]["weight_bp"] = 3500.0
        with self.assertRaises(dp.ValidationError):
            dp.evaluate(p)

    def test_weight_sum_is_enforced(self):
        p = load("examples/point_trade.json")
        p["objectives"][0]["weight_bp"] -= 1
        with self.assertRaisesRegex(dp.ValidationError, "sum to 10000"):
            dp.evaluate(p)

    def test_constraint_excludes_option_deterministically(self):
        p = load("examples/point_trade.json")
        p["options"][0]["metrics"]["pack_mass_kg"] = 651
        p["constraints"][1]["value"] = 600
        result = dp.evaluate(p)
        rows = {r["option_id"]: r for r in result["option_results"]}
        self.assertFalse(rows["lfp"]["eligible"])
        self.assertIn("mass_limit", rows["lfp"]["failed_constraints"])

    def test_unresolved_assumption_and_high_risk_hold_refresh(self):
        result = dp.evaluate(load("examples/long_horizon_g2.json"))
        self.assertEqual(result["readiness"], "HOLD")
        self.assertIn("ASSUMPTION_NOT_SUPPORTED", result["blockers"])
        self.assertIn("HIGH_OR_CRITICAL_RISK", result["blockers"])

    def test_refresh_binds_exact_predecessor(self):
        receipt = dp.verify_refresh(load("examples/long_horizon_g1.json"), load("examples/long_horizon_g2.json"))
        self.assertEqual(receipt["from_generation"], 1)
        self.assertEqual(receipt["to_generation"], 2)
        self.assertTrue(receipt["human_re_review_required"])
        self.assertIn("ev-api-refresh", receipt["changed_evidence_ids"])

    def test_wrong_predecessor_digest_fails(self):
        g1 = load("examples/long_horizon_g1.json")
        g2 = load("examples/long_horizon_g2.json")
        g2["supersedes_digest"] = "0" * 64
        with self.assertRaisesRegex(dp.ValidationError, "exact prior generation"):
            dp.verify_refresh(g1, g2)

    def test_human_authority_cannot_be_disabled(self):
        p = load("examples/point_trade.json")
        p["human_authority"]["required"] = False
        with self.assertRaisesRegex(dp.ValidationError, "human authority"):
            dp.evaluate(p)

    def test_duplicate_ids_fail(self):
        p = load("examples/point_trade.json")
        p["risks"].append(dict(p["risks"][0]))
        with self.assertRaisesRegex(dp.ValidationError, "duplicate id"):
            dp.evaluate(p)

    def test_bias_not_run_holds(self):
        p = load("examples/point_trade.json")
        p["bias_checks"][0]["status"] = "NOT_RUN"
        result = dp.evaluate(p)
        self.assertEqual(result["readiness"], "HOLD")
        self.assertIn("BIAS_CHECK_NOT_PASS", result["blockers"])

    def test_supported_assumption_requires_evidence(self):
        p = load("examples/point_trade.json")
        p["assumptions"][0]["evidence_ids"] = []
        with self.assertRaisesRegex(dp.ValidationError, "at least one evidence id"):
            dp.evaluate(p)

    def test_risk_requires_evidence(self):
        p = load("examples/point_trade.json")
        p["risks"][0]["evidence_ids"] = []
        with self.assertRaisesRegex(dp.ValidationError, "at least one evidence id"):
            dp.evaluate(p)

    def test_bias_requires_evidence(self):
        p = load("examples/point_trade.json")
        p["bias_checks"][0]["evidence_ids"] = []
        with self.assertRaisesRegex(dp.ValidationError, "at least one evidence id"):
            dp.evaluate(p)

    def test_each_option_score_requires_evidence(self):
        p = load("examples/point_trade.json")
        p["options"][0]["score_evidence_ids"]["mass"] = []
        with self.assertRaisesRegex(dp.ValidationError, "at least one evidence id"):
            dp.evaluate(p)

    def test_unknown_semantic_evidence_ref_fails(self):
        p = load("examples/point_trade.json")
        p["risks"][0]["evidence_ids"] = ["made-up"]
        with self.assertRaisesRegex(dp.ValidationError, "unknown evidence made-up"):
            dp.evaluate(p)

    def test_timestamps_are_real_utc_not_opaque_strings(self):
        p = load("examples/point_trade.json")
        p["as_of"] = "not-a-time"
        with self.assertRaisesRegex(dp.ValidationError, "UTC RFC3339"):
            dp.evaluate(p)

    def test_future_evidence_fails(self):
        p = load("examples/point_trade.json")
        p["evidence"][0]["observed_at"] = "2026-09-15T00:00:00Z"
        with self.assertRaisesRegex(dp.ValidationError, "after program as_of"):
            dp.evaluate(p)

    def test_semantic_refresh_requires_evidence_generation_change(self):
        g1 = load("examples/long_horizon_g1.json")
        g2 = copy.deepcopy(g1)
        g2["generation"] = 2
        g2["supersedes_digest"] = dp.digest(g1)
        g2["as_of"] = "2026-09-14T00:00:00Z"
        g2["assumptions"][0]["status"] = "UNRESOLVED"
        with self.assertRaisesRegex(dp.ValidationError, "without authoritative evidence-generation change"):
            dp.verify_refresh(g1, g2)

    def test_cli_rejects_duplicate_json_keys(self):
        bad = ROOT / "tests" / "_duplicate.json"
        try:
            bad.write_text('{"schema_version":"commons.decision-program/v1","schema_version":"x"}\n')
            cp = subprocess.run([sys.executable, str(ROOT / "decision_program.py"), "evaluate", str(bad)], text=True, capture_output=True)
            self.assertEqual(cp.returncode, 2)
            self.assertIn("duplicate JSON key", cp.stderr)
        finally:
            bad.unlink(missing_ok=True)


class QualificationTests(unittest.TestCase):
    def test_example_stays_hold_and_never_authorizes_external_action(self):
        result = qg.evaluate(load("qualification.example.json"))
        self.assertEqual(result["disposition"], "HOLD")
        self.assertFalse(result["external_contact_authorized"])
        self.assertFalse(result["portal_mutation_authorized"])
        self.assertFalse(result["proposal_submission_authorized"])
        self.assertFalse(result["signature_authorized"])
        self.assertFalse(result["recognized_revenue"])

    def test_all_green_caller_assertions_cannot_mint_readiness(self):
        raw = load("qualification.example.json")
        for key in qg.REQUIRED_FACTS:
            raw["facts"][key] = True
            raw["evidence_refs"][key] = "fixture://evidence/" + key
        result = qg.evaluate(raw)
        self.assertEqual(result["disposition"], "HOLD")
        self.assertTrue(result["caller_assertions_complete"])
        self.assertIn("INDEPENDENT_AUTHORITY_NOT_BOUND", result["hold_reasons"])
        self.assertFalse(result["proposal_submission_authorized"])

    def test_explicit_ineligibility_is_no_go(self):
        raw = load("qualification.example.json")
        raw["facts"]["sbir_small_business_eligibility_evidenced"] = False
        raw["evidence_refs"]["sbir_small_business_eligibility_evidenced"] = "EXPLICIT_INELIGIBILITY"
        result = qg.evaluate(raw)
        self.assertEqual(result["disposition"], "NO_GO")


if __name__ == "__main__":
    unittest.main()
