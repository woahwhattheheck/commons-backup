from __future__ import annotations
import copy
import csv
import io
import itertools
import json
import random
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal, localcontext
from pathlib import Path

import economics as e
from synthetic_cases import synthetic_document

D = Decimal
ROOT = Path(__file__).parent


class EconomicsTests(unittest.TestCase):
    def setUp(self):
        self.doc = synthetic_document()
        self.case = self.doc["scenarios"][0]

    def set_range(self, key, low, base=None, high=None, scenario=None):
        case = self.case if scenario is None else scenario
        case["inputs"][key]["range"] = dict(zip(("low", "base", "high"), map(str, (low, low if base is None else base, low if high is None else high))))

    def point(self, **overrides):
        value = e.values_at(self.case)
        value.update({key: None if item is None else D(str(item)) for key, item in overrides.items()})
        return value

    def test_four_expected_classifications(self):
        report = e.analyze(self.doc)
        self.assertEqual([x["economic_classification"] for x in report["scenarios"]], ["POSITIVE_ACROSS_RANGE", "NEGATIVE_ACROSS_RANGE", "SENSITIVE_TO_ASSUMPTIONS", "UNKNOWN"])

    def test_known_decimal_base_case(self):
        point = e.analyze(self.doc)["scenarios"][0]["base"]
        self.assertEqual(point["assisted_tasks_per_month"], D("320"))
        self.assertEqual(point["net_capacity_hours_per_month"], D("129"))
        self.assertEqual(point["economic_horizon_net"], D("90942"))
        self.assertEqual(point["net_capacity_hours_horizon"], D("1530"))
        self.assertEqual(point["external_cash_horizon"], D("858"))
        self.assertEqual(point["cash_conversion_horizon_net"], D("-858"))

    def test_simple_hand_calculation(self):
        v = {key: D(0) for key in e.FIELDS}
        v.update(monthly_tasks=D(60), adoption_fraction=D(1), baseline_minutes=D(60), author_minutes=D(10), checking_minutes=D(10), rework_fraction=D("0.5"), rework_minutes=D(20), loaded_hourly_rate=D(60), attempts_per_task=D(2), generation_cash_per_attempt=D("0.1"), integration_hours=D(10), setup_cash=D(100), support_hours=D(2), maintenance_hours=D(3), platform_cash=D(8), cash_conversion_fraction=D(0))
        r = e.evaluate(v, 12)
        self.assertEqual(r["net_capacity_hours_per_month"], D(25))
        self.assertEqual(r["external_cash_per_month"], D(20))
        self.assertEqual(r["operating_economic_net_per_month"], D(1480))
        self.assertEqual(r["setup_economic_value"], D(700))
        self.assertEqual(r["economic_horizon_net"], D(17060))
        self.assertEqual(r["cash_conversion_horizon_net"], D(-340))
        self.assertEqual(r["unit_economic_margin"], D("29.8"))

    def test_zero_conversion_is_not_economic_zero(self):
        r = e.evaluate(self.point(cash_conversion_fraction=0), 12)
        self.assertGreater(r["economic_horizon_net"], 0)
        self.assertEqual(r["cash_conversion_horizon_net"], -r["external_cash_horizon"])

    def test_full_conversion_equals_opportunity_value(self):
        r = e.evaluate(self.point(cash_conversion_fraction=1), 12)
        self.assertEqual(r["cash_conversion_horizon_net"], r["economic_horizon_net"])

    def test_half_conversion_does_not_discount_external_cash(self):
        r = e.evaluate(self.point(cash_conversion_fraction="0.5"), 12)
        self.assertEqual(r["cash_conversion_horizon_net"], r["net_capacity_hours_horizon"] * D(60) * D("0.5") - r["external_cash_horizon"])

    def test_more_bad_volume_is_worse(self):
        v = e.values_at(self.doc["scenarios"][1])
        a = e.evaluate(dict(v, monthly_tasks=D(10)), 12)
        b = e.evaluate(dict(v, monthly_tasks=D(20)), 12)
        self.assertLess(b["economic_horizon_net"], a["economic_horizon_net"])
        self.assertIsNone(b["break_even"]["assisted_tasks_per_month_exact"])

    def test_more_checking_and_rework_reduce_value(self):
        base = e.evaluate(self.point(), 12)["economic_horizon_net"]
        for key in ("checking_minutes", "rework_minutes", "attempts_per_task", "integration_hours", "support_hours", "maintenance_hours", "setup_cash", "platform_cash"):
            v = self.point()
            v[key] += D(1)
            self.assertLess(e.evaluate(v, 12)["economic_horizon_net"], base, key)

    def test_zero_volume_keeps_fixed_and_setup_costs(self):
        r = e.evaluate(self.point(monthly_tasks=0), 12)
        self.assertLess(r["economic_horizon_net"], 0)
        self.assertEqual(r["assisted_tasks_per_month"], 0)
        self.assertIsNone(r["break_even"]["maximum_checking_minutes"])
        self.assertIsNone(r["break_even"]["adoption_fraction_exact"])

    def test_zero_adoption_keeps_fixed_costs(self):
        r = e.evaluate(self.point(adoption_fraction=0), 12)
        self.assertLess(r["economic_horizon_net"], 0)
        self.assertEqual(r["baseline_hours_per_month"], 0)

    def test_zero_loaded_rate_no_division_failure(self):
        r = e.evaluate(self.point(loaded_hourly_rate=0), 12)
        self.assertEqual(r["economic_horizon_net"], -r["external_cash_horizon"])
        self.assertIsNone(r["break_even"]["maximum_checking_minutes"])

    def test_all_zero_break_even(self):
        v = {key: D(0) for key in e.FIELDS}
        r = e.evaluate(v, 12)
        self.assertEqual(r["economic_horizon_net"], 0)
        self.assertEqual(r["break_even"]["simple_payback_months"], 0)
        self.assertEqual(r["break_even"]["assisted_tasks_per_month_exact"], 0)

    def test_break_even_tasks_threshold(self):
        v = self.point()
        r = e.evaluate(v, 12)
        threshold = r["break_even"]["assisted_tasks_per_month_exact"]
        with localcontext() as ctx:
            ctx.prec = 50
            at = dict(v, monthly_tasks=threshold / v["adoption_fraction"])
            self.assertLess(abs(e.evaluate(at, 12)["economic_horizon_net"]), D("1e-40"))
        ceil = r["break_even"]["assisted_tasks_per_month_ceiling"]
        self.assertGreaterEqual(e.evaluate(dict(v, monthly_tasks=ceil, adoption_fraction=D(1)), 12)["economic_horizon_net"], 0)
        self.assertLess(e.evaluate(dict(v, monthly_tasks=ceil-D(1), adoption_fraction=D(1)), 12)["economic_horizon_net"], 0)

    def test_checking_threshold(self):
        v = self.point()
        threshold = e.evaluate(v, 12)["break_even"]["maximum_checking_minutes"]
        self.assertLess(abs(e.evaluate(dict(v, checking_minutes=threshold), 12)["economic_horizon_net"]), D("1e-40"))
        self.assertLess(e.evaluate(dict(v, checking_minutes=threshold+D("0.01")), 12)["economic_horizon_net"], 0)

    def test_missing_core_input_stays_unknown(self):
        r = e.analyze(self.doc)["scenarios"][3]
        self.assertEqual(r["economic_classification"], "UNKNOWN")
        self.assertIsNone(r["base"])
        self.assertEqual(r["sensitivity"], [])
        self.assertEqual({x["field"] for x in r["measurement_plan"]}, {"checking_minutes", "rework_fraction"})

    def test_missing_conversion_preserves_economics(self):
        cell = self.case["inputs"]["cash_conversion_fraction"]
        cell.update(range=None, basis="unknown")
        r = e.analyze(self.doc)["scenarios"][0]
        self.assertEqual(r["economic_classification"], "POSITIVE_ACROSS_RANGE")
        self.assertEqual(r["cash_classification"], "UNKNOWN")
        self.assertIsNone(r["base"]["cash_conversion_horizon_net"])

    def test_bounds_contain_base_and_witnesses_replay(self):
        for scenario in self.doc["scenarios"][:3]:
            bounds = e.envelope(scenario, 12)
            base = e.evaluate(e.values_at(scenario), 12)
            for key in ("economic_horizon_net", "cash_conversion_horizon_net"):
                self.assertLessEqual(bounds[key]["low"], base[key])
                self.assertLessEqual(base[key], bounds[key]["high"])
                for side in ("low", "high"):
                    self.assertEqual(e.evaluate(bounds[key][side+"_witness"], 12)[key], bounds[key][side])

    def test_optimized_envelope_matches_bruteforce_seeded_boxes(self):
        rng = random.Random(78019)
        all_fields = list(e.FIELDS)
        for trial in range(12):
            scenario = copy.deepcopy(self.case)
            for key in all_fields:
                base = scenario["inputs"][key]["range"]["base"]
                self.set_range(key, base, scenario=scenario)
            variable = rng.sample(all_fields, 7)
            for key in variable:
                base = D(scenario["inputs"][key]["range"]["base"])
                lo, hi = max(D(0), base/D(2)), base*D(2)+D(1)
                if key in e.FRACTIONS:
                    lo, hi = D(0), D(1)
                self.set_range(key, lo, min(max(base, lo), hi), hi, scenario=scenario)
            if trial % 2:
                self.set_range("checking_minutes", 90, scenario=scenario)
            extrema = e.envelope(scenario, 12)
            candidates = []
            start = e.values_at(scenario)
            for corners in itertools.product(("low", "high"), repeat=len(variable)):
                v = dict(start)
                for key, side in zip(variable, corners):
                    v[key] = D(scenario["inputs"][key]["range"][side])
                candidates.append(e.evaluate(v, 12))
            for metric in ("economic_horizon_net", "cash_conversion_horizon_net"):
                self.assertEqual(extrema[metric]["low"], min(x[metric] for x in candidates), (trial, metric))
                self.assertEqual(extrema[metric]["high"], max(x[metric] for x in candidates), (trial, metric))

    def test_one_at_a_time_sensitivity_replays(self):
        rows = e.sensitivity(self.case, 12)
        self.assertEqual(len(rows), len(e.FIELDS))
        self.assertEqual(rows, sorted(rows, key=lambda row: (-row["economic_swing"], row["field"])))
        for row in rows:
            v = self.point(**{row["field"]: row["input_low"]})
            self.assertEqual(e.evaluate(v, 12)["economic_horizon_net"], row["economic_at_low_input"])

    def test_conversion_has_no_economic_sensitivity(self):
        row = next(x for x in e.sensitivity(self.doc["scenarios"][2], 12) if x["field"] == "cash_conversion_fraction")
        self.assertEqual(row["economic_swing"], 0)
        self.assertNotEqual(row["cash_at_low_input"], row["cash_at_high_input"])

    def test_nine_point_two_way_grid(self):
        rows = e.grid(self.case, 12)
        self.assertEqual(len(rows), 9)
        middle = next(x for x in rows if x["volume_level"] == x["checking_level"] == "base")
        self.assertEqual(middle["economic_horizon_net"], e.evaluate(self.point(), 12)["economic_horizon_net"])

    def test_export_is_deterministic(self):
        a = e.artifacts(self.doc, e.analyze(self.doc))
        b = e.artifacts(self.doc, e.analyze(self.doc))
        self.assertEqual(a, b)
        self.assertEqual(len(a), 7)

    def test_json_uses_decimal_strings_and_explicit_null(self):
        report = json.loads(e.artifacts(self.doc, e.analyze(self.doc))["report.json"])
        self.assertIsInstance(report["scenarios"][0]["base"]["economic_horizon_net"], str)
        self.assertIsNone(report["scenarios"][3]["base"])
        self.assertFalse(report["spend_authorized"])
        self.assertFalse(report["institution_finding"])

    def test_csv_missing_not_empty_and_context_preserved(self):
        rows = list(csv.DictReader(io.StringIO(e.artifacts(self.doc, e.analyze(self.doc))["summary.csv"])))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[-1]["economic_base"], "UNKNOWN")
        self.assertEqual(rows[0]["result_basis"], "MODELED_NOT_OBSERVED")

    def test_csv_formula_text_neutralized_numeric_minus_kept(self):
        value = e.csv_text([{"text": " =SUM(A1:A2)", "number": D("-1.20")}, {"text": "@formula", "number": None}], ["text", "number"])
        rows = list(csv.DictReader(io.StringIO(value)))
        self.assertEqual(rows[0]["text"], "' =SUM(A1:A2)")
        self.assertEqual(rows[0]["number"], "-1.20")
        self.assertEqual(rows[1]["text"], "'@formula")

    def test_unicode_multiline_source_preserved(self):
        text = "Fictional\nRésumé — α | source:pp.12–14"
        self.case["inputs"]["monthly_tasks"]["source"] = text
        values = e.artifacts(self.doc, e.analyze(self.doc))
        rows = list(csv.DictReader(io.StringIO(values["input_register.csv"])))
        self.assertEqual(rows[0]["source"], text)

    def test_markdown_escapes_user_markup(self):
        self.case["label"] = "<script> | example\nheading"
        report = e.render_markdown(e.analyze(self.doc))
        self.assertNotIn("<script>", report)
        self.assertIn("&lt;script&gt; \\| example heading", report)

    def test_input_receipt_changes_on_assumption_change(self):
        a = e.analyze(self.doc)["input_sha256"]
        self.set_range("monthly_tasks", 123)
        self.assertNotEqual(a, e.analyze(self.doc)["input_sha256"])

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(e.InputError):
            e.load_document('{"schema_version":"1.0","schema_version":"1.0"}')

    def test_nan_infinity_float_bool_negative_rejected(self):
        for value in (True, False, 0.1, -1, "-0.1", "NaN", "Infinity", "1e3", "", " 12"):
            with self.subTest(value=value), self.assertRaises(e.InputError):
                e.decimal_value(value, "test")
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaises(e.InputError):
                e.load_document('{"n":'+value+'}')

    def test_bad_ranges_and_fractions_rejected(self):
        for ranges in ((2, 1, 3), (1, 4, 3)):
            self.set_range("monthly_tasks", *ranges)
            with self.assertRaises(e.InputError):
                e.validate_document(self.doc)
        self.doc = synthetic_document()
        self.case = self.doc["scenarios"][0]
        self.set_range("adoption_fraction", "1.1")
        with self.assertRaises(e.InputError):
            e.validate_document(self.doc)

    def test_unknown_and_unit_contracts(self):
        for mutation in (lambda c: c.update(unit="minutes"), lambda c: c.update(range=None), lambda c: c.update(basis="unknown")):
            doc = synthetic_document()
            mutation(doc["scenarios"][0]["inputs"]["monthly_tasks"])
            with self.assertRaises(e.InputError):
                e.validate_document(doc)

    def test_duplicate_scenarios_and_missing_keys_rejected(self):
        self.doc["scenarios"].append(copy.deepcopy(self.case))
        with self.assertRaises(e.InputError):
            e.validate_document(self.doc)
        doc = synthetic_document()
        del doc["scenarios"][0]["inputs"]["checking_minutes"]
        with self.assertRaises(e.InputError):
            e.validate_document(doc)

    def test_synthetic_cannot_claim_observed(self):
        self.case["inputs"]["monthly_tasks"]["basis"] = "observed"
        with self.assertRaises(e.InputError):
            e.validate_document(self.doc)

    def test_bad_horizons_and_currency(self):
        for months in (0, -1, True, 1.5, "12"):
            self.doc["horizon_months"] = months
            with self.assertRaises(e.InputError):
                e.validate_document(self.doc)
        self.doc = synthetic_document()
        self.doc["currency"] = "dollars"
        with self.assertRaises(e.InputError):
            e.validate_document(self.doc)

    def test_wrong_basis_types_raise_input_error(self):
        for value in ([], {}, None, True):
            doc = synthetic_document()
            doc["input_basis"] = value
            with self.assertRaises(e.InputError):
                e.validate_document(doc)
            doc = synthetic_document()
            doc["scenarios"][0]["inputs"]["monthly_tasks"]["basis"] = value
            with self.assertRaises(e.InputError):
                e.validate_document(doc)

    def test_measured_label_cannot_relabel_synthetic_inputs(self):
        self.doc["input_basis"] = "MEASURED_INPUTS"
        with self.assertRaises(e.InputError):
            e.validate_document(self.doc)

    def test_full_box_exact_envelope_65536_corners(self):
        scenario = self.doc["scenarios"][2]
        bounds = e.envelope(scenario, 12)
        values = {key: tuple(D(cell["range"][side]) for side in ("low", "high")) for key, cell in scenario["inputs"].items()}
        metrics = ("economic_horizon_net", "cash_conversion_horizon_net")
        mins, maxs = {k: D("Infinity") for k in metrics}, {k: D("-Infinity") for k in metrics}
        count = 0
        for combination in itertools.product(*values.values()):
            result = e.evaluate(dict(zip(values, combination)), 12)
            count += 1
            for metric in metrics:
                mins[metric] = min(mins[metric], result[metric])
                maxs[metric] = max(maxs[metric], result[metric])
        self.assertEqual(count, 65536)
        for metric in metrics:
            self.assertEqual(bounds[metric]["low"], mins[metric])
            self.assertEqual(bounds[metric]["high"], maxs[metric])

    def test_cli_writes_seven_reports_and_handles_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            source = path/"input.json"
            source.write_text(json.dumps(self.doc), encoding="utf-8")
            cmd = [sys.executable, str(ROOT/"economics.py"), str(source), "--out", str(path/"result")]
            completed = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(len(list((path/"result").iterdir())), 7)
            self.assertIn("MODELED_NOT_OBSERVED", completed.stdout)
            source.write_text("{broken", encoding="utf-8")
            failed = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("ERROR: invalid JSON", failed.stderr)

    def test_cli_will_not_overwrite_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            source = path/"report.json"
            source.write_text(json.dumps(self.doc), encoding="utf-8")
            before = source.read_bytes()
            completed = subprocess.run([sys.executable, str(ROOT/"economics.py"), str(source), "--out", str(path)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
