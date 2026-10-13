import json
import tempfile
import unittest
from pathlib import Path

import observability


HERE = Path(__file__).resolve().parent


class ObservabilityAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.packet = json.loads((HERE / "examples.json").read_text(encoding="utf-8"))

    def test_examples_cover_three_fictional_services(self):
        result = observability.assess_packet(self.packet)
        self.assertEqual(result["finding_count"], 3)
        findings = {f["objective_id"]: f for f in result["findings"]}

        self.assertEqual(findings["REG-01"]["status"], "SUPPORTED")
        self.assertIn("dependency_visibility_partial", findings["REG-01"]["issues"])

        self.assertEqual(findings["RES-01"]["status"], "SUPPORTED")
        self.assertIn("dependency_visibility_unknown", findings["RES-01"]["issues"])
        self.assertIn("decision_use_not_evidenced", findings["RES-01"]["issues"])

        self.assertEqual(findings["SIGNIN-01"]["status"], "PARTIAL")
        self.assertIn("indicator_not_user_visible", findings["SIGNIN-01"]["issues"])
        self.assertIn("indicator_definition_missing", findings["SIGNIN-01"]["issues"])
        self.assertIn("diagnostic_context_missing", findings["SIGNIN-01"]["issues"])

    def test_missing_measurement_evidence_is_unknown_not_failure(self):
        service = {
            "service_id": "SYN-X",
            "service_name": "Fictional service",
        }
        objective = {
            "objective_id": "X-1",
            "objective": "Fictional user outcome",
            "window": "30 days",
            "target": {"operator": ">=", "value": 0.99},
            "indicator": {
                "kind": "ratio",
                "user_visible": True,
            },
            "dependencies": [],
            "diagnostic_context": ["correlation id"],
            "decision_evidence": [],
        }
        finding = observability.assess_objective(service, objective)
        self.assertEqual(finding.status, "UNKNOWN")
        self.assertIn("measurement_evidence_missing", finding.issues)

    def test_zero_ratio_denominator_is_partial_with_question(self):
        service = {"service_id": "SYN-X", "service_name": "Fictional service"}
        objective = {
            "objective_id": "X-2",
            "objective": "Fictional success ratio",
            "window": "7 days",
            "target": {"operator": ">=", "value": 0.99},
            "indicator": {"kind": "ratio", "user_visible": True},
            "measurement_evidence": {
                "source_ref": "SYN-M",
                "definition_ref": "SYN-D",
                "period_start": "2026-01-01T00:00:00Z",
                "period_end": "2026-01-07T23:59:59Z",
                "numerator": 0,
                "denominator": 0,
            },
            "dependencies": [],
            "diagnostic_context": ["trace id"],
            "decision_evidence": [],
        }
        finding = observability.assess_objective(service, objective)
        self.assertEqual(finding.status, "PARTIAL")
        self.assertIn("invalid_denominator", finding.issues)

    def test_bad_indicator_kind_is_rejected(self):
        service = {"service_id": "SYN-X", "service_name": "Fictional service"}
        objective = {
            "objective_id": "X-3",
            "objective": "Fictional outcome",
            "window": "7 days",
            "indicator": {"kind": "magic-score", "user_visible": True},
        }
        with self.assertRaisesRegex(ValueError, "unsupported indicator kind"):
            observability.assess_objective(service, objective)

    def test_result_round_trip_is_plain_json(self):
        result = observability.assess_packet(self.packet)
        rendered = json.dumps(result, sort_keys=True)
        parsed = json.loads(rendered)
        self.assertEqual(parsed["schema"], "uiowa-065-observability-assessment-v1")
        self.assertEqual(parsed["status_counts"]["SUPPORTED"], 2)
        self.assertEqual(parsed["status_counts"]["PARTIAL"], 1)
        self.assertEqual(parsed["status_counts"]["UNKNOWN"], 0)


if __name__ == "__main__":
    unittest.main()
