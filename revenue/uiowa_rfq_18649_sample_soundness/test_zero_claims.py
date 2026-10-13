"""Zero counts, population claims, and explicitly conditional inference.

TestExistingBoundary uses only predecessor APIs so its failures discriminate
incorrect behavior, rather than merely detecting the added fields.
"""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import soundness as S

HERE = Path(__file__).resolve().parent


def measure(**updates):
    args = dict(id="M-SYN-ZERO", label="synthetic exercises", kind="PROPORTION",
                numerator=0, denominator=8, sampling="UNKNOWN", scope="SAMPLE")
    args.update(updates)
    return S.Measure(**args)


def inference(**updates):
    args = dict(method="BINOMIAL_ZERO_UPPER", confidence=0.95,
                independent_trials=True, constant_probability=True,
                rationale="Fictional independently sampled trials from one stable process.")
    args.update(updates)
    return args


def findings(**updates):
    return S.check([measure(**updates)])


def codes(rows):
    return {r.code for r in rows}


def limits(rows):
    return [r for r in rows if r.code == "ZERO_EVENT_MODEL_LIMIT"]


class TestExistingBoundary(unittest.TestCase):
    def test_plain_random_zero_is_not_an_absence_claim(self):
        self.assertNotIn("ZERO_OBSERVED_AS_ABSENCE", codes(findings(sampling="RANDOM")))

    def test_scoped_census_zero_is_not_an_absence_error(self):
        self.assertNotIn("ZERO_OBSERVED_AS_ABSENCE", codes(findings(
            sampling="CENSUS", scope="POPULATION", denominator=100)))

    def test_unknown_zero_does_not_mint_population_bound(self):
        text = " ".join(r.restatement for r in findings(sampling="UNKNOWN"))
        self.assertNotIn("underlying rate", text)

    def test_convenience_zero_does_not_mint_population_bound(self):
        text = " ".join(r.restatement for r in findings(sampling="CONVENIENCE"))
        self.assertNotIn("underlying rate", text)

    def test_self_selected_zero_does_not_mint_population_bound(self):
        text = " ".join(r.restatement for r in findings(sampling="SELF_SELECTED"))
        self.assertNotIn("underlying rate", text)

    def test_legacy_approximation_stays_in_probability_domain(self):
        for n in (1, 2, 3, 8, 300):
            with self.subTest(n=n):
                self.assertGreater(S.rule_of_three_upper_bound(n), 0)
                self.assertLessEqual(S.rule_of_three_upper_bound(n), 100)


class TestClaims(unittest.TestCase):
    def test_descriptive_small_counts_need_no_percentage_advice(self):
        for sampling in S.SAMPLING_KINDS:
            for n in (1, 2, 8, 100):
                with self.subTest(sampling=sampling, n=n):
                    self.assertEqual(findings(sampling=sampling, denominator=n,
                        presentation="COUNT"), [])

    def test_named_complete_census_can_state_collection_absence(self):
        self.assertEqual(findings(sampling="CENSUS", scope="POPULATION",
            presentation="COUNT", claim="POPULATION_ABSENCE",
            population="all four fictional exercises recorded for week 1", denominator=4), [])

    def test_census_absence_without_named_collection_is_not_accepted(self):
        self.assertIn("ZERO_OBSERVED_AS_ABSENCE", codes(findings(sampling="CENSUS",
            scope="POPULATION", presentation="COUNT", claim="POPULATION_ABSENCE")))

    def test_census_of_sample_does_not_prove_population_absence(self):
        self.assertIn("ZERO_OBSERVED_AS_ABSENCE", codes(findings(sampling="CENSUS",
            scope="SAMPLE", population="larger fictional population",
            presentation="COUNT", claim="POPULATION_ABSENCE")))

    def test_explicit_sample_based_population_absence_is_flagged_for_all_designs(self):
        for sampling in ("RANDOM", "UNKNOWN", "CONVENIENCE", "SELF_SELECTED"):
            with self.subTest(sampling=sampling):
                fs = findings(sampling=sampling, presentation="COUNT",
                    claim="POPULATION_ABSENCE", population="fictional process")
                self.assertIn("ZERO_OBSERVED_AS_ABSENCE", codes(fs))
                self.assertFalse(limits(fs))
                restated = " ".join(f.restatement for f in fs)
                self.assertNotIn("underlying rate", restated)

    def test_nonzero_count_contradicts_absence_even_for_census(self):
        self.assertIn("ABSENCE_CONTRADICTED", codes(findings(numerator=1,
            sampling="CENSUS", scope="POPULATION", population="fictional frame",
            claim="POPULATION_ABSENCE", presentation="COUNT")))

    def test_random_label_does_not_enable_interval(self):
        self.assertFalse(limits(findings(sampling="RANDOM", population="fictional process")))

    def test_nonprobability_population_scope_still_fails(self):
        for sampling in ("UNKNOWN", "CONVENIENCE", "SELF_SELECTED"):
            with self.subTest(sampling=sampling):
                self.assertIn("SAMPLE_STATED_AS_POPULATION", codes(findings(
                    sampling=sampling, scope="POPULATION", presentation="COUNT")))

    def test_zero_denominator_stays_unknown(self):
        self.assertEqual(codes(findings(denominator=0, presentation="COUNT")),
                         {"EMPTY_DENOMINATOR"})

    def test_missing_numerator_is_not_zero(self):
        self.assertEqual(codes(findings(numerator=None, presentation="COUNT")),
                         {"NUMERATOR_UNKNOWN"})


