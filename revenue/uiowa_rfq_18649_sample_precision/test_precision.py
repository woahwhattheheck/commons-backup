"""Independent numerical, evidence-scope, intake and CLI checks.

Known-answer endpoints below are frozen reference values, not a second copy of
the production Wilson formula. All checks use unittest so python -O retains them.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import precision


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "precision.py"


def sample(**changes):
    row = {
        "id": "case-1",
        "label": "Observed release checks",
        "unit": "release",
        "outcome": "check completed",
        "observation_window": "Synthetic rehearsal window",
        "eligible": 10,
        "success": 5,
        "failure": 5,
        "unknown": 0,
        "sampling_design": "independent_bernoulli",
        "design_basis": "Synthetic independent-trial assumption for this exercise only.",
        "source_refs": ["synthetic://release-log#rows-1-10"],
    }
    row.update(changes)
    return row


def document(*rows, **changes):
    value = {
        "schema": "uiowa-sample-precision/v1",
        "synthetic": True,
        "samples": list(rows) if rows else [sample()],
    }
    value.update(changes)
    return value


class WilsonReferenceTests(unittest.TestCase):
    def test_standard_five_of_ten_95_percent_reference(self):
        lower, upper = precision.wilson_interval(5, 10)
        self.assertAlmostEqual(lower, 0.2365930905, delta=5e-10)
        self.assertAlmostEqual(upper, 0.7634069095, delta=5e-10)

    def test_three_and_three_hundred_all_pass_have_different_precision(self):
        small = precision.wilson_interval(3, 3)
        large = precision.wilson_interval(300, 300)
        self.assertAlmostEqual(small[0], 0.4385029682, delta=5e-10)
        self.assertAlmostEqual(large[0], 0.9873570288, delta=5e-10)
        self.assertAlmostEqual(small[1], 1.0, places=14)
        self.assertAlmostEqual(large[1], 1.0, places=14)
        self.assertGreater(large[0], small[0])

    def test_zero_of_three_keeps_positive_upper_uncertainty(self):
        lower, upper = precision.wilson_interval(0, 3)
        self.assertAlmostEqual(lower, 0.0, places=14)
        self.assertAlmostEqual(upper, 0.5614970318, delta=5e-10)

    def test_interval_is_symmetric_under_success_failure_exchange(self):
        for successes, total in [(1, 7), (4, 19), (29, 30)]:
            with self.subTest(successes=successes, total=total):
                lower, upper = precision.wilson_interval(successes, total)
                inverse = precision.wilson_interval(total - successes, total)
                self.assertAlmostEqual(lower, 1.0 - inverse[1], places=13)
                self.assertAlmostEqual(upper, 1.0 - inverse[0], places=13)
                self.assertLessEqual(lower, successes / total)
                self.assertGreaterEqual(upper, successes / total)

    def test_higher_confidence_widens_the_same_observation_interval(self):
        narrow = precision.wilson_interval(4, 10, 0.5)
        wide = precision.wilson_interval(4, 10, 0.9999)
        self.assertGreater(narrow[0], wide[0])
        self.assertLess(narrow[1], wide[1])
        self.assertGreaterEqual(wide[0], 0.0)
        self.assertLessEqual(wide[1], 1.0)


class EvidenceScopeTests(unittest.TestCase):
    def test_default_and_explicit_confidence_and_output_identity(self):
        result = precision.evaluate(document())
        self.assertEqual(result["schema"], "uiowa-sample-precision-result/v1")
        self.assertEqual(result["confidence"], 0.95)
        self.assertIs(result["synthetic"], True)
        row = result["samples"][0]
        self.assertEqual(row["observed_rate"], {
            "numerator": 5, "denominator": 10, "ratio": 0.5, "exact": "1/2",
        })
        self.assertEqual(row["interval"]["status"], "CONDITIONAL_MODEL")
        self.assertEqual(row["interval"]["method"], "Wilson score")
        self.assertEqual(row["interval"]["level"], 0.95)
        self.assertEqual(row["interval"]["reasons"], [])
        for confidence in (0.5, 0.9, 0.9999):
            with self.subTest(confidence=confidence):
                actual = precision.evaluate(document(confidence=confidence))
                self.assertEqual(actual["confidence"], confidence)
                self.assertEqual(actual["samples"][0]["interval"]["level"], confidence)

    def test_missing_outcomes_preserve_known_rate_and_collection_bounds(self):
        row = precision.evaluate(document(sample(
            eligible=15, success=14, failure=0, unknown=1,
        )))["samples"][0]
        self.assertEqual(row["observed_rate"], {
            "numerator": 14, "denominator": 14, "ratio": 1.0, "exact": "1",
        })
        bounds = row["collection_bounds"]
        self.assertEqual(bounds["denominator"], 15)
        self.assertEqual(bounds["lower"]["numerator"], 14)
        self.assertEqual(bounds["lower"]["denominator"], 15)
        self.assertEqual(bounds["lower"]["exact"], "14/15")
        self.assertAlmostEqual(bounds["lower"]["ratio"], 14 / 15)
        self.assertEqual(bounds["upper"], {
            "numerator": 15, "denominator": 15, "ratio": 1.0, "exact": "1",
        })
        self.assertEqual(row["interval"]["status"], "NOT_COMPUTED")
        self.assertIn("INCOMPLETE_OUTCOMES", row["interval"]["reasons"])

    def test_no_model_interval_for_non_independent_sampling_designs(self):
        for design in ("convenience", "prepared_demo", "census", "clustered", "unknown"):
            with self.subTest(design=design):
                row = precision.evaluate(document(sample(sampling_design=design)))["samples"][0]
                self.assertEqual(row["interval"]["status"], "NOT_COMPUTED")
                self.assertIn("SAMPLING_DESIGN_" + design.upper(), row["interval"]["reasons"])
                self.assertEqual(row["observed_rate"]["exact"], "1/2")
                self.assertEqual(row["collection_bounds"]["lower"]["exact"], "1/2")
                self.assertEqual(row["collection_bounds"]["upper"]["exact"], "1/2")

    def test_design_and_missingness_reasons_are_both_retained(self):
        row = precision.evaluate(document(sample(
            eligible=10, success=5, failure=4, unknown=1, sampling_design="convenience",
        )))["samples"][0]
        self.assertEqual(row["interval"]["status"], "NOT_COMPUTED")
        self.assertIn("SAMPLING_DESIGN_CONVENIENCE", row["interval"]["reasons"])
        self.assertIn("INCOMPLETE_OUTCOMES", row["interval"]["reasons"])

    def test_zero_eligible_has_no_rate_or_collection_bounds(self):
        row = precision.evaluate(document(sample(
            eligible=0, success=0, failure=0, unknown=0,
        )))["samples"][0]
        self.assertIsNone(row["observed_rate"])
        self.assertIsNone(row["collection_bounds"])
        self.assertEqual(row["interval"]["status"], "NOT_COMPUTED")
        self.assertIn("NO_OBSERVED_OUTCOMES", row["interval"]["reasons"])

    def test_all_unknown_has_full_collection_bounds_without_observed_rate(self):
        row = precision.evaluate(document(sample(
            eligible=10, success=0, failure=0, unknown=10,
        )))["samples"][0]
        self.assertIsNone(row["observed_rate"])
        self.assertEqual(row["collection_bounds"]["lower"]["exact"], "0")
        self.assertEqual(row["collection_bounds"]["upper"]["exact"], "1")
        self.assertEqual(row["interval"]["status"], "NOT_COMPUTED")
        self.assertIn("INCOMPLETE_OUTCOMES", row["interval"]["reasons"])
        self.assertIn("NO_OBSERVED_OUTCOMES", row["interval"]["reasons"])

    def test_large_valid_counts_keep_exact_fraction_and_declared_denominator(self):
        row = precision.evaluate(document(sample(
            eligible=10**12, success=1, failure=10**12 - 1, unknown=0,
        )))["samples"][0]
        self.assertEqual(row["observed_rate"]["exact"], "1/1000000000000")
        self.assertEqual(row["observed_rate"]["denominator"], 10**12)
        self.assertEqual(row["observed_rate"]["ratio"], 1e-12)

    def test_each_sample_stays_separate_in_order_without_pooling(self):
        inputs = document(sample(id="small", eligible=3, success=3, failure=0),
                          sample(id="large", eligible=300, success=300, failure=0))
        rows = precision.evaluate(inputs)["samples"]
        self.assertEqual([r["input"]["id"] for r in rows], ["small", "large"])
        self.assertEqual([r["observed_rate"]["denominator"] for r in rows], [3, 300])
        self.assertLess(rows[0]["interval"]["lower"], rows[1]["interval"]["lower"])

    def test_returned_input_is_an_independent_deep_copy(self):
        original = document()
        snapshot = copy.deepcopy(original)
        result = precision.evaluate(original)
        self.assertEqual(original, snapshot)
        self.assertEqual(result["samples"][0]["input"], original["samples"][0])
        result["samples"][0]["input"]["source_refs"].append("changed-output-only")
        result["samples"][0]["input"]["label"] = "changed-output-only"
        self.assertEqual(original, snapshot)

    def test_synthetic_false_is_preserved_without_forcing_a_demo_design(self):
        result = precision.evaluate(document(synthetic=False))
        self.assertIs(result["synthetic"], False)
        self.assertEqual(result["samples"][0]["interval"]["status"], "CONDITIONAL_MODEL")


class IntakeValidationTests(unittest.TestCase):
    def test_counts_reject_bool_negative_fraction_string_and_oversize(self):
        for field in ("eligible", "success", "failure", "unknown"):
            for invalid in (True, False, -1, 0.5, "1", 10**12 + 1, None):
                with self.subTest(field=field, invalid=invalid):
                    with self.assertRaises(ValueError):
                        precision.evaluate(document(sample(**{field: invalid})))

    def test_partition_must_equal_eligible_in_both_directions(self):
        for eligible in (9, 11):
            with self.subTest(eligible=eligible), self.assertRaises(ValueError):
                precision.evaluate(document(sample(eligible=eligible)))

    def test_confidence_rejects_nonfinite_boolean_wrong_type_and_out_of_range(self):
        for invalid in (float("nan"), float("inf"), -float("inf"), True, False,
                        "0.95", None, 0.499999, 0.99991, 1, -1):
            with self.subTest(confidence=invalid), self.assertRaises(ValueError):
                precision.evaluate(document(confidence=invalid))

    def test_duplicate_ids_are_rejected_even_when_evidence_differs(self):
        with self.assertRaises(ValueError):
            precision.evaluate(document(sample(), sample(label="Another distinct label")))

    def test_required_text_fields_reject_blank_or_non_string(self):
        for field in ("id", "label", "unit", "outcome", "observation_window", "design_basis"):
            for invalid in ("", " \t\n", None, 42, False):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValueError):
                    precision.evaluate(document(sample(**{field: invalid})))

    def test_source_references_require_nonempty_list_of_nonempty_strings(self):
        for invalid in ([], "source", None, [""], [" "], [42], ["valid", None]):
            with self.subTest(refs=invalid), self.assertRaises(ValueError):
                precision.evaluate(document(sample(source_refs=invalid)))

    def test_schema_container_synthetic_and_design_are_validated(self):
        malformed = [None, [], "document", document(schema="other/v1"),
                     document(synthetic=1), document(synthetic="true"),
                     document(samples={}), document(samples=[None]),
                     document(sample(sampling_design="randomish"))]
        missing_synthetic = document()
        del missing_synthetic["synthetic"]
        malformed.append(missing_synthetic)
        missing_count = document()
        del missing_count["samples"][0]["unknown"]
        malformed.append(missing_count)
        for value in malformed:
            with self.subTest(value=value), self.assertRaises(ValueError):
                precision.evaluate(value)


class MarkdownAndCliTests(unittest.TestCase):
    def run_cli(self, raw, *options):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text(raw, encoding="utf-8")
            return subprocess.run(
                [sys.executable, *(["-O"] if sys.flags.optimize else []),
                 str(SCRIPT), str(source), *options],
                cwd=directory, capture_output=True, text=True, timeout=10, check=False,
            )

    def test_markdown_escapes_dynamic_pipes_html_and_preserves_json_input(self):
        value = document(sample(
            label="Team | Alpha <b>label</b>",
            unit="service | <i>unit</i>",
            outcome="passed | <em>outcome</em>",
            observation_window="Window | <u>time</u>",
            design_basis="Basis | <strong>assumption</strong>",
            source_refs=["source|<script>literal</script>"],
        ))
        result = precision.evaluate(value)
        before = copy.deepcopy(result)
        markdown = precision.render_markdown(result)
        self.assertEqual(result, before)
        self.assertEqual(result["samples"][0]["input"], value["samples"][0])
        self.assertIn("&#124;", markdown)
        self.assertIn("&lt;b&gt;label&lt;/b&gt;", markdown)
        for tag in ("b", "i", "em", "u", "strong", "script"):
            self.assertNotIn("<" + tag + ">", markdown)
        self.assertNotIn("Team | Alpha", markdown)

    def test_cli_default_json_and_explicit_json_return_the_evaluation(self):
        value = document()
        for options in ((), ("--format", "json")):
            with self.subTest(options=options):
                result = self.run_cli(json.dumps(value), *options)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(json.loads(result.stdout), precision.evaluate(value))

    def test_cli_markdown_uses_the_public_renderer(self):
        value = document(sample(success=3, failure=0, eligible=3))
        result = self.run_cli(json.dumps(value), "--format", "markdown")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.rstrip(), precision.render_markdown(precision.evaluate(value)).rstrip())

    def test_cli_invalid_json_duplicate_keys_nonfinite_and_bad_partition_fail_without_stdout(self):
        malformed = ["{", "[]", json.dumps(document(sample(eligible=11))),
                     json.dumps(document(confidence=float("nan"))),
                     '{"schema":"uiowa-sample-precision/v1","synthetic":true,"synthetic":false,"samples":[]}']
        for raw in malformed:
            with self.subTest(raw=raw):
                result = self.run_cli(raw)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
