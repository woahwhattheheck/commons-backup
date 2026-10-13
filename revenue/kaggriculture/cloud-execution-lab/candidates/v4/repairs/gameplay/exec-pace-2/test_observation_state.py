# SPDX-License-Identifier: Apache-2.0
"""Contract tests for the existing EXEC-PACE-2 module API.

EXEC_PACE_SOURCE selects a candidate or exact donor for negative controls.
No source transformation, policy installation, or external dependency.
"""
from __future__ import annotations
import copy
import importlib.util
import math
import os
from pathlib import Path
import random
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("EXEC_PACE_SOURCE", HERE / "r04_exec_adaptive.py"))
spec = importlib.util.spec_from_file_location("exec_pace_contract_subject", SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def observation(step, price=100, player=0):
    return {"step": step, "player": player,
            "market": {"prices": dict.fromkeys(m.GOODS, price)}}


def warm(start=0, player=0, increasing=True):
    for i in range(m.HIST_WINDOW):
        m.note_prices(observation(start + i, 100 + i if increasing else 100, player))


class ObservationState(unittest.TestCase):
    def setUp(self):
        m.reset()

    def test_01_original_constants_and_full_warmup(self):
        self.assertEqual(m.GOODS, ("WOOL", "MILK", "STRAWBERRY", "MELON", "EGG", "CARROT", "TOMATO"))
        self.assertEqual(m.HIST_WINDOW, 25)
        self.assertEqual(m.SLOPE_THRESHOLD, 0.03)
        for i in range(24):
            m.note_prices(observation(i, 100 + i))
            self.assertIsNone(m.slope("MILK"))
            self.assertFalse(m.rising("MILK"))
        m.note_prices(observation(24, 124))
        self.assertEqual(m.slope("MILK"), 1.0)
        self.assertTrue(m.rising("MILK"))

    def test_02_random_complete_window_parity(self):
        rng = random.Random(270311)
        for seat in (0, 1):
            m.reset()
            history = {g: [] for g in m.GOODS}
            for step in range(720):
                prices = {g: rng.randrange(1, 2001) for g in m.GOODS}
                obs = observation(step, player=seat)
                obs["market"]["prices"] = prices
                m.note_prices(obs)
                for good, px in prices.items():
                    history[good].append(px)
                    history[good] = history[good][-25:]
                    expected = None if step < 24 else (history[good][-1] - history[good][0]) / 24
                    with self.subTest(seat=seat, step=step, good=good):
                        self.assertEqual(m.slope(good), expected)
                        self.assertEqual(m.rising(good), expected is not None and expected > 0.03)

    def test_03_flat_falling_and_integer_threshold(self):
        for delta in (-24, -1, 0, 1, 24):
            m.reset()
            for step in range(25):
                m.note_prices(observation(step, 100 + (delta if step == 24 else 0)))
            self.assertEqual(m.slope("MILK"), delta / 24)
            self.assertEqual(m.rising("MILK"), delta > 0)

    def test_04_bounded_history_and_rollover(self):
        for step in range(1000):
            m.note_prices(observation(step, 100 + step))
        self.assertEqual(m.slope("MILK"), 1.0)
        for good in m.GOODS:
            self.assertEqual(len(m._phist[good]), 25)

    def test_05_identical_duplicate_is_idempotent(self):
        warm()
        before = copy.deepcopy(m._phist)
        for _ in range(3):
            m.note_prices(observation(24, 124))
            self.assertEqual(m._phist, before)
            self.assertTrue(m.rising("MILK"))

    def test_06_conflicting_duplicate_restarts_warmup(self):
        warm()
        m.note_prices(observation(24, 125))
        self.assertIsNone(m.slope("MILK"))
        for step in range(25, 48):
            m.note_prices(observation(step, 101 + step))
            self.assertIsNone(m.slope("MILK"))
        m.note_prices(observation(48, 149))
        self.assertEqual(m.slope("MILK"), 1)

    def test_07_gap_clears_previous_evidence(self):
        for next_step in (26, 250, 10000):
            m.reset()
            warm()
            m.note_prices(observation(next_step, 126))
            self.assertIsNone(m.slope("MILK"))
            self.assertFalse(m.rising("MILK"))

    def test_08_sparse_samples_are_not_a_25_step_window(self):
        for step in range(25):
            m.note_prices(observation(10 * step, 100 + (step == 24)))
        self.assertIsNone(m.slope("MILK"))
        self.assertFalse(m.rising("MILK"))

    def test_09_invalid_steps_invalidate_stale_signal(self):
        for bad in (None, True, False, "25", 25.0, -1, float("inf"), float("nan"), [], {}):
            with self.subTest(bad=repr(bad)):
                m.reset()
                warm()
                m.note_prices(observation(bad))
                self.assertIsNone(m.slope("MILK"))
                self.assertFalse(m.rising("MILK"))

    def test_10_invalid_player_and_seat_change(self):
        for bad in (None, True, False, "0", 0.0, -1, 2, [], {}):
            with self.subTest(bad=repr(bad)):
                m.reset()
                warm()
                m.note_prices(observation(25, 125, bad))
                self.assertFalse(m.rising("MILK"))
        for seat in (0, 1):
            m.reset()
            warm(player=seat)
            m.note_prices(observation(25, 125, 1-seat))
            self.assertIsNone(m.slope("MILK"))

    def test_11_rewind_restarts_from_current_sample(self):
        warm(start=100)
        m.note_prices(observation(4, 400))
        self.assertIsNone(m.slope("MILK"))
        for step in range(5, 29):
            m.note_prices(observation(step, 400 + step - 4))
        self.assertEqual(m.slope("MILK"), 1.0)

    def test_12_missing_quote_cannot_create_zero_baseline(self):
        for good in m.GOODS:
            m.reset()
            for step in range(24):
                obs = observation(step)
                del obs["market"]["prices"][good]
                m.note_prices(obs)
            m.note_prices(observation(24))
            self.assertIsNone(m.slope(good))
            self.assertFalse(m.rising(good))

    def test_13_invalid_quote_breaks_only_its_own_history(self):
        poisons = (None, True, False, 0, -1, "125", 125.0,
                   float("nan"), float("inf"), -float("inf"), [], {})
        for poison in poisons:
            with self.subTest(poison=repr(poison)):
                m.reset()
                warm()
                obs = observation(25, 125)
                obs["market"]["prices"]["MILK"] = poison
                m.note_prices(obs)
                self.assertIsNone(m.slope("MILK"))
                self.assertFalse(m.rising("MILK"))
                self.assertEqual(m.slope("WOOL"), 1.0)
                for step in range(26, 50):
                    m.note_prices(observation(step, 100 + step))
                    self.assertIsNone(m.slope("MILK"))
                m.note_prices(observation(50, 150))
                self.assertEqual(m.slope("MILK"), 1.0)

    def test_14_malformed_observation_clears_stale_evidence(self):
        values = (None, 1, [], {}, {"step":25, "player":0},
                  {"step":25, "player":0, "market":[]},
                  {"step":25, "player":0, "market":{"prices":[]}})
        for bad in values:
            m.reset()
            warm()
            m.note_prices(bad)
            self.assertFalse(m.rising("MILK"))

    def test_15_struct_mapping_supported(self):
        class Struct(dict):
            __getattr__ = dict.__getitem__
        for step in range(25):
            raw = observation(step, 100 + step)
            obs = Struct(raw)
            obs["market"] = Struct(raw["market"])
            obs.market["prices"] = Struct(raw["market"]["prices"])
            m.note_prices(obs)
        self.assertTrue(m.rising("MILK"))

    def test_16_input_and_price_aliases_are_not_retained(self):
        for step in range(25):
            obs = observation(step, 100 + step)
            before = copy.deepcopy(obs)
            m.note_prices(obs)
            self.assertEqual(obs, before)
            obs["market"]["prices"]["MILK"] = 1
        self.assertEqual(m.slope("MILK"), 1.0)

    def test_17_unknown_and_unhashable_goods_fail_closed(self):
        warm()
        for good in (None, "WHEAT", "FERTILIZER", [], {}):
            self.assertFalse(m.rising(good))
            self.assertIsNone(m.slope(good))

    def test_18_explicit_reset_clears_all_state(self):
        warm()
        m.reset()
        self.assertEqual(m._phist, {})
        self.assertEqual(m._last_step, [-1])
        for good in m.GOODS:
            self.assertFalse(m.rising(good))

    def test_19_bad_mapping_access_fails_closed(self):
        class Broken(dict):
            def get(self, *_):
                raise ValueError("unreadable observation")
        warm()
        m.note_prices(Broken(step=25))
        self.assertFalse(m.rising("MILK"))

    def test_20_bad_step_cannot_bridge_missing_callback(self):
        for step in range(24):
            m.note_prices(observation(step, 100 + step))
        m.note_prices(observation(None, 124))
        m.note_prices(observation(25, 125))
        self.assertFalse(m.rising("MILK"))

    def test_21_empty_prices_break_each_good_warmup(self):
        warm()
        obs = observation(25, 125)
        obs["market"]["prices"] = {}
        m.note_prices(obs)
        self.assertTrue(all(m.slope(g) is None for g in m.GOODS))

    def test_22_same_step_seat_change_cannot_reuse_history(self):
        warm()
        m.note_prices(observation(24, 124, 1))
        self.assertIsNone(m.slope("MILK"))

    def test_23_missing_quote_at_final_sample_is_not_certified(self):
        warm()
        obs = observation(25, 125)
        del obs["market"]["prices"]["MILK"]
        m.note_prices(obs)
        self.assertIsNone(m.slope("MILK"))

    def test_24_no_future_sample_or_threshold_lookahead(self):
        for step in range(24):
            m.note_prices(observation(step, 100))
        self.assertFalse(m.rising("MILK"))
        m.note_prices(observation(24, 101))
        self.assertTrue(m.rising("MILK"))
        m.note_prices(observation(25, 99))
        self.assertFalse(m.rising("MILK"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
