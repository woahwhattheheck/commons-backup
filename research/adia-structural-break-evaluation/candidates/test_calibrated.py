from __future__ import annotations

import math
import random
import unittest
import warnings
import numpy as np
from calibrated import OnlineBreakDetector


def history(n=1000):
    r = random.Random(1294)
    return [r.gauss(0, 1) for _ in range(n)]


def stream(n=200):
    r = random.Random(1989)
    return [r.gauss(0, 1) + (2.0 if i >= n//2 else 0) for i in range(n)]


def scores(h, xs):
    d = OnlineBreakDetector(h)
    return [d.update(x) for x in xs]


class CalibratedTests(unittest.TestCase):
    def test_finite_range(self):
        result = scores(history(), stream())
        self.assertTrue(all(type(x) is float and math.isfinite(x) and 0 < x < 1 for x in result))

    def test_prefix_causality(self):
        h, x = history(), stream()
        expected = scores(h, x)
        for n in (1, 7, 8, 16, 33, 65, 128):
            self.assertEqual(expected[:n], scores(h, x[:n]))

    def test_suffix_cannot_change_prefix(self):
        h, x = history(), stream()
        y = x[:70] + [100.0] * 130
        self.assertEqual(scores(h, x)[:70], scores(h, y)[:70])

    def test_cold_restart_and_interleaving(self):
        h, x = history(), stream()
        a, b = OnlineBreakDetector(h), OnlineBreakDetector([0.0] * 1000)
        first = []
        for point in x:
            first.append(a.update(point))
            b.update(10.0)
        self.assertEqual(first, scores(h, x))

    def test_generator_history_consumed_once(self):
        h, x = history(), stream()
        self.assertEqual(scores(h, x), scores(iter(h), x))

    def test_translation(self):
        h, x = history(), stream()
        np.testing.assert_allclose(scores(h, x), scores([v + 100 for v in h], [v + 100 for v in x]), atol=2e-11, rtol=2e-11)

    def test_positive_scale(self):
        h, x = history(), stream()
        np.testing.assert_allclose(scores(h, x), scores([v * 7 for v in h], [v * 7 for v in x]), atol=1e-12, rtol=1e-12)

    def test_negative_scale(self):
        h, x = history(), stream()
        np.testing.assert_allclose(scores(h, x), scores([-v for v in h], [-v for v in x]), atol=1e-12, rtol=1e-12)

    def test_no_partial_horizon_votes(self):
        d = OnlineBreakDetector(history())
        for _ in range(15):
            self.assertLess(d.update(4.0), 0.05)
        self.assertEqual(d.state, 0.0)

    def test_minimum_history_has_two_calibrated_horizons(self):
        d = OnlineBreakDetector(history(32))
        self.assertIn(8, d.windows)
        self.assertIn(16, d.windows)
        self.assertGreater(max(d.update(20) for _ in range(64)), 0.5)

    def test_constant_no_change(self):
        self.assertLess(max(scores([1.0] * 1000, [1.0] * 1000)), 0.05)

    def test_isolated_impulse_not_a_break(self):
        for history_values in ([0.0] * 1000, history()):
            for at in (0, 7, 8, 15, 16, 31, 32, 63, 64, 100):
                # Gaussian history followed by all zeros is a real scale break;
                # the impulse fixture must retain its historical null process.
                x = list(history_values[-300:])
                x[at] = 1e30
                self.assertLess(max(scores(history_values, x)), 0.5, (at, history_values[:3]))

    def test_single_historical_outlier_does_not_erase_shift(self):
        h, x = history(), [3.0] * 100
        h[100] = 1e30
        self.assertGreater(max(scores(h, x)), 0.9)

    def test_mean_shift_detected(self):
        self.assertGreater(max(scores(history(), [3.0] * 80)), 0.9)

    def test_scale_decrease_detected(self):
        self.assertGreater(max(scores(history(), [0.0] * 160)), 0.5)

    def test_bounded_retained_state(self):
        d = OnlineBreakDetector(history())
        for i in range(3000):
            d.update(math.sin(i))
        self.assertEqual(sum(len(b) for b in d.buffers), sum(d.windows))
        self.assertLessEqual(sum(len(b) for b in d.buffers) * 4, 2016)

    def test_invalid_online_does_not_mutate_state(self):
        d = OnlineBreakDetector(history())
        d.update(0.0)
        for x in (float('nan'), float('inf'), -float('inf')):
            before = (d.state, d.steps, d.previous_z, [len(b) for b in d.buffers])
            with self.assertRaises(ValueError):
                d.update(x)
            self.assertEqual(before, (d.state, d.steps, d.previous_z, [len(b) for b in d.buffers]))

    def test_invalid_history(self):
        for h in ([], [0] * 31, [float('nan')] * 32, [float('inf')] * 32, [[0, 1]] * 32):
            with self.assertRaises(ValueError):
                OnlineBreakDetector(h)

    def test_unrepresentable_dispersion_rejected(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            with self.assertRaises(ValueError):
                OnlineBreakDetector([-1e308, 1e308] * 100)


if __name__ == '__main__':
    unittest.main()