class TestConditionalInference(unittest.TestCase):
    def test_model_calculation_is_explicitly_named_and_conditional(self):
        rows = limits(findings(presentation="COUNT", sampling="RANDOM",
            population="fictional stable process", inference=inference()))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].severity, S.INFO)
        self.assertIn("exact one-sided 95% BINOMIAL_ZERO_UPPER", rows[0].message)
        self.assertIn("31.2344%", rows[0].message)
        self.assertIn("model-based, not proof of absence", rows[0].message)
        self.assertIn("Fictional independently sampled", rows[0].message)

    def test_model_does_not_clear_absence_claim(self):
        fs = findings(presentation="COUNT", sampling="RANDOM", claim="POPULATION_ABSENCE",
            population="fictional process", inference=inference())
        self.assertIn("ZERO_EVENT_MODEL_LIMIT", codes(fs))
        self.assertIn("ZERO_OBSERVED_AS_ABSENCE", codes(fs))
        self.assertTrue(any(f.severity == S.ERROR for f in fs))

    def test_nonprobability_or_census_never_gets_model_limit(self):
        for sampling in ("UNKNOWN", "CONVENIENCE", "SELF_SELECTED", "CENSUS"):
            with self.subTest(sampling=sampling):
                fs = findings(sampling=sampling, population="fictional frame", inference=inference())
                self.assertFalse(limits(fs))
                self.assertIn("ZERO_EVENT_MODEL_UNSUPPORTED", codes(fs))

    def test_incomplete_or_false_assumptions_do_not_get_limit(self):
        for key in ("method", "confidence", "independent_trials", "constant_probability", "rationale"):
            for value in (None, False, ""):
                with self.subTest(key=key, value=value):
                    model = inference(**{key: value})
                    fs = findings(sampling="RANDOM", population="fictional frame", inference=model)
                    self.assertFalse(limits(fs))
                    self.assertIn("ZERO_EVENT_MODEL_UNSUPPORTED", codes(fs))

    def test_no_named_target_means_no_model_limit(self):
        self.assertIn("ZERO_EVENT_MODEL_UNSUPPORTED", codes(findings(
            sampling="RANDOM", inference=inference())))

    def test_nonzero_count_is_not_a_zero_event_calculation(self):
        self.assertFalse(limits(findings(numerator=1, sampling="RANDOM",
            population="fictional frame", inference=inference())))

    def test_invalid_confidences_return_no_limit(self):
        for value in (True, 0, 1, -1, 2, "0.95", float("nan"), float("inf"), 10**500):
            with self.subTest(value=str(value)[:20]):
                fs = findings(sampling="RANDOM", population="fictional frame",
                              inference=inference(confidence=value))
                self.assertFalse(limits(fs))
                self.assertIn("ZERO_EVENT_MODEL_UNSUPPORTED", codes(fs))

    def test_input_measure_and_model_are_not_mutated(self):
        m = measure(sampling="RANDOM", population="fictional frame", inference=inference())
        before = copy.deepcopy(m)
        S.check([m])
        self.assertEqual(m, before)


