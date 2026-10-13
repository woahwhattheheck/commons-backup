"""Retained arithmetic, scope, interchange and actual CLI regression tests."""
import copy
import csv
from decimal import Decimal, localcontext
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from estimator import PlanError, activity_csv, estimate, load_json, markdown
from example_plans import band, make_plan


class EstimatorTests(unittest.TestCase):
    def setUp(self):
        self.plan = make_plan("release")

    def test_release_exact_totals(self):
        report = estimate(self.plan)
        self.assertEqual(report["one_time"]["total_hours"], band("52", "84.0", "128"))
        self.assertEqual(report["monthly_maintenance"]["total_hours"], band("6.00", "10.0", "16"))
        self.assertEqual(report["horizon_total_hours"], band("70.00", "114.0", "176"))

    def test_shared_training_is_counted_once(self):
        report = estimate(self.plan)
        self.assertEqual(len(report["activities"]), 7)
        self.assertEqual(report["by_kind"]["training"]["total_hours"], band("16", "24.0", "32"))
        for rec in report["recommendations"]:
            self.assertIn("REL-LEARN", rec["shared_activity_ids"])

    def test_specialist_bottleneck_not_hidden_by_developer_capacity(self):
        report = estimate(make_plan("security"))
        self.assertEqual(report["roles"][1]["implementation_capacity_status"], "EXCEEDS_EVEN_OPTIMISTIC_CAPACITY")
        self.assertEqual(report["roles"][1]["one_time"]["total_hours"], band("20", "28", "42"))
        self.assertEqual(report["roles"][0]["implementation_capacity_status"], "SCENARIO_DEPENDENT")

    def test_recurring_uses_horizon_without_changing_monthly_units(self):
        before = estimate(self.plan)
        self.plan["planning_months"] = 6
        after = estimate(self.plan)
        self.assertEqual(before["monthly_maintenance"], after["monthly_maintenance"])
        self.assertEqual(before["one_time"], after["one_time"])
        self.assertEqual(after["horizon_maintenance_hours"], band("36.00", "60.0", "96"))

    def test_reliability_keeps_unknown_effort_and_capacity_visible(self):
        report = estimate(make_plan("reliability"))
        self.assertEqual(report["estimate_status"], "INCOMPLETE")
        self.assertIsNone(report["one_time"]["total_hours"])
        self.assertIsNone(report["horizon_total_hours"])
        self.assertEqual(report["one_time"]["known_hours"], band("34", "56", "90"))
        self.assertEqual(report["roles"][0]["maintenance_capacity_status"], "UNKNOWN_CAPACITY")
        self.assertEqual(report["roles"][1]["implementation_capacity_status"], "UNKNOWN_DEMAND")
        self.assertIn("OPS-SIGNALS", report["one_time"]["missing_activity_ids"])

    def test_unknown_quantity_is_not_zero(self):
        self.plan["activities"][0]["units"] = None
        report = estimate(self.plan)
        self.assertIsNone(report["one_time"]["total_hours"])
        self.assertEqual(report["activities"][0]["missing_inputs"], ["units"])

    def test_unscoped_recommendation_keeps_totals_incomplete(self):
        rec = copy.deepcopy(self.plan["recommendations"][0])
        rec["id"] = "UNSCOPED"
        self.plan["recommendations"].append(rec)
        report = estimate(self.plan)
        self.assertEqual(report["recommendations_without_activities"], ["UNSCOPED"])
        self.assertIsNone(report["one_time"]["total_hours"])
        self.assertIsNone(report["monthly_maintenance"]["total_hours"])
        self.assertEqual(report["estimate_status"], "INCOMPLETE")

    def test_unknown_role_capacity_does_not_invalidate_known_effort(self):
        self.plan["roles"][0]["implementation_hours_per_month"] = None
        report = estimate(self.plan)
        self.assertEqual(report["estimate_status"], "COMPLETE_INPUTS")
        self.assertEqual(report["roles"][0]["implementation_capacity_status"], "UNKNOWN_CAPACITY")
        self.assertIsNotNone(report["one_time"]["total_hours"])

    def test_zero_capacity_and_zero_demand_are_distinct(self):
        self.plan["roles"][0]["implementation_hours_per_month"] = band(0)
        report = estimate(self.plan)
        self.assertEqual(report["roles"][0]["implementation_capacity_status"], "UNRESOURCED")
        self.assertEqual(report["roles"][0]["maintenance_capacity_status"], "NO_DEMAND")

    def test_conservative_capacity_envelope(self):
        report = estimate(self.plan)
        self.assertEqual(report["roles"][0]["implementation_capacity_status"], "FITS_ALL_STATED_SCENARIOS")
        self.assertEqual(report["roles"][1]["implementation_capacity_status"], "SCENARIO_DEPENDENT")
        self.assertEqual(report["roles"][1]["maintenance_capacity_status"], "SCENARIO_DEPENDENT")

    def test_bad_ranges(self):
        for value in (band(3, 2, 4), band(-1, 2, 3), band(True), band("NaN"), band("Infinity"), band("0E9999999"), band("0.0000001"), band("1e20"), band("nonsense")):
            with self.subTest(value=value):
                plan = copy.deepcopy(self.plan)
                plan["activities"][0]["units"] = value
                with self.assertRaises(PlanError):
                    estimate(plan)

    def test_bad_horizons(self):
        for value in (0, -1, 121, True, "3", 1.5):
            self.plan["planning_months"] = value
            with self.assertRaises(PlanError):
                estimate(self.plan)

    def test_duplicate_ids_and_references(self):
        for collection in ("roles", "recommendations", "activities", "assumptions"):
            plan = copy.deepcopy(self.plan)
            plan[collection].append(copy.deepcopy(plan[collection][0]))
            with self.assertRaises(PlanError):
                estimate(plan)
        self.plan["activities"][0]["recommendation_ids"] *= 2
        with self.assertRaises(PlanError):
            estimate(self.plan)

    def test_unknown_references(self):
        for field, value in (("role_id", "missing"), ("recommendation_ids", ["missing"]), ("assumption_ids", ["missing"])):
            plan = copy.deepcopy(self.plan)
            plan["activities"][0][field] = value
            with self.assertRaises(PlanError):
                estimate(plan)

    def test_cycle_and_unknown_prerequisite(self):
        self.plan["recommendations"][0]["dependencies"] = ["SYN-REL-2"]
        with self.assertRaisesRegex(PlanError, "cycle"):
            estimate(self.plan)
        self.plan["recommendations"][0]["dependencies"] = ["MISSING"]
        with self.assertRaises(PlanError):
            estimate(self.plan)

    def test_dependency_order_does_not_depend_on_input_order(self):
        self.plan["recommendations"].reverse()
        report = estimate(self.plan)
        self.assertEqual([r["id"] for r in report["recommendations"]], ["SYN-REL-1", "SYN-REL-2"])

    def test_missing_or_unknown_fields(self):
        for change in ("missing", "extra"):
            plan = copy.deepcopy(self.plan)
            if change == "missing":
                del plan["activities"][0]["unit_label"]
            else:
                plan["undocumented"] = True
            with self.assertRaises(PlanError):
                estimate(plan)

    def test_empty_model_and_unknown_evidence_class_rejected(self):
        for key, value in (("roles", []), ("recommendations", []), ("evidence_class", "VERIFIED_UNIVERSITY_DATA")):
            plan = copy.deepcopy(self.plan)
            plan[key] = value
            with self.assertRaises(PlanError):
                estimate(plan)

    def test_strict_json_and_decimal_numbers(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{broken'):
            with self.assertRaises(PlanError):
                load_json(text)
        plan = load_json(json.dumps(self.plan).replace('"1.5"', '1.5'))
        self.assertEqual(estimate(plan)["one_time"]["total_hours"], band("52", "84.0", "128"))

    def test_no_mutation_or_decimal_context_dependency(self):
        before = copy.deepcopy(self.plan)
        expected = estimate(self.plan)
        with localcontext() as ctx:
            ctx.prec = 2
            self.assertEqual(estimate(self.plan), expected)
        self.assertEqual(self.plan, before)
        expected["recommendations"][0]["dependencies"].append("CHANGED")
        self.assertEqual(self.plan, before)

    def test_csv_unicode_multiline_and_formula_looking_text(self):
        self.plan["activities"][0]["description"] = '  =not a formula,\nUnicode: caf\u00e9 \u0394 | notes'
        report = estimate(self.plan)
        rows = list(csv.DictReader(io.StringIO(activity_csv(report))))
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["description"], "'" + self.plan["activities"][0]["description"])
        self.assertTrue(all(len(r) == 18 for r in rows))
        self.assertEqual(rows[0]["period"], "ONE_TIME")
        self.assertEqual(rows[-1]["period"], "PER_MONTH")

    def test_markdown_carries_adoption_assumptions_and_unknowns(self):
        plan = make_plan("reliability")
        plan["roles"][0]["name"] = "Ops | <team>"
        text = markdown(estimate(plan))
        self.assertIn("UNKNOWN", text)
        self.assertIn("Ops &#124; &lt;team&gt;", text)
        self.assertIn("Evidence to collect later:", text)
        self.assertIn("A-CAPACITY", text)
        self.assertIn("not confidence intervals", text)

    def test_positive_range_arithmetic_randomized(self):
        rng = random.Random(8642)
        for _ in range(100):
            plan = make_plan("security")
            plan["activities"] = [plan["activities"][0]]
            units = sorted(rng.randrange(0, 30) for _ in range(3))
            hours = sorted(rng.randrange(0, 20) for _ in range(3))
            plan["activities"][0]["units"] = dict(zip(("low", "central", "high"), units))
            plan["activities"][0]["hours_per_unit"] = dict(zip(("low", "central", "high"), hours))
            actual = estimate(plan)["one_time"]["total_hours"]
            self.assertEqual(actual, {p: str(u * h) for p, u, h in zip(("low", "central", "high"), units, hours)})

    def test_cli_all_three_cases_and_repeat_does_not_overwrite(self):
        script = Path(__file__).with_name("estimator.py")
        with tempfile.TemporaryDirectory() as td:
            for case in ("release", "security", "reliability"):
                destination = Path(td) / case
                command = [sys.executable, str(script), "--demo", case, "--output-dir", str(destination)]
                run = subprocess.run(command, capture_output=True, text=True, timeout=10)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(set(p.name for p in destination.iterdir()), {"input.json", "estimate.json", "estimate.md", "activities.csv"})
                report = json.loads((destination / "estimate.json").read_text())
                self.assertEqual(report, estimate(make_plan(case)))
                before = {p.name: p.read_bytes() for p in destination.iterdir()}
                again = subprocess.run(command, capture_output=True, text=True, timeout=10)
                self.assertEqual(again.returncode, 2)
                self.assertEqual(before, {p.name: p.read_bytes() for p in destination.iterdir()})

    def test_cli_invalid_input_leaves_no_output(self):
        script = Path(__file__).with_name("estimator.py")
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "broken.json"
            source.write_text('{"schema":"bad"}')
            destination = Path(td) / "out"
            result = subprocess.run([sys.executable, str(script), "--input", str(source), "--output-dir", str(destination)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(destination.exists())


class OperatorContractTests(unittest.TestCase):
    def test_blank_worksheet_stays_unassessed(self):
        plan = load_json((Path(__file__).parent / "worksheet.json").read_text())
        report = estimate(plan)
        self.assertEqual(report["estimate_status"], "INCOMPLETE")
        self.assertIsNone(report["one_time"]["total_hours"])
        self.assertIsNone(report["monthly_maintenance"]["total_hours"])
        self.assertEqual(report["roles"][0]["implementation_capacity_status"], "UNKNOWN_DEMAND")

    def test_operator_report_exposes_skills_and_actual_capacity(self):
        text = markdown(estimate(make_plan("security")))
        self.assertIn("Facilitated design and review", text)
        self.assertIn("8 / 12 / 16 person-hours", text)
        self.assertIn("EXCEEDS_EVEN_OPTIMISTIC_CAPACITY", text)


if __name__ == "__main__":
    unittest.main()
