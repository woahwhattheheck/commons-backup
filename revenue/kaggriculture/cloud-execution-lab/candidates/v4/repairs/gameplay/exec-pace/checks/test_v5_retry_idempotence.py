# SPDX-License-Identifier: Apache-2.0
"""Retry-safety regression for the landed r04 execution-pacing lane."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_exec_pace as lane  # noqa: E402


class RetryIdempotence(unittest.TestCase):
    def setUp(self):
        lane.reset()

    def tearDown(self):
        lane.reset()

    def test_same_step_retry_preserves_full_rising_window(self):
        for step in range(lane.HIST_WINDOW):
            lane.note_prices({
                "step": step,
                "market": {"prices": {"WOOL": 20.0 + step * 0.10}},
            })
        self.assertTrue(lane.rising("WOOL"))
        slope = lane.slope("WOOL")

        # A deadline/retry callback can repeat the same public step. It must not
        # erase the already-authoritative trailing window or append twice.
        lane.note_prices({
            "step": lane.HIST_WINDOW - 1,
            "market": {"prices": {"WOOL": 0.0}},
        })
        self.assertEqual(lane.slope("WOOL"), slope)
        self.assertTrue(lane.rising("WOOL"))
        self.assertEqual(lane.cap_for("WOOL"), lane.CAPS["WOOL"])

    def test_backward_step_still_resets_game_history(self):
        for step in range(lane.HIST_WINDOW):
            lane.note_prices({
                "step": step,
                "market": {"prices": {"WOOL": 20.0 + step * 0.10}},
            })
        self.assertTrue(lane.rising("WOOL"))

        lane.note_prices({"step": 0, "market": {"prices": {"WOOL": 20.0}}})
        self.assertFalse(lane.rising("WOOL"))
        self.assertIsNone(lane.slope("WOOL"))


if __name__ == "__main__":
    unittest.main()
