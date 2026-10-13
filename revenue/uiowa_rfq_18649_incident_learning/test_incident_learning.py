"""Behavior and failure tests for the UIOWA-067 fictional preparation kit."""
import copy
import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from revenue.uiowa_rfq_18649_incident_learning.analyze import analyze
from revenue.uiowa_rfq_18649_incident_learning.contract import load, validate
from revenue.uiowa_rfq_18649_incident_learning.fixture import sample
from revenue.uiowa_rfq_18649_incident_learning.report import actions_csv, markdown


class IncidentLearningTests(unittest.TestCase):
    def setUp(self):
        self.data = sample()

    def action(self, aid="ACT-01"):
        return next(a for a in analyze(self.data)["actions"] if a["id"] == aid)

    def test_required_acceptance_states(self):
        report = analyze(self.data)
        self.assertEqual(report["summary"], {"incidents": 3, "actions": 6, "states": {
            "closure_unverified": 1, "implementation_verified": 1, "open_work": 3, "replacement_documented": 1}, "overdue_unresolved": 3})

    def test_exact_time_and_unknown_interval(self):
        ess, iam, ris = analyze(self.data)["incidents"]
        self.assertEqual(ess["minutes"]["impact_to_restoration"], 60)
        self.assertEqual(ess["minutes"]["detection_to_restoration"], 55)
        self.assertIsNone(iam["minutes"]["impact_to_restoration"])
        self.assertIsNone(ris["minutes"]["restoration_to_verification"])

    def test_overdue_is_explicit_asof_not_wall_clock(self):
        self.assertEqual(self.action("ACT-02")["days_past_due"], 9)
        self.assertEqual(analyze(self.data), analyze(copy.deepcopy(self.data)))

    def test_due_exact_boundary_not_overdue(self):
        self.data["actions"][1]["due_at"] = self.data["as_of"]
        self.assertFalse(self.action("ACT-02")["overdue_unresolved"])

    def test_verified_implementation_is_not_merely_closed(self):
        self.data["actions"][0]["verification_evidence_ids"] = []
        self.assertEqual(self.action()["evidence_state"], "closure_unverified")

    def test_postmortem_cannot_be_implementation_proof(self):
        self.data["actions"][0]["implementation_evidence_ids"] = ["EV-ESS"]
        with self.assertRaisesRegex(ValueError, "wrong evidence kind"):
            analyze(self.data)

    def test_temporal_verification_must_follow_completion(self):
        self.data["actions"][0]["completed_at"] = "2026-09-08T00:00:00Z"
        self.assertEqual(self.action()["evidence_state"], "closure_unverified")

    def test_late_completion_is_preserved(self):
        self.data["actions"][0]["due_at"] = "2026-09-07T00:00:00Z"
        self.assertFalse(self.action()["overdue_unresolved"])
        self.assertAlmostEqual(self.action()["late_completion_days"], 0.438)

    def test_replacement_preserves_unfinished_successor(self):
        self.assertEqual(self.action("ACT-04")["evidence_state"], "replacement_documented")
        self.assertEqual(self.action("ACT-05")["evidence_state"], "open_work")
        self.assertTrue(self.action("ACT-05")["overdue_unresolved"])

    def test_missing_decision_not_justified(self):
        self.data["actions"][3]["replacement"]["evidence_ids"] = []
        self.assertEqual(self.action("ACT-04")["evidence_state"], "replacement_unsubstantiated")

    def test_replacement_cycle_rejected(self):
        self.data["actions"][4]["replacement"] = {"action_id": "ACT-04", "reason": "loop", "evidence_ids": ["EV-DECISION"]}
        with self.assertRaisesRegex(ValueError, "replacement cycle"):
            analyze(self.data)

    def test_replacement_cannot_drop_condition(self):
        self.data["actions"][3]["replacement"]["action_id"] = "ACT-06"
        with self.assertRaisesRegex(ValueError, "drops original"):
            analyze(self.data)

    def test_normalized_comparison(self):
        self.assertEqual(self.action()["effectiveness"]["rates_per_1000"], {"before": 6.0, "after": 1.0})
        self.assertEqual(self.action()["effectiveness"]["state"], "observed_improvement")
        self.assertIn("descriptive_comparison_not_causal_proof", self.action()["effectiveness"]["reasons"])

    def test_zero_and_unknown_exposure_not_success(self):
        for value in (0, None):
            with self.subTest(value=value):
                self.data["actions"][0]["effectiveness"]["after"]["exposure"] = value
                self.assertEqual(self.action()["effectiveness"]["state"], "not_comparable")

    def test_missing_or_incomplete_measurements(self):
        for field, value in (("complete", False), ("events", None), ("evidence_ids", []), ("cohort", "different")):
            with self.subTest(field=field):
                self.data = sample()
                self.data["actions"][0]["effectiveness"]["after"][field] = value
                self.assertEqual(self.action()["effectiveness"]["state"], "not_comparable")

    def test_effectiveness_cannot_precede_implementation(self):
        self.data["actions"][0]["completed_at"] = "2026-09-10T00:00:00Z"
        self.assertIn("followup_precedes_completion", self.action()["effectiveness"]["reasons"])

    def test_deterioration_and_equality(self):
        for count, expected in ((12, "unchanged"), (20, "observed_deterioration")):
            self.data["actions"][0]["effectiveness"]["after"]["events"] = count
            self.assertEqual(self.action()["effectiveness"]["state"], expected)

    def test_duplicate_source_and_dangling_reference(self):
        self.data["sources"].append(copy.deepcopy(self.data["sources"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate source"):
            analyze(self.data)
        self.data = sample()
        self.data["actions"][0]["verification_evidence_ids"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "unresolved"):
            analyze(self.data)

    def test_bad_time_and_future_source(self):
        for value in ("2026-09-01T09:00:00", "not-a-date", "2026-09-20T00:00:00Z"):
            self.data = sample()
            self.data["sources"][0]["observed_at"] = value
            with self.assertRaises(ValueError):
                analyze(self.data)

    def test_boolean_count_rejected(self):
        self.data["actions"][0]["effectiveness"]["before"]["events"] = True
        with self.assertRaisesRegex(ValueError, "counts"):
            analyze(self.data)

    def test_reversed_incident_rejected(self):
        self.data["incidents"][0]["events"][4]["at"] = "2026-09-01T08:00:00Z"
        with self.assertRaisesRegex(ValueError, "reversed timeline"):
            analyze(self.data)

    def test_shared_condition_count_not_group_votes(self):
        condition = next(c for c in analyze(self.data)["conditions"] if c["id"] == "COND-QUEUE")
        self.assertEqual(condition["observed_incident_count"], 2)
        self.assertEqual(condition["groups"], ["ESS", "RIS"])
        self.assertEqual(condition["action_ids"].count("ACT-02"), 1)
        self.assertIn("not independent", condition["interpretation"])

    def test_source_and_reports_portable(self):
        report = analyze(self.data)
        text = markdown(report)
        self.assertIn("SYNTHETIC", text)
        for source in self.data["sources"]:
            self.assertIn(source["locator"], text)
        rows = list(csv.DictReader(io.StringIO(actions_csv(report))))
        self.assertEqual(json.loads(rows[0]["incident_ids"]), ["INC-ESS-1"])
        self.assertIsNone(json.loads(rows[-1]["owner_role"]))

    def test_unicode_multiline_and_formula_as_text(self):
        self.data["actions"][0]["owner_role"] = '=1+1 | naïve\nowner'
        result = analyze(self.data)
        row = next(csv.DictReader(io.StringIO(actions_csv(result))))
        self.assertEqual(json.loads(row["owner_role"]), self.data["actions"][0]["owner_role"])
        self.assertTrue(row["owner_role"].startswith('"'))
        self.assertIn('\\|', markdown(result))

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"schema":"a","schema":"b"}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load(path)

    def test_interview_is_not_a_measured_timeline(self):
        next(s for s in self.data["sources"] if s["id"] == "EV-ESS")["kind"] = "interview"
        incident = analyze(self.data)["incidents"][0]
        self.assertIsNone(incident["minutes"]["impact_to_restoration"])
        self.assertIn("verified", incident["milestones_missing_evidence"])

    def test_baseline_cannot_include_postimplementation_data(self):
        self.data["actions"][0]["effectiveness"]["before"]["end"] = "2026-09-07T23:00:00Z"
        self.assertIn("baseline_overlaps_implementation", self.action()["effectiveness"]["reasons"])

    def test_measurement_evidence_cannot_predate_its_window(self):
        next(s for s in self.data["sources"] if s["id"] == "EV-AFTER")["observed_at"] = "2026-09-09T00:00:00Z"
        self.assertIn("after_evidence_precedes_window_end", self.action()["effectiveness"]["reasons"])

    def test_cli_roundtrip_and_bad_input(self):
        root = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(root / "fixture.py"), tmp], check=True)
            path = Path(tmp) / "packet.json"
            original = path.read_bytes()
            for fmt in ("json", "csv", "markdown"):
                result = subprocess.run([sys.executable, str(root / "report.py"), str(path), "--format", fmt], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout)
            self.assertEqual(original, path.read_bytes())
            path.write_text('{"oops":1}')
            result = subprocess.run([sys.executable, str(root / "report.py"), str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
