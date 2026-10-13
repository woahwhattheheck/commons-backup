import json
import tempfile
import unittest
from pathlib import Path

from tools.authority_boundary_lint import lint


class AuthorityBoundaryLintTests(unittest.TestCase):
    def _scan_text(self, suffix: str, text: str, baseline=None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / f"case{suffix}"
            path.write_text(text, encoding="utf-8")
            baseline_path = None
            if baseline is not None:
                baseline_path = root / "baseline.json"
                baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            return lint.run(root, [path.name], baseline_path)

    def test_python_candidate_flag_controls_qualification(self):
        report = self._scan_text(".py", '''
def compile(candidate):
    if candidate.get("diagnostic_passed"):
        return {"state": "QUALIFIED_FOR_OWNER_SALES_REVIEW"}
    return {"state": "HOLD"}
''')
        self.assertEqual(report["summary"]["findings"], 1)
        row = report["findings"][0]
        self.assertEqual(row["rule_id"], lint.RULE_SELF_ATTESTED)
        self.assertEqual(row["field"], "diagnostic_passed")
        self.assertIn("QUALIFIED", row["sink"])

    def test_python_independent_receipt_in_gate_suppresses(self):
        report = self._scan_text(".py", '''
def compile(candidate, diagnostic_receipt):
    if candidate.get("diagnostic_passed") and diagnostic_receipt.verified:
        return {"state": "QUALIFIED_FOR_OWNER_SALES_REVIEW"}
    return {"state": "HOLD"}
''')
        self.assertEqual(report["summary"]["findings"], 0)

    def test_python_derived_authority_local_suppresses(self):
        report = self._scan_text(".py", '''
def compile(candidate, source_receipt):
    receipt_ok = source_receipt.verified
    if candidate.approved and receipt_ok:
        return "AUTHORIZED_FOR_RELEASE"
    return "HOLD"
''')
        self.assertEqual(report["summary"]["findings"], 0)

    def test_javascript_hostile_fixture_detected(self):
        fixture = Path(__file__).with_name("fixtures") / "freight_self_attested.js"
        report = lint.run(Path.cwd(), [str(fixture)])
        self.assertEqual(report["summary"]["findings"], 1)
        self.assertEqual(report["findings"][0]["field"], "diagnostic_passed")

    def test_javascript_independent_receipt_negative_control(self):
        fixture = Path(__file__).with_name("fixtures") / "freight_independent_authority.js"
        report = lint.run(Path.cwd(), [str(fixture)])
        self.assertEqual(report["summary"]["findings"], 0)

    def test_non_promotion_condition_is_not_flagged(self):
        report = self._scan_text(".js", '''
function metrics(candidate) {
  if (candidate.diagnostic_passed) { return { count: 1 }; }
  return { count: 0 };
}
''')
        self.assertEqual(report["summary"]["findings"], 0)

    def test_structured_json_candidate_hint(self):
        report = self._scan_text(".json", json.dumps({
            "candidate": {"diagnostic_passed": True, "state": "QUALIFIED_FOR_OWNER_SALES_REVIEW"}
        }))
        self.assertEqual(report["summary"]["findings"], 1)
        self.assertEqual(report["findings"][0]["rule_id"], lint.RULE_STRUCTURED_HINT)

    def test_structured_json_with_receipt_key_is_negative_control(self):
        report = self._scan_text(".json", json.dumps({
            "candidate": {"diagnostic_passed": True, "source_receipt": "abc", "state": "QUALIFIED_FOR_OWNER_SALES_REVIEW"}
        }))
        self.assertEqual(report["summary"]["findings"], 0)

    def test_exact_fingerprint_baseline_suppresses(self):
        text = '''
def compile(payload):
    if payload.approved:
        return "READY_FOR_SALES"
    return "HOLD"
'''
        first = self._scan_text(".py", text)
        row = first["findings"][0]
        baseline = {"schema": lint.BASELINE_SCHEMA, "findings": [{
            "rule_id": row["rule_id"], "path": row["path"], "content_fingerprint": row["content_fingerprint"]
        }]}
        second = self._scan_text(".py", text, baseline)
        self.assertEqual(second["summary"]["findings"], 0)
        self.assertEqual(second["summary"]["baseline_suppressed"], 1)

    def test_baseline_drift_resurfaces(self):
        text = '''
def compile(payload):
    if payload.approved:
        return "READY_FOR_SALES"
    return "HOLD"
'''
        first = self._scan_text(".py", text)
        row = first["findings"][0]
        baseline = {"schema": lint.BASELINE_SCHEMA, "findings": [{
            "rule_id": row["rule_id"], "path": row["path"], "content_fingerprint": row["content_fingerprint"]
        }]}
        changed = text.replace('"READY_FOR_SALES"', '"QUALIFIED_FOR_OWNER_SALES_REVIEW"')
        second = self._scan_text(".py", changed, baseline)
        self.assertEqual(second["summary"]["findings"], 1)
        self.assertTrue(second["findings"][0]["baseline_drift"])

    def test_receipt_digest_is_deterministic(self):
        report_a = self._scan_text(".js", 'function f(candidate){ if(candidate.ready){ return "READY_FOR_SALES"; } }')
        report_b = self._scan_text(".js", 'function f(candidate){ if(candidate.ready){ return "READY_FOR_SALES"; } }')
        self.assertEqual(report_a["receipt_digest"], report_b["receipt_digest"])

    def test_markdown_states_advisory_boundary(self):
        report = self._scan_text(".js", 'function f(candidate){ if(candidate.ready){ return "READY_FOR_SALES"; } }')
        rendered = lint.render_markdown(report)
        self.assertIn("Advisory review signal only", rendered)
        self.assertIn(report["receipt_digest"], rendered)

    def test_invalid_baseline_rejected(self):
        with self.assertRaises(ValueError):
            self._scan_text(".py", 'x = 1', {"schema": "wrong", "findings": []})


if __name__ == "__main__":
    unittest.main()
