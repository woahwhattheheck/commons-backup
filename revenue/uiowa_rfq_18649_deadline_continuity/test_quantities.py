"""Finite-quantity regressions for the existing UIOWA-107 calculator."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import continuity
from intervals import Assumption, AssumptionError, Interval
from test_continuity import minimal_scenario

HERE = Path(__file__).resolve().parent
BAD = (True, False, float('nan'), float('inf'), -float('inf'), '4', [], {}, None)


class QuantityContract(unittest.TestCase):
    def test_lower_bounds_reject_non_quantities(self):
        for value in BAD:
            with self.subTest(value=repr(value)), self.assertRaises(AssumptionError):
                Interval(value, 10)

    def test_upper_bounds_reject_non_quantities_but_none(self):
        for value in BAD[:-1]:
            with self.subTest(value=repr(value)), self.assertRaises(AssumptionError):
                Interval(0, value)

    def test_multipliers_reject_non_quantities(self):
        for value in BAD:
            with self.subTest(value=repr(value)), self.assertRaises(AssumptionError):
                Interval(0, 10).scaled(value)

    def test_overflowing_sum_is_not_an_infinite_quantity(self):
        with self.assertRaises(AssumptionError):
            Interval(1e308, 1e308) + Interval(1e308, 1e308)

    def test_overflowing_scale_is_not_an_infinite_quantity(self):
        with self.assertRaises(AssumptionError):
            Interval(1e308, 1e308).scaled(2)

    def test_too_large_integer_is_controlled(self):
        with self.assertRaises(AssumptionError):
            Interval(10 ** 400, 10 ** 401)

    def test_negative_and_reversed_are_still_rejected(self):
        for lo, hi in ((-1, 2), (2, 1)):
            with self.subTest(lo=lo, hi=hi), self.assertRaises(AssumptionError):
                Interval(lo, hi)
        with self.assertRaises(AssumptionError):
            Interval(1, 2).scaled(-1)

    def test_valid_zero_fraction_and_integer_preserved(self):
        for lo, hi in ((0, 0), (1, 2), (0.25, 1.5), (0.0, 2.0)):
            with self.subTest(lo=lo, hi=hi):
                value = Interval(lo, hi)
                self.assertEqual(value.as_dict(), {'low': lo, 'high': hi})
                self.assertEqual(value.scaled(0.5).as_dict(),
                                 {'low': lo * 0.5, 'high': hi * 0.5})

    def test_none_upper_bound_remains_explicitly_unknown(self):
        value = Interval(2, None).scaled(3)
        self.assertEqual(value.as_dict(), {'low': 6, 'high': None})
        self.assertFalse(value.bounded)

    def test_nonquantity_assumption_rejected_even_when_unused(self):
        scenario = minimal_scenario()
        scenario['assumptions'].append({'id': 'unused', 'statement': 'unused',
            'basis': 'ESTIMATED', 'low': float('nan'), 'high': float('nan')})
        with self.assertRaises(AssumptionError):
            continuity.Analysis(scenario)

    def test_bool_and_nan_capacity_do_not_become_verdicts(self):
        for value in (True, False, float('nan'), float('inf'), '32'):
            scenario = minimal_scenario()
            scenario['assumptions'][1].update(low=value, high=value)
            with self.subTest(value=repr(value)), self.assertRaises(AssumptionError):
                continuity.Analysis(scenario)

    def test_unknown_with_numbers_remains_rejected(self):
        for value in (0, True, float('nan')):
            with self.subTest(value=repr(value)), self.assertRaises(AssumptionError):
                Assumption({'id': 'a', 'statement': 's', 'basis': 'UNKNOWN',
                            'low': value, 'high': None})

    def test_unknown_without_numbers_remains_unknown(self):
        a = Assumption({'id': 'a', 'statement': 's', 'basis': 'UNKNOWN'})
        self.assertFalse(a.resolved)
        self.assertIsNone(a.low)
        self.assertIsNone(a.high)
        self.assertEqual(a.interval(), Interval(0, None))

    def test_finite_validation_does_not_resolve_assumed_evidence(self):
        a = Assumption({'id': 'a', 'statement': 's', 'basis': 'ASSUMED',
                        'low': 0, 'high': 16})
        self.assertEqual(a.as_dict()['basis'], 'ASSUMED')
        self.assertIsNone(a.source_ref)

    def test_cli_rejects_bad_quantities_without_traceback_or_outputs(self):
        for value in (True, float('nan'), float('inf'), '32'):
            with self.subTest(value=repr(value)), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                scenario = minimal_scenario()
                scenario['assumptions'][1].update(low=value, high=value)
                source = root / 'input.json'
                source.write_text(json.dumps(scenario), encoding='utf-8')
                original = source.read_bytes()
                cmd = [sys.executable] + (['-O'] if sys.flags.optimize else [])
                cmd += [str(HERE / 'continuity.py'), '--input', str(source),
                        '--outdir', str(root / 'out')]
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                self.assertEqual(p.returncode, 2, p.stderr)
                self.assertNotIn('Traceback', p.stderr)
                self.assertEqual(p.stdout, '')
                self.assertFalse((root / 'out').exists())
                self.assertEqual(source.read_bytes(), original)

    def test_finite_grid_arithmetic_and_verdicts(self):
        # Independent endpoint calculation, not the implementation's helpers.
        values = [0, 0.25, 1, 3]
        ranges = [(a, b) for a in values for b in values if a <= b]
        for lo, hi in ranges:
            for cl, ch in ranges:
                with self.subTest(exposure=(lo, hi), capacity=(cl, ch)):
                    e, c = Interval(lo, hi), Interval(cl, ch)
                    expected = 'FITS' if hi < cl else 'AT_RISK' if ch < lo else 'NOT_DETERMINED'
                    self.assertEqual(continuity.verdict_for(e, c), expected)
                    self.assertEqual((e + c).as_dict(), {'low': lo + cl, 'high': hi + ch})
                    self.assertEqual(e.scaled(2).as_dict(), {'low': lo * 2, 'high': hi * 2})


if __name__ == '__main__':
    unittest.main()
