"""Independent regression battery for the existing UIOWA-087 component.

ZZ-HELIX / GPT-6 Astra Pro. All records are synthetic. Load by exact file path
so similarly named analyzers in other components cannot satisfy these tests.
"""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("_uiowa087_validity_analyze", ROOT / "analyze.py")
analyze = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = analyze
SPEC.loader.exec_module(analyze)


class MeasurementValidityTests(unittest.TestCase):
    def setUp(self):
        self.recs = analyze.read_csv(str(ROOT / "recommendations.csv"))
        self.register = analyze.read_csv(str(ROOT / "measure_register.csv"))
        self.rows = analyze.read_csv(str(ROOT / "examples/measurements.csv"))

    def run_case(self):
        findings, comparisons = analyze.validate_and_compare(self.recs, self.register, self.rows)
        return findings, {c.measure_id: c for c in comparisons}

    def assert_invalid(self, measure_id="DEV-A1"):
        findings, comparisons = self.run_case()
        c = comparisons[measure_id]
        self.assertTrue(any(f.level == "ERROR" for f in findings))
        self.assertEqual(c.comparability, "INVALID_DATA")
        self.assertEqual(c.directional_signal, "INSUFFICIENT_DATA")
        self.assertIsNone(c.baseline_rate_pct)
        self.assertIsNone(c.followup_rate_pct)
        self.assertIsNone(c.absolute_change_pp)
        return findings, comparisons

    def test_missing_observation_provenance_cannot_produce_signal(self):
        for field in ("evidence_locator", "period_id", "population_definition"):
            with self.subTest(field=field):
                self.setUp()
                self.rows[1][field] = ""
                self.assert_invalid()

    def test_two_blank_populations_are_not_equivalent_evidence(self):
        self.rows[0]["population_definition"] = ""
        self.rows[1]["population_definition"] = ""
        self.assert_invalid()

    def test_required_measure_metadata_is_comparison_eligibility(self):
        for field in ("recommendation_id", "assessment_area", "measure_class", "measure_name",
                      "numerator_definition", "denominator_definition", "unit", "direction",
                      "evidence_source", "collection_cadence", "interpretation_limit"):
            with self.subTest(field=field):
                self.setUp()
                self.register[0][field] = ""
                self.assert_invalid()

    def test_unknown_enum_values_do_not_fall_back_to_valid_context(self):
        for field, value in (("direction", "typo"), ("measure_class", "typo"), ("unit", "seconds")):
            with self.subTest(field=field):
                self.setUp()
                self.register[0][field] = value
                self.assert_invalid()

    def test_unknown_recommendation_suppresses_affected_result_only(self):
        self.register[0]["recommendation_id"] = "MISSING"
        _, comparisons = self.assert_invalid()
        self.assertEqual(comparisons["SEC-A1"].comparability, "COMPARABLE")

    def test_duplicate_recommendation_invalidates_dependents(self):
        self.recs.append(dict(self.recs[0], title="Different recommendation"))
        _, comparisons = self.assert_invalid()
        self.assertEqual(comparisons["DEV-O1"].comparability, "INVALID_DATA")
        self.assertEqual(comparisons["SEC-A1"].comparability, "COMPARABLE")

    def test_duplicate_measure_never_selects_a_direction_by_row_order(self):
        self.register.append(dict(self.register[0], direction="lower_better"))
        self.assert_invalid()
        self.register.reverse()
        self.assert_invalid()

    def test_duplicate_period_roles_never_select_a_count_by_row_order(self):
        self.rows.append(dict(self.rows[1], numerator="0", evidence_locator="synthetic://disputed"))
        _, comparisons = self.assert_invalid()
        self.assertEqual(comparisons["DEV-A1"].followup_evidence, "")
        self.rows.reverse()
        self.assert_invalid()

    def test_invalid_unpaired_counts_are_still_validated(self):
        for field, value in (("numerator", "oops"), ("numerator", "-1"),
                             ("denominator", "0"), ("numerator", "21")):
            with self.subTest(field=field, value=value):
                self.setUp()
                self.rows = [r for r in self.rows if not
                             (r["measure_id"] == "DEV-A1" and r["period_role"] == "followup")]
                self.rows[0][field] = value
                self.assert_invalid()

    def test_invalid_role_with_an_otherwise_complete_pair_is_not_ignored(self):
        self.rows.append(dict(self.rows[0], period_role="unknown"))
        self.assert_invalid()

    def test_distinct_baseline_and_followup_windows_required(self):
        self.rows[1]["period_id"] = self.rows[0]["period_id"]
        self.assert_invalid()

    def test_missing_pair_without_invalid_rows_remains_insufficient(self):
        self.rows = self.rows[1:]
        findings, comparisons = self.run_case()
        self.assertFalse(any(f.level == "ERROR" for f in findings))
        self.assertEqual(comparisons["DEV-A1"].comparability, "INSUFFICIENT_DATA")

    def test_missing_effort_warns_without_invalidating_outcome(self):
        self.register[0]["estimated_minutes_per_cycle"] = ""
        findings, comparisons = self.run_case()
        self.assertTrue(any(f.code == "EFFORT_UNKNOWN" for f in findings))
        self.assertEqual(comparisons["DEV-A1"].comparability, "COMPARABLE")
        self.assertIsNone(comparisons["DEV-A1"].collection_effort_minutes)

    def test_valid_unrelated_measure_survives_invalid_neighbor(self):
        self.rows[1]["evidence_locator"] = ""
        _, comparisons = self.assert_invalid()
        self.assertEqual(sum(c.comparability == "COMPARABLE" for c in comparisons.values()), 5)

    def test_large_valid_count_ratio_does_not_overflow(self):
        for row in self.rows[:2]:
            row.update(numerator=str(10**400), denominator=str(2 * 10**400))
        findings, comparisons = self.run_case()
        self.assertFalse(any(f.level == "ERROR" for f in findings))
        self.assertEqual(comparisons["DEV-A1"].baseline_rate_pct, 50.0)
        self.assertEqual(comparisons["DEV-A1"].directional_signal, "UNCHANGED")

    def test_direction_uses_exact_counts_not_float_tolerance(self):
        self.rows[0].update(numerator="1", denominator=str(10**15))
        self.rows[1].update(numerator="2", denominator=str(10**15))
        _, comparisons = self.run_case()
        self.assertEqual(comparisons["DEV-A1"].directional_signal, "FAVORABLE_DIRECTION")
        self.assertGreater(comparisons["DEV-A1"].absolute_change_pp, 0)

    def test_unknown_measure_is_diagnosed_without_poisoning_known_measures(self):
        self.rows.append(dict(self.rows[0], measure_id="UNKNOWN"))
        findings, comparisons = self.run_case()
        self.assertTrue(any(f.code == "UNKNOWN_MEASURE" for f in findings))
        self.assertTrue(all(c.comparability == "COMPARABLE" for c in comparisons.values()))

    def test_report_exposes_both_source_locators(self):
        findings, comparisons = self.run_case()
        report = analyze.render_markdown(self.recs, list(comparisons.values()), findings)
        for row in self.rows:
            self.assertIn(row["evidence_locator"], report)

    def test_markdown_preserves_cell_content_without_new_columns(self):
        self.register[0]["measure_name"] = "Delivery | review\n<script>"
        findings, comparisons = self.run_case()
        report = analyze.render_markdown(self.recs, list(comparisons.values()), findings)
        self.assertIn("Delivery &#124; review<br>&lt;script&gt;", report)
        self.assertNotIn("<script>", report)

    def test_duplicate_recommendation_cannot_supply_arbitrary_title(self):
        self.recs.append(dict(self.recs[0], title="ARBITRARY DUPLICATE TITLE"))
        findings, comparisons = self.run_case()
        report = analyze.render_markdown(self.recs, list(comparisons.values()), findings)
        self.assertNotIn("ARBITRARY DUPLICATE TITLE", report)
        self.assertIn("Ambiguous recommendation", report)

    def test_csv_rejects_duplicate_blank_headers_and_wrong_row_width(self):
        cases = ("a,a\n1,2\n", "a,\n1,2\n", "a,b\n1,2,3\n", "a,b\n1\n", "", 'a,b\n"unterminated,2\n')
        for data in cases:
            with self.subTest(data=data), tempfile.TemporaryDirectory() as temp:
                p = Path(temp) / "input.csv"
                p.write_text(data, encoding="utf-8")
                with self.assertRaises(ValueError):
                    analyze.read_csv(str(p))

    def test_csv_valid_multiline_unicode_and_empty_values_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "input.csv"
            p.write_text('a,b,c\n"naïve, note","two\nlines",\n', encoding="utf-8")
            self.assertEqual(analyze.read_csv(str(p)), [{"a": "naïve, note", "b": "two\nlines", "c": ""}])

    def test_cli_malformed_csv_produces_json_diagnostic_and_no_traceback(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "bad.csv"
            p.write_text("measure_id,measure_id\nDEV-A1,DEV-A1\n", encoding="utf-8")
            proc = subprocess.run([sys.executable, str(ROOT / "analyze.py"), "validate", "--json",
                                   "--recommendations", str(ROOT / "recommendations.csv"),
                                   "--register", str(ROOT / "measure_register.csv"), "--measurements", str(p)],
                                  capture_output=True, text=True, timeout=10)
            self.assertEqual(proc.returncode, 2)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["comparisons"], [])
            self.assertEqual(payload["findings"][0]["code"], "INPUT_ERROR")
            self.assertNotIn("Traceback", proc.stderr)

    def test_cli_header_only_wrong_schema_cannot_report_clean(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "bad.csv"
            p.write_text("unrelated_header\n", encoding="utf-8")
            proc = subprocess.run([sys.executable, str(ROOT / "analyze.py"), "validate", "--json",
                                   "--recommendations", str(ROOT / "recommendations.csv"),
                                   "--register", str(p), "--measurements", str(ROOT / "examples/measurements.csv")],
                                  capture_output=True, text=True, timeout=10)
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(proc.stdout)["findings"][0]["code"], "INPUT_ERROR")


if __name__ == "__main__":
    unittest.main()
