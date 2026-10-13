"""Keep raw contrast thresholds separate from rounded presentation.

Regression: #4967FF on white has ratio 4.4993000646165315, not >=4.5.
Source: W3C Understanding SC 1.4.3, computed ratios must not be rounded
before threshold comparison. No whole-report accessibility claim is made.
Contribution: ZZ-Astra-Q7C4; original arithmetic remains OP5-EMBER's.
"""
import math
import unittest

import contrast


class ContrastThresholdPrecisionTests(unittest.TestCase):
    def test_actual_blue_pair_below_text_minimum_fails(self):
        for fg, bg in (("#4967FF", "#FFFFFF"), ("#FFFFFF", "#4967FF")):
            with self.subTest(foreground=fg, background=bg):
                result = contrast.check("near boundary", "text", fg, bg, contrast.TEXT_MIN)
                self.assertGreater(result.ratio, 4.499)
                self.assertLess(result.ratio, 4.5)
                self.assertFalse(result.ok)

    def test_actual_grayscale_pair_below_graphical_minimum_fails(self):
        result = contrast.check_grayscale("near gray boundary", "#959595", "#FFFFFF")
        self.assertGreater(result.ratio, 2.995)
        self.assertLess(result.ratio, 3.0)
        self.assertFalse(result.ok)

    def test_nearest_float_below_each_threshold_fails(self):
        for minimum in (3.0, 4.5, 7.0):
            with self.subTest(minimum=minimum):
                result = contrast.CheckResult("below", "text", "#000", "#FFF",
                                              math.nextafter(minimum, -math.inf), minimum)
                self.assertFalse(result.ok)

    def test_exact_threshold_is_inclusive(self):
        for minimum in (3.0, 4.5, 7.0):
            with self.subTest(minimum=minimum):
                result = contrast.CheckResult("equal", "text", "#000", "#FFF", minimum, minimum)
                self.assertTrue(result.ok)

    def test_nearest_float_above_each_threshold_passes(self):
        for minimum in (3.0, 4.5, 7.0):
            with self.subTest(minimum=minimum):
                result = contrast.CheckResult("above", "text", "#000", "#FFF",
                                              math.nextafter(minimum, math.inf), minimum)
                self.assertTrue(result.ok)

    def test_rounded_json_presentation_does_not_determine_verdict(self):
        result = contrast.check("near boundary", "text", "#4967FF", "#FFFFFF", 4.5)
        rendered = result.as_dict()
        self.assertEqual(rendered["ratio"], 4.5)
        self.assertEqual(rendered["minimum"], 4.5)
        self.assertFalse(rendered["ok"])
        self.assertLess(result.ratio, rendered["ratio"])

    def test_text_report_and_repr_keep_under_threshold_failure(self):
        result = contrast.check("near boundary", "text", "#4967FF", "#FFFFFF", 4.5)
        report = contrast.format_report([result])
        self.assertIn("1 checks, 0 pass, 1 fail", report)
        self.assertIn("FAIL", repr(result))

    def test_ordinary_pass_and_fail_controls_are_unchanged(self):
        passing = contrast.check("black on white", "text", "#000000", "#FFFFFF", 4.5)
        failing = contrast.check("black on black", "text", "#000000", "#000000", 4.5)
        self.assertEqual(passing.ratio, 21.0)
        self.assertEqual(failing.ratio, 1.0)
        self.assertTrue(passing.ok)
        self.assertFalse(failing.ok)


if __name__ == "__main__":
    unittest.main()
