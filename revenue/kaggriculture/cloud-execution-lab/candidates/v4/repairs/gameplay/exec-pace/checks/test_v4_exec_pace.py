# SPDX-License-Identifier: Apache-2.0
"""Focused checks for the V4 ``r04_exec_pace`` key (microstructure lane, V4 port).

Run in the materialised carrier tree::

    python -B -m unittest checks.test_v4_exec_pace

Covers: slope detection (rising/flat/falling/threshold), cap_for rising-only
semantics, per-game state reset (cross-game leak fix), the router seams
(flag off/on, END_STEP gating), key-ships-off, install toggling, and
never-raises on malformed input.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_exec_pace as lane  # noqa: E402


def observation(step, prices):
    return {"step": step, "player": 0, "market": {"prices": dict(prices)}}


BASE_PRICES = {"WOOL": 20, "MILK": 10, "STRAWBERRY": 30, "MELON": 15}


def feed(price_fn, steps):
    """Run note_prices over a range of steps with prices from price_fn(step)."""
    for step in range(steps):
        px = dict(BASE_PRICES)
        px.update(price_fn(step))
        lane.note_prices(observation(step, px))


class SlopeDetection(unittest.TestCase):
    def setUp(self):
        lane.reset()

    def tearDown(self):
        lane.reset()

    def test_rising_slope_detected(self):
        # +0.10/step over the trailing window > 0.03 threshold.
        feed(lambda s: {"WOOL": 20 + 0.10 * s}, 40)
        self.assertTrue(lane.rising("WOOL"))

    def test_falling_slope_not_rising(self):
        feed(lambda s: {"MILK": 40 - 0.10 * s}, 40)
        self.assertFalse(lane.rising("MILK"))

    def test_flat_market_not_rising(self):
        feed(lambda s: {"STRAWBERRY": 30.0}, 40)
        self.assertFalse(lane.rising("STRAWBERRY"))

    def test_below_threshold_slope_not_rising(self):
        # +0.02/step < 0.03 threshold: directionally rising but not "rising".
        feed(lambda s: {"MELON": 15 + 0.02 * s}, 40)
        self.assertFalse(lane.rising("MELON"))

    def test_incomplete_history_never_rising(self):
        feed(lambda s: {"WOOL": 20 + 1.0 * s}, lane.HIST_WINDOW - 1)
        self.assertFalse(lane.rising("WOOL"))

    def test_other_goods_independent(self):
        feed(lambda s: {"WOOL": 20 + 0.10 * s}, 40)
        self.assertTrue(lane.rising("WOOL"))
        self.assertFalse(lane.rising("MILK"))

    def test_uncapped_good_never_rising(self):
        feed(lambda s: {}, 40)
        self.assertFalse(lane.rising("EGG"))
        self.assertIsNone(lane.cap_for("EGG"))


class CapSemantics(unittest.TestCase):
    def setUp(self):
        lane.reset()

    def tearDown(self):
        lane.reset()

    def test_cap_for_rising_only(self):
        feed(lambda s: {"WOOL": 20 + 0.10 * s, "MILK": 40 - 0.10 * s,
                        "STRAWBERRY": 30.0}, 40)
        self.assertEqual(lane.cap_for("WOOL"), lane.CAPS["WOOL"])
        self.assertEqual(lane.cap_for("WOOL"), 3)
        self.assertIsNone(lane.cap_for("MILK"))          # falling
        self.assertIsNone(lane.cap_for("STRAWBERRY"))    # flat
        self.assertIsNone(lane.cap_for("EGG"))           # not a capped good

    def test_canned_caps(self):
        self.assertEqual(lane.CAPS, {"WOOL": 3, "MILK": 3, "STRAWBERRY": 4, "MELON": 6})


class PerGameReset(unittest.TestCase):
    """Cross-game state leak fix: a step <= the last recorded step (new game in
    a reused worker process) resets histories first."""

    def setUp(self):
        lane.reset()

    def tearDown(self):
        lane.reset()

    def test_new_game_resets_history(self):
        feed(lambda s: {"WOOL": 20 + 0.10 * s}, 40)
        self.assertTrue(lane.rising("WOOL"))
        # New game: step regresses to 0 with fresh (flat) prices.
        lane.note_prices(observation(0, BASE_PRICES))
        self.assertFalse(lane.rising("WOOL"))

    def test_duplicate_step_idempotent(self):
        feed(lambda s: {"WOOL": 20 + 0.10 * s}, 40)
        self.assertTrue(lane.rising("WOOL"))
        obs = observation(39, {"WOOL": 24.0})
        lane.note_prices(obs)
        lane.note_prices(obs)  # repeated observation: reset, no double count
        self.assertFalse(lane.rising("WOOL"))  # only one sample now

    def test_malformed_observation_is_noop(self):
        lane.note_prices(None)
        lane.note_prices({})
        lane.note_prices({"step": "x"})
        self.assertFalse(lane.rising("WOOL"))
        self.assertIsNone(lane.cap_for("WOOL"))

    def test_never_raises(self):
        try:
            for bad in (None, [], "x", {"step": None},
                        {"step": 5, "market": {"prices": None}},
                        {"step": 5, "market": {"prices": {"WOOL": float("inf")}}},
                        {"step": float("nan")}):
                lane.note_prices(bad)
                lane.rising(None)
                lane.rising("WOOL")
                lane.slope("WOOL")
                lane.cap_for(None)
                lane.cap_for("WOOL")
        except Exception as exc:  # pragma: no cover
            self.fail("must never raise: %r" % exc)


class RouterWiring(unittest.TestCase):
    def setUp(self):
        lane.reset()
        import r04_full_router as r04
        r04.install(exec_pace=False)
        self.addCleanup(r04.install, exec_pace=False)

    def test_key_ships_off(self):
        import r04_full_router as r04
        self.assertIs(r04.R04_EXEC_PACE, False)

    def test_install_toggles(self):
        import r04_full_router as r04
        r04.install(exec_pace=True)
        self.assertIs(r04.R04_EXEC_PACE, True)
        r04.install(exec_pace=False)
        self.assertIs(r04.R04_EXEC_PACE, False)

    def test_config_ships_off(self):
        cfg = json.loads((ROOT / "TITAN-CONFIG.json").read_text())
        self.assertIs(cfg["r04_exec_pace"], False)

    def test_seam_off_is_noop(self):
        import r04_full_router as r04
        feed(lambda s: {"WOOL": 20 + 0.10 * s}, 40)
        self.assertTrue(lane.rising("WOOL"))
        # Flag off: the seam never returns a cap.
        self.assertIsNone(r04._exec_pace_cap("WOOL", 100))

    def test_seam_on_rising_only(self):
        import r04_full_router as r04
        r04.install(exec_pace=True)
        feed(lambda s: {"WOOL": 20 + 0.10 * s, "STRAWBERRY": 30.0}, 40)
        self.assertEqual(r04._exec_pace_cap("WOOL", 100), 3)
        self.assertIsNone(r04._exec_pace_cap("STRAWBERRY", 100))  # flat
        self.assertIsNone(r04._exec_pace_cap("EGG", 100))          # uncapped

    def test_seam_end_step_gate(self):
        import r04_full_router as r04
        r04.install(exec_pace=True)
        feed(lambda s: {"WOOL": 20 + 0.10 * s}, 40)
        self.assertTrue(lane.rising("WOOL"))
        self.assertIsNone(r04._exec_pace_cap("WOOL", lane.END_STEP))
        self.assertIsNone(r04._exec_pace_cap("WOOL", lane.END_STEP + 28))
        self.assertEqual(r04._exec_pace_cap("WOOL", lane.END_STEP - 1), 3)


if __name__ == "__main__":
    unittest.main()
