from __future__ import annotations

import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import eval_tool as ev

HERE = Path(__file__).parent
NOW = dt.datetime(2026, 9, 16, 22, 10, 0, tzinfo=dt.timezone.utc)


def load(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


class EvalToolTests(unittest.TestCase):
    def setUp(self):
        self.suite = load("synthetic_suite.json")
        self.policy = load("policy.json")

    def test_clean_suite_passes_with_exact_metrics(self):
        report = ev.compile_report(self.suite, self.policy, NOW)
        self.assertEqual(report["state"], "PASS")
        self.assertEqual(report["metrics"]["nominal_accuracy"]["basis_points"], 10000)
        self.assertEqual(report["metrics"]["reliability"]["basis_points"], 7500)

    def test_policy_can_hold_reliability(self):
        p = copy.deepcopy(self.policy); p["min_reliability_bps"] = 8000
        report = ev.compile_report(self.suite, p, NOW)
        self.assertEqual(report["state"], "HOLD")
        self.assertIn("HOLD_RELIABILITY", report["reason_codes"])

    def test_perturbation_error_holds_robustness(self):
        s = copy.deepcopy(self.suite); s["cases"][3]["observed_class"] = "A"
        report = ev.compile_report(s, self.policy, NOW)
        self.assertIn("HOLD_ROBUST_ACCURACY", report["reason_codes"])

    def test_drift_drop_holds(self):
        s = copy.deepcopy(self.suite); s["cases"][5]["observed_class"] = "A"
        p = copy.deepcopy(self.policy); p["max_drift_drop_bps"] = 1000
        report = ev.compile_report(s, p, NOW)
        self.assertIn("HOLD_DRIFT_DROP", report["reason_codes"])

    def test_latency_holds(self):
        s = copy.deepcopy(self.suite); s["cases"][0]["latency_ms"] = 999
        report = ev.compile_report(s, self.policy, NOW)
        self.assertIn("HOLD_SUCCESS_LATENCY", report["reason_codes"])

    def test_explainability_evidence_holds(self):
        s = copy.deepcopy(self.suite)
        for case in s["cases"][:3]:
            case["explanation"] = {"provided": False, "evidence_ids": []}
        report = ev.compile_report(s, self.policy, NOW)
        self.assertIn("HOLD_EXPLAINABILITY_COVERAGE", report["reason_codes"])

    def test_future_suite_rejected(self):
        s = copy.deepcopy(self.suite); s["generated_at"] = "2026-10-01T00:00:00Z"
        with self.assertRaises(ev.EvalError): ev.compile_report(s, self.policy, NOW)

    def test_non_research_provider_rejected(self):
        s = copy.deepcopy(self.suite); s["provider"]["class"] = "GOVERNMENT_LIVE"
        with self.assertRaises(ev.EvalError): ev.compile_report(s, self.policy, NOW)

    def test_success_requires_observed_class(self):
        s = copy.deepcopy(self.suite); s["cases"][0]["observed_class"] = None
        with self.assertRaises(ev.EvalError): ev.compile_report(s, self.policy, NOW)

    def test_failure_cannot_claim_classification(self):
        s = copy.deepcopy(self.suite); s["cases"][-1]["observed_class"] = "B"
        with self.assertRaises(ev.EvalError): ev.compile_report(s, self.policy, NOW)

    def test_explanation_boolean_evidence_consistency(self):
        s = copy.deepcopy(self.suite); s["cases"][0]["explanation"] = {"provided": True, "evidence_ids": []}
        with self.assertRaises(ev.EvalError): ev.compile_report(s, self.policy, NOW)

    def test_bool_int_policy_alias_rejected(self):
        p = copy.deepcopy(self.policy); p["min_reliability_bps"] = True
        with self.assertRaises(ev.EvalError): ev.compile_report(self.suite, p, NOW)

    def test_duplicate_case_id_rejected(self):
        s = copy.deepcopy(self.suite); s["cases"][1]["id"] = s["cases"][0]["id"]
        with self.assertRaises(ev.EvalError): ev.compile_report(s, self.policy, NOW)

    def test_unknown_critical_field_rejected(self):
        s = copy.deepcopy(self.suite); s["cases"][0]["mission_ready"] = True
        with self.assertRaises(ev.EvalError): ev.compile_report(s, self.policy, NOW)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ev.EvalError): ev.strict_loads(b'{"schema":"x","schema":"y"}')

    def test_nonfinite_rejected(self):
        with self.assertRaises(ev.EvalError): ev.strict_loads(b'{"x":NaN}')

    def test_report_tamper_rejected(self):
        report = ev.compile_report(self.suite, self.policy, NOW)
        report["state"] = "HOLD"
        with self.assertRaises(ev.EvalError): ev.verify_report(self.suite, self.policy, report)

    def test_input_order_does_not_change_semantics(self):
        a = ev.compile_report(self.suite, self.policy, NOW)
        s = copy.deepcopy(self.suite); s["cases"] = list(reversed(s["cases"]))
        b = ev.compile_report(s, self.policy, NOW)
        self.assertEqual(a["metrics"], b["metrics"])
        self.assertNotEqual(a["source_bindings"]["suite_sha256"], b["source_bindings"]["suite_sha256"])

    def test_authority_ceiling_all_false(self):
        report = ev.compile_report(self.suite, self.policy, NOW)
        self.assertFalse(any(report["authority"].values()))

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); target = root / "real"; target.write_text("{}")
            link = root / "link"; link.symlink_to(target)
            with self.assertRaises(ev.EvalError): ev.read_regular(link)

    def test_create_exclusive_output(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "out"
            ev.write_exclusive(path, b"one")
            with self.assertRaises(ev.EvalError): ev.write_exclusive(path, b"two")

    def test_cli_compile_verify(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); s = root / "s.json"; p = root / "p.json"; r = root / "r.json"
            s.write_bytes(ev.canonical(self.suite)); p.write_bytes(ev.canonical(self.policy))
            self.assertEqual(ev.main(["compile-current", "--suite", str(s), "--policy", str(p), "--out", str(r)]), 0)
            self.assertEqual(ev.main(["verify-integrity", "--suite", str(s), "--policy", str(p), "--report", str(r)]), 0)


if __name__ == "__main__":
    unittest.main()
