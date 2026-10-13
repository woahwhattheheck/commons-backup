import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detector import OnlineBreakDetector
from synthetic import score_series


class RobustnessRegressionTests(unittest.TestCase):
    def test_exact_review_impulse_cannot_mint_high_alarm_during_warmup(self):
        history = [-1.0, 1.0] * 600
        online = [-1.0, 1.0] * 40
        self.assertLess(max(score_series(history, online)), 0.02)
        online[6] = 18.0
        self.assertLess(max(score_series(history, online)), 0.5)

    def test_single_impulse_cannot_alias_16_or_32_point_horizons(self):
        history = [-1.0, 1.0] * 600
        baseline = [-1.0, 1.0] * 60
        for index in (14, 30):
            with self.subTest(index=index):
                online = list(baseline)
                online[index] = 18.0
                self.assertLess(max(score_series(history, online)), 0.5)

    def test_historical_tail_outlier_cannot_erase_real_later_mean_break(self):
        history = [0.0] * 1199 + [1_000_000.0]
        detector = OnlineBreakDetector(history)
        self.assertLess(detector.reference.scale, 1.0)
        scores = [detector.update(value) for value in ([0.0] * 60 + [2.0] * 180)]
        self.assertGreaterEqual(max(scores), 0.5)


if __name__ == "__main__":
    unittest.main()
