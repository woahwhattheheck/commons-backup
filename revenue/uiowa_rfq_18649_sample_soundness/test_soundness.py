"""Tests for the sample-soundness checker.

The rules encode opinions about how a number may be stated, so the tests that
matter most are the ones asserting a rule does NOT fire on a measure that is
actually well-founded.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

import check_soundness
import soundness as S

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
UNSOUND = os.path.join(FIX, "measures_UNSOUND.json")
SOUND = os.path.join(FIX, "measures_SOUND.json")
MALFORMED = os.path.join(FIX, "malformed.json")


def codes(findings):
    return {f.code for f in findings}


def one(**kw):
    base = dict(id="M-T", label="things", kind="PROPORTION", sampling="RANDOM",
                scope="SAMPLE", reported_decimals=0)
    base.update(kw)
    return S.Measure(**kw) if False else S.Measure(**base)


class TestArithmetic(unittest.TestCase):
    def test_resolvable_step(self):
        self.assertAlmostEqual(S.resolvable_step_pp(12), 8.3333, places=3)
        self.assertAlmostEqual(S.resolvable_step_pp(100), 1.0)

    def test_rule_of_three(self):
        """Zero events in n trials is consistent with a rate up to about 3/n."""
        self.assertAlmostEqual(S.rule_of_three_upper_bound(8), 37.5)
        self.assertAlmostEqual(S.rule_of_three_upper_bound(300), 1.0)


class TestBeforeAfterPair(unittest.TestCase):
    def test_unsound_set_fails(self):
        measures = S.load_measures(UNSOUND)
        findings = S.check(measures)
        self.assertTrue(any(f.severity == S.ERROR for f in findings))

    def test_sound_set_passes(self):
        measures = S.load_measures(SOUND)
        self.assertEqual([f.to_dict() for f in S.check(measures)], [])

    def test_every_rule_fires_on_the_unsound_set(self):
        found = codes(S.check(S.load_measures(UNSOUND)))
        for code in ("FALSE_PRECISION", "SAMPLE_STATED_AS_POPULATION",
                     "DENOMINATOR_TOO_SMALL", "PERCENTAGE_WITHOUT_DENOMINATOR",
                     "ZERO_OBSERVED_AS_ABSENCE", "MEDIAN_OF_TOO_FEW",
                     "MEDIAN_OF_FEW", "COMPONENT_UNKNOWN",
                     "COMPONENT_SUM_MISMATCH", "EMPTY_DENOMINATOR",
                     "NUMERATOR_UNKNOWN"):
            self.assertIn(code, found, f"{code} never fired")

    def test_every_finding_proposes_a_restatement(self):
        """Objecting without proposing wording moves the work, it does not do it."""
        for f in S.check(S.load_measures(UNSOUND)):
            if f.code == "NUMERATOR_UNKNOWN":
                continue   # nothing can be said until the value exists
            self.assertTrue(f.restatement, f"{f.code} gave no restatement")


class TestIndividualRules(unittest.TestCase):
    def test_small_denominator_reports_once_not_twice(self):
        """DENOMINATOR_TOO_SMALL supersedes FALSE_PRECISION below the threshold."""
        found = codes(S._check_proportion(one(numerator=3, denominator=4)))
        self.assertIn("DENOMINATOR_TOO_SMALL", found)
        self.assertNotIn("FALSE_PRECISION", found)

    def test_large_sample_at_whole_percent_is_clean(self):
        found = codes(S._check_proportion(one(numerator=58, denominator=100)))
        self.assertEqual(found, set())

    def test_decimal_place_on_a_small_sample_is_an_error(self):
        found = S._check_proportion(one(numerator=7, denominator=12,
                                        reported_decimals=1))
        fp = [f for f in found if f.code == "FALSE_PRECISION"]
        self.assertEqual(len(fp), 1)
        self.assertEqual(fp[0].severity, S.ERROR)
        self.assertIn("7 of 12", fp[0].restatement)

    def test_whole_percent_on_a_small_sample_is_only_a_warning(self):
        found = [f for f in S._check_proportion(one(numerator=3, denominator=9))
                 if f.code == "FALSE_PRECISION"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, S.WARN)

    def test_zero_observed_is_not_absence(self):
        found = [f for f in S._check_proportion(one(numerator=0, denominator=8,
                     claim="POPULATION_ABSENCE", scope="POPULATION"))
                 if f.code == "ZERO_OBSERVED_AS_ABSENCE"]
        self.assertEqual(len(found), 1)
        self.assertIn("does not establish", found[0].message)
        self.assertNotIn("%", found[0].restatement)

    def test_random_sample_scoped_to_population_is_allowed(self):
        """The rule objects to convenience samples, not to all generalisation."""
        found = codes(S._check_proportion(
            one(numerator=58, denominator=100, sampling="RANDOM", scope="POPULATION")))
        self.assertNotIn("SAMPLE_STATED_AS_POPULATION", found)

    def test_convenience_sample_scoped_to_population_is_caught(self):
        found = codes(S._check_proportion(
            one(numerator=58, denominator=100, sampling="CONVENIENCE",
                scope="POPULATION")))
        self.assertIn("SAMPLE_STATED_AS_POPULATION", found)

    def test_census_scoped_to_population_is_allowed(self):
        found = codes(S._check_proportion(
            one(numerator=58, denominator=100, sampling="CENSUS", scope="POPULATION")))
        self.assertEqual(found, set())

    def test_missing_numerator_is_unknown_not_zero(self):
        found = S._check_proportion(one(numerator=None, denominator=20))
        self.assertEqual([f.code for f in found], ["NUMERATOR_UNKNOWN"])
        self.assertIn("rather than defaulting to zero", found[0].message)

    def test_median_of_nine_is_clean(self):
        m = S.Measure(id="M", label="days", kind="MEDIAN",
                      observations=[1, 2, 3, 4, 5, 6, 7, 8, 9], unit="days")
        self.assertEqual(codes(S._check_median(m)), set())

    def test_median_without_observations_is_caught(self):
        m = S.Measure(id="M", label="days", kind="MEDIAN", observations=None)
        self.assertIn("MEDIAN_WITHOUT_OBSERVATIONS", codes(S._check_median(m)))

    def test_component_none_is_not_summed_as_zero(self):
        m = S.Measure(id="M", label="x", kind="COUNT",
                      components={"a": 5, "b": None}, stated_total=5)
        found = codes(S._check_components(m))
        self.assertIn("COMPONENT_UNKNOWN", found)
        self.assertNotIn("COMPONENT_SUM_MISMATCH", found)


class TestLoader(unittest.TestCase):
    def test_numerator_greater_than_denominator_is_refused(self):
        with self.assertRaises(S.MeasureError):
            S.load_measures(MALFORMED)

    def test_set_must_be_marked_synthetic(self):
        path = os.path.join(tempfile.mkdtemp(), "m.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"measures": []}, fh)
        with self.assertRaises(S.MeasureError):
            S.load_measures(path)

    def test_unknown_kind_is_refused(self):
        path = os.path.join(tempfile.mkdtemp(), "m.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"synthetic": True, "measures": [
                {"id": "M", "label": "x", "kind": "VIBES"}]}, fh)
        with self.assertRaises(S.MeasureError):
            S.load_measures(path)

    def test_unknown_sampling_is_refused(self):
        path = os.path.join(tempfile.mkdtemp(), "m.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"synthetic": True, "measures": [
                {"id": "M", "label": "x", "kind": "COUNT", "sampling": "GUESSWORK"}]}, fh)
        with self.assertRaises(S.MeasureError):
            S.load_measures(path)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.original = S.MIN_DENOMINATOR_FOR_RATE

    def tearDown(self):
        S.MIN_DENOMINATOR_FOR_RATE = self.original

    def test_exit_codes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check_soundness.main(["--measures", UNSOUND]), 1)
            self.assertEqual(check_soundness.main(["--measures", SOUND]), 0)

    def test_malformed_set_reports_rather_than_crashing(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = check_soundness.main(["--measures", MALFORMED])
        self.assertEqual(code, 2)
        self.assertIn("could not load measures", err.getvalue())

    def test_threshold_is_an_argument_not_a_law(self):
        """Raising the threshold makes a previously clean measure report."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            check_soundness.main(["--measures", SOUND, "--format", "json",
                                  "--min-denominator", "200"])
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["passed"])
        self.assertEqual(payload["min_denominator_for_rate"], 200)

    def test_two_runs_are_byte_identical(self):
        a, b = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(a):
            check_soundness.main(["--measures", UNSOUND, "--format", "json"])
        with contextlib.redirect_stdout(b):
            check_soundness.main(["--measures", UNSOUND, "--format", "json"])
        self.assertEqual(a.getvalue(), b.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