class TestArithmeticAndIngress(unittest.TestCase):
    def test_zero_event_formula_inverts_zero_event_probability(self):
        for n in (1, 2, 8, 30, 1000):
            for confidence in (.90, .95, .99):
                with self.subTest(n=n, confidence=confidence):
                    p = S.zero_event_upper_bound(n, confidence)
                    self.assertAlmostEqual((1-p)**n, 1-confidence, places=12)

    def test_bounds_are_finite_inside_unit_interval_and_decrease_with_n(self):
        values = [S.zero_event_upper_bound(n, .95) for n in (1,2,8,30,100,1000000,10**12)]
        self.assertTrue(all(math.isfinite(p) and 0 < p < 1 for p in values))
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertAlmostEqual(values[0], .95)
        self.assertAlmostEqual(values[1], 1-math.sqrt(.05))

    def test_larger_confidence_increases_upper_limit(self):
        self.assertLess(S.zero_event_upper_bound(8,.90), S.zero_event_upper_bound(8,.95))

    def test_invalid_trial_counts_are_refused(self):
        for n in (True, False, 0, -1, 1.5, "8", 10**500):
            with self.subTest(n=str(n)[:20]):
                with self.assertRaises(S.MeasureError):
                    S.zero_event_upper_bound(n, .95)
                with self.assertRaises(S.MeasureError):
                    S.rule_of_three_upper_bound(n)

    def test_invalid_confidences_are_refused_by_math_api(self):
        for c in (True, 0, 1, -1, "0.95", float("nan"), float("inf"), 10**500):
            with self.subTest(c=str(c)[:20]):
                with self.assertRaises(S.MeasureError):
                    S.zero_event_upper_bound(8, c)

    def test_invalid_direct_counts_are_refused_before_division(self):
        for name in ("numerator", "denominator"):
            for value in (True, "2", -1, 1.5, float("inf")):
                with self.subTest(name=name, value=value):
                    with self.assertRaises(S.MeasureError):
                        findings(**{name: value})
        with self.assertRaises(S.MeasureError):
            findings(numerator=9)

    def test_bad_new_field_types_are_refused(self):
        for fields in ({"claim":"guess"}, {"presentation":"rate"}, {"population":None},
                       {"inference":[]}, {"reported_decimals":True}):
            with self.subTest(fields=fields):
                with self.assertRaises(S.MeasureError):
                    findings(**fields)

    def test_count_kind_cannot_silently_ignore_new_claim_fields(self):
        with self.assertRaises(S.MeasureError):
            S.check([measure(kind="COUNT", claim="POPULATION_ABSENCE")])


class TestLoaderAndCli(unittest.TestCase):
    def run_cli(self, payload, optimized=False):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/"measures.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            cmd = [sys.executable] + (["-O"] if optimized else [])
            return subprocess.run(cmd + [str(HERE/"check_soundness.py"), "--measures",
                str(source), "--format", "json"], capture_output=True, text=True,
                encoding="utf-8", timeout=10, cwd=td)

    def packet(self, **updates):
        m = dict(id="M-SYN", label="fictional examples", kind="PROPORTION", numerator=0,
                 denominator=2, sampling="UNKNOWN", scope="SAMPLE", presentation="COUNT")
        m.update(updates)
        return {"synthetic":True, "measures":[m]}

    def test_cli_round_trips_new_fields_in_another_working_directory(self):
        result = self.run_cli(self.packet(sampling="RANDOM", population="fictional process",
                                         inference=inference()))
        self.assertEqual(result.returncode, 0, result.stderr)
        body = json.loads(result.stdout)
        self.assertTrue(body["passed"])
        self.assertEqual(body["findings"][0]["code"], "ZERO_EVENT_MODEL_LIMIT")
        self.assertIn("77.6393%", body["findings"][0]["message"])

    def test_cli_optimized_output_is_identical(self):
        p = self.packet(sampling="RANDOM", population="fictional process", inference=inference())
        a,b = self.run_cli(p),self.run_cli(p,optimized=True)
        self.assertEqual((a.returncode,a.stdout,a.stderr),(b.returncode,b.stdout,b.stderr))

    def test_invalid_input_gets_exit_two_not_a_traceback(self):
        for packet in ([True], {"synthetic":1,"measures":[]},
                       {"synthetic":True,"measures":{}},
                       {"synthetic":True,"measures":[None]},
                       self.packet(numerator=True), self.packet(inference=[])):
            with self.subTest(packet=packet):
                result = self.run_cli(packet)
                self.assertEqual(result.returncode,2,result.stdout+result.stderr)
                self.assertNotIn("Traceback",result.stderr)

    def test_cli_rejects_absence_but_accepts_same_observations_descriptively(self):
        before = self.run_cli(self.packet(claim="POPULATION_ABSENCE", scope="POPULATION"))
        after = self.run_cli(self.packet())
        self.assertEqual(before.returncode,1)
        self.assertEqual(after.returncode,0)
        self.assertFalse(json.loads(before.stdout)["passed"])
        self.assertTrue(json.loads(after.stdout)["passed"])

    def test_cli_synthetic_worked_packet_is_readable(self):
        path=HERE/"fixtures"/"zero_claim_cases.json"
        if not path.exists():
            self.fail("retained worked packet missing")
        result=self.run_cli(json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(result.returncode,1,result.stderr)
        report=json.loads(result.stdout)
        self.assertEqual(report["measures_checked"],9)
        self.assertEqual(sum(f["code"]=="ZERO_EVENT_MODEL_LIMIT" for f in report["findings"]),2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
