import json
import math
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detector import OnlineBreakDetector
import submission
from synthetic import benchmark, first_crossing, make_case, score_series


class DetectorTests(unittest.TestCase):
    def test_mean_shift_detects_quickly(self):
        history, online, tau = make_case("mean", 10)
        scores = score_series(history, online)
        crossing = first_crossing(scores)
        self.assertIsNotNone(crossing)
        self.assertGreaterEqual(crossing, tau)
        self.assertLessEqual(crossing - tau, 18)
        self.assertGreater(scores[-1], 0.95)

    def test_variance_shift_detects_quickly(self):
        history, online, tau = make_case("variance", 11)
        scores = score_series(history, online)
        crossing = first_crossing(scores)
        self.assertIsNotNone(crossing)
        self.assertGreaterEqual(crossing, tau)
        self.assertLessEqual(crossing - tau, 18)

    def test_persistence_change_detects_without_marginal_variance_change(self):
        history, online, tau = make_case("persistence", 12)
        scores = score_series(history, online)
        crossing = first_crossing(scores)
        self.assertIsNotNone(crossing)
        self.assertGreaterEqual(crossing, tau)
        self.assertLessEqual(crossing - tau, 70)

    def test_single_outlier_does_not_create_high_alarm(self):
        history, online, _ = make_case("outlier_only", 13)
        scores = score_series(history, online)
        self.assertLess(max(scores), 0.5)

    def test_null_stream_stays_below_high_alarm(self):
        history, online, _ = make_case("null", 14)
        scores = score_series(history, online)
        self.assertLess(max(scores), 0.5)

    def test_prefix_invariance_future_suffix_cannot_change_past(self):
        history, online, _ = make_case("mean", 15)
        prefix = online[:100]
        alternate_suffix = [999.0 if i % 2 else -999.0 for i in range(80)]
        first = score_series(history, prefix + online[100:])
        second = score_series(history, prefix + alternate_suffix)
        self.assertEqual(first[:100], second[:100])

    def test_repeat_replay_is_byte_deterministic(self):
        history, online, _ = make_case("variance", 16)
        a = score_series(history, online)
        b = score_series(list(history), list(online))
        self.assertEqual(
            json.dumps(a, separators=(",", ":")).encode(),
            json.dumps(b, separators=(",", ":")).encode(),
        )

    def test_cross_series_state_isolation(self):
        h1, o1, _ = make_case("mean", 17)
        h2, o2, _ = make_case("variance", 18)
        direct_1 = score_series(h1, o1)
        direct_2 = score_series(h2, o2)
        with tempfile.TemporaryDirectory() as tmp:
            submission.train([], tmp)
            generator = submission.infer([(h1, iter(o1)), (h2, iter(o2))], tmp)
            self.assertIsNone(next(generator))
            emitted = list(generator)
        self.assertEqual(emitted[:len(o1)], direct_1)
        self.assertEqual(emitted[len(o1):], direct_2)

    def test_single_pass_online_iterable(self):
        class OnePass:
            def __init__(self, values):
                self.values = list(values)
                self.iterated = False
            def __iter__(self):
                if self.iterated:
                    raise AssertionError("online stream iterated twice")
                self.iterated = True
                return iter(self.values)

        history, online, _ = make_case("mean", 19)
        with tempfile.TemporaryDirectory() as tmp:
            submission.train([], tmp)
            stream = OnePass(online)
            generator = submission.infer([(history, stream)], tmp)
            self.assertIsNone(next(generator))
            scores = list(generator)
        self.assertEqual(len(scores), len(online))
        self.assertTrue(stream.iterated)

    def test_no_future_horizon_dependency(self):
        rng = random.Random(20)
        history = [rng.gauss(0, 1) for _ in range(1200)]
        prefix = [rng.gauss(0, 1) for _ in range(80)]
        d = OnlineBreakDetector(history)
        scores = [d.update(value) for value in prefix]
        self.assertEqual(len(scores), 80)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in scores))

    def test_bounded_online_state(self):
        history, online, _ = make_case("variance", 21, online_length=600, tau=80)
        detector = OnlineBreakDetector(history)
        for value in online:
            detector.update(value)
            self.assertLessEqual(
                detector.retained_observation_cells(),
                detector.maximum_retained_observation_cells(),
            )

    def test_non_finite_observations_fail_closed(self):
        history, _, _ = make_case("null", 22)
        detector = OnlineBreakDetector(history)
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                detector.update(bad)

    def test_non_finite_history_fails_closed(self):
        history, _, _ = make_case("null", 23)
        history[5] = float("nan")
        with self.assertRaises(ValueError):
            OnlineBreakDetector(history)

    def test_too_short_history_fails_closed(self):
        with self.assertRaises(ValueError):
            OnlineBreakDetector([0.0] * 31)

    def test_submission_contract_and_model_tamper_guard(self):
        history, online, _ = make_case("mean", 24)
        with tempfile.TemporaryDirectory() as tmp:
            submission.train([], tmp)
            model_path = Path(tmp) / submission.MODEL_FILENAME
            data = json.loads(model_path.read_text())
            self.assertFalse(data["pretrained"])
            generator = submission.infer([(history, iter(online))], tmp)
            self.assertIsNone(next(generator))
            scores = list(generator)
            self.assertEqual(len(scores), len(online))
            self.assertTrue(all(isinstance(value, float) for value in scores))

            data["pretrained"] = True
            model_path.write_text(json.dumps(data), encoding="utf-8")
            broken = submission.infer([(history, iter(online))], tmp)
            with self.assertRaises(ValueError):
                next(broken)

    def test_score_range_on_adversarial_extremes(self):
        history = [0.0] * 1200
        # A zero-variance reference is legal; scale floor must keep the detector finite.
        detector = OnlineBreakDetector(history)
        scores = [detector.update(value) for value in [1e300, -1e300] * 50]
        self.assertTrue(all(math.isfinite(value) and 0 <= value <= 1 for value in scores))

    def test_synthetic_benchmark_regression(self):
        report = benchmark(seed_count=8)
        self.assertEqual(report["nullFalseAlarmRateAt0_5"], 0.0)
        self.assertGreaterEqual(report["mean"]["hitRate"], 1.0)
        self.assertGreaterEqual(report["variance"]["hitRate"], 1.0)
        self.assertGreaterEqual(report["trend"]["hitRate"], 0.75)
        self.assertGreaterEqual(report["persistence"]["hitRate"], 0.75)


if __name__ == "__main__":
    unittest.main()
